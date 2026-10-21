"""Generator tests (section 24.3): every published instance has a replayed
solution, items are reachable, codes match clues, solutions fit budgets,
unsolvable instances are rejected, generation reproduces from seed and
version."""

import pytest

from escapement_engine.core import CompiledRoom, Episode, instance_hash
from escapement_engine.generation import (
    PRACTICE_SEED,
    build_practice,
    daily_seed,
    generate,
    practice_manifest,
    season_seed,
)
from escapement_engine.rooms.emergency_lockdown import TIERS, apply_transforms, build
from escapement_engine.schemas.manifest import Rule
from escapement_engine.validation import validate

PRACTICE_HASH = "2415cfbedd3f99222f8d7fcf4e5ebf27ca3249fdbb7f65e496ebebd82b43bc93"


def test_practice_is_fixed_and_reproducible():
    committed = practice_manifest()
    assert instance_hash(committed) == PRACTICE_HASH
    assert instance_hash(build_practice().manifest) == PRACTICE_HASH
    assert committed.seed == PRACTICE_SEED and committed.tier == "practice"


@pytest.mark.parametrize("tier", ["standard", "hard"])
@pytest.mark.parametrize("i", range(4))
def test_generated_instances_validate_and_reproduce(tier, i):
    g = generate(tier, f"gen-{i}", f"r-{tier}-{i}")
    assert g.report.passed
    assert g.optimality == "proven"
    again = generate(tier, f"gen-{i}", f"r-{tier}-{i}")
    assert again.instance_hash == g.instance_hash
    m = g.manifest
    params = TIERS[tier]
    assert m.budget.actions == params.budget
    locations = [loc for loc in m.locations if not loc.terminal]
    assert len(locations) == params.locations
    assert sum(1 for o in m.objects if o.decoy) == params.decoys
    lock = next(o.code_lock for o in m.objects if o.code_lock)
    assert len(lock.code) == params.code_digits
    assert apply_transforms(lock.derivation.base_digits, list(lock.derivation.transforms)) == lock.code
    assert len(lock.derivation.offset_clues) == params.depth - 1
    ep = Episode.start(m, "check")
    for a in g.solution:
        ep.step(a)
    assert ep.status == "escaped"
    assert g.min_length <= m.budget.actions // 2


def test_different_seeds_differ():
    a = generate("standard", "seed-a", "r").instance_hash
    b = generate("standard", "seed-b", "r").instance_hash
    assert a != b


def test_unsolvable_instance_is_rejected():
    m, intended = build("standard", "broken", "broken")
    rules = [r for r in m.rules if r.id != "install_fuse"]
    broken = m.model_copy(update={"rules": rules})
    report = validate(broken, intended)
    assert not report.passed
    failing = {c.id for c in report.checks if not c.passed}
    assert "reachability" in failing


def test_shortcut_is_detected():
    m, intended = build("standard", "shortcut", "shortcut")
    # A rule that opens the blast door straight from the screwdriver skips power.
    from escapement_engine.schemas.manifest import Effect

    cheat = Rule(
        id="cheat",
        tool="use",
        item="screwdriver",
        target="tool_cabinet",
        effects=[Effect(kind="set_flag", name="exit_open", value=True), Effect(kind="set_flag", name="power", value=True)],
        message="Hmm.",
    )
    report = validate(m.model_copy(update={"rules": [*m.rules, cheat]}), intended)
    failing = {c.id for c in report.checks if not c.passed}
    assert "shortcuts" in failing


def test_dead_end_is_detected():
    from escapement_engine.schemas.manifest import Effect

    m, intended = build("standard", "deadend", "deadend")
    # Using the card on the panel destroys it: the exit becomes unreachable
    # from any state after that mistake, though still reachable overall.
    bad = Rule(id="shred", tool="use", item="access_card", target="maintenance_panel", effects=[Effect(kind="move_object", obj="access_card", to="@gone")], message="Gone.")
    rules = [bad, *m.rules]
    report = validate(m.model_copy(update={"rules": rules}), intended)
    assert any(c.id == "dead_ends" and not c.passed for c in report.checks)


def test_schema_integrity_rejects_bad_references():
    m, intended = build("standard", "refs", "refs")
    objs = [o.model_copy(update={"location": "atlantis"}) if o.id == "screwdriver" else o for o in m.objects]
    report = validate(m.model_copy(update={"objects": objs}), intended)
    assert not report.passed and report.checks[0].id == "schema"


def test_seeds_are_secret_salted_and_stable():
    assert daily_seed("s", "2026-10-21") == daily_seed("s", "2026-10-21")
    assert daily_seed("s", "2026-10-21") != daily_seed("t", "2026-10-21")
    assert season_seed("s", "s1", "hard", 3) != season_seed("s", "s1", "hard", 4)
    assert len(daily_seed("s", "2026-10-21")) == 32


def test_hidden_fuse_variant_reveals_on_inspect():
    for i in range(30):
        m, _ = build("standard", f"hidden-{i}", "x")
        if any(o.id == "workbench" for o in m.objects):
            break
    else:
        pytest.skip("no hidden-fuse variant in sampled seeds")
    room = CompiledRoom(m)
    ep = Episode.start(room, "x")
    bench_loc = next(o.location for o in m.objects if o.id == "workbench")
    if bench_loc != "maintenance_bay":
        ep.step({"tool": "move", "arguments": {"destination_id": bench_loc}})
    assert ep.step({"tool": "take", "arguments": {"item_id": "replacement_fuse"}}).result["error"] == "UNKNOWN_TARGET"
    rec = ep.step({"tool": "inspect", "arguments": {"target_id": "workbench"}})
    assert {"type": "object_revealed", "object_id": "replacement_fuse"} in rec.result["events"]
    assert ep.step({"tool": "take", "arguments": {"item_id": "replacement_fuse"}}).result["ok"]
