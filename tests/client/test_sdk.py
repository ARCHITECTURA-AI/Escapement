"""SDK, CLI and MCP against the real application (in-process)."""

from __future__ import annotations

import json

import httpx
import pytest
from escapement import Client, LocalRun
from escapement.cli.main import main as cli
from escapement_engine.generation import build_practice
from fastapi.testclient import TestClient

from ..api.conftest import api_key, app, settings


class AppTransport(httpx.BaseTransport):
    """Routes SDK requests into the in-process app."""

    def __init__(self, app) -> None:
        self.tc = TestClient(app)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        r = self.tc.request(request.method, url, content=request.read(), headers=headers)
        return httpx.Response(r.status_code, headers=r.headers, content=r.content, request=request)


class FlakyTransport(httpx.BaseTransport):
    """Delivers the first action request to the server, then drops the
    response, as a network failure would."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner
        self.dropped = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.inner.handle_request(request)
        if request.url.path.endswith("/actions") and self.dropped == 0:
            self.dropped += 1
            raise httpx.ReadError("connection reset", request=request)
        return response


def sdk_client(app, key: str, flaky: bool = False) -> Client:
    transport: httpx.BaseTransport = AppTransport(app)
    if flaky:
        transport = FlakyTransport(transport)
    client = Client(api_key=key, base_url="http://testserver", transport=transport)
    return client


def test_sdk_practice_escape_and_certificate(app, tmp_path):
    web, key = api_key(app)
    client = sdk_client(app, key)
    run = client.create_run("practice", agent={"name": "sdk-agent", "version": "1.0", "model": "test-model"})
    for a in build_practice().solution:
        run.act(a["tool"], **a["arguments"])
    assert run.escaped and run.certificate_id
    cert = run.certificate()
    replay = run.replay()
    keys = client.keys()
    manifest = client.request("GET", "/api/v1/rooms/practice/manifest")
    for name, data in (("cert", cert), ("replay", replay), ("keys", keys), ("manifest", manifest)):
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    cli(
        [
            "verify",
            str(tmp_path / "cert.json"),
            "--replay",
            str(tmp_path / "replay.json"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--keys",
            str(tmp_path / "keys.json"),
            "--offline",
        ]
    )
    cert["outcome"] = "escaped!"
    (tmp_path / "bad.json").write_text(json.dumps(cert))
    with pytest.raises(SystemExit):
        cli(["verify", str(tmp_path / "bad.json"), "--keys", str(tmp_path / "keys.json"), "--offline"])
    cli(["replay", str(tmp_path / "replay.json"), "--manifest", str(tmp_path / "manifest.json"), "-q"])


def test_sdk_retry_never_double_charges(app):
    web, key = api_key(app)
    client = sdk_client(app, key, flaky=True)
    run = client.create_run("practice", agent={"name": "flaky", "version": "1"})
    result = run.review_journal()
    assert result["ok"]
    assert client._http._transport.dropped == 1
    assert run.sequence == 1 and run.observation["actions_used"] == 1
    run.review_journal()
    assert run.sequence == 2 and run.observation["actions_used"] == 2


def test_sdk_resume_after_disconnect(app):
    web, key = api_key(app)
    client = sdk_client(app, key)
    run = client.create_run("practice", agent={"name": "resumer", "version": "1"})
    run.inspect("maintenance_panel")
    again = client.resume_run(run.id, run.token)
    assert again.sequence == 1 and again.chain_hash == run.chain_hash
    again.review_journal()
    assert again.sequence == 2


def test_send_raw_records_malformed_calls(app):
    web, key = api_key(app)
    client = sdk_client(app, key)
    run = client.create_run("practice", agent={"name": "raw", "version": "1"})
    result = run.send_raw({"tool": "inspect", "arguments": "not-an-object"})
    assert result["malformed"] and result["cost"] == 0


def test_local_run_matches_interface():
    run = LocalRun("practice")
    for a in build_practice().solution:
        run.act(a["tool"], **a["arguments"])
    assert run.escaped
    from escapement_engine.replay import verify_chain

    assert verify_chain(run.replay()).ok


def test_cli_play_parser():
    from escapement.cli.main import parse_command

    assert parse_command("use screwdriver on maintenance_panel") == {
        "tool": "use",
        "arguments": {"item_id": "screwdriver", "target_id": "maintenance_panel"},
    }
    assert parse_command("code equipment_locker 274")["arguments"]["value"] == "274"
    assert "error" in parse_command("dance")


def test_mcp_tools_listed():
    import asyncio

    from escapement.mcp.server import server

    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"start_run", "inspect", "take", "use", "interact", "move", "review_journal", "finish_run"} <= names
