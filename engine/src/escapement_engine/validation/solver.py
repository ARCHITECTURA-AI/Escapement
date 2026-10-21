"""Engine-based solver (sections 12.3 and 12.4).

The solver never approximates the game: every edge it explores is produced by
`core.world.transition`, the same function that judges agents. It is
privileged (it may read codes from the manifest) but fair: it only enters a
code once every clue needed to derive it has been discovered.

Breadth-first search over the reachable state space proves the minimum
solution length when the space is small enough. Otherwise the result is
labelled "best verified solution" and path efficiency is not shown.

State reduction is sound: the search key keeps every part of private state
that any condition, visibility rule or goal can read. Bookkeeping that only
affects error wording (what was seen or inspected) and the state of objects
no rule reads and that hold nothing is dropped. Actions that the engine
defines as no-ops on the search key (inspecting an object with no effects,
using a pair with no rule, reviewing the journal) are skipped, since they
lead back to the same key.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..core.world import CompiledRoom, State, goal_reached, initial_state, is_visible, transition
from ..schemas.actions import Action
from ..schemas.manifest import INVENTORY, Cond


@dataclass
class SolveResult:
    solved: bool
    solution: list[dict[str, Any]] = field(default_factory=list)
    min_length: int | None = None
    proven_optimal: bool = False
    states_explored: int = 0
    exhausted: bool = False  # True if the whole reachable space was explored
    dead_ends: int = 0  # reachable states from which the goal is unreachable
    dead_end_example: list[dict[str, Any]] | None = None


def _referenced_objects(room: CompiledRoom) -> set[str]:
    refs: set[str] = set()

    def walk(conds: list[Cond]) -> None:
        for c in conds:
            if c.obj:
                refs.add(c.obj)
            if c.item:
                refs.add(c.item)

    m = room.manifest
    walk(m.goal)
    for ms in m.milestones:
        walk(ms.requires)
    for rule in m.rules:
        walk(rule.requires)
        walk(rule.already)
        refs.add(rule.target)
        if rule.item:
            refs.add(rule.item)
    for loc in m.locations:
        for e in loc.exits:
            walk(e.requires)
    for o in m.objects:
        walk(o.open_requires)
        for v in o.inspect_variants:
            walk(v.when)
            for eff in v.effects:
                if eff.obj:
                    refs.add(eff.obj)
        if o.code_lock:
            refs.add(o.id)
            walk(o.code_lock.requires)
        if o.portable:
            refs.add(o.id)
    for oid, contents in room.contents.items():
        if oid in room.objects and contents:
            refs.add(oid)
    return refs


class Solver:
    def __init__(self, room: CompiledRoom, max_states: int = 250_000) -> None:
        self.room = room
        self.max_states = max_states
        self.relevant = _referenced_objects(room)
        self._effect_inspect = {o.id for o in room.manifest.objects if any(v.effects for v in o.inspect_variants)}
        self._code_ready: dict[str, list[str]] = {}
        for o in room.manifest.objects:
            if o.code_lock:
                d = o.code_lock.derivation
                self._code_ready[o.id] = [d.base_clue, d.instruction_clue, *d.offset_clues]

    def key(self, state: State) -> str:
        objs = {oid: o for oid, o in state["objs"].items() if oid in self.relevant}
        return json.dumps(
            [state["loc"], objs, state["flags"], sorted(state["found"])],
            sort_keys=True,
            separators=(",", ":"),
        )

    def actions(self, state: State) -> list[Action]:
        room = self.room
        out: list[Action] = []
        here = room.locations[state["loc"]]
        for e in here.exits:
            out.append(Action("move", {"destination_id": e.to}))
        visible = [oid for oid in room.object_order if is_visible(room, state, oid)]
        for oid in visible:
            odef = room.objects[oid]
            o = state["objs"][oid]
            if oid in self._effect_inspect:
                out.append(Action("inspect", {"target_id": oid}))
            if odef.portable and o["at"] != INVENTORY:
                out.append(Action("take", {"item_id": oid}))
            if oid not in self.relevant:
                continue
            if "open" in odef.operations and not o["st"].get("open"):
                out.append(Action("interact", {"target_id": oid, "operation": "open"}))
            if "close" in odef.operations and o["st"].get("open"):
                out.append(Action("interact", {"target_id": oid, "operation": "close"}))
            if "activate" in odef.operations:
                out.append(Action("interact", {"target_id": oid, "operation": "activate"}))
            if odef.code_lock and o["st"].get("locked"):
                if all(c in state["found"] for c in self._code_ready[oid]):
                    out.append(Action("interact", {"target_id": oid, "operation": "enter_code", "value": odef.code_lock.code}))
        for item, target in room.use_rules:
            if state["objs"][item]["at"] == INVENTORY and target in visible:
                out.append(Action("use", {"item_id": item, "target_id": target}))
        return out

    def solve(self, check_dead_ends: bool = True) -> SolveResult:
        room = self.room
        start = initial_state(room)
        start_key = self.key(start)
        parents: dict[str, tuple[str | None, Action | None]] = {start_key: (None, None)}
        states: dict[str, State] = {start_key: start}
        edges: dict[str, list[str]] = {}
        queue: deque[str] = deque([start_key])
        goal_key: str | None = None
        goal_keys: set[str] = set()
        exhausted = True
        while queue:
            k = queue.popleft()
            state = states[k]
            succ: list[str] = []
            for action in self.actions(state):
                new, result = transition(room, state, action)
                if not result["ok"]:
                    continue
                nk = self.key(new)
                succ.append(nk)
                if nk in parents:
                    continue
                parents[nk] = (k, action)
                if goal_reached(room, new):
                    goal_keys.add(nk)
                    if goal_key is None:
                        goal_key = nk
                    states[nk] = new
                    continue  # the episode ends at the goal
                states[nk] = new
                if len(parents) >= self.max_states:
                    exhausted = False
                    queue.clear()
                    break
                queue.append(nk)
            edges[k] = succ
            if not exhausted:
                break
            if goal_key is not None and not check_dead_ends:
                exhausted = False
                break

        res = SolveResult(solved=goal_key is not None, states_explored=len(parents), exhausted=exhausted)
        if goal_key is not None:
            path: list[dict[str, Any]] = []
            node: str | None = goal_key
            while node is not None:
                parent, step = parents[node]
                if step is not None:
                    path.append(step.to_dict())
                node = parent
            path.reverse()
            res.solution = path
            res.min_length = len(path)
            # BFS visits in order of depth, so the first goal found is the shortest
            # path whenever the search was not cut short before reaching that depth.
            res.proven_optimal = True
        if exhausted and check_dead_ends and goal_keys:
            reverse: dict[str, list[str]] = {}
            for src, dsts in edges.items():
                for dst in dsts:
                    reverse.setdefault(dst, []).append(src)
            alive = set(goal_keys)
            frontier = deque(goal_keys)
            while frontier:
                node = frontier.popleft()
                for prev in reverse.get(node, []):
                    if prev not in alive:
                        alive.add(prev)
                        frontier.append(prev)
            dead = [k for k in parents if k not in alive]
            res.dead_ends = len(dead)
            if dead:
                example: list[dict[str, Any]] = []
                node = dead[0]
                while node is not None:
                    parent, step = parents[node]
                    if step is not None:
                        example.append(step.to_dict())
                    node = parent
                res.dead_end_example = list(reversed(example))
        return res


def solve(room: CompiledRoom, max_states: int = 250_000, check_dead_ends: bool = True) -> SolveResult:
    return Solver(room, max_states=max_states).solve(check_dead_ends=check_dead_ends)
