"""Trace Clinic (section 14.5): failure analysis on a user's own runs.

Every label is a heuristic, not ground truth, and says so. Findings computed
from public data are always available to the run's owner. Comparisons with
private milestones and the reference solution are only produced when the
caller supplies them, which the server does once the room's solution is no
longer sealed (Practice, Daily after the UTC day, ranked after the season).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .core.episode import Episode
from .schemas.manifest import RoomManifest

CLUE_WINDOW = 8


@dataclass
class Finding:
    kind: str
    title: str
    detail: str
    steps: list[int] = field(default_factory=list)
    severity: str = "info"  # "info", "warn"
    heuristic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _target_ids(action: dict[str, Any]) -> list[str]:
    args = action.get("arguments") or {}
    return [v for k, v in args.items() if k in ("target_id", "item_id", "destination_id")]


def analyze(replay: dict[str, Any], private: dict[str, Any] | None = None) -> dict[str, Any]:
    steps = [s for s in replay.get("steps", []) if not s.get("system")]
    findings: list[Finding] = []
    names: dict[str, str] = {}
    observations = [replay.get("initial_observation") or {}] + [s.get("observation") or {} for s in steps]
    for obs in observations:
        for o in obs.get("objects", []) + obs.get("inventory", []):
            names[o["id"]] = o["name"]

    # 1. First invalid action.
    first_bad = next((s for s in steps if not s["result"].get("ok")), None)
    if first_bad:
        findings.append(
            Finding(
                "first_invalid_action",
                "First invalid action",
                f"Step {first_bad['seq']}: {_describe(first_bad['action'])} failed with "
                f"{first_bad['result'].get('error')}: {first_bad['result'].get('message')}",
                [first_bad["seq"]],
                "warn",
            )
        )

    # 2. Clues discovered but not acted on within a window.
    for s in steps:
        for ev in s["result"].get("events", []):
            if ev["type"] != "clue_discovered":
                continue
            text = s["result"].get("message", "").lower()
            mentioned = {oid for oid, name in names.items() if name.lower() in text}
            has_digits = bool(re.search(r"\d", text))
            later = [t for t in steps if s["seq"] < t["seq"] <= s["seq"] + CLUE_WINDOW]
            used = any(
                set(_target_ids(t["action"])) & mentioned
                or (has_digits and (t["action"].get("arguments") or {}).get("operation") == "enter_code")
                or t["action"].get("tool") == "review_journal"
                for t in later
            )
            if later and not used:
                findings.append(
                    Finding(
                        "unused_clue",
                        f"Clue {ev['clue_id']} not acted on",
                        f"Discovered at step {s['seq']}; none of the next {CLUE_WINDOW} actions touched what it mentions or reviewed the journal.",
                        [s["seq"]],
                    )
                )

    # 3. Repeated actions with the same result and no progress.
    seen: dict[str, list[int]] = {}
    for s in steps:
        if s["result"].get("ok") and s["action"].get("tool") != "inspect":
            continue
        key = json.dumps([s["action"], s["result"].get("message")], sort_keys=True)
        seen.setdefault(key, []).append(s["seq"])
    repeats = [(json.loads(k)[0], v) for k, v in seen.items() if len(v) > 1]
    repeated_actions = sum(len(v) - 1 for _, v in repeats)
    for action, seqs in sorted(repeats, key=lambda r: -len(r[1]))[:5]:
        findings.append(
            Finding(
                "no_progress_repeat",
                "Repeated action, same result",
                f"{_describe(action)} repeated {len(seqs)} times with an identical result.",
                seqs,
                "warn",
            )
        )

    # 4. Wrong code attempts.
    wrong = [(s["seq"], ev) for s in steps for ev in s["result"].get("events", []) if ev["type"] == "wrong_code"]
    if wrong:
        extra = sum(max(0, s["result"].get("cost", 1) - 1) for s in steps)
        findings.append(
            Finding(
                "wrong_codes",
                "Wrong code attempts",
                f"{len(wrong)} wrong code{'' if len(wrong) == 1 else 's'} entered"
                + (f"; the security delay cost {extra} extra actions." if extra else "."),
                [seq for seq, _ in wrong],
                "warn" if len(wrong) >= 3 else "info",
            )
        )

    # 5. Actions before the first milestone, compared with the reference.
    if private and private.get("milestones"):
        first = private["milestones"][0]
        ref = private.get("reference_first_milestone")
        detail = f"{first['seq']} actions before the first milestone ({first['label'].lower()})"
        if ref:
            detail += f"; the reference solution needs {ref}."
        findings.append(
            Finding(
                "first_milestone",
                "Actions before the first milestone",
                detail,
                [first["seq"]],
                "warn" if ref and first["seq"] > 2 * ref else "info",
            )
        )
        missed = private.get("missed")
        if missed:
            findings.append(Finding("milestones_missed", "Milestones not reached", ", ".join(missed), []))

    # 6. Visible objects never inspected.
    visible = set()
    for obs in observations:
        visible |= {o["id"] for o in obs.get("objects", [])}
    inspected = {(s["action"].get("arguments") or {}).get("target_id") for s in steps if s["action"].get("tool") == "inspect"}
    never = sorted(visible - inspected)
    if never:
        findings.append(
            Finding(
                "never_inspected",
                "Visible objects never inspected",
                ", ".join(names.get(o, o) for o in never),
                [],
            )
        )

    n = len(steps)
    invalid = sum(1 for s in steps if not s["result"].get("ok"))
    metrics = {
        "steps": n,
        "actions_used": (steps[-1]["observation"] or {}).get("actions_used") if steps else 0,
        "invalid_action_rate": invalid / n if n else None,
        "repeated_action_rate": repeated_actions / n if n else None,
        "malformed": sum(1 for s in steps if s.get("malformed")),
        "clues_found": sum(1 for s in steps for ev in s["result"].get("events", []) if ev["type"] == "clue_discovered"),
        "wrong_codes": len(wrong),
    }
    return {
        "note": "Every finding is a heuristic label, not ground truth.",
        "findings": [f.to_dict() for f in findings],
        "metrics": metrics,
        "milestones": private.get("milestones") if private else None,
    }


def _describe(action: dict[str, Any]) -> str:
    args = action.get("arguments") or {}
    if not args:
        return f"{action.get('tool')}()"
    inner = ", ".join(f"{v}" for v in args.values())
    return f"{action.get('tool')}({inner})"


def milestone_timeline(replay: dict[str, Any], manifest: RoomManifest) -> list[dict[str, Any]]:
    """Re-simulate privately and list when each milestone was reached."""
    ep = Episode.start(manifest, replay["run_id"])
    labels = {m.id: m.label for m in manifest.milestones}
    out: list[dict[str, Any]] = []
    reached: list[str] = []
    for step in replay["steps"]:
        action = step["action"]
        if action.get("tool") == "system.end":
            break
        if ep.finished:
            break
        ep.step(step.get("request", action))
        for ms in ep.state["milestones"]:
            if ms not in reached:
                reached.append(ms)
                out.append({"id": ms, "label": labels[ms], "seq": step["seq"], "actions_used": ep.state["used"]})
    return out


def private_context(replay: dict[str, Any], manifest: RoomManifest, reference_solution: list[dict[str, Any]] | None) -> dict[str, Any]:
    timeline = milestone_timeline(replay, manifest)
    ref_first = None
    if reference_solution:
        ref = {"run_id": "reference", "steps": [{"seq": i + 1, "action": a} for i, a in enumerate(reference_solution)]}
        ref_timeline = milestone_timeline(ref, manifest)
        ref_first = ref_timeline[0]["seq"] if ref_timeline else None
    reached = {m["id"] for m in timeline}
    missed = [m.label for m in manifest.milestones if m.id not in reached and m.required]
    return {"milestones": timeline, "reference_first_milestone": ref_first, "missed": missed}
