from escapement_engine.agents import HeuristicExplorer, RandomAgent, run_local
from escapement_engine.clinic import analyze, private_context
from escapement_engine.replay import replay_from_episode
from escapement_engine.stats import ceil_pct, floor_pct, interval_text, pass_k, rank_bands, summarize, wilson


def test_wilson_bounds():
    lo, hi = wilson(10, 10)
    assert 0.69 < lo < 0.73 and abs(hi - 1.0) < 1e-12
    assert wilson(0, 0) == (0.0, 1.0)


def test_perfect_record_still_has_an_honest_interval():
    s = summarize({str(i): [(True, 20)] * 3 for i in range(10)})
    assert s.rate == 1.0 and s.ci_low < 0.75 and s.pass3 == 1.0 and s.pass3_instances == 10


def test_summary_counts_failures():
    s = summarize({"a": [(True, 20), (False, 60), (False, 60)], "b": [(True, 18)]})
    assert (s.runs, s.escapes, s.instances) == (4, 2, 2)
    assert s.pass3 == 0.0 and s.pass3_instances == 1
    assert s.median_actions_success == 19.0
    assert s.ci_low <= s.rate <= s.ci_high


def test_pass_k():
    assert pass_k({"a": [True, True, True], "b": [True, False, True], "c": [True]}) == (0.5, 2)


def test_rank_bands_group_overlaps():
    bands = rank_bands([("a", 0.9, 0.8, 0.97), ("b", 0.88, 0.78, 0.96), ("c", 0.3, 0.2, 0.4)])
    assert bands["a"] == bands["b"] == 1 and bands["c"] == 2


def test_rounding_never_flatters():
    assert floor_pct(0.6666) == "66.6%"
    assert ceil_pct(0.6661) == "66.7%"
    assert interval_text(0.12345, 0.98761) == "12.3%–98.8%"


def test_trace_clinic_labels_are_heuristic(practice, practice_solution):
    run = run_local(RandomAgent(seed=11), practice, "clinic")
    replay = replay_from_episode(run.episode)
    out = analyze(replay, private_context(replay, practice, practice_solution))
    assert out["findings"]
    assert all(f["heuristic"] for f in out["findings"])
    kinds = {f["kind"] for f in out["findings"]}
    assert "first_invalid_action" in kinds and "never_inspected" in kinds or "no_progress_repeat" in kinds
    public_only = analyze(replay)
    assert not any(f["kind"] == "first_milestone" for f in public_only["findings"])
    assert public_only["milestones"] is None
