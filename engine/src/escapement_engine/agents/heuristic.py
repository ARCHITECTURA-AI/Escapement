"""Heuristic explorer: a strong non-LLM baseline (section 15).

Inspect everything, take portable items, try advertised interactions, visit
new locations, review clues, avoid exact repeated failures. For keypads it
tries digit groups found in its journal, as written and reversed; it does not
understand instructions, so deeper code compositions defeat it.
"""

from __future__ import annotations

import json
import re
from typing import Any

PERMANENT = {"INVALID_OPERATION", "UNKNOWN_TARGET", "ALREADY_COMPLETED"}
PROGRESS_EVENTS = {"state_changed", "item_consumed", "unlocked", "clue_discovered", "object_revealed", "item_taken"}


class HeuristicExplorer:
    name = "heuristic"
    version = "1.0.0"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.inspected: set[str] = set()
        self.failed: set[str] = set()
        self.visits: dict[str, int] = {}
        self.clues: dict[str, str] = {}
        self.pending_review = False
        self.tried_codes: set[tuple[str, str]] = set()
        self.blockers: set[str] = set()
        self.never: set[str] = set()
        self.containers: set[str] = set()
        self.blocked_moves: set[str] = set()
        self.retry_moves: set[str] = set()
        self.carried: list[str] = []
        self.last_action: dict[str, Any] | None = None
        self.step = 0

    @staticmethod
    def _key(action: dict[str, Any]) -> str:
        return json.dumps(action, sort_keys=True)

    def _observe(self, obs: dict[str, Any]) -> None:
        result = obs.get("last_result")
        loc = obs["location"]["id"]
        if self.last_action is None or (result and result.get("tool") == "move" and result.get("ok")):
            self.visits[loc] = self.visits.get(loc, 0) + 1
        if not result or self.last_action is None:
            return
        if not result.get("ok"):
            if result.get("error") in PERMANENT:
                self.never.add(self._key(self.last_action))
            self.failed.add(self._key(self.last_action))
            target = self.last_action.get("arguments", {}).get("target_id")
            if target and self.last_action["tool"] in ("interact", "use"):
                self.blockers.add(target)
        if result.get("ok") and self.last_action["tool"] == "use":
            self.never.add(self._key(self.last_action))
        if not result.get("ok") and self.last_action["tool"] == "move":
            self.blocked_moves.add(self._key(self.last_action))
        events = {e["type"] for e in result.get("events", [])}
        big_change = result.get("ok") and (result.get("tool") == "use" or "unlocked" in events)
        if big_change:
            # The world changed: earlier failures may differ now.
            self.failed.clear()
            self.retry_moves = set(self.blocked_moves)
            if result.get("tool") == "use":
                # Dark screens and dead panels may have woken up.
                self.inspected = {oid for oid in self.inspected if oid in self.carried or oid in self.containers}
        if "clue_discovered" in events:
            self.pending_review = True
        for ev in result.get("events", []):
            if ev["type"] == "item_taken":
                self.carried.insert(0, ev["item_id"])
        data = result.get("data") or {}
        for clue in data.get("clues", []):
            self.clues[clue["id"]] = clue["text"]

    def _candidate_codes(self) -> list[str]:
        out: list[str] = []
        for text in self.clues.values():
            for group in re.findall(r"\d(?:[ -]?\d){2,7}", text):
                digits = re.sub(r"\D", "", group)
                for cand in (digits, digits[::-1]):
                    if cand not in out:
                        out.append(cand)
        return out

    def _ok(self, action: dict[str, Any]) -> bool:
        key = self._key(action)
        return key not in self.failed and key not in self.never

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        self._observe(observation)
        action = self._choose(observation)
        self.last_action = action
        self.step += 1
        return action

    def _choose(self, obs: dict[str, Any]) -> dict[str, Any]:
        if self.pending_review:
            self.pending_review = False
            return {"tool": "review_journal", "arguments": {}}
        for e in obs.get("exits", []):
            a = {"tool": "move", "arguments": {"destination_id": e["id"]}}
            key = self._key(a)
            if key in self.retry_moves:
                self.retry_moves.discard(key)
                self.blocked_moves.discard(key)
                return a
        objects = obs.get("objects", [])
        inventory = [i["id"] for i in obs.get("inventory", [])]
        self.containers |= {o["id"] for o in objects if "open" in o.get("state", []) or "closed" in o.get("state", [])}
        for o in objects:
            a = {"tool": "take", "arguments": {"item_id": o["id"]}}
            if o.get("portable") and self._ok(a):
                return a
        for oid in [o["id"] for o in objects] + inventory:
            if oid not in self.inspected:
                self.inspected.add(oid)
                return {"tool": "inspect", "arguments": {"target_id": oid}}
        for o in objects:
            state = o.get("state", [])
            ops = o.get("operations", [])
            if "open" in ops and "closed" in state:
                a = {"tool": "interact", "arguments": {"target_id": o["id"], "operation": "open"}}
                if self._ok(a):
                    return a
            if "enter_code" in ops and "locked" in state:
                for code in self._candidate_codes():
                    if (o["id"], code) not in self.tried_codes:
                        self.tried_codes.add((o["id"], code))
                        return {"tool": "interact", "arguments": {"target_id": o["id"], "operation": "enter_code", "value": code}}
            if "activate" in ops:
                a = {"tool": "interact", "arguments": {"target_id": o["id"], "operation": "activate"}}
                if self._ok(a):
                    return a
        exits = obs.get("exits", [])
        for e in exits:
            a = {"tool": "move", "arguments": {"destination_id": e["id"]}}
            if e["id"] not in self.visits and self._ok(a) and self._key(a) not in self.blocked_moves:
                return a
        items = sorted(inventory, key=lambda i: self.carried.index(i) if i in self.carried else 99)
        clue_text = " ".join(self.clues.values()).lower()
        targets = sorted(
            objects,
            key=lambda o: (o["id"] not in self.blockers, o["name"].lower() not in clue_text),
        )
        for o in targets:
            for item in items:
                a = {"tool": "use", "arguments": {"item_id": item, "target_id": o["id"]}}
                if self._ok(a):
                    return a
        moves = [{"tool": "move", "arguments": {"destination_id": e["id"]}} for e in exits]
        moves = [m for m in moves if self._ok(m)]
        if moves:
            moves.sort(key=lambda m: (self.visits.get(m["arguments"]["destination_id"], 0)))
            return moves[0]
        # Everything known has failed here: forget and wander.
        self.failed.clear()
        if exits:
            return {"tool": "move", "arguments": {"destination_id": exits[self.step % len(exits)]["id"]}}
        return {"tool": "review_journal", "arguments": {}}
