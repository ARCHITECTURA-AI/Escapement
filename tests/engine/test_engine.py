"""Engine unit tests (section 24.3): visibility, inventory, item use, locks,
codes, movement, power dependencies, costs, terminal states, invalid actions."""

import pytest

from escapement_engine.core import Episode, EpisodeFinished
from escapement_engine.schemas.endings import (
    ACTION_BUDGET_EXHAUSTED,
    CLIENT_ABORTED,
    ESCAPED,
    MALFORMED_LIMIT_REACHED,
)

from .conftest import act


def code_of(room):
    return next(o.code_lock.code for o in room.manifest.objects if o.code_lock)


def visible(ep):
    return {o["id"] for o in ep.observation()["objects"]}


def to_power(ep):
    for a in [
        act("interact", target_id="tool_cabinet", operation="open"),
        act("take", item_id="screwdriver"),
        act("use", item_id="screwdriver", target_id="maintenance_panel"),
        act("move", destination_id="control_room"),
        act("interact", target_id="parts_drawer", operation="open"),
        act("take", item_id="replacement_fuse"),
        act("move", destination_id="maintenance_bay"),
        act("use", item_id="replacement_fuse", target_id="maintenance_panel"),
    ]:
        rec = ep.step(a)
        assert rec.result["ok"], (a, rec.result)


def test_initial_observation(ep):
    obs = ep.observation()
    assert obs["location"]["id"] == "maintenance_bay"
    assert visible(ep) == {"maintenance_panel", "tool_cabinet", "mop_bucket"}
    assert obs["actions_remaining"] == 60 and obs["status"] == "in_progress"
    assert obs["inventory"] == [] and obs["last_result"] is None


def test_container_contents_hidden_until_open(ep):
    assert "screwdriver" not in visible(ep)
    rec = ep.step(act("interact", target_id="tool_cabinet", operation="open"))
    assert rec.result["ok"]
    assert "screwdriver" in visible(ep)
    assert {"type": "object_revealed", "object_id": "screwdriver"} in rec.result["events"]
    ep.step(act("interact", target_id="tool_cabinet", operation="close"))
    assert "screwdriver" not in visible(ep)
    # Seen before but not visible now: NOT_VISIBLE, not UNKNOWN_TARGET.
    assert ep.step(act("take", item_id="screwdriver")).result["error"] == "NOT_VISIBLE"


def test_unknown_and_undiscovered_targets_get_identical_errors(practice_room):
    a = Episode.start(practice_room, "r1").step(act("inspect", target_id="access_card")).result
    b = Episode.start(practice_room, "r1").step(act("inspect", target_id="access_kard")).result
    assert a["error"] == b["error"] == "UNKNOWN_TARGET"
    assert a["message"].replace("access_card", "X") == b["message"].replace("access_kard", "X")


def test_take_and_inventory(ep):
    ep.step(act("interact", target_id="tool_cabinet", operation="open"))
    rec = ep.step(act("take", item_id="screwdriver"))
    assert rec.result["ok"] and ep.observation()["inventory"] == [{"id": "screwdriver", "name": "Screwdriver"}]
    assert ep.step(act("take", item_id="screwdriver")).result["error"] == "ALREADY_COMPLETED"
    assert ep.step(act("take", item_id="maintenance_panel")).result["error"] == "INVALID_OPERATION"
    # Inventory items stay inspectable everywhere.
    ep.step(act("move", destination_id="control_room"))
    assert ep.step(act("inspect", target_id="screwdriver")).result["ok"]


def test_use_requires_carrying_the_item(ep):
    ep.step(act("interact", target_id="tool_cabinet", operation="open"))
    rec = ep.step(act("use", item_id="screwdriver", target_id="maintenance_panel"))
    assert rec.result["error"] == "MISSING_ITEM"


def test_use_without_rule_is_invalid_operation(ep):
    ep.step(act("interact", target_id="tool_cabinet", operation="open"))
    ep.step(act("take", item_id="screwdriver"))
    assert ep.step(act("use", item_id="screwdriver", target_id="mop_bucket")).result["error"] == "INVALID_OPERATION"


