"""The agent interface shared by baselines, the starter agent and the
reference worker. An agent sees public observations only (section 10.4)."""

from __future__ import annotations

from typing import Any, Protocol


class Agent(Protocol):
    name: str
    version: str

    def reset(self) -> None: ...

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Return {"tool": ..., "arguments": {...}} and optionally
        "decision_summary" (self-reported, at most 280 characters)."""
        ...


def object_ids(observation: dict[str, Any]) -> list[str]:
    return [o["id"] for o in observation.get("objects", [])] + [i["id"] for i in observation.get("inventory", [])]
