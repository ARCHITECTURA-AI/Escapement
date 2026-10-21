"""Property tests (section 24.3, Hypothesis): an item is never in two places,
state invariants survive every action, escape cannot precede its conditions,
discovered facts never revert, hidden entities never appear publicly,
identical actions give identical hashes."""

import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from escapement_engine.core import Episode
from escapement_engine.core.world import is_visible
from escapement_engine.generation import generate

IDS = [
    "maintenance_panel", "tool_cabinet", "screwdriver", "replacement_fuse", "parts_drawer", "operations_note",
    "operations_terminal", "equipment_locker", "access_card", "exit_reader", "mop_bucket", "wall_calendar",
    "fire_extinguisher", "workbench", "duty_roster", "supply_crate", "nonexistent",
]
LOCS = ["maintenance_bay", "control_room", "security_vestibule", "exterior", "nowhere"]

action = st.one_of(
    st.builds(lambda t: {"tool": "inspect", "arguments": {"target_id": t}}, st.sampled_from(IDS)),
    st.builds(lambda t: {"tool": "take", "arguments": {"item_id": t}}, st.sampled_from(IDS)),
    st.builds(lambda i, t: {"tool": "use", "arguments": {"item_id": i, "target_id": t}}, st.sampled_from(IDS), st.sampled_from(IDS)),
    st.builds(
        lambda t, op: {"tool": "interact", "arguments": {"target_id": t, "operation": op}},
        st.sampled_from(IDS),
        st.sampled_from(["open", "close", "activate"]),
    ),
    st.builds(
        lambda t, v: {"tool": "interact", "arguments": {"target_id": t, "operation": "enter_code", "value": v}},
        st.sampled_from(IDS),
        st.text("0123456789", min_size=1, max_size=5),
    ),
    st.builds(lambda d: {"tool": "move", "arguments": {"destination_id": d}}, st.sampled_from(LOCS)),
    st.just({"tool": "review_journal", "arguments": {}}),
    st.just({"tool": "teleport", "arguments": {}}),
    st.just({"tool": "inspect"}),
)


def _invariants(ep, prev_found, room):
    s = ep.state
    inv_objs = [oid for oid, o in s["objs"].items() if o["at"] == "@inv"]
    assert sorted(inv_objs) == sorted(s["inv"]), "inventory list disagrees with object locations"
    assert len(set(s["inv"])) == len(s["inv"]), "item in inventory twice"
    assert s["found"][: len(prev_found)] == prev_found, "discovered facts reverted"
    assert 0 <= s["used"] <= room.manifest.budget.actions
    if s["status"] == "escaped":
        assert s["flags"]["power"] and s["flags"]["exit_open"] and s["loc"] == "exterior"
        assert s["objs"]["access_card"]["at"] == "@inv"
    obs_text = json.dumps(ep.observation())
    for oid, o in s["objs"].items():
        if not is_visible(room, s, oid):
            assert f'"id": "{oid}"' not in obs_text, f"hidden {oid} in observation"
    for o in room.manifest.objects:
        if o.code_lock:
            assert o.code_lock.code not in json.dumps(ep.observation()["objects"])


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(action, min_size=1, max_size=80))
def test_invariants_survive_any_action_sequence(practice_room, actions):
    ep = Episode.start(practice_room, "prop")
    for a in actions:
        if ep.finished:
            break
        prev = list(ep.state["found"])
        ep.step(a)
        _invariants(ep, prev, practice_room)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(action, min_size=1, max_size=40))
def test_identical_actions_identical_hashes(practice_room, actions):
    a, b = Episode.start(practice_room, "x"), Episode.start(practice_room, "x")
    for act_ in actions:
        if a.finished:
            break
        assert a.step(act_).chain_hash == b.step(act_).chain_hash


_STANDARD = generate("standard", "property-seed", "prop-standard").manifest


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(action, min_size=1, max_size=60))
def test_invariants_on_generated_room(actions):
    from escapement_engine.core import CompiledRoom

    room = CompiledRoom(_STANDARD)
    ep = Episode.start(room, "prop")
    for a in actions:
        if ep.finished:
            break
        prev = list(ep.state["found"])
        ep.step(a)
        _invariants(ep, prev, room)