def test_panel_open_precondition_and_screwdriver(ep):
    rec = ep.step(act("interact", target_id="maintenance_panel", operation="open"))
    assert rec.result["error"] == "PRECONDITION_NOT_MET"
    assert "screws" in rec.result["message"]
    ep.step(act("interact", target_id="tool_cabinet", operation="open"))
    ep.step(act("take", item_id="screwdriver"))
    assert ep.step(act("use", item_id="screwdriver", target_id="maintenance_panel")).result["ok"]
    assert ep.step(act("use", item_id="screwdriver", target_id="maintenance_panel")).result["error"] == "ALREADY_COMPLETED"


def test_fuse_needs_open_panel(ep):
    ep.step(act("move", destination_id="control_room"))
    ep.step(act("interact", target_id="parts_drawer", operation="open"))
    ep.step(act("take", item_id="replacement_fuse"))
    ep.step(act("move", destination_id="maintenance_bay"))
    rec = ep.step(act("use", item_id="replacement_fuse", target_id="maintenance_panel"))
    assert rec.result["error"] == "PRECONDITION_NOT_MET" and rec.result["message"] == "The panel cover is closed."


def test_power_gates_vestibule_and_terminal(ep):
    ep.step(act("move", destination_id="control_room"))
    assert ep.step(act("move", destination_id="security_vestibule")).result["error"] == "PRECONDITION_NOT_MET"
    rec = ep.step(act("inspect", target_id="operations_terminal"))
    assert "dark" in rec.result["message"] and not rec.result["events"]
    ep.step(act("move", destination_id="maintenance_bay"))
    to_power(ep)
    ep.step(act("move", destination_id="control_room"))
    rec = ep.step(act("inspect", target_id="operations_terminal"))
    assert any(e["type"] == "clue_discovered" for e in rec.result["events"])
    assert ep.step(act("move", destination_id="security_vestibule")).result["ok"]


def test_fuse_is_consumed_and_never_in_two_places(ep):
    to_power(ep)
    assert ep.state["objs"]["replacement_fuse"]["at"] == "@gone"
    assert "replacement_fuse" not in ep.state["inv"]


def test_movement_errors(ep):
    assert ep.step(act("move", destination_id="exterior")).result["error"] == "UNKNOWN_TARGET"
    assert ep.step(act("move", destination_id="maintenance_bay")).result["error"] == "ALREADY_COMPLETED"
    ep.step(act("move", destination_id="control_room"))
    ep.step(act("move", destination_id="maintenance_bay"))
    # security_vestibule is known (seen as an exit) but not adjacent here.
    assert ep.step(act("move", destination_id="security_vestibule")).result["error"] == "NOT_REACHABLE"


def test_codes_and_brute_force_penalty(ep, practice_room):
    to_power(ep)
    ep.step(act("move", destination_id="control_room"))
    ep.step(act("move", destination_id="security_vestibule"))
    assert ep.step(act("interact", target_id="equipment_locker", operation="open")).result["error"] == "PRECONDITION_NOT_MET"
    code = code_of(practice_room)
    wrong = "000" if code != "000" else "111"
    used = ep.state["used"]
    costs = [ep.step(act("interact", target_id="equipment_locker", operation="enter_code", value=wrong)).result["cost"] for _ in range(5)]
    assert costs == [1, 1, 1, 3, 3]
    assert ep.state["used"] == used + 9
    rec = ep.step(act("interact", target_id="equipment_locker", operation="enter_code", value=code))
    assert rec.result["ok"] and {"type": "unlocked", "object_id": "equipment_locker"} in rec.result["events"]
    assert ep.step(act("interact", target_id="equipment_locker", operation="enter_code", value=code)).result["error"] == "ALREADY_COMPLETED"


