"""An episode: one run of one room, with budgets and the hash chain.

    chain_hash(0) = SHA-256(room_instance_hash + engine_version + run_id)
    chain_hash(n) = SHA-256(chain_hash(n-1)
                            + canonical_json(action n)
                            + canonical_json(public result n)
                            + SHA-256(canonical_json(private state after n)))

Every request that reaches the engine is recorded, including schema-invalid
ones (which cost no environment action but count toward the malformed limit)
and system endings imposed from outside (idle, wall clock, client abort).
Nothing executes after a terminal condition (AC-08).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import canonical_json, hash_value, sha256_hex
from ..schemas.actions import Action, Malformed, parse_action
from ..schemas.endings import (
    ACTION_BUDGET_EXHAUSTED,
    ESCAPED,
    IN_PROGRESS,
    MALFORMED_LIMIT_REACHED,
    SYSTEM_ENDINGS,
)
from ..schemas.manifest import RoomManifest
from ..version import ENGINE_VERSION
from .world import CompiledRoom, Result, State, goal_reached, initial_state, observe, transition


class EpisodeFinished(Exception):
    """Raised when an action arrives after the episode has ended."""

    def __init__(self, status: str) -> None:
        super().__init__(f"episode already finished: {status}")
        self.status = status


def instance_hash(manifest: RoomManifest) -> str:
    return hash_value(manifest.model_dump(mode="json"))


def chain_start(room_instance_hash: str, run_id: str, engine_version: str = ENGINE_VERSION) -> str:
    return sha256_hex(room_instance_hash + engine_version + run_id)


def chain_next(prev: str, action: dict[str, Any], result: dict[str, Any], state_hash: str) -> str:
    return sha256_hex(prev + canonical_json(action) + canonical_json(result) + state_hash)


def state_hash(state: State) -> str:
    return hash_value(state)


@dataclass
class StepRecord:
    seq: int
    action: dict[str, Any]
    result: Result
    observation: dict[str, Any]
    state_hash: str
    chain_hash: str
    status: str
    malformed: bool = False
    system: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "action": self.action,
            "result": self.result,
            "observation": self.observation,
            "state_hash": self.state_hash,
            "chain_hash": self.chain_hash,
            "status": self.status,
            "malformed": self.malformed,
            "system": self.system,
        }


@dataclass
class Episode:
    room: CompiledRoom
    run_id: str
    state: State
    chain_hash: str
    room_hash: str
    last_result: Result | None = None
    records: list[StepRecord] = field(default_factory=list)

    # -- construction -----------------------------------------------------

    @classmethod
    def start(cls, manifest: RoomManifest | CompiledRoom, run_id: str) -> "Episode":
        room = manifest if isinstance(manifest, CompiledRoom) else CompiledRoom(manifest)
        rh = instance_hash(room.manifest)
        return cls(
            room=room,
            run_id=run_id,
            state=initial_state(room),
            chain_hash=chain_start(rh, run_id),
            room_hash=rh,
        )

    @classmethod
    def resume(
        cls,
        manifest: RoomManifest | CompiledRoom,
        run_id: str,
        state: State,
        chain_hash: str,
        last_result: Result | None = None,
    ) -> "Episode":
        room = manifest if isinstance(manifest, CompiledRoom) else CompiledRoom(manifest)
        return cls(
            room=room,
            run_id=run_id,
            state=state,
            chain_hash=chain_hash,
            room_hash=instance_hash(room.manifest),
            last_result=last_result,
        )

    # -- queries ----------------------------------------------------------

    @property
    def status(self) -> str:
        return self.state["status"]

    @property
    def finished(self) -> bool:
        return self.state["status"] != IN_PROGRESS

    @property
    def seq(self) -> int:
        return self.state["seq"]

    def observation(self) -> dict[str, Any]:
        return observe(self.room, self.state, self.last_result)

    # -- transitions ------------------------------------------------------

    def step(self, request: Any) -> StepRecord:
        if self.finished:
            raise EpisodeFinished(self.status)
        parsed = parse_action(request)
        budget = self.room.manifest.budget
        if isinstance(parsed, Malformed):
            new = dict(self.state)
            new["mal"] = self.state["mal"] + 1
            new["mal_total"] = self.state["mal_total"] + 1
            result: Result = {
                "ok": False,
                "tool": parsed.tool,
                "error": "INVALID_ARGUMENT",
                "message": parsed.message,
                "events": [],
                "cost": 0,
                "malformed": True,
            }
            if new["mal"] >= budget.malformed:
                new["status"] = MALFORMED_LIMIT_REACHED
                result["message"] += f" Malformed-request limit of {budget.malformed} reached; the run has ended."
            return self._commit(new, parsed.to_dict(), result, malformed=True)
        action: Action = parsed
        new, result = transition(self.room, self.state, action)
        if new is self.state:
            new = dict(self.state)
        new["mal"] = 0
        new["used"] = min(budget.actions, self.state["used"] + result["cost"])
        if goal_reached(self.room, new):
            new["status"] = ESCAPED
            result = dict(result)
            result["events"] = list(result["events"]) + [{"type": "escaped"}]
        elif new["used"] >= budget.actions:
            new["status"] = ACTION_BUDGET_EXHAUSTED
            result = dict(result)
            result["message"] += " The action budget is exhausted; the run has ended."
        return self._commit(new, action.to_dict(), result)

    def terminate(self, ending: str, note: str | None = None) -> StepRecord:
        """End the episode for a reason outside the rules (idle, abort...)."""
        if self.finished:
            raise EpisodeFinished(self.status)
        if ending not in SYSTEM_ENDINGS:
            raise ValueError(f"not a system ending: {ending}")
        new = dict(self.state)
        new["status"] = ending
        message = note or f"Run ended: {ending.replace('_', ' ')}."
        result: Result = {"ok": True, "tool": None, "error": None, "message": message, "events": [], "cost": 0}
        return self._commit(new, {"tool": "system.end", "arguments": {"ending": ending}}, result, system=True)

    def apply_recorded(self, action: dict[str, Any]) -> StepRecord:
        """Re-apply a recorded chain entry during re-simulation."""
        if action.get("tool") == "system.end":
            return self.terminate(action["arguments"]["ending"])
        if action.get("malformed"):
            raise ValueError("malformed entries are re-simulated from their raw request")
        return self.step(action)

    def _commit(self, new: State, action: dict[str, Any], result: Result, malformed: bool = False, system: bool = False) -> StepRecord:
        new["seq"] = self.state["seq"] + 1
        sh = state_hash(new)
        chain = chain_next(self.chain_hash, action, result, sh)
        self.state = new
        self.chain_hash = chain
        self.last_result = result
        record = StepRecord(
            seq=new["seq"],
            action=action,
            result=result,
            observation=self.observation(),
            state_hash=sh,
            chain_hash=chain,
            status=new["status"],
            malformed=malformed,
            system=system,
        )
        self.records.append(record)
        return record
