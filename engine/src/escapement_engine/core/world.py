"""The deterministic transition function (sections 9 and 10).

Only this module changes world state. `transition` is pure: it takes a
compiled room, a private state and a parsed action, and returns a new state,
the public result and the action cost. A failed action returns the original
state object untouched (atomic transitions, section 9.4).

Private state is a plain JSON-compatible dict of strings, integers, booleans,
lists and dicts so that it hashes canonically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas.actions import Action
from ..schemas.endings import IN_PROGRESS
from ..schemas.manifest import GONE, INVENTORY, Cond, Effect, ObjectDef, RoomManifest, Rule

State = dict[str, Any]
Result = dict[str, Any]


def _the(name: str) -> str:
    return "the " + name[:1].lower() + name[1:]


@dataclass
class CompiledRoom:
    """Index structures over a manifest. Built once, shared read-only."""

    manifest: RoomManifest

    def __post_init__(self) -> None:
        m = self.manifest
        self.objects: dict[str, ObjectDef] = {o.id: o for o in m.objects}
        self.object_order: list[str] = [o.id for o in m.objects]
        self.locations = {loc.id: loc for loc in m.locations}
        self.clues = {c.id: c for c in m.clues}
        self.use_rules: dict[tuple[str, str], list[Rule]] = {}
        self.activate_rules: dict[str, list[Rule]] = {}
        for rule in m.rules:
            if rule.tool == "use":
                self.use_rules.setdefault((rule.item or "", rule.target), []).append(rule)
            elif rule.operation == "activate":
                self.activate_rules.setdefault(rule.target, []).append(rule)
        self.contents: dict[str, list[str]] = {}
        for o in m.objects:
            self.contents.setdefault(o.location, []).append(o.id)


# ---------------------------------------------------------------------------
# State construction and queries


def initial_state(room: CompiledRoom) -> State:
    m = room.manifest
    objs = {
        o.id: {"at": o.location, "hidden": o.hidden, "st": dict(o.state)} for o in m.objects
    }
    state: State = {
        "loc": m.start,
        "objs": objs,
        "inv": [],
        "flags": dict(m.flags),
        "found": [],
        "seen": [],
        "known_locs": [],
        "visited": [m.start],
        "inspected": [],
        "wrong": {},
        "entered": [],
        "used": 0,
        "mal": 0,
        "mal_total": 0,
        "status": IN_PROGRESS,
        "seq": 0,
        "milestones": [],
    }
    state["seen"] = sorted(visible_ids(room, state))
    state["known_locs"] = sorted({m.start, *(e.to for e in room.locations[m.start].exits)})
    return state


def is_visible(room: CompiledRoom, state: State, oid: str) -> bool:
    obj = state["objs"].get(oid)
    if obj is None or obj["hidden"]:
        return False
    at = obj["at"]
    if at == INVENTORY:
        return True
    if at == GONE:
        return False
    if at == state["loc"]:
        return True
    container = state["objs"].get(at)
    if container is not None:
        if not container["st"].get("open", True):
            return False
        return is_visible(room, state, at)
    return False


def visible_ids(room: CompiledRoom, state: State) -> list[str]:
    return [oid for oid in room.object_order if is_visible(room, state, oid)]


def check(room: CompiledRoom, state: State, cond: Cond) -> bool:
    kind = cond.kind
    if kind == "flag":
        return state["flags"].get(cond.name) == cond.value
    if kind == "state":
        return state["objs"][cond.obj]["st"].get(cond.key) == cond.value
    if kind == "has":
        return state["objs"][cond.item]["at"] == INVENTORY
    if kind == "at":
        return state["loc"] == cond.location
    if kind == "discovered":
        return cond.clue in state["found"]
    raise AssertionError(kind)


def all_hold(room: CompiledRoom, state: State, conds: list[Cond]) -> bool:
    return all(check(room, state, c) for c in conds)


def first_failure(room: CompiledRoom, state: State, conds: list[Cond]) -> Cond | None:
    for cond in conds:
        if not check(room, state, cond):
            return cond
    return None


def state_tags(room: CompiledRoom, oid: str, st: dict[str, Any]) -> list[str]:
    obj = room.objects[oid]
    labels = room.manifest.state_labels
    tags = []
    for key in obj.public_state:
        if key in st and key in labels:
            on, off = labels[key]
            tags.append(on if st[key] else off)
    return tags


# ---------------------------------------------------------------------------
# Copy-on-write mutation


class _Tx:
    def __init__(self, room: CompiledRoom, state: State) -> None:
        self.room = room
        self.s: State = dict(state)
        self._objs_copied = False
        self._obj_copied: set[str] = set()
        self.events: list[dict[str, Any]] = []

    def obj(self, oid: str) -> dict[str, Any]:
        if not self._objs_copied:
            self.s["objs"] = dict(self.s["objs"])
            self._objs_copied = True
        if oid not in self._obj_copied:
            old = self.s["objs"][oid]
            self.s["objs"][oid] = {"at": old["at"], "hidden": old["hidden"], "st": dict(old["st"])}
            self._obj_copied.add(oid)
        return self.s["objs"][oid]

    def add_to(self, key: str, value: Any, keep_sorted: bool = True) -> bool:
        if value in self.s[key]:
            return False
        items = list(self.s[key]) + [value]
        self.s[key] = sorted(items) if keep_sorted else items
        return True

    def apply(self, effect: Effect) -> None:
        kind = effect.kind
        if kind == "set_flag":
            flags = dict(self.s["flags"])
            flags[effect.name] = effect.value
            self.s["flags"] = flags
        elif kind == "set_state":
            obj = self.obj(effect.obj)  # type: ignore[arg-type]
            before = obj["st"].get(effect.key)
            obj["st"][effect.key] = effect.value
            if before != effect.value and is_visible(self.room, self.s, effect.obj):  # type: ignore[arg-type]
                tags = state_tags(self.room, effect.obj, {effect.key: effect.value})  # type: ignore[arg-type]
                if tags:
                    self.events.append(
                        {"type": "state_changed", "object_id": effect.obj, "state": tags[0]}
                    )
        elif kind == "move_object":
            obj = self.obj(effect.obj)  # type: ignore[arg-type]
            was = obj["at"]
            obj["at"] = effect.to
            inv = list(self.s["inv"])
            if was == INVENTORY and effect.obj in inv:
                inv.remove(effect.obj)
            if effect.to == INVENTORY and effect.obj not in inv:
                inv.append(effect.obj)
            self.s["inv"] = inv
            if effect.to == GONE and was == INVENTORY:
                self.events.append({"type": "item_consumed", "item_id": effect.obj})
        elif kind == "reveal":
            self.obj(effect.obj)["hidden"] = False  # type: ignore[arg-type]
        elif kind == "discover":
            if effect.clue not in self.s["found"]:
                self.s["found"] = list(self.s["found"]) + [effect.clue]
                self.events.append({"type": "clue_discovered", "clue_id": effect.clue})
        else:  # pragma: no cover - schema forbids it
            raise AssertionError(kind)

    def apply_all(self, effects: list[Effect]) -> None:
        for effect in effects:
            self.apply(effect)

    def finish(self, announce: bool = True) -> State:
        """Record newly visible objects and achieved milestones."""
        room = self.room
        seen = set(self.s["seen"])
        new = [oid for oid in visible_ids(room, self.s) if oid not in seen]
        if new:
            self.s["seen"] = sorted(seen | set(new))
            if announce:
                for oid in new:
                    self.events.append({"type": "object_revealed", "object_id": oid})
        achieved = self.s["milestones"]
        for ms in room.manifest.milestones:
            if ms.id not in achieved and all_hold(room, self.s, ms.requires):
                achieved = list(achieved) + [ms.id]
        self.s["milestones"] = achieved
        return self.s


# ---------------------------------------------------------------------------
# Results


def _ok(tool: str, message: str, events: list[dict[str, Any]], cost: int = 1, data: Any = None) -> Result:
    result: Result = {"ok": True, "tool": tool, "error": None, "message": message, "events": events, "cost": cost}
    if data is not None:
        result["data"] = data
    return result


def _fail(tool: str, code: str, message: str, cost: int = 1, events: list[dict[str, Any]] | None = None) -> Result:
    return {"ok": False, "tool": tool, "error": code, "message": message, "events": events or [], "cost": cost}


def _unknown(tool: str, oid: str) -> Result:
    # Undiscovered and nonexistent targets get the same public error (10.2).
    return _fail(tool, "UNKNOWN_TARGET", f"You don't know of anything called '{oid}'.")


def _resolve(room: CompiledRoom, state: State, tool: str, oid: str) -> Result | None:
    """Return a failure if `oid` is not an object the player can act on here."""
    if oid not in room.objects or oid not in state["seen"]:
        return _unknown(tool, oid)
    if not is_visible(room, state, oid):
        return _fail(tool, "NOT_VISIBLE", f"You can't see {_the(room.objects[oid].name)} from here.")
    return None


# ---------------------------------------------------------------------------
# Tools


def transition(room: CompiledRoom, state: State, action: Action) -> tuple[State, Result]:
    """Apply one schema-valid action. Returns (new_state, public_result).

    The caller (Episode) owns budgets, sequence numbers and the hash chain.
    """
    handler = _HANDLERS[action.tool]
    new_state, result = handler(room, state, action.arguments)
    return new_state, result


def _inspect(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    oid = args["target_id"]
    failure = _resolve(room, state, "inspect", oid)
    if failure:
        return state, failure
    obj = room.objects[oid]
    tx = _Tx(room, state)
    text = obj.description
    for variant in obj.inspect_variants:
        if all_hold(room, state, variant.when):
            text = variant.text
            tx.apply_all(variant.effects)
            break
    tx.add_to("inspected", oid)
    return tx.finish(), _ok("inspect", text, tx.events)


def _take(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    oid = args["item_id"]
    failure = _resolve(room, state, "take", oid)
    if failure:
        return state, failure
    obj = room.objects[oid]
    if state["objs"][oid]["at"] == INVENTORY:
        return state, _fail("take", "ALREADY_COMPLETED", f"You are already carrying {_the(obj.name)}.")
    if not obj.portable:
        return state, _fail("take", "INVALID_OPERATION", f"{obj.name} can't be carried.")
    tx = _Tx(room, state)
    tx.apply(Effect(kind="move_object", obj=oid, to=INVENTORY))
    tx.events.append({"type": "item_taken", "item_id": oid})
    return tx.finish(), _ok("take", f"You take {_the(obj.name)}.", tx.events)


def _run_rule(room: CompiledRoom, state: State, tool: str, rules: list[Rule], none_message: str) -> tuple[State, Result]:
    if not rules:
        return state, _fail(tool, "INVALID_OPERATION", none_message)
    for rule in rules:
        if rule.already and all_hold(room, state, rule.already):
            continue
        if first_failure(room, state, rule.requires) is None:
            tx = _Tx(room, state)
            tx.apply_all(rule.effects)
            return tx.finish(), _ok(tool, rule.message, tx.events, cost=rule.cost)
    # Report against the first rule that is not already completed.
    pending = [r for r in rules if not (r.already and all_hold(room, state, r.already))]
    if not pending:
        return state, _fail(tool, "ALREADY_COMPLETED", rules[0].already_message)
    cond = first_failure(room, state, pending[0].requires)
    assert cond is not None
    return state, _fail(tool, cond.fail_code, cond.fail_message)


def _use(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    item, target = args["item_id"], args["target_id"]
    if item not in room.objects or item not in state["seen"]:
        return state, _unknown("use", item)
    if state["objs"][item]["at"] != INVENTORY:
        return state, _fail("use", "MISSING_ITEM", f"You aren't carrying {_the(room.objects[item].name)}.")
    failure = _resolve(room, state, "use", target)
    if failure:
        return state, failure
    rules = room.use_rules.get((item, target), [])
    message = f"Using {_the(room.objects[item].name)} on {_the(room.objects[target].name)} does nothing."
    return _run_rule(room, state, "use", rules, message)


def _interact(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    oid, op = args["target_id"], args["operation"]
    failure = _resolve(room, state, "interact", oid)
    if failure:
        return state, failure
    obj = room.objects[oid]
    if op not in obj.operations:
        return state, _fail("interact", "INVALID_OPERATION", f"You can't {op.replace('_', ' ')} {_the(obj.name)}.")
    st = state["objs"][oid]["st"]
    if op == "open":
        if st.get("open"):
            return state, _fail("interact", "ALREADY_COMPLETED", f"{obj.name} is already open.")
        if st.get("locked"):
            return state, _fail("interact", "PRECONDITION_NOT_MET", f"{obj.name} is locked.")
        cond = first_failure(room, state, obj.open_requires)
        if cond is not None:
            return state, _fail("interact", cond.fail_code, cond.fail_message)
        tx = _Tx(room, state)
        tx.apply(Effect(kind="set_state", obj=oid, key="open", value=True))
        new_state = tx.finish()
        inside = [c for c in room.contents.get(oid, []) if is_visible(room, new_state, c)]
        if obj.container:
            names = ", ".join(_the(room.objects[c].name) for c in inside)
            msg = f"You open {_the(obj.name)}." + (f" Inside: {names}." if names else " It is empty.")
        else:
            msg = f"You open {_the(obj.name)}."
        return new_state, _ok("interact", msg, tx.events)
    if op == "close":
        if not st.get("open"):
            return state, _fail("interact", "ALREADY_COMPLETED", f"{obj.name} is already closed.")
        tx = _Tx(room, state)
        tx.apply(Effect(kind="set_state", obj=oid, key="open", value=False))
        return tx.finish(), _ok("interact", f"You close {_the(obj.name)}.", tx.events)
    if op == "enter_code":
        lock = obj.code_lock
        if lock is None:  # pragma: no cover - validation forbids it
            return state, _fail("interact", "INVALID_OPERATION", f"{obj.name} has no keypad.")
        if not st.get("locked"):
            return state, _fail("interact", "ALREADY_COMPLETED", f"{obj.name} is already unlocked.")
        cond = first_failure(room, state, lock.requires)
        if cond is not None:
            return state, _fail("interact", cond.fail_code, cond.fail_message)
        value = args["value"]
        tx = _Tx(room, state)
        tx.s["entered"] = list(state["entered"]) + [[oid, value]]
        if value == lock.code:
            tx.apply(Effect(kind="set_state", obj=oid, key="locked", value=False))
            tx.apply_all(lock.on_unlock)
            tx.events.append({"type": "unlocked", "object_id": oid})
            return tx.finish(), _ok("interact", f"The keypad chimes. {obj.name} unlocks.", tx.events)
        budget = room.manifest.budget
        wrong = dict(state["wrong"])
        wrong[oid] = wrong.get(oid, 0) + 1
        tx.s["wrong"] = wrong
        cost = 1 + (budget.wrong_code_penalty if wrong[oid] > budget.wrong_code_free_attempts else 0)
        msg = "The keypad buzzes: incorrect code."
        if wrong[oid] == budget.wrong_code_free_attempts:
            msg += f" Security delay armed: each further wrong code here costs {budget.wrong_code_penalty} extra actions."
        elif cost > 1:
            msg += f" Security delay: this attempt cost {cost} actions."
        tx.events.append({"type": "wrong_code", "object_id": oid, "attempts": wrong[oid]})
        new_state = tx.finish()
        return new_state, _fail("interact", "PRECONDITION_NOT_MET", msg, cost=cost, events=tx.events)
    # activate
    rules = room.activate_rules.get(oid, [])
    return _run_rule(room, state, "interact", rules, f"Activating {_the(obj.name)} does nothing.")


def _move(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    dest = args["destination_id"]
    if dest not in room.locations or dest not in state["known_locs"]:
        return state, _unknown("move", dest)
    here = room.locations[state["loc"]]
    exit_ = next((e for e in here.exits if e.to == dest), None)
    name = room.locations[dest].name
    if exit_ is None:
        if dest == state["loc"]:
            return state, _fail("move", "ALREADY_COMPLETED", f"You are already in the {name[:1].lower() + name[1:]}.")
        return state, _fail("move", "NOT_REACHABLE", f"You can't get to the {name[:1].lower() + name[1:]} from here.")
    cond = first_failure(room, state, exit_.requires)
    if cond is not None:
        return state, _fail("move", cond.fail_code, cond.fail_message)
    tx = _Tx(room, state)
    tx.s["loc"] = dest
    tx.add_to("visited", dest)
    for e in room.locations[dest].exits:
        tx.add_to("known_locs", e.to)
    tx.events.append({"type": "moved", "location_id": dest})
    return tx.finish(announce=False), _ok("move", f"You move to the {name[:1].lower() + name[1:]}.", tx.events)


def _review_journal(room: CompiledRoom, state: State, args: dict[str, str]) -> tuple[State, Result]:
    entries = [{"id": cid, "text": room.clues[cid].text} for cid in state["found"]]
    n = len(entries)
    msg = f"Journal: {n} " + ("entry" if n == 1 else "entries") + "." if n else "Your journal is empty."
    return state, _ok("review_journal", msg, [], data={"clues": entries})


_HANDLERS = {
    "inspect": _inspect,
    "take": _take,
    "use": _use,
    "interact": _interact,
    "move": _move,
    "review_journal": _review_journal,
}


# ---------------------------------------------------------------------------
# Observation (section 10.3): what an agent sees, and nothing else (10.4).


def observe(room: CompiledRoom, state: State, last_result: Result | None) -> dict[str, Any]:
    m = room.manifest
    here = room.locations[state["loc"]]
    objects = []
    for oid in visible_ids(room, state):
        o = state["objs"][oid]
        if o["at"] == INVENTORY:
            continue
        odef = room.objects[oid]
        entry: dict[str, Any] = {"id": oid, "name": odef.name}
        tags = state_tags(room, oid, o["st"])
        if tags:
            entry["state"] = tags
        if o["at"] != state["loc"]:
            entry["in"] = o["at"]
        if odef.portable:
            entry["portable"] = True
        ops = [
            op
            for op in odef.operations
            if not (op == "open" and o["st"].get("open")) and not (op == "close" and not o["st"].get("open"))
        ]
        if ops:
            entry["operations"] = ops
        objects.append(entry)
    inventory = [{"id": oid, "name": room.objects[oid].name} for oid in state["inv"]]
    exits = [{"id": e.to, "name": room.locations[e.to].name} for e in here.exits]
    budget = m.budget.actions
    return {
        "goal": m.goal_text,
        "location": {"id": here.id, "name": here.name, "description": here.description},
        "objects": objects,
        "exits": exits,
        "inventory": inventory,
        "journal_entries": len(state["found"]),
        "actions_used": state["used"],
        "action_budget": budget,
        "actions_remaining": max(0, budget - state["used"]),
        "status": state["status"],
        "last_result": last_result,
    }


def goal_reached(room: CompiledRoom, state: State) -> bool:
    return all_hold(room, state, room.manifest.goal)
