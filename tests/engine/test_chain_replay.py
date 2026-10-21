"""Hash chain and replay (AC-05, AC-06) plus golden recordings (21.3)."""

import copy
import json
from pathlib import Path

import pytest
from escapement_engine.agents import HeuristicExplorer, RandomAgent, run_local
from escapement_engine.canonical import canonical_json, sha256_hex
from escapement_engine.core import Episode, chain_next, chain_start, instance_hash, state_hash
from escapement_engine.generation import load_manifest
from escapement_engine.replay import replay_from_episode, resimulate, verify_chain
from escapement_engine.version import ENGINE_VERSION

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def test_chain_formula_matches_spec(practice, practice_solution):
    ep = Episode.start(practice, "run-1")
    expected = sha256_hex(instance_hash(practice) + ENGINE_VERSION + "run-1")
    assert ep.chain_hash == expected == chain_start(instance_hash(practice), "run-1")
    rec = ep.step(practice_solution[0])
    manual = sha256_hex(expected + canonical_json(rec.action) + canonical_json(rec.result) + sha256_hex(canonical_json(ep.state)))
    assert rec.chain_hash == manual == chain_next(expected, rec.action, rec.result, state_hash(ep.state))


@pytest.fixture
def replay(practice):
    run = run_local(HeuristicExplorer(), practice, "replay-test")
    return replay_from_episode(run.episode)


def test_ac05_deterministic_replay(replay, practice):
    assert verify_chain(replay).ok
    sim = resimulate(replay, practice)
    assert sim.ok, sim.mismatches
    assert sim.final_hash == replay["final_chain_hash"]


@pytest.mark.parametrize("tamper", ["change", "remove", "reorder", "outcome"])
def test_ac06_tamper_evidence(replay, practice, tamper):
    bad = copy.deepcopy(replay)
    if tamper == "change":
        bad["steps"][5]["action"]["arguments"] = {"target_id": "access_card"}
    elif tamper == "remove":
        del bad["steps"][7]
    elif tamper == "reorder":
        bad["steps"][3], bad["steps"][4] = bad["steps"][4], bad["steps"][3]
    else:
        bad["outcome"] = "escaped" if replay["outcome"] != "escaped" else "client_aborted"
    chain = verify_chain(bad)
    sim = resimulate(bad, practice)
    if tamper == "outcome":
        assert not sim.ok
    else:
        assert not chain.ok
        assert not sim.ok


def test_replay_needs_matching_manifest(replay):
    from escapement_engine.generation import generate

    other = generate("standard", "other", "other").manifest
    assert not resimulate(replay, other).ok


def test_malformed_requests_replay(practice):
    ep = Episode.start(practice, "mal")
    requests = [{"tool": "fly"}, {"tool": "inspect", "arguments": {"target_id": "mop_bucket"}}, {"tool": "x", "arguments": 3}]
    for r in requests:
        ep.step(r)
    replay = replay_from_episode(ep, requests=requests)
    assert verify_chain(replay).ok
    assert resimulate(replay, practice).ok


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("*.replay.json")), ids=lambda p: p.name)
def test_golden_replays(path):
    """CI replays golden recordings against every release so an engine change
    cannot silently alter an old result."""
    replay = json.loads(path.read_text())
    manifest = load_manifest((GOLDEN / replay["manifest_file"]).read_text())
    assert verify_chain(replay).ok
    sim = resimulate(replay, manifest)
    assert sim.ok, sim.mismatches
    assert sim.outcome == replay["outcome"]


def test_golden_set_present():
    assert len(list(GOLDEN.glob("*.replay.json"))) >= 3
