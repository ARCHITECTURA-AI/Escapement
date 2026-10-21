"""API test fixtures. Every test runs on SQLite; set
ESCAPEMENT_TEST_DATABASE_URL to also run the suite on Postgres with
row-level security."""

from __future__ import annotations

import os
import uuid
import warnings
from typing import Any

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from escapement_api.app import create_app  # noqa: E402
from escapement_api.config import Settings  # noqa: E402
from escapement_api.db import normalize_url  # noqa: E402
from escapement_engine.generation import build_practice  # noqa: E402

PG_URL = os.environ.get("ESCAPEMENT_TEST_DATABASE_URL")
BACKENDS = ["sqlite"] + (["postgres"] if PG_URL else [])
WEB = {"x-escapement-client": "web"}
_migrated = False


def _reset_postgres(url: str) -> None:
    global _migrated
    from escapement_api.migrate import upgrade

    if not _migrated:
        engine = create_engine(normalize_url(url))
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
        upgrade(url)
        _migrated = True
        return
    engine = create_engine(normalize_url(url))
    with engine.begin() as conn:
        tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")).scalars().all()
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
    engine.dispose()


@pytest.fixture(params=BACKENDS)
def settings(request, tmp_path) -> Settings:
    if request.param == "postgres":
        _reset_postgres(PG_URL)  # type: ignore[arg-type]
        url = PG_URL
    else:
        url = f"sqlite:///{tmp_path}/test.db"
    return Settings(database_url=url, data_dir=tmp_path / "data", mode="local", seed_secret="test-secret")


@pytest.fixture
def app(settings):
    application = create_app(settings, embedded_worker=False)
    yield application
    application.state.ctx.db.dispose()


@pytest.fixture
def ctx(app):
    return app.state.ctx


@pytest.fixture
def anon(app) -> TestClient:
    return TestClient(app)


def login(app, handle: str = "alice") -> TestClient:
    client = TestClient(app)
    r = client.post("/api/v1/auth/local", json={"handle": handle})
    assert r.status_code == 200, r.text
    return client


def api_key(app, handle: str = "alice") -> tuple[TestClient, str]:
    web = login(app, handle)
    r = web.post("/api/v1/me/keys", json={"name": "test"}, headers=WEB)
    assert r.status_code == 201, r.text
    return web, r.json()["key"]


class Runner:
    """Plays a run through the HTTP protocol, tracking sequence and hash."""

    def __init__(self, client: TestClient, created: dict[str, Any]) -> None:
        self.client = client
        self.run_id = created["run_id"]
        self.token = created["run_token"]
        self.hash = created["chain_hash"]
        self.seq = 0
        self.last: dict[str, Any] = created

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def act(self, action: dict[str, Any], **extra: Any) -> Any:
        body = {"expected_sequence": self.seq + 1, "action_id": str(uuid.uuid4()), "prev_hash": self.hash, **action, **extra}
        r = self.client.post(f"/api/v1/runs/{self.run_id}/actions", json=body, headers=self.auth)
        if r.status_code == 200:
            self.last = r.json()
            self.seq = self.last["sequence"]
            self.hash = self.last["chain_hash"]
        return r

    def finish(self) -> dict[str, Any]:
        r = self.client.post(f"/api/v1/runs/{self.run_id}/finish", json={}, headers=self.auth)
        assert r.status_code == 200, r.text
        return r.json()


def start(client: TestClient, key: str | None = None, room: str = "practice", headers: dict[str, str] | None = None, **body: Any) -> Runner:
    hdrs = dict(headers or {})
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    payload = {"room": room, **body}
    if key and "agent" not in body:
        payload["agent"] = {"name": "test-agent", "version": "1.0", "model": "gpt-test", "framework": "none", "memory": "none"}
    r = client.post("/api/v1/runs", json=payload, headers=hdrs)
    assert r.status_code == 201, r.text
    return Runner(client, r.json())


@pytest.fixture(scope="session")
def solution() -> list[dict[str, Any]]:
    return build_practice().solution
