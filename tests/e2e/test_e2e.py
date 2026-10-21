"""End-to-end tests against a running stack (PRD 24.3):

* a human completes the room in the browser;
* the starter agent completes Practice;
* an agent fails within budget;
* replay and compare work;
* public mode rejects administrative calls.

Set E2E_BASE_URL (the web origin, which proxies the API) to run them.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

BASE = os.environ.get("E2E_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set E2E_BASE_URL to run end-to-end tests")
WEB = {"X-Escapement-Client": "web"}


def practice_solution():
    from escapement_engine.generation import build_practice

    return build_practice().solution


def command_for(action):
    a = action["arguments"]
    tool = action["tool"]
    if tool == "interact":
        if a["operation"] == "enter_code":
            return f"code {a['target_id']} {a['value']}"
        return f"{a['operation']} {a['target_id']}"
    if tool == "use":
        return f"use {a['item_id']} on {a['target_id']}"
    if tool == "move":
        return f"move {a['destination_id']}"
    if tool == "take":
        return f"take {a['item_id']}"
    return f"inspect {a['target_id']}"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        yield b
        b.close()


def api_key(handle: str) -> tuple[httpx.Client, str]:
    web = httpx.Client(base_url=BASE, timeout=30)
    web.post("/api/v1/auth/local", json={"handle": handle}).raise_for_status()
    key = web.post("/api/v1/me/keys", json={"name": "e2e"}, headers=WEB).json()["key"]
    return web, key


def test_human_completes_the_room(browser):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/play", wait_until="networkidle")
    page.get_by_role("button", name="Start Practice").click()
    page.wait_for_selector("#cmd")
    for action in practice_solution():
        page.fill("#cmd", command_for(action))
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('#cmd').value === ''")
        page.wait_for_timeout(120)
    page.get_by_text("You escaped.").wait_for(timeout=10_000)
    page.get_by_role("link", name="Watch the replay").click()
    page.wait_for_url("**/runs/**")
    page.get_by_text("Run facts").wait_for()
    assert not errors, errors


class FakeModel(BaseHTTPRequestHandler):
    """An OpenAI-compatible stand-in that replays the Practice solution as
    tool calls, so the real starter agent runs end to end without a key."""

    solution: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        step = sum(1 for m in body["messages"] if m["role"] == "tool")
        action = self.solution[min(step, len(self.solution) - 1)]
        reply = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"step {step + 1}",
                        "tool_calls": [
                            {
                                "id": f"c{step}",
                                "type": "function",
                                "function": {"name": action["tool"], "arguments": json.dumps(action["arguments"])},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 800, "completion_tokens": 30},
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_starter_agent_completes_practice():
    _web, key = api_key("e2e-starter")
    FakeModel.solution = practice_solution()
    server = HTTPServer(("127.0.0.1", 0), FakeModel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(
        os.environ,
        ESCAPEMENT_API_KEY=key,
        ESCAPEMENT_BASE_URL=BASE,
        MODEL_API_KEY="fake",
        MODEL_BASE_URL=f"http://127.0.0.1:{server.server_port}",
        MODEL="fake-model",
    )
    out = subprocess.run([sys.executable, "-m", "escapement.examples.starter_agent"], env=env, capture_output=True, text=True, timeout=180)
    server.shutdown()
    assert out.returncode == 0, out.stderr
    assert "Outcome: escaped" in out.stdout
    cert_url = next(line for line in out.stdout.splitlines() if line.startswith("Certificate:")).split()[-1]
    cert_id = cert_url.rsplit("/", 1)[-1]
    cert = httpx.get(f"{BASE}/api/v1/certificates/{cert_id}").json()["certificate"]
    assert cert["outcome"] == "escaped" and cert["agent"]["name"] == "starter-agent"
    assert cert["usage"]["tokens_in"] == 800 * len(FakeModel.solution)


def test_agent_fails_within_budget_then_replay_and_compare(browser):
    from escapement import Client
    from escapement_engine.agents import RandomAgent

    _web, key = api_key("e2e-random")
    client = Client(api_key=key, base_url=BASE)
    run = client.create_run("practice", agent={"name": "random", "version": "1"}, replace_active=True)
    agent = RandomAgent(seed=5)
    while not run.done:
        run.send_raw(agent.act(run.observation))
    assert run.status in ("action_budget_exhausted", "malformed_limit_reached")
    assert run.observation["actions_used"] <= 60
    run.finish()
    assert run.certificate_id

    other = client.create_run("practice", agent={"name": "short", "version": "1"}, replace_active=True)
    other.inspect("maintenance_panel")
    other.finish()

    page = browser.new_page()
    page.goto(f"{BASE}/runs/{run.id}", wait_until="networkidle")
    page.get_by_text("Run facts").wait_for()
    page.get_by_role("button", name="Go to start").click()
    page.get_by_role("button", name="Step forward").click()
    page.get_by_text("Observation after step 1").wait_for()
    page.goto(f"{BASE}/compare?runs={run.id},{other.id}", wait_until="networkidle")
    page.get_by_text("Paired comparison").wait_for()
    page.get_by_role("button", name="Go to end").click()
    page.get_by_text("Finished at step 2").wait_for()
    page.goto(f"{BASE}/c/{run.certificate_id}", wait_until="networkidle")
    page.get_by_role("button", name="Verify now").click()
    page.get_by_text("Verified at the full re-simulation level").wait_for()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_public_mode_rejects_administrative_calls():
    port = _free_port()
    tmp = tempfile.mkdtemp()
    env = dict(
        os.environ,
        ESCAPEMENT_MODE="public",
        ESCAPEMENT_DATABASE_URL=f"sqlite:///{tmp}/public.db",
        ESCAPEMENT_DATA_DIR=tmp,
        ESCAPEMENT_SIGNING_KEY="nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A=",
    )
    proc = subprocess.Popen(
        ["escapement-api", "serve", "--port", str(port), "--no-worker"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(f"{url}/api/health").status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.5)
        for method, path in [
            ("GET", "/api/v1/admin/overview"),
            ("POST", "/api/v1/admin/generate"),
            ("POST", "/api/v1/admin/seasons"),
            ("POST", "/api/v1/admin/kill-switch"),
            ("POST", "/api/v1/admin/certificates/x/revoke"),
            ("GET", "/api/v1/admin/jobs"),
        ]:
            r = httpx.request(method, url + path, json={})
            assert r.status_code == 403 and r.json()["error"]["code"] == "ADMIN_DISABLED", path
        assert httpx.post(f"{url}/api/v1/auth/local", json={}).status_code == 403
    finally:
        proc.terminate()
        proc.wait(10)
