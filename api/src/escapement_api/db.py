"""Database access with three pools.

* owner:   migrations, the worker and operator commands.
* service: the gateway's trusted services (auth lookups, the run service,
           certificate signing). It can read sealed manifests.
* api:     everything that serves data to users. On Postgres it runs as the
           `escapement_api` role, which has no privileges on sealed
           manifests or private run state, and every user-owned table
           applies row-level security keyed on `app.user_id`.

On SQLite (zero-setup local mode and fast tests) all three share one engine
and the service layer's own checks apply; RLS is a Postgres feature.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings

API_ROLE = "escapement_api"
SERVICE_ROLE = "escapement_service"


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _make_engine(url: str, role: str | None = None, pool_size: int = 10) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    engine = create_engine(url, pool_size=pool_size, max_overflow=20, pool_pre_ping=True)
    if role:

        @event.listens_for(engine, "connect")
        def _set_role(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute(f"SET ROLE {role}")
            cur.close()
            dbapi_conn.commit()

    return engine


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.postgres = settings.is_postgres()
        self.owner = _make_engine(settings.database_url, pool_size=5)
        if self.postgres:
            self.api = (
                _make_engine(settings.database_url_api)
                if settings.database_url_api
                else _make_engine(settings.database_url, role=API_ROLE)
            )
            self.service = (
                _make_engine(settings.database_url_service)
                if settings.database_url_service
                else _make_engine(settings.database_url, role=SERVICE_ROLE)
            )
        else:
            self.api = self.service = self.owner
        self._owner = sessionmaker(self.owner, expire_on_commit=False)
        self._api = sessionmaker(self.api, expire_on_commit=False)
        self._service = sessionmaker(self.service, expire_on_commit=False)

    def _set_user(self, session: Session, user_id: str | None) -> None:
        if self.postgres:
            session.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": user_id or ""})

    @contextmanager
    def api_session(self, user_id: str | None = None) -> Iterator[Session]:
        with self._api() as session:
            with session.begin():
                self._set_user(session, user_id)
                yield session

    @contextmanager
    def service_session(self) -> Iterator[Session]:
        with self._service() as session:
            with session.begin():
                yield session

    @contextmanager
    def owner_session(self) -> Iterator[Session]:
        with self._owner() as session:
            with session.begin():
                yield session

    def create_all_sqlite(self) -> None:
        """SQLite has no migrations-with-RLS path; create tables directly."""
        from .models import Base

        Base.metadata.create_all(self.owner)

    def dispose(self) -> None:
        for engine in {self.owner, self.api, self.service}:
            engine.dispose()
