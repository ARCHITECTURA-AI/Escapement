"""LocalRun: the same interface as `Run`, backed by the in-process engine.
Useful for developing an agent offline against Practice or generated rooms;
nothing is certified."""

from __future__ import annotations

import uuid
from typing import Any

from escapement_engine.core import Episode
from escapement_engine.generation import generate, practice_manifest
from escapement_engine.replay import replay_from_episode
from escapement_engine.schemas.manifest import RoomManifest


class LocalRun:
    def __init__(self, room: str | RoomManifest = "practice", tier: str = "standard", seed: str = "local") -> None:
        if isinstance(room, RoomManifest):
            manifest = room
        elif room == "practice":
            manifest = practice_manifest()
        else:
            manifest = generate(tier, seed, room).manifest
        self.manifest = manifest
        self.id = f"local-{uuid.uuid4()}"
        self.episode = Episode.start(manifest, self.id)
        self.requests: list[Any] = []
        self.observation = self.episode.observation()
        self.room = {"id": manifest.room_id, "title": manifest.title, "tier": manifest.tier, "intro": manifest.intro, "goal": manifest.goal_text, "action_budget": manifest.budget.actions}
        self.last_result: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        return self.episode.status

    @property
    def done(self) -> bool:
        return self.episode.finished

    @property
    def escaped(self) -> bool:
        return self.status == "escaped"

    @property
    def sequence(self) -> int:
        return self.episode.seq

    @property
    def chain_hash(self) -> str:
        return self.episode.chain_hash

    def act(self, tool: str, decision_summary: str | None = None, usage: dict[str, Any] | None = None, **arguments: Any) -> dict[str, Any]:
        return self.send_raw({"tool": tool, "arguments": {k: v for k, v in arguments.items() if v is not None}})

    def send_raw(self, request: dict[str, Any]) -> dict[str, Any]:
        req = {k: v for k, v in request.items() if k in ("tool", "arguments")}
        self.requests.append(req)
        rec = self.episode.step(req)
        self.observation = rec.observation
        self.last_result = rec.result
        return rec.result

    def inspect(self, target_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("inspect", target_id=target_id, **kw)

    def take(self, item_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("take", item_id=item_id, **kw)

    def use(self, item_id: str, target_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("use", item_id=item_id, target_id=target_id, **kw)

    def interact(self, target_id: str, operation: str, value: str | None = None, **kw: Any) -> dict[str, Any]:
        return self.act("interact", target_id=target_id, operation=operation, value=value, **kw)

    def move(self, destination_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("move", destination_id=destination_id, **kw)

    def review_journal(self, **kw: Any) -> dict[str, Any]:
        return self.act("review_journal", **kw)

    def finish(self, usage: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.done:
            self.episode.terminate("client_aborted")
            self.requests.append({"tool": "system.end", "arguments": {"ending": "client_aborted"}})
        return {"status": self.status, "certificate_id": None}

    def replay(self) -> dict[str, Any]:
        return replay_from_episode(self.episode, requests=self.requests)
