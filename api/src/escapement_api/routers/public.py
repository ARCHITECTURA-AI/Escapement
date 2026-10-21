from __future__ import annotations

from datetime import date
from typing import Any

from escapement_engine.certificate import DOES_NOT_PROVE, PROVES
from escapement_engine.rooms.emergency_lockdown import TIERS
from escapement_engine.schemas.actions import tool_schemas
from escapement_engine.schemas.endings import ENDING_LABELS, ENDINGS
from escapement_engine.schemas.manifest import FAILURE_CODES
from escapement_engine.version import ENGINE_VERSION, PROTOCOL_VERSION
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from ..deps import ctx, principal
from ..errors import APIError, not_found
from ..models import Certificate, DailyRoom, PublishedManifest, RoomInstance, Run, Season, User
from ..services import daily as daily_service
from ..services.certs import certificate_public, server_verify
from ..services.results import leaderboard
from ..services.rooms import room_public, season_status
from ..services.runs import build_run_replay
from ..services.seasons import season_public
from ..timeutil import iso, utc_today, utcnow

router = APIRouter(tags=["public"])


@router.get("/api/v1/meta")
def meta(request: Request) -> dict[str, Any]:
    st = ctx(request).settings
    return {
        "name": "Escapement",
        "mode": st.mode,
        "engine_version": ENGINE_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "github_login": bool(st.github_client_id),
        "local_login": st.mode == "local",
        "limits": {
            "idle_timeout_s": st.idle_timeout_s,
            "wall_clock_s": st.wall_clock_s,
            "decision_summary_max": st.decision_summary_max,
            "payload_limit_bytes": st.payload_limit_bytes,
            "daily_run_cap": st.daily_run_cap,
            "new_account_daily_run_cap": st.new_account_daily_run_cap,
            "new_account_days": st.new_account_days,
            "rate_per_key_per_min": st.rate_per_key_per_min,
            "certified_runs_per_instance": st.certified_runs_per_instance,
            "daily_attempts": st.daily_attempts,
            "season_weeks": st.season_weeks,
            "season_instances_per_tier": st.season_instances_per_tier,
            "bullet_min_instances": st.bullet_min_instances,
            "bullet_min_runs_per_instance": st.bullet_min_runs_per_instance,
        },
        "tiers": {
            name: {
                "locations": p.locations,
                "irrelevant_objects": p.decoys,
                "clue_composition_depth": p.depth,
                "code_digits": p.code_digits,
                "action_budget": p.budget,
                "ranked": p.ranked,
            }
            for name, p in TIERS.items()
        },
        "tools": tool_schemas(),
        "failure_codes": list(FAILURE_CODES),
        "endings": [{"id": e, "label": ENDING_LABELS[e]} for e in ENDINGS],
        "certificate": {"proves": PROVES, "does_not_prove": DOES_NOT_PROVE},
        "support": "No uptime or response-time promise in season one. Documentation, GitHub issues and a community channel.",
    }


