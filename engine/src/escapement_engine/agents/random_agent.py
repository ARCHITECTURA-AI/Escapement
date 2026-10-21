"""Random baseline: the floor. Schema-valid actions over public targets with a
recorded seed (section 15)."""

from __future__ import annotations

from typing import Any

from ..rng import SeededRandom
from .base import object_ids


class RandomAgent:
    name = "random"
    version = "1.0.0"

    def __init__(self, seed: int | str = 0) -> None:
        self.seed = str(seed)
        self.reset()

    def reset(self) -> None:
        self._rng = SeededRandom("random-agent", self.seed)

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        rng = self._rng
        objects = object_ids(observation)
        inventory = [i["id"] for i in observation.get("inventory", [])]
        exits = [e["id"] for e in observation.get("exits", [])]
        options: list[dict[str, Any]] = [{"tool": "review_journal", "arguments": {}}]
        for oid in objects:
            options.append({"tool": "inspect", "arguments": {"target_id": oid}})
            options.append({"tool": "take", "arguments": {"item_id": oid}})
            for op in ("open", "close", "activate"):
                options.append({"tool": "interact", "arguments": {"target_id": oid, "operation": op}})
            options.append(
                {"tool": "interact", "arguments": {"target_id": oid, "operation": "enter_code", "value": rng.digits(rng.choice([3, 4]))}}
            )
            for item in inventory:
                options.append({"tool": "use", "arguments": {"item_id": item, "target_id": oid}})
        for dest in exits:
            options.append({"tool": "move", "arguments": {"destination_id": dest}})
        return rng.choice(options)