def test_unsupported_operation(ep):
    rec = ep.step(act("interact", target_id="mop_bucket", operation="open"))
    assert rec.result["error"] == "INVALID_OPERATION" and rec.result["cost"] == 1


def test_review_journal_costs_one(ep):
    ep.step(act("inspect", target_id="maintenance_panel"))
    rec = ep.step(act("review_journal"))
    assert rec.result["ok"] and rec.result["cost"] == 1
    assert len(rec.result["data"]["clues"]) == 1
    assert ep.state["used"] == 2


def test_full_solution_escapes(practice_room, practice_solution):
    ep = Episode.start(practice_room, "r")
    for a in practice_solution:
        ep.step(a)
    assert ep.status == ESCAPED
    assert ep.records[-1].result["events"][-1] == {"type": "escaped"}


def test_malformed_costs_nothing_and_limit_ends_run(ep):
    for i in range(2):
        rec = ep.step({"tool": "fly"})
        assert rec.malformed and rec.result["cost"] == 0 and rec.result["error"] == "INVALID_ARGUMENT"
    assert ep.state["used"] == 0
    # A valid request resets the consecutive count.
    ep.step(act("review_journal"))
    for i in range(3):
        rec = ep.step({"tool": "fly"})
    assert ep.status == MALFORMED_LIMIT_REACHED
    assert ep.state["mal_total"] == 5


def test_budget_exhausted_ends_run(ep):
    for _ in range(60):
        ep.step(act("review_journal"))
    assert ep.status == ACTION_BUDGET_EXHAUSTED
    assert ep.observation()["actions_remaining"] == 0


def test_ac08_nothing_executes_after_terminal(ep):
    for _ in range(60):
        ep.step(act("review_journal"))
    before = (ep.chain_hash, ep.seq)
    with pytest.raises(EpisodeFinished):
        ep.step(act("review_journal"))
    with pytest.raises(EpisodeFinished):
        ep.terminate(CLIENT_ABORTED)
    assert (ep.chain_hash, ep.seq) == before


def test_ac01_claims_change_nothing(ep):
    """Saying "I unlocked the door" is not an action."""
    rec = ep.step({"tool": "move", "arguments": {"destination_id": "exterior"}, "claim": "I unlocked the door"})
    assert rec.malformed
    rec = ep.step(act("interact", target_id="exit_reader", operation="activate"))
    assert not rec.result["ok"]
    assert ep.state["flags"]["exit_open"] is False


def test_ac07_claimed_success_with_exit_locked_is_not_escaped(ep):
    to_power(ep)
    ep.step(act("move", destination_id="control_room"))
    ep.step(act("move", destination_id="security_vestibule"))
    assert ep.step(act("move", destination_id="exterior")).result["error"] == "PRECONDITION_NOT_MET"
    rec = ep.terminate(CLIENT_ABORTED, note="Agent declared: escaped!")
    assert rec.status == CLIENT_ABORTED != ESCAPED


def test_failed_action_is_atomic(ep):
    before = ep.state
    snapshot = repr(before["objs"]), before["flags"], before["loc"]
    ep.step(act("interact", target_id="maintenance_panel", operation="open"))
    assert (repr(ep.state["objs"]), ep.state["flags"], ep.state["loc"]) == snapshot


def test_determinism_same_actions_same_hashes(practice_room, practice_solution):
    a, b = Episode.start(practice_room, "same"), Episode.start(practice_room, "same")
    for step in practice_solution + [act("review_journal")]:
        if a.finished:
            break
        ra, rb = a.step(step), b.step(step)
        assert ra.chain_hash == rb.chain_hash and ra.state_hash == rb.state_hash and ra.observation == rb.observation
    c = Episode.start(practice_room, "different-run-id")
    assert c.chain_hash != Episode.start(practice_room, "same").chain_hash


def test_observation_withholds_private_state(ep, practice_room):
    code = code_of(practice_room)
    obs = ep.observation()
    text = repr(obs)
    for word in ("secured", "hidden", "decoy", "milestone", "power", code):
        assert word not in text