@router.get("/.well-known/escapement-keys.json")
def keys(request: Request, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "public, max-age=3600"
    return ctx(request).signer.keyset()


@router.get("/api/v1/keys/signing")
def keys_alias(request: Request) -> dict[str, Any]:
    return ctx(request).signer.keyset()


# ----------------------------------------------------------------- rooms


@router.get("/api/v1/rooms")
def rooms(request: Request) -> dict[str, Any]:
    """Practice and the Daily Room, plus the current season's ranked rooms."""
    c = ctx(request)
    with c.db.service_session() as s:  # ensures Practice and today's Daily exist
        from ..services.rooms import ensure_practice, get_or_create_daily

        ensure_practice(s)
        get_or_create_daily(s, c.settings)
    p = principal(request)
    with c.db.api_session(p.user_id) as s:
        practice = s.get(RoomInstance, "practice")
        today = s.get(DailyRoom, utc_today())
        daily = s.get(RoomInstance, today.instance_id) if today else None
        season = _current_season(s)
        ranked = []
        if season is not None:
            ranked = [
                room_public(i, season)
                for i in s.execute(
                    select(RoomInstance).where(RoomInstance.season_id == season.id).order_by(RoomInstance.tier, RoomInstance.position)
                ).scalars()
            ]
        return {
            "practice": room_public(practice) if practice else None,
            "daily": room_public(daily) if daily else None,
            "season": {"id": season.id, "name": season.name, "status": season_status(season)} if season else None,
            "ranked": ranked,
        }


@router.get("/api/v1/rooms/{room_id}")
def room(room_id: str, request: Request) -> dict[str, Any]:
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        inst = s.get(RoomInstance, room_id)
        if inst is None or (inst.kind == "research" and ctx(request).settings.mode != "local"):
            raise not_found("Unknown room.")
        season = s.get(Season, inst.season_id) if inst.season_id else None
        out = room_public(inst, season)
        pm = s.get(PublishedManifest, room_id) if inst.manifest_public else None
        if pm is not None:
            out["min_length"] = pm.min_length
            out["optimality"] = pm.optimality
        return out


@router.get("/api/v1/rooms/{room_id}/manifest")
def room_manifest(room_id: str, request: Request, response: Response) -> dict[str, Any]:
    """Published manifests only, for full re-simulation by anyone."""
    with ctx(request).db.api_session(principal(request).user_id) as s:
        pm = s.get(PublishedManifest, room_id)
        if pm is None:
            raise APIError(403, "SEALED", "This room's manifest is sealed until its results are released.")
        response.headers["Content-Disposition"] = f'attachment; filename="{room_id}.manifest.json"'
        return pm.manifest


def _current_season(s) -> Season | None:  # type: ignore[no-untyped-def]
    seasons = s.execute(select(Season).order_by(Season.starts_at.desc())).scalars().all()
    for season in seasons:
        if season_status(season) in ("open", "ended"):
            return season
    scheduled = [x for x in seasons if season_status(x) == "scheduled"]
    if scheduled:
        return scheduled[-1]
    return seasons[0] if seasons else None


# ----------------------------------------------------------------- seasons


@router.get("/api/v1/seasons")
def seasons(request: Request) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        rows = s.execute(select(Season).order_by(Season.starts_at.desc())).scalars().all()
        cur = _current_season(s)
        return {"current": cur.id if cur else None, "seasons": [season_public(s, x) for x in rows]}


@router.get("/api/v1/seasons/current")
def season_current(request: Request) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        cur = _current_season(s)
        if cur is None:
            raise not_found("No season has been scheduled yet.")
        return season_public(s, cur)


@router.get("/api/v1/seasons/{season_id}")
def season(season_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        x = s.get(Season, season_id)
        if x is None:
            raise not_found("Unknown season.")
        return season_public(s, x)


@router.get("/api/v1/seasons/{season_id}/leaderboard")
def season_leaderboard(season_id: str, request: Request, tier: str = Query("standard")) -> dict[str, Any]:
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        x = s.get(Season, season_id)
        if x is None:
            raise not_found("Unknown season.")
        if tier not in x.tiers:
            raise APIError(422, "INVALID_REQUEST", f"Tier must be one of {x.tiers}.")
        return leaderboard(s, x, tier, p.user_id)


@router.get("/api/v1/seasons/{season_id}/report")
def season_report(season_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        x = s.get(Season, season_id)
        if x is None:
            raise not_found("Unknown season.")
        if x.report is None:
            raise APIError(409, "NOT_RELEASED", "The season report is published when the season closes.", {"ends_at": iso(x.ends_at)})
        return x.report


@router.get("/api/v1/reference")
def reference(request: Request) -> dict[str, Any]:
    """Reference agents: last-refreshed dates and stale rows marked (15.3)."""
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        cur = _current_season(s)
        boards = {}
        if cur is not None:
            for tier in cur.tiers:
                lb = leaderboard(s, cur, tier, p.user_id)
                boards[tier] = [r for r in lb["rows"] if r["reference"]]
        system = s.execute(select(User.id).where(User.is_system.is_(True))).scalars().all()
        practice = (
            s.execute(select(Run).where(Run.instance_id == "practice", Run.user_id.in_(system), Run.status != "in_progress"))
            .scalars()
            .all()
        )
        by_agent: dict[str, dict[str, Any]] = {}
        for r in practice:
            key = f"{(r.declared or {}).get('name')} {(r.declared or {}).get('version')}"
            row = by_agent.setdefault(key, {"agent": r.declared, "runs": 0, "escapes": 0, "last_run_at": None})
            row["runs"] += 1
            row["escapes"] += r.status == "escaped"
            row["last_run_at"] = max(filter(None, [row["last_run_at"], iso(r.finished_at)]), default=None)
        return {
            "season_id": cur.id if cur else None,
            "season": boards,
            "practice": list(by_agent.values()),
            "policy": [
                "Reference LLM runs use a slow drip queue on the Groq free tier that respects rate-limit headers and stops at 90% of the daily token limit.",
                "Results are cached by room instance hash, agent configuration hash and seed, and never rerun.",
                "Random and heuristic baselines run every season at no cost.",
                "If provider limits shrink, fewer reference runs are published and this page says so.",
            ],
        }


# ----------------------------------------------------------------- daily


@router.get("/api/v1/daily")
def daily(request: Request) -> dict[str, Any]:
    c = ctx(request)
    p = principal(request)
    with c.db.service_session() as s:
        from ..services.rooms import get_or_create_daily

        inst = get_or_create_daily(s, c.settings)
        iid = inst.id
    with c.db.api_session(p.user_id) as s:
        inst = s.get(RoomInstance, iid)
        today = utc_today()
        return {
            "room": room_public(inst),  # type: ignore[arg-type]
            "attempts_allowed": c.settings.daily_attempts,
            "humans": daily_service.board(s, today, "humans", p.user_id),
            "agents": daily_service.board(s, today, "agents", p.user_id),
        }


@router.get("/api/v1/daily/{day}")
def daily_day(day: str, request: Request) -> dict[str, Any]:
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise APIError(422, "INVALID_REQUEST", "Use YYYY-MM-DD.")
    if d > utc_today():
        raise not_found("That Daily Room does not exist yet.")
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        row = s.get(DailyRoom, d)
        if row is None:
            raise not_found("No Daily Room was played that day.")
        inst = s.get(RoomInstance, row.instance_id)
        pm = s.get(PublishedManifest, row.instance_id)
        return {
            "room": room_public(inst),  # type: ignore[arg-type]
            "humans": daily_service.board(s, d, "humans", p.user_id),
            "agents": daily_service.board(s, d, "agents", p.user_id),
            "solution": {"actions": pm.solution, "min_length": pm.min_length, "optimality": pm.optimality} if pm else None,
        }


@router.get("/api/v1/daily-history")
def daily_history(request: Request, limit: int = Query(14, le=60)) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        rows = s.execute(select(DailyRoom).order_by(DailyRoom.date.desc()).limit(limit)).scalars().all()
        out = []
        for r in rows:
            runs = s.execute(select(Run.status, Run.agent_type).where(Run.instance_id == r.instance_id, Run.status != "in_progress")).all()
            out.append(
                {
                    "date": r.date.isoformat(),
                    "instance_id": r.instance_id,
                    "unlocked": r.date < utc_today(),
                    "attempts": len(runs),
                    "escapes": sum(1 for st, _ in runs if st == "escaped") if r.date < utc_today() else None,
                }
            )
        return {"days": out}


# ----------------------------------------------------------------- certificates


@router.get("/api/v1/certificates/{cert_id}")
def certificate(cert_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        cert = s.get(Certificate, cert_id)
        if cert is None:
            raise not_found("Unknown certificate.")
        return certificate_public(s, cert)


@router.get("/api/v1/certificates/{cert_id}/download")
def certificate_download(cert_id: str, request: Request, response: Response) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        cert = s.get(Certificate, cert_id)
        if cert is None:
            raise not_found("Unknown certificate.")
        response.headers["Content-Disposition"] = f'attachment; filename="{cert_id}.certificate.json"'
        return cert.body


@router.get("/api/v1/certificates/{cert_id}/verify")
def certificate_verify(cert_id: str, request: Request) -> dict[str, Any]:
    """Server-side check of signature, chain and (when the manifest is public)
    full re-simulation. The same checks run offline with `escapement verify`."""
    c = ctx(request)
    with c.db.service_session() as s:
        cert = s.get(Certificate, cert_id)
        if cert is None:
            raise not_found("Unknown certificate.")
        replay = None
        if cert.run_id:
            run = s.get(Run, cert.run_id)
            if run is not None:
                replay = (c.store.get(run.replay_key) if run.replay_key else None) or build_run_replay(s, run)
        report = server_verify(c, s, cert, replay)
        report["checked_at"] = iso(utcnow())
        return report
