"""Leakage tests (sections 10.4, 24.3, AC-03, AC-18): public payloads contain
no solver data, hidden milestones, codes or generation metadata."""

import json

import pytest

from escapement_engine.agents import HeuristicExplorer, RandomAgent, run_local
from escapement_engine.generation import generate
from escapement_engine.replay import replay_from_episode


@pytest.fixture(scope="module", params=["practice", "standard", "hard"])
def instance(request, practice):
    if request.param == "practice":
        from escapement_engine.generation import build_practice

        return build_practice()
    return generate(request.param, f"leak-{request.param}", f"leak-{request.param}")


def _forbidden(m):
    words = [ms.label for ms in m.milestones] + [m.template_version, "decoy", "milestone", "solution", "derivation", "transform"]
    words += [h for ms in m.milestones for h in ms.hints]
    if len(m.seed) >= 8:
        words.append(m.seed)
    return words


def test_public_outputs_carry_no_private_data(instance):
    m = instance.manifest
    lock = next(o.code_lock for o in m.objects if o.code_lock)
    for agent, rid in ((HeuristicExplorer(), "h"), (RandomAgent(seed=3), "r")):
        run = run_local(agent, m, rid)
        replay = replay_from_episode(run.episode)
        typed = False
        for step in replay["steps"]:
            if (step["action"].get("arguments") or {}).get("value") == lock.code:
                typed = True
            text = json.dumps({"result": step["result"], "observation": step["observation"]})
            for word in _forbidden(m):
                assert word not in text, word
            if not typed:
                assert lock.code not in json.dumps(step["observation"]["objects"]) + step["result"]["message"]
            assert "secured" not in text and "fuse_found" not in text


def test_no_hint_text_in_observations(instance):
    m = instance.manifest
    run = run_local(HeuristicExplorer(), m, "hints")
    blob = json.dumps(replay_from_episode(run.episode))
    for ms in m.milestones:
        for hint in ms.hints:
            assert hint not in blob
