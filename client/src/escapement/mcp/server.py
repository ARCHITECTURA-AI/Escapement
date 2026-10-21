"""Escapement MCP server (FR-08): the room tools for any MCP client.

    {"mcpServers": {"escapement": {"command": "escapement-mcp",
                                   "env": {"ESCAPEMENT_API_KEY": "esk_..."}}}}

The server holds one live run at a time and plays through the public API,
so runs started from an MCP client are recorded, hash-chained and certified
exactly like SDK runs. Each tool returns the public result and the new
observation as text.
"""

from __future__ import annotations

import json
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

from ..sdk.client import Client, Run
from ..sdk.errors import EscapementError
from ..sdk.tools import SYSTEM_PROMPT, describe_observation

INSTRUCTIONS = (
    SYSTEM_PROMPT
    + " Start with start_run (room 'practice' is free and unranked). Then call one room tool per decision. "
    "Call finish_run when you are done or stuck; the run ends by itself when you escape or the budget runs out."
)


class Session:
    def __init__(self) -> None:
        self.client: Client | None = None
        self.run: Run | None = None

    def get_client(self) -> Client:
        if self.client is None:
            self.client = Client(client_kind="mcp")
        return self.client

    def require_run(self) -> Run:
        if self.run is None:
            raise ValueError("No run yet. Call start_run first.")
        return self.run


state = Session()
server = _Server("escapement", instructions=INSTRUCTIONS)


def _render(result: dict[str, Any] | None, run: Run) -> str:
    lines = []
    if result is not None:
        tag = "OK" if result.get("ok") else result.get("error")
        lines.append(f"Result ({tag}, cost {result.get('cost', 0)}): {result.get('message')}")
        if result.get("data", {}).get("clues"):
            lines += [f"  {c['id']}: {c['text']}" for c in result["data"]["clues"]]
    obs = dict(run.observation)
    obs["last_result"] = None
    lines.append(describe_observation(obs))
    if run.done:
        lines.append(f"The run has ended: {run.status}." + (f" Certificate: {run.certificate_url}" if run.certificate_url else ""))
    return "\n".join(lines)


def _act(tool: str, decision_summary: str | None, **arguments: Any) -> str:
    run = state.require_run()
    try:
        result = run.act(tool, decision_summary=decision_summary, **arguments)
    except EscapementError as exc:
        return f"Error {exc.code}: {exc.message}"
    return _render(result, run)


@server.tool()
def start_run(
    room: str = "practice",
    agent_name: str = "mcp-agent",
    agent_version: str = "0.1.0",
    model: str | None = None,
    framework: str | None = "MCP client",
    memory: str | None = None,
) -> str:
    """Start a run in a room ('practice', 'daily' or a ranked room id). Model,
    framework and memory are self-reported and labelled as such."""
    try:
        state.run = state.get_client().create_run(
            room,
            agent={"name": agent_name, "version": agent_version, "model": model, "framework": framework, "memory": memory},
            replace_active=True,
        )
    except EscapementError as exc:
        return f"Could not start: {exc.code}: {exc.message}"
    run = state.run
    return f"Run {run.id} started in {run.room.get('title')}. Watch: {run.watch_url}\n{run.room.get('intro', '')}\n\n" + _render(None, run)


@server.tool()
def observe() -> str:
    """Show the current observation without spending an action."""
    run = state.require_run()
    run.refresh()
    return _render(None, run)


@server.tool()
def inspect(target_id: str, decision_summary: str | None = None) -> str:
    """Examine a visible object or an item you carry. Costs one action."""
    return _act("inspect", decision_summary, target_id=target_id)


@server.tool()
def take(item_id: str, decision_summary: str | None = None) -> str:
    """Collect a reachable portable item. Costs one action."""
    return _act("take", decision_summary, item_id=item_id)


@server.tool()
def use(item_id: str, target_id: str, decision_summary: str | None = None) -> str:
    """Apply an item from your inventory to an object. Costs one action."""
    return _act("use", decision_summary, item_id=item_id, target_id=target_id)


@server.tool()
def interact(target_id: str, operation: str, value: str | None = None, decision_summary: str | None = None) -> str:
    """Operate an object: open, close, activate or enter_code (value = digits). Costs one action;
    after three wrong codes at one lock each further wrong code costs two extra."""
    return _act("interact", decision_summary, target_id=target_id, operation=operation, value=value)


@server.tool()
def move(destination_id: str, decision_summary: str | None = None) -> str:
    """Go through an accessible connection to an adjacent location. Costs one action."""
    return _act("move", decision_summary, destination_id=destination_id)


@server.tool()
def review_journal(decision_summary: str | None = None) -> str:
    """Return the notes and clues discovered so far. Costs one action."""
    return _act("review_journal", decision_summary)


@server.tool()
def finish_run() -> str:
    """End the run now (if it has not ended) and get its certificate link."""
    run = state.require_run()
    try:
        data = run.finish()
    except EscapementError as exc:
        return f"Error {exc.code}: {exc.message}"
    return f"Run {run.id} ended: {data['status']}." + (f" Certificate: {run.certificate_url}" if run.certificate_url else "")


@server.tool()
def get_certificate() -> str:
    """Return the signed certificate of the current run as JSON."""
    run = state.require_run()
    cert = run.certificate()
    return json.dumps(cert, indent=1) if cert else "No certificate yet: finish the run first."


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
