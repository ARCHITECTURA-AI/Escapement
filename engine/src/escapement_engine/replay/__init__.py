"""Replay format and integrity checks (section 21).

A recording holds room and engine versions, the initial public observation,
ordered actions, public results and events, state and chain hashes, declared
metadata, self-reported usage (labelled), and the final outcome. The initial
private state is stored server-side only.

Two kinds of playback:

* recorded playback renders stored observations and events;
* re-simulation executes the recorded actions against the original manifest
  through the pinned engine version and compares hashes.

`verify_chain` needs only the replay: it recomputes every chain hash from
the recorded action, public result and state hash, so a replay that has been
edited, truncated or reordered fails without access to the sealed manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.episode import Episode, chain_next, chain_start, instance_hash
from ..schemas.manifest import RoomManifest
from ..version import ENGINE_VERSION, PROTOCOL_VERSION, REPLAY_FORMAT


class ReplayFormatError(ValueError):
    pass


def build_replay(
    *,
    run_id: str,
    room: dict[str, Any],
    mode: str,
    agent: dict[str, Any],
    initial_observation: dict[str, Any],
    steps: list[dict[str, Any]],
    outcome: str,
    final_chain_hash: str,
    usage: dict[str, Any] | None = None,
    engine_version: str = ENGINE_VERSION,
    protocol_version: str = PROTOCOL_VERSION,
    started_at: str | None = None,
    finished_at: str | None = None,
    wall_time_ms: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    replay = {
        "format": REPLAY_FORMAT,
        "run_id": run_id,
        "engine_version": engine_version,
        "protocol_version": protocol_version,
        "room": room,
        "mode": mode,
        "agent": agent,
        "self_reported": {
            "note": "Agent name, model, framework, memory strategy, tokens, cost and decision summaries are reported by the client and not verified.",
            "usage": usage or {},
        },
        "initial_observation": initial_observation,
        "chain_start": chain_start(room["instance_hash"], run_id, engine_version),
        "steps": steps,
        "outcome": outcome,
        "final_chain_hash": final_chain_hash,
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_time_ms": wall_time_ms,
    }
    if extra:
        replay.update(extra)
    return replay


def replay_from_episode(
    ep: Episode, *, mode: str = "local", agent: dict[str, Any] | None = None, requests: list[Any] | None = None
) -> dict[str, Any]:
    """Build a replay from an in-process episode (local research mode)."""
    m = ep.room.manifest
    initial = Episode.start(ep.room, ep.run_id).observation()
    steps = []
    for i, rec in enumerate(ep.records):
        step = rec.to_dict()
        step["request"] = requests[i] if requests else rec.action
        steps.append(step)
    return build_replay(
        run_id=ep.run_id,
        room=room_meta(m),
        mode=mode,
        agent=agent or {"name": "local", "version": "0"},
        initial_observation=initial,
        steps=steps,
        outcome=ep.status,
        final_chain_hash=ep.chain_hash,
    )


def room_meta(m: RoomManifest, season: str | None = None) -> dict[str, Any]:
    return {
        "room_id": m.room_id,
        "title": m.title,
        "tier": m.tier,
        "family": m.family,
        "template_version": m.template_version,
        "instance_hash": instance_hash(m),
        "season": season,
        "action_budget": m.budget.actions,
    }


@dataclass
class ChainCheck:
    ok: bool
    final_hash: str | None = None
    steps_checked: int = 0
    first_bad_seq: int | None = None
    reason: str = ""


def verify_chain(replay: dict[str, Any]) -> ChainCheck:
    if replay.get("format") != REPLAY_FORMAT:
        return ChainCheck(False, reason=f"unsupported replay format {replay.get('format')!r}")
    try:
        expected_start = chain_start(replay["room"]["instance_hash"], replay["run_id"], replay["engine_version"])
    except (KeyError, TypeError) as exc:
        return ChainCheck(False, reason=f"missing field {exc}")
    if replay.get("chain_start") not in (None, expected_start):
        return ChainCheck(False, reason="chain start does not match room, engine version and run id")
    prev = expected_start
    for i, step in enumerate(replay.get("steps", [])):
        if step.get("seq") != i + 1:
            return ChainCheck(False, steps_checked=i, first_bad_seq=i + 1, reason="sequence numbers are not contiguous")
        try:
            computed = chain_next(prev, step["action"], step["result"], step["state_hash"])
        except Exception as exc:  # canonical errors, missing keys
            return ChainCheck(False, steps_checked=i, first_bad_seq=step.get("seq"), reason=f"step not canonical: {exc}")
        if computed != step.get("chain_hash"):
            return ChainCheck(False, steps_checked=i, first_bad_seq=step.get("seq"), reason="chain hash mismatch")
        prev = computed
    if prev != replay.get("final_chain_hash"):
        return ChainCheck(False, final_hash=prev, steps_checked=len(replay.get("steps", [])), reason="final chain hash mismatch")
    return ChainCheck(True, final_hash=prev, steps_checked=len(replay.get("steps", [])))


@dataclass
class ResimCheck:
    ok: bool
    outcome: str | None = None
    final_hash: str | None = None
    mismatches: list[str] = field(default_factory=list)


def resimulate(replay: dict[str, Any], manifest: RoomManifest) -> ResimCheck:
    """Execute recorded requests through the engine and compare every hash."""
    if instance_hash(manifest) != replay["room"]["instance_hash"]:
        return ResimCheck(False, mismatches=["manifest does not match the recorded room instance hash"])
    if replay["engine_version"] != ENGINE_VERSION:
        return ResimCheck(
            False,
            mismatches=[f"replay needs engine {replay['engine_version']}; this is {ENGINE_VERSION}. Install the pinned version."],
        )
    ep = Episode.start(manifest, replay["run_id"])
    mismatches: list[str] = []
    for step in replay["steps"]:
        action = step["action"]
        try:
            if action.get("tool") == "system.end":
                rec = ep.terminate(action["arguments"]["ending"], note=step["result"].get("message"))
            else:
                rec = ep.step(step.get("request", action))
        except Exception as exc:
            mismatches.append(f"step {step['seq']}: engine refused ({exc})")
            break
        if rec.state_hash != step["state_hash"]:
            mismatches.append(f"step {step['seq']}: state hash differs")
        if rec.result != step["result"]:
            mismatches.append(f"step {step['seq']}: public result differs")
        if rec.chain_hash != step["chain_hash"]:
            mismatches.append(f"step {step['seq']}: chain hash differs")
            break
    if ep.status != replay["outcome"]:
        mismatches.append(f"outcome {ep.status} differs from recorded {replay['outcome']}")
    if ep.chain_hash != replay["final_chain_hash"]:
        mismatches.append("final chain hash differs")
    return ResimCheck(not mismatches, outcome=ep.status, final_hash=ep.chain_hash, mismatches=mismatches)


def public_replay(replay: dict[str, Any]) -> dict[str, Any]:
    """Strip anything not meant for viewers. Replays contain only public data
    by construction; this keeps the guarantee explicit."""
    allowed = {
        "format",
        "run_id",
        "engine_version",
        "protocol_version",
        "room",
        "mode",
        "agent",
        "self_reported",
        "initial_observation",
        "chain_start",
        "steps",
        "outcome",
        "final_chain_hash",
        "started_at",
        "finished_at",
        "wall_time_ms",
        "certificate_id",
    }
    return {k: v for k, v in replay.items() if k in allowed}


__all__ = [
    "ChainCheck",
    "ReplayFormatError",
    "ResimCheck",
    "build_replay",
    "public_replay",
    "replay_from_episode",
    "resimulate",
    "room_meta",
    "verify_chain",
]
