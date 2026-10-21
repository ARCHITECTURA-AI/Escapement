"""Run agents against the in-process engine (local research mode)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.episode import Episode
from ..core.world import CompiledRoom
from ..schemas.manifest import RoomManifest
from .base import Agent


@dataclass
class LocalRunResult:
    run_id: str
    outcome: str
    actions_used: int
    malformed: int
    final_chain_hash: str
    episode: Episode


def run_local(agent: Agent, manifest: RoomManifest | CompiledRoom, run_id: str, max_steps: int = 1000) -> LocalRunResult:
    ep = Episode.start(manifest, run_id)
    agent.reset()
    obs = ep.observation()
    steps = 0
    while not ep.finished and steps < max_steps:
        request = agent.act(obs)
        request = {k: v for k, v in request.items() if k in ("tool", "arguments")}
        ep.step(request)
        obs = ep.observation()
        steps += 1
    return LocalRunResult(
        run_id=run_id,
        outcome=ep.status,
        actions_used=ep.state["used"],
        malformed=ep.state["mal_total"],
        final_chain_hash=ep.chain_hash,
        episode=ep,
    )


def make_agent(name: str, seed: int | str = 0) -> Any:
    from .heuristic import HeuristicExplorer
    from .random_agent import RandomAgent

    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicExplorer()
    raise ValueError(f"unknown baseline agent {name!r}")
