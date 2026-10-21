"""Tool definitions in the shapes common agent frameworks expect."""

from __future__ import annotations

from typing import Any

from escapement_engine.schemas.actions import tool_schemas

SYSTEM_PROMPT = (
    "You are an agent in an Escapement room: a puzzle world whose rules a server enforces. "
    "Act only through the tools. Saying you did something changes nothing; only valid actions do. "
    "Every action costs one unit of a fixed budget, and so does a failed one. Read results carefully, "
    "keep track of clues (ids like clue_07) and use review_journal to reread them. Codes come from "
    "combining discovered facts; wrong codes are penalised after the third try."
)


def openai_tools() -> list[dict[str, Any]]:
    return [{"type": "function", "function": t} for t in tool_schemas()]


def anthropic_tools() -> list[dict[str, Any]]:
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tool_schemas()]


def describe_observation(obs: dict[str, Any]) -> str:
    """A compact text rendering, handy for prompts and terminals."""
    lines = [f"Location: {obs['location']['name']} ({obs['location']['id']}). {obs['location']['description']}"]
    if obs.get("objects"):
        parts = []
        for o in obs["objects"]:
            bits = [", ".join(o.get("state", []))] if o.get("state") else []
            if o.get("in"):
                bits.append(f"in {o['in']}")
            if o.get("portable"):
                bits.append("portable")
            if o.get("operations"):
                bits.append("ops: " + "/".join(o["operations"]))
            parts.append(f"{o['name']} [{o['id']}]" + (f" ({'; '.join(bits)})" if bits else ""))
        lines.append("You see: " + "; ".join(parts))
    lines.append("Exits: " + (", ".join(f"{e['name']} [{e['id']}]" for e in obs.get("exits", [])) or "none"))
    lines.append("Carrying: " + (", ".join(f"{i['name']} [{i['id']}]" for i in obs.get("inventory", [])) or "nothing"))
    lines.append(
        f"Journal entries: {obs.get('journal_entries', 0)}. Actions: {obs['actions_used']}/{obs['action_budget']} used. Status: {obs['status']}."
    )
    last = obs.get("last_result")
    if last:
        tag = "OK" if last.get("ok") else last.get("error")
        lines.append(f"Last result ({tag}): {last.get('message')}")
    return "\n".join(lines)
