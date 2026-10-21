"""The Escapement SDK.

    client = Client(api_key="esk_...")
    run = client.create_run("practice", agent={"name": "my-agent", "version": "0.1.0"})
    while not run.done:
        run.act("inspect", target_id="maintenance_panel")
    run.finish()

Every action carries expected_sequence, action_id and prev_hash. A network
failure is retried with the same action_id, which the server deduplicates,
so a retry never executes an action twice (section 20.4).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from .config import resolve
from .errors import EscapementError, RunFinished

USER_AGENT = "escapement-python/1.0.0"


class Client:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        client_kind: str | None = None,
    ) -> None:
        self.api_key, self.base_url = resolve(api_key, base_url)
        self.max_retries = max_retries
        headers = {"User-Agent": USER_AGENT}
        if client_kind:
            headers["X-Escapement-Client"] = client_kind
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers, transport=transport)

    # -- low level ---------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> Any:
        headers = {}
        bearer = token or self.api_key
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        attempt = 0
        while True:
            try:
                resp = self._http.request(method, path, json=json, params=params, headers=headers)
            except httpx.TransportError:
                attempt += 1
                if not retry or attempt > self.max_retries:
                    raise
                time.sleep(min(16.0, 0.5 * 2**attempt))
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                attempt += 1
                retry_after = float(resp.headers.get("Retry-After", "0") or 0)
                if retry and attempt <= self.max_retries and resp.status_code != 503:
                    time.sleep(max(retry_after, min(16.0, 0.5 * 2**attempt)))
                    continue
            if resp.status_code >= 400:
                raise self._error(resp)
            return resp.json()

    @staticmethod
    def _error(resp: httpx.Response) -> EscapementError:
        try:
            err = resp.json().get("error", {})
        except Exception:
            err = {}
        code = err.get("code", f"HTTP_{resp.status_code}")
        cls = RunFinished if code == "EPISODE_FINISHED" else EscapementError
        ra = resp.headers.get("Retry-After")
        return cls(resp.status_code, code, err.get("message", resp.text[:200]), err.get("details"), float(ra) if ra else None)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- runs ----------------------------------------------------------------

    def create_run(
        self,
        room: str = "practice",
        agent: dict[str, Any] | None = None,
        agent_version_id: str | None = None,
        replace_active: bool = False,
        **extra: Any,
    ) -> Run:
        """Start a run. `agent` declares name, version and, self-reported,
        model, framework and memory strategy."""
        body: dict[str, Any] = {"room": room, "replace_active": replace_active, **extra}
        if agent:
            body["agent"] = agent
        if agent_version_id:
            body["agent_version_id"] = agent_version_id
        data = self.request("POST", "/api/v1/runs", json=body)
        return Run(self, data)

    def resume_run(self, run_id: str, run_token: str) -> Run:
        """Reattach after a dropped connection with the same run token."""
        data = self.request("GET", f"/api/v1/runs/{run_id}/observation", token=run_token)
        data["run_token"] = run_token
        data["chain_hash"] = data["chain_hash"]
        return Run(self, data)

    def rooms(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/rooms")

    def season(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/seasons/current")

    def certificate(self, certificate_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/certificates/{certificate_id}/download")

    def replay(self, run_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/runs/{run_id}/replay")["replay"]

    def keys(self) -> dict[str, Any]:
        return self.request("GET", "/.well-known/escapement-keys.json")

    def meta(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/meta")


class Run:
    """A live run. Tool methods return the public result and update
    `observation`, `sequence`, `chain_hash` and `status`."""

    def __init__(self, client: Client, data: dict[str, Any]) -> None:
        self.client = client
        self.id: str = data["run_id"]
        self.token: str = data["run_token"]
        self.sequence: int = data.get("sequence", 0)
        self.chain_hash: str = data["chain_hash"]
        self.status: str = data.get("status", "in_progress")
        self.observation: dict[str, Any] = data.get("observation", {})
        self.room: dict[str, Any] = data.get("room", {})
        self.limits: dict[str, Any] = data.get("limits", {})
        self.watch_url: str | None = data.get("watch_url")
        self.certificate_id: str | None = data.get("certificate_id")
        self.last_result: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []

    @property
    def done(self) -> bool:
        return self.status != "in_progress"

    @property
    def escaped(self) -> bool:
        return self.status == "escaped"

    @property
    def certificate_url(self) -> str | None:
        if not self.certificate_id:
            return None
        return f"{self.client.base_url}/c/{self.certificate_id}"

    def act(self, tool: str, decision_summary: str | None = None, usage: dict[str, Any] | None = None, **arguments: Any) -> dict[str, Any]:
        """Submit one action. `usage` (tokens_in, tokens_out, cost_usd,
        model_decisions) and `decision_summary` are self-reported and
        labelled as such everywhere."""
        if self.done:
            raise RunFinished(409, "EPISODE_FINISHED", f"The run has ended ({self.status}).")
        body: dict[str, Any] = {
            "expected_sequence": self.sequence + 1,
            "action_id": str(uuid.uuid4()),
            "prev_hash": self.chain_hash,
            "tool": tool,
            "arguments": {k: v for k, v in arguments.items() if v is not None},
        }
        if decision_summary:
            body["decision_summary"] = decision_summary[:280]
        if usage:
            body["usage"] = usage
        return self._send(body)

    def send_raw(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send a tool call exactly as an agent produced it (tool and
        arguments), so schema errors are recorded by the server rather than
        rewritten client-side."""
        body = {"expected_sequence": self.sequence + 1, "action_id": str(uuid.uuid4()), "prev_hash": self.chain_hash}
        body.update({k: v for k, v in request.items() if k in ("tool", "arguments", "decision_summary", "usage", "memory")})
        return self._send(body)

    def _send(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self.client.request("POST", f"/api/v1/runs/{self.id}/actions", token=self.token, json=body)
        self.sequence = data["sequence"]
        self.chain_hash = data["chain_hash"]
        self.status = data["status"]
        self.observation = data["observation"]
        self.last_result = data["result"]
        self.certificate_id = data.get("certificate_id") or self.certificate_id
        self.history.append({"request": body, "result": data["result"]})
        return data["result"]

    # Tool helpers (section 10.1).

    def inspect(self, target_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("inspect", target_id=target_id, **kw)

    def take(self, item_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("take", item_id=item_id, **kw)

    def use(self, item_id: str, target_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("use", item_id=item_id, target_id=target_id, **kw)

    def interact(self, target_id: str, operation: str, value: str | None = None, **kw: Any) -> dict[str, Any]:
        return self.act("interact", target_id=target_id, operation=operation, value=value, **kw)

    def move(self, destination_id: str, **kw: Any) -> dict[str, Any]:
        return self.act("move", destination_id=destination_id, **kw)

    def review_journal(self, **kw: Any) -> dict[str, Any]:
        return self.act("review_journal", **kw)

    def refresh(self) -> dict[str, Any]:
        data = self.client.request("GET", f"/api/v1/runs/{self.id}/observation", token=self.token)
        self.sequence, self.chain_hash, self.status = data["sequence"], data["chain_hash"], data["status"]
        self.observation = data["observation"]
        self.certificate_id = data.get("certificate_id") or self.certificate_id
        return self.observation

    def finish(self, usage: dict[str, Any] | None = None) -> dict[str, Any]:
        """End the run (client_aborted if it is still going) and get the
        certificate id. Safe to call after the run has already ended."""
        data = self.client.request("POST", f"/api/v1/runs/{self.id}/finish", token=self.token, json={"usage": usage} if usage else {})
        self.status = data["status"]
        self.certificate_id = data.get("certificate_id")
        return data

    def certificate(self) -> dict[str, Any] | None:
        return self.client.certificate(self.certificate_id) if self.certificate_id else None

    def replay(self) -> dict[str, Any]:
        return self.client.request("GET", f"/api/v1/runs/{self.id}/replay", token=self.token)["replay"]
