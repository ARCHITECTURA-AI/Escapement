"""`escapement-api`: serve, migrate and operate the arena.

In public mode the HTTP admin endpoints are disabled; operators run these
commands with database access instead."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def _ctx():  # type: ignore[no-untyped-def]
    from .app import build_context

    return build_context()


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .app import create_app

    app = create_app(embedded_worker=not args.no_worker)
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=True, forwarded_allow_ips="*")


def cmd_migrate(args: argparse.Namespace) -> None:
    from .migrate import upgrade

    upgrade()
    print("migrations applied")


def cmd_worker(args: argparse.Namespace) -> None:
    from .worker import Worker

    ctx = _ctx()
    print("worker started; kinds:", ", ".join(Worker(ctx).kinds))
    Worker(ctx).run_forever()


def cmd_create_season(args: argparse.Namespace) -> None:
    from .services import seasons as season_service

    ctx = _ctx()
    starts = datetime.fromisoformat(args.starts_at) if args.starts_at else datetime.now(timezone.utc)
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=timezone.utc)
    with ctx.db.owner_session() as s:
        season = season_service.create_season(
            s, ctx.settings, args.id, args.name or f"Season {args.id.upper()}", starts,
            weeks=args.weeks, instances=args.instances, progress=lambda t: print(t, flush=True),
        )
        if starts <= datetime.now(timezone.utc):
            season.status = "open"
    if not args.no_baselines:
        from .services import jobs

        with ctx.db.owner_session() as s:
            jobs.enqueue(s, "reference_baselines", {"season_id": args.id}, priority=50)
    print(f"season {args.id} created")


def cmd_close_season(args: argparse.Namespace) -> None:
    from .services import jobs

    ctx = _ctx()
    with ctx.db.owner_session() as s:
        job = jobs.enqueue(s, "close_season", {"season_id": args.id}, priority=5)
    from .worker import Worker

    Worker(ctx, kinds=["close_season"]).run_once()
    print(f"season {args.id} closed (job {job.id})")


def cmd_revoke(args: argparse.Namespace) -> None:
    from .models import Certificate
    from .timeutil import utcnow

    ctx = _ctx()
    with ctx.db.owner_session() as s:
        cert = s.get(Certificate, args.certificate_id)
        if cert is None:
            sys.exit("unknown certificate")
        cert.revoked_at = utcnow()
        cert.revocation_reason = args.reason
    print(f"revoked {args.certificate_id}")


def cmd_kill_switch(args: argparse.Namespace) -> None:
    from .models import Setting

    ctx = _ctx()
    on = args.state == "on"
    with ctx.db.owner_session() as s:
        row = s.get(Setting, "kill_switch")
        if row is None:
            s.add(Setting(key="kill_switch", value=on))
        else:
            row.value = on
    cancelled = ctx.runs.cancel_live() if on else 0
    print(json.dumps({"kill_switch": on, "cancelled_runs": cancelled}))


def cmd_reference_key(args: argparse.Namespace) -> None:
    """Create the first-party reference user and an API key for the
    reference worker, which plays through the public API."""
    from sqlalchemy import select

    from .models import ApiKey, User, UserPrivate
    from .security import new_api_key

    ctx = _ctx()
    with ctx.db.owner_session() as s:
        user = s.execute(select(User).where(User.handle == "escapement-reference")).scalar_one_or_none()
        if user is None:
            user = User(handle="escapement-reference", display_name="Escapement reference agents", is_system=True, profile_public=True)
            s.add(user)
            s.flush()
            s.add(UserPrivate(user_id=user.id))
        key, prefix, digest = new_api_key()
        s.add(ApiKey(user_id=user.id, name=args.name, prefix=prefix, key_hash=digest))
    print(key)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="escapement-api", description="Run and operate the Escapement arena.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve", help="Run the API server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-worker", action="store_true", help="Do not run the embedded jobs worker")
    p.set_defaults(func=cmd_serve)
    sub.add_parser("migrate", help="Apply database migrations (Postgres)").set_defaults(func=cmd_migrate)
    sub.add_parser("worker", help="Run the jobs worker").set_defaults(func=cmd_worker)
    ops = sub.add_parser("ops", help="Operator commands").add_subparsers(dest="op", required=True)
    p = ops.add_parser("create-season")
    p.add_argument("id")
    p.add_argument("--name")
    p.add_argument("--starts-at")
    p.add_argument("--weeks", type=int)
    p.add_argument("--instances", type=int)
    p.add_argument("--no-baselines", action="store_true")
    p.set_defaults(func=cmd_create_season)
    p = ops.add_parser("close-season")
    p.add_argument("id")
    p.set_defaults(func=cmd_close_season)
    p = ops.add_parser("revoke")
    p.add_argument("certificate_id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_revoke)
    p = ops.add_parser("kill-switch")
    p.add_argument("state", choices=["on", "off"])
    p.set_defaults(func=cmd_kill_switch)
    p = ops.add_parser("reference-key")
    p.add_argument("--name", default="reference-worker")
    p.set_defaults(func=cmd_reference_key)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
