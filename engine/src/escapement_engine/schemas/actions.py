"""The six tools and their argument schemas (section 10.1).

Validation is hand-written instead of delegated to pydantic so that the
messages for malformed requests are stable across library versions: those
messages are part of the public result, and the public result is part of the
hash chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
CODE_RE = re.compile(r"^[0-9]{1,12}$")

TOOL_ARGS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # tool: (required, optional)
    "inspect": (("target_id",), ()),
    "take": (("item_id",), ()),
    "use": (("item_id", "target_id"), ()),
    "interact": (("target_id", "operation"), ("value",)),
    "move": (("destination_id",), ()),
    "review_journal": ((), ()),
}

TOOLS: tuple[str, ...] = tuple(TOOL_ARGS)
OPERATIONS = ("open", "close", "activate", "enter_code")

TOOL_DESCRIPTIONS: dict[str, str] = {
    "inspect": "Examine a visible object or an item you carry.",
    "take": "Collect a reachable portable item.",
    "use": "Apply an item from your inventory to an object.",
    "interact": "Operate an object: open, close, activate or enter_code (enter_code needs a digit string value).",
    "move": "Go through an accessible connection to an adjacent location.",
    "review_journal": "Return the notes and clues you have discovered so far.",
}


@dataclass(frozen=True)
class Action:
    tool: str
    arguments: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "arguments": dict(self.arguments)}


@dataclass(frozen=True)
class Malformed:
    message: str
    tool: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "malformed": True}


def parse_action(request: Any) -> Action | Malformed:
    """Validate a request of the form {"tool": str, "arguments": {...}}.

    A schema-invalid request is never silently rewritten into an intended
    action (section 11.2).
    """
    if not isinstance(request, dict):
        return Malformed("Request must be an object with 'tool' and 'arguments'.")
    extra = set(request) - {"tool", "arguments"}
    if extra:
        return Malformed(f"Unexpected field '{sorted(extra)[0]}'.")
    tool = request.get("tool")
    if not isinstance(tool, str) or tool not in TOOL_ARGS:
        shown = tool if isinstance(tool, str) and len(tool) <= 40 else None
        return Malformed(
            "Unknown tool. Valid tools: " + ", ".join(TOOLS) + ".",
            tool=shown if shown and ID_RE.match(shown) else None,
        )
    args = request.get("arguments", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return Malformed("'arguments' must be an object.", tool=tool)
    required, optional = TOOL_ARGS[tool]
    unknown = set(args) - set(required) - set(optional)
    if unknown:
        return Malformed(f"Unexpected argument '{sorted(unknown)[0]}' for {tool}.", tool=tool)
    for name in required:
        if name not in args:
            return Malformed(f"Missing argument '{name}' for {tool}.", tool=tool)
    clean: dict[str, str] = {}
    for name in required + optional:
        if name not in args or (name == "value" and args[name] is None):
            continue
        value = args[name]
        if not isinstance(value, str):
            return Malformed(f"Argument '{name}' must be a string.", tool=tool)
        if name == "operation":
            if value not in OPERATIONS:
                return Malformed(
                    "Unsupported operation. Valid operations: " + ", ".join(OPERATIONS) + ".",
                    tool=tool,
                )
        elif name == "value":
            if not CODE_RE.match(value):
                return Malformed("Argument 'value' must be a string of 1 to 12 digits.", tool=tool)
        elif not ID_RE.match(value):
            return Malformed(
                f"Argument '{name}' must be an id of lowercase letters, digits and underscores.",
                tool=tool,
            )
        clean[name] = value
    if tool == "interact":
        if clean["operation"] == "enter_code" and "value" not in clean:
            return Malformed("Operation enter_code needs a 'value' of digits.", tool=tool)
        if clean["operation"] != "enter_code" and "value" in clean:
            return Malformed("Only enter_code takes a 'value'.", tool=tool)
    return Action(tool=tool, arguments=clean)


def tool_schemas() -> list[dict[str, Any]]:
    """JSON-schema descriptions of the tools, shared by SDK, MCP and agents."""
    props = {
        "target_id": {"type": "string", "description": "Id of a visible object or carried item."},
        "item_id": {"type": "string", "description": "Id of an item."},
        "destination_id": {"type": "string", "description": "Id of an adjacent location."},
        "operation": {"type": "string", "enum": list(OPERATIONS)},
        "value": {"type": "string", "description": "Digits, only for enter_code."},
    }
    out = []
    for tool, (required, optional) in TOOL_ARGS.items():
        out.append(
            {
                "name": tool,
                "description": TOOL_DESCRIPTIONS[tool],
                "parameters": {
                    "type": "object",
                    "properties": {n: props[n] for n in required + optional},
                    "required": list(required),
                    "additionalProperties": False,
                },
            }
        )
    return out
