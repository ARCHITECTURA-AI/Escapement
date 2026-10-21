"""The validation every instance must pass before it is published (12.2).

1. Schema validity and reference integrity.
2. Valid initial state.
3. Goal reachability.
4. Solution replay in the actual engine.
5. Budget feasibility with margin.
6. Required clues are discoverable.
7. Basic unintended-shortcut checks, including a bounded search for shorter
   paths than the intended one.
8. No hidden-ID or text leakage into public fields.

Plus the design constraints of section 8.2 that can be checked mechanically:
no reachable dead ends (nothing missable or destroyable that the exit
needs) and observations within the 400-token target.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..core.episode import Episode
from ..core.world import CompiledRoom, goal_reached, initial_state
from ..rng import SeededRandom
from ..rooms.emergency_lockdown import apply_transforms
from ..schemas.actions import ID_RE, CODE_RE
from ..schemas.manifest import GONE, INVENTORY, RoomManifest
from ..version import ENGINE_VERSION
from .solver import SolveResult, solve

BUDGET_MARGIN = 0.5  # the shortest solution may use at most half the budget
OBSERVATION_TOKEN_TARGET = 400


def estimate_tokens(text: str) -> int:
    """A conservative token estimate: about 3.6 characters per token for this
    kind of compact JSON, rounded up."""
    return -(-len(text) * 10 // 36)


@dataclass
class Check:
    id: str
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    solution: list[dict[str, Any]] = field(default_factory=list)
    min_length: int | None = None
    optimality: str = "unknown"  # "proven" or "best_verified"
    states_explored: int = 0
    max_observation_tokens: int = 0

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, cid: str, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(Check(cid, name, passed, detail))
        return passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "min_length": self.min_length,
            "optimality": self.optimality,
            "states_explored": self.states_explored,
            "max_observation_tokens": self.max_observation_tokens,
            "solution_length": len(self.solution),
        }


def _integrity(m: RoomManifest) -> list[str]:
    problems: list[str] = []
    loc_ids = [loc.id for loc in m.locations]
    obj_ids = [o.id for o in m.objects]
    clue_ids = [c.id for c in m.clues]
    for kind, ids in (("location", loc_ids), ("object", obj_ids), ("clue", clue_ids)):
        if len(set(ids)) != len(ids):
            problems.append(f"duplicate {kind} ids")
        for i in ids:
            if not ID_RE.match(i):
                problems.append(f"bad {kind} id {i!r}")
    if set(loc_ids) & set(obj_ids):
        problems.append("location and object ids collide")
    containers = {o.id for o in m.objects if o.container}
    if m.start not in loc_ids:
        problems.append("start location missing")
    for loc in m.locations:
        for e in loc.exits:
            if e.to not in loc_ids:
                problems.append(f"exit from {loc.id} to unknown {e.to}")
    for o in m.objects:
        if o.location not in loc_ids and o.location not in containers:
            problems.append(f"object {o.id} placed in unknown {o.location}")
        if o.location == o.id:
            problems.append(f"object {o.id} contains itself")
        if o.code_lock:
            if "enter_code" not in o.operations:
                problems.append(f"{o.id} has a code lock but no enter_code operation")
            if not CODE_RE.match(o.code_lock.code):
                problems.append(f"{o.id} code is not digits")
            if "locked" not in o.state:
                problems.append(f"{o.id} code lock without locked state")
        if "enter_code" in o.operations and not o.code_lock:
            problems.append(f"{o.id} advertises enter_code without a code lock")
        if "activate" in o.operations and not any(r.target == o.id and r.operation == "activate" for r in m.rules):
            problems.append(f"{o.id} advertises activate without a rule")
        for key in o.public_state:
            if key not in m.state_labels:
                problems.append(f"{o.id} public state {key} has no label")

    def cond_refs(conds: list[Any], where: str) -> None:
        for c in conds:
            if c.obj and c.obj not in obj_ids:
                problems.append(f"{where}: unknown object {c.obj}")
            if c.item and c.item not in obj_ids:
                problems.append(f"{where}: unknown item {c.item}")
            if c.location and c.location not in loc_ids:
                problems.append(f"{where}: unknown location {c.location}")
            if c.clue and c.clue not in clue_ids:
                problems.append(f"{where}: unknown clue {c.clue}")

    def effect_refs(effects: list[Any], where: str) -> None:
        for e in effects:
            if e.obj and e.obj not in obj_ids:
                problems.append(f"{where}: unknown object {e.obj}")
            if e.clue and e.clue not in clue_ids:
                problems.append(f"{where}: unknown clue {e.clue}")
            if e.to and e.to not in (INVENTORY, GONE) and e.to not in loc_ids and e.to not in containers:
                problems.append(f"{where}: unknown destination {e.to}")

    for r in m.rules:
        if r.target not in obj_ids or (r.item and r.item not in obj_ids):
            problems.append(f"rule {r.id} references unknown objects")
        cond_refs(r.requires + r.already, f"rule {r.id}")
        effect_refs(r.effects, f"rule {r.id}")
    for o in m.objects:
        cond_refs(o.open_requires, o.id)
        for v in o.inspect_variants:
            cond_refs(v.when, o.id)
            effect_refs(v.effects, o.id)
        if o.code_lock:
            cond_refs(o.code_lock.requires, o.id)
            effect_refs(o.code_lock.on_unlock, o.id)
    for ms in m.milestones:
        cond_refs(ms.requires, f"milestone {ms.id}")
    cond_refs(m.goal, "goal")
    return problems


def _public_texts(record: Any) -> str:
    return json.dumps(record, ensure_ascii=False)


def validate(manifest: RoomManifest, intended: list[dict[str, Any]] | None = None, max_states: int = 250_000) -> ValidationReport:
    report = ValidationReport()
    m = manifest

    # 1. schema validity and reference integrity
    try:
        RoomManifest.model_validate(m.model_dump(mode="json"))
        problems = _integrity(m)
    except Exception as exc:  # pragma: no cover - defensive
        problems = [f"schema: {exc}"]
    if not report.add("schema", "Schema validity and reference integrity", not problems, "; ".join(problems[:5])):
        return report
    if m.engine_version.split(".")[0] != ENGINE_VERSION.split(".")[0]:
        report.add("engine", "Engine version compatible", False, f"manifest {m.engine_version}, engine {ENGINE_VERSION}")
        return report

    room = CompiledRoom(m)

    # 2. valid initial state
    s0 = initial_state(room)
    init_problems = []
    if goal_reached(room, s0):
        init_problems.append("goal already satisfied")
    if room.locations[m.start].terminal:
        init_problems.append("start is terminal")
    if s0["inv"]:
        init_problems.append("inventory not empty")
    if not s0["seen"]:
        init_problems.append("nothing visible at start")
    report.add("initial_state", "Valid initial state", not init_problems, "; ".join(init_problems))

    # 3. goal reachability (and 8.2: no reachable dead ends)
    result: SolveResult = solve(room, max_states=max_states)
    report.states_explored = result.states_explored
    report.add(
        "reachability",
        "Goal reachability",
        result.solved,
        f"{result.states_explored} states explored" + ("" if result.exhausted else " (search bounded)"),
    )
    if not result.solved:
        return report
    report.min_length = result.min_length
    report.optimality = "proven" if result.proven_optimal else "best_verified"
    report.solution = result.solution
    if result.exhausted:
        report.add(
            "dead_ends",
            "No reachable dead ends (nothing required is missable or destroyable)",
            result.dead_ends == 0,
            f"{result.dead_ends} dead-end states" + (f"; e.g. after {result.dead_end_example}" if result.dead_end_example else ""),
        )

    # 4. solution replay in the actual engine
    replays: dict[str, Episode] = {}
    replay_ok = True
    details = []
    for label, actions in (("solver", result.solution), ("intended", intended or [])):
        if not actions:
            continue
        ep = Episode.start(room, f"validation-{label}")
        for a in actions:
            rec = ep.step(a)
            if not rec.result["ok"]:
                replay_ok = False
                details.append(f"{label} step {rec.seq} failed: {rec.result['message']}")
                break
        if ep.status != "escaped":
            replay_ok = False
            details.append(f"{label} ended {ep.status}")
        replays[label] = ep
    report.add("replay", "Solution replay in the real engine", replay_ok, "; ".join(details) or f"solver path {len(result.solution)} actions")

    # 5. budget feasibility with margin
    limit = int(m.budget.actions * BUDGET_MARGIN)
    report.add(
        "budget",
        "Budget feasibility with margin",
        (result.min_length or 0) <= limit,
        f"shortest {result.min_length} of budget {m.budget.actions} (limit {limit})",
    )

    # 6. required clues are discoverable and codes derive from them
    clue_problems = []
    texts = {c.id: c.text for c in m.clues}
    for o in m.objects:
        if not o.code_lock:
            continue
        d = o.code_lock.derivation
        if apply_transforms(d.base_digits, list(d.transforms)) != o.code_lock.code:
            clue_problems.append(f"{o.id}: code does not follow from its derivation")
        if " ".join(d.base_digits) not in texts.get(d.base_clue, ""):
            clue_problems.append(f"{o.id}: base digits absent from clue")
        for t in d.transforms:
            if t.op == "add_mod10" and f"+{t.k}" not in " ".join(texts.get(c, "") for c in d.offset_clues):
                clue_problems.append(f"{o.id}: offset absent from clues")
        ep = replays.get("solver")
        if ep is not None:
            needed = [d.base_clue, d.instruction_clue, *d.offset_clues]
            entered_at = next(
                (r.seq for r in ep.records if r.action.get("arguments", {}).get("operation") == "enter_code" and r.action["arguments"]["target_id"] == o.id),
                None,
            )
            found_before = set()
            for r in ep.records:
                if entered_at is not None and r.seq >= entered_at:
                    break
                for ev in r.result["events"]:
                    if ev["type"] == "clue_discovered":
                        found_before.add(ev["clue_id"])
            missing = [c for c in needed if c not in found_before]
            if missing:
                clue_problems.append(f"{o.id}: clues {missing} not discovered before the code")
    report.add("clues", "Required clues are discoverable", not clue_problems, "; ".join(clue_problems))

    # 7. unintended shortcuts
    required = [ms for ms in m.milestones if ms.required]
    shortcut_problems = []
    ep = replays.get("solver")
    if ep is not None:
        reached = set(ep.state["milestones"])
        skipped = [ms.id for ms in required if ms.id not in reached]
        if skipped:
            shortcut_problems.append(f"shortest path skips milestones {skipped}")
    if intended and result.min_length is not None and result.min_length < len(intended):
        detail_short = f"shortest {result.min_length} < intended {len(intended)} (same milestones; accepted)"
    else:
        detail_short = f"shortest {result.min_length}, intended {len(intended or [])}"
    report.add("shortcuts", "No unintended shortcuts", not shortcut_problems, "; ".join(shortcut_problems) or detail_short)

    # 8. leakage into public fields
    leak_problems: list[str] = []
    max_tokens = 0
    codes = [o.code_lock.code for o in m.objects if o.code_lock]
    from ..schemas.endings import ENDINGS

    private_words = [ms.label for ms in m.milestones] + [ms.id for ms in m.milestones if ms.id not in ENDINGS]
    private_words += [m.template_version, "decoy", "milestone", "solution"]
    if len(m.seed) >= 8:
        private_words.append(m.seed)
    hidden_ids = {o.id for o in m.objects if o.hidden}
    walks = list(replays.values())
    # A seeded random walk exercises failure messages too.
    rng = SeededRandom("leakage", m.room_id)
    walker = Episode.start(room, "validation-walk")
    from ..agents.random_agent import RandomAgent  # local import: agents depend on core

    agent = RandomAgent(seed=rng.u32())
    obs = walker.observation()
    for _ in range(m.budget.actions):
        if walker.finished:
            break
        walker.step(agent.act(obs))
        obs = walker.observation()
    walks.append(walker)
    for ep_ in walks:
        start_obs = Episode.start(room, "x").observation()
        sequence = [start_obs] + [r.observation for r in ep_.records]
        revealed: set[str] = set(s0["seen"])
        for i, obs_ in enumerate(sequence):
            text = _public_texts(obs_)
            max_tokens = max(max_tokens, estimate_tokens(json.dumps(obs_, separators=(",", ":"))))
            for code in codes:
                if re.search(rf"(?<!\d){re.escape(code)}(?!\d)", text) and not _code_was_typed(ep_, i, code):
                    leak_problems.append("code appears in public output")
            for word in private_words:
                if word and word in text:
                    leak_problems.append(f"private term {word!r} in public output")
            if i > 0:
                for ev in ep_.records[i - 1].result["events"]:
                    if ev["type"] == "object_revealed":
                        revealed.add(ev["object_id"])
            for hid in hidden_ids - revealed:
                if re.search(rf'"{re.escape(hid)}"', text):
                    leak_problems.append(f"hidden id {hid} visible before reveal")
    if max_tokens > OBSERVATION_TOKEN_TARGET:
        leak_problems.append(f"observation estimated at {max_tokens} tokens")
    report.max_observation_tokens = max_tokens
    report.add("leakage", "No hidden-ID or text leakage", not leak_problems, "; ".join(sorted(set(leak_problems))[:5]) or f"max observation ~{max_tokens} tokens")
    return report


def _code_was_typed(ep: Episode, index: int, code: str) -> bool:
    """A code echoed back after the agent typed it is not a leak."""
    for r in ep.records[:index]:
        if r.action.get("arguments", {}).get("value") == code:
            return True
    return False
