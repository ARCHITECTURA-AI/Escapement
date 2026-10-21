"""Application context and FastAPI factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from escapement_engine.version import ENGINE_VERSION
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .db import Database
from .errors import APIError, api_error_handler, validation_error_handler
from .services.rooms import ensure_practice
from .services.runs import RunService
from .signing import Signer
from .storage import FilesystemStore, ReplayStore

log = logging.getLogger("escapement.api")


@dataclass
class Context:
    settings: Settings
    db: Database
    store: ReplayStore
    signer: Signer
    runs: RunService = field(init=False)
    worker: Any = None

    def __post_init__(self) -> None:
        self.runs = RunService(self)


def build_context(settings: Settings | None = None) -> Context:
    settings = settings or get_settings()
    db = Database(settings)
    if not db.postgres:
        db.create_all_sqlite()
    if settings.replay_store == "s3":
        from .storage import S3Store

        store: ReplayStore = S3Store(settings.s3_bucket or "escapement", settings.s3_prefix, settings.s3_endpoint_url)
    else:
        store = FilesystemStore(Path(settings.data_dir) / "replays")
    signer = Signer(settings, db)
    signer.register()
    ctx = Context(settings=settings, db=db, store=store, signer=signer)
    with db.service_session() as s:
        ensure_practice(s)
    return ctx


def create_app(settings: Settings | None = None, context: Context | None = None, embedded_worker: bool | None = None) -> FastAPI:
    ctx = context or build_context(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        run_worker = embedded_worker if embedded_worker is not None else ctx.settings.mode == "local"
        if run_worker and ctx.worker is None:
            from .worker import start_embedded

            ctx.worker = start_embedded(ctx)
        yield
        if ctx.worker is not None:
            ctx.worker.stop()

    app = FastAPI(
        title="Escapement API",
        version=ENGINE_VERSION,
        description="A verifiable, replayable, bring-your-own-agent arena with signed records.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.ctx = ctx
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    @app.middleware("http")
    async def limits(request: Request, call_next):  # type: ignore[no-untyped-def]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > ctx.settings.payload_limit_bytes:
            return JSONResponse(
                {
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Requests are limited to {ctx.settings.payload_limit_bytes} bytes.",
                        "details": {},
                    }
                },
                status_code=413,
            )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    from .routers import account, admin, public, runs

    app.include_router(runs.router)
    app.include_router(public.router)
    app.include_router(account.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "engine_version": ENGINE_VERSION, "mode": ctx.settings.mode}

    return app
