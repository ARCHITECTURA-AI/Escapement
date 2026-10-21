from __future__ import annotations

import json
from typing import Any

from escapement_engine.clinic import analyze, private_context
from escapement_engine.generation import load_manifest
from escapement_engine.schemas.endings import ENDING_LABELS, IN_PROGRESS
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

from ..deps import Principal, client_fingerprint, ctx, principal, require_user
from ..errors import APIError, forbidden, not_found
from ..models import HintEvent, PublishedManifest, RoomInstance, Run, RunState
from ..security import matches
from ..services.rooms import load_room
from ..services.runs import build_run_replay
from ..timeutil import as_utc, iso, utcnow

router = APIRouter(prefix="/api/v1", tags=["runs"])


async def json_body(request: Request) -> Any:
    raw = await request.body()
    limit = ctx(request).settings.payload_limit_bytes
    if len(raw) > limit:
        raise APIError(413, "PAYLOAD_TOO_LARGE", f"Requests are limited to {limit} bytes.")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise APIError(400, "INVALID_JSON", "The body is not valid JSON.")


def run_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ert_"):
        return auth[7:].strip()
    return request.headers.get("x-run-token")


@router.post("/runs", status_code=201)
async def create_run(request: Request, p: Principal = Depends(principal)) -> dict[str, Any]:
    body = await json_body(request)
    if not isinstance(body, dict):
        raise APIError(422, "INVALID_REQUEST", "The body must be a JSON object.")
    via = (
        "web"
        if request.headers.get("x-escapement-client") == "web"
        else ("mcp" if request.headers.get("x-escapement-client") == "mcp" else "api")
    )
    if p.is_system:
        via = "worker"
    return ctx(request).runs.create(p, body, client_fingerprint(request), via)


@router.get("/runs/{run_id}/observation")
def get_observation(run_id: str, request: Request) -> dict[str, Any]:
    return ctx(request).runs.observation(run_id, run_token(request))


@router.post("/runs/{run_id}/actions")
async def submit_action(run_id: str, request: Request, response: Response) -> dict[str, Any]:
    body = await json_body(request)
    data, replayed = ctx(request).runs.act(run_id, run_token(request), body)
    if replayed:
        response.headers["Idempotent-Replay"] = "true"
    return data


@router.post("/runs/{run_id}/finish")
async def finish_run(run_id: str, request: Request) -> dict[str, Any]:
    body = await json_body(request)
    return ctx(request).runs.finish(run_id, run_token(request), body if isinstance(body, dict) else {})


# ---------------------------------------------------------------- reading runs


def _viewer(request: Request) -> Principal:
    return principal(request)


def _token_owner(run: Run, request: Request) -> bool:
    token = run_token(request)
    return bool(token and matches(token, run.run_token_hash))


def run_summary(run: Run, inst: RoomInstance | None, viewer: Principal, token_ok: bool = False) -> dict[str, Any]:
    owner = viewer.user_id is not None and viewer.user_id == run.user_id
    embargoed = run.embargo_until is not None and as_utc(run.embargo_until) > utcnow()
    return {
        "id": run.id,
        "room": {
            "id": run.instance_id,
            "title": inst.title if inst else None,
            "tier": inst.tier if inst else None,
            "kind": inst.kind if inst else None,
            "season_id": run.season_id,
            "instance_hash": inst.instance_hash if inst else None,
            "manifest_public": inst.manifest_public if inst else False,
        },
        "mode": run.mode,
        "agent_type": run.agent_type,
        "agent": run.declared,
        "status": run.status,
        "status_label": ENDING_LABELS.get(run.status, "In progress"),
        "actions_used": run.actions_used,
        "action_budget": run.action_budget,
        "malformed_count": run.malformed_count,
        "sequence": run.seq,
        "chain_hash": run.chain_hash,
        "final_chain_hash": run.final_chain_hash,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "wall_time_ms": run.wall_time_ms,
        "usage": run.usage,
        "usage_label": "self-reported",
        "hints_used": run.hints_used,
        "assisted": run.assisted,
        "certificate_id": run.certificate_id,
        "engine_version": run.engine_version,
        "embargo_until": iso(run.embargo_until) if embargoed else None,
        "replay_visible": owner or token_ok or not embargoed,
        "is_owner": owner or token_ok,
        "views": run.view_count,
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    viewer = _viewer(request)
    with ctx(request).db.api_session(viewer.user_id) as s:
        run = s.get(Run, run_id)
        if run is None:
            raise not_found("Unknown run.")
        inst = s.get(RoomInstance, run.instance_id)
        return run_summary(run, inst, viewer, _token_owner(run, request))


@router.get("/runs/{run_id}/replay")
def get_replay(
    run_id: str, request: Request, response: Response, after_seq: int = Query(0, ge=0), download: bool = False
) -> dict[str, Any]:
    """Replay, subject to the embargo rules (21.4, AC-12). Ranked replays are
    visible only to their owner until the season closes."""
    c = ctx(request)
    viewer = _viewer(request)
    with c.db.api_session(viewer.user_id) as s:
        run = s.get(Run, run_id)
        if run is None:
            raise not_found("Unknown run.")
        inst = s.get(RoomInstance, run.instance_id)
        summary = run_summary(run, inst, viewer, _token_owner(run, request))
        if not summary["replay_visible"]:
            raise APIError(
                403,
                "EMBARGOED",
                "This replay is embargoed until its room's results are released.",
                {"embargo_until": summary["embargo_until"]},
            )
        if after_seq:
            partial = build_run_replay(s, run)
            return {"run": summary, "steps": [st for st in partial["steps"] if st["seq"] > after_seq], "status": run.status}
        replay: dict[str, Any] | None = None
        if run.replay_key and run.status != IN_PROGRESS:
            replay = c.store.get(run.replay_key)
        if replay is None:
            replay = build_run_replay(s, run)
        if download:
            response.headers["Content-Disposition"] = f'attachment; filename="{run.id}.replay.json"'
            return replay
        return {"run": summary, "replay": replay}


@router.get("/runs/{run_id}/clinic")
def get_clinic(run_id: str, request: Request, p: Principal = Depends(principal)) -> dict[str, Any]:
    """Trace Clinic works on a user's own runs (14.5)."""
    c = ctx(request)
    with c.db.service_session() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise not_found("Unknown run.")
        if not ((p.user_id and p.user_id == run.user_id) or _token_owner(run, request)):
            raise forbidden("Trace Clinic is available on your own runs.")
        inst = s.get(RoomInstance, run.instance_id)
        replay = build_run_replay(s, run)
        private = None
        unavailable = None
        if inst is not None and inst.manifest_public:
            pm = s.get(PublishedManifest, inst.id)
            if pm is not None:
                private = private_context(replay, load_manifest(pm.manifest), pm.solution)
        else:
            unavailable = "Milestone comparisons unlock when this room's solution is published (after the UTC day for Daily, after the season for ranked rooms)."
        out = analyze(replay, private)
        out["run"] = run_summary(run, inst, p, True)
        out["milestone_comparison_unavailable"] = unavailable
        return out


@router.post("/runs/{run_id}/hint")
async def get_hint(run_id: str, request: Request) -> dict[str, Any]:
    """Hints are for humans in Play and the Daily Room only. They are
    progressive, need confirmation and are recorded. Hinted runs are
    excluded from unassisted boards. Hints never enter an agent's
    observations (17.5)."""
    body = await json_body(request)
    c = ctx(request)
    with c.db.service_session() as s:
        run = s.execute(select(Run).where(Run.id == run_id).with_for_update()).scalar_one_or_none()
        if run is None:
            raise not_found("Unknown run.")
        if not _token_owner(run, request):
            raise forbidden("Hints need the run's token.")
        if run.agent_type != "human" or run.mode not in ("practice", "daily"):
            raise APIError(403, "HINTS_HUMANS_ONLY", "Hints are only for humans playing Practice or the Daily Room.")
        if run.status != IN_PROGRESS:
            raise APIError(409, "EPISODE_FINISHED", "The run has ended.")
        if not (isinstance(body, dict) and body.get("confirm") is True):
            raise APIError(
                428,
                "CONFIRM_HINT",
                "Taking a hint marks this run as assisted: it will not appear on the unassisted Daily board. Send confirm: true to continue.",
            )
        room = load_room(s, run.instance_id)
        state = s.get(RunState, run.id).state  # type: ignore[union-attr]
        reached = set(state.get("milestones", []))
        target = next((m for m in room.manifest.milestones if m.id not in reached and m.hints), None)
        if target is None:
            raise APIError(409, "NO_HINT", "There is nothing left to hint at.")
        given = s.execute(select(HintEvent).where(HintEvent.run_id == run.id, HintEvent.milestone_id == target.id)).scalars().all()
        level = min(len(given) + 1, len(target.hints))
        s.add(HintEvent(run_id=run.id, user_id=run.user_id, milestone_id=target.id, level=level, at_seq=run.seq))
        run.assisted = True
        run.hints_used += 1
        return {
            "hint": target.hints[level - 1],
            "level": level,
            "levels": len(target.hints),
            "hints_used": run.hints_used,
            "assisted": True,
        }


@router.get("/runs/{run_id}/solution")
def get_solution(run_id: str, request: Request) -> dict[str, Any]:
    """The optional solution view (17.4): only after the run ends and only for
    rooms whose manifest is public."""
    viewer = _viewer(request)
    with ctx(request).db.api_session(viewer.user_id) as s:
        run = s.get(Run, run_id)
        if run is None:
            raise not_found("Unknown run.")
        inst = s.get(RoomInstance, run.instance_id)
        if run.status == IN_PROGRESS:
            raise APIError(409, "RUN_IN_PROGRESS", "The solution view appears after the run ends.")
        pm = s.get(PublishedManifest, run.instance_id)
        if pm is None or inst is None or not inst.manifest_public:
            raise APIError(403, "SEALED", "This room's solution is still sealed.")
        manifest = load_manifest(pm.manifest)
        return {
            "room_id": inst.id,
            "solution": pm.solution,
            "min_length": pm.min_length,
            "optimality": pm.optimality,
            "optimality_label": "Proven minimum (breadth-first search)" if pm.optimality == "proven" else "Best verified solution",
            "milestones": [{"id": m.id, "label": m.label} for m in manifest.milestones],
            "path_efficiency": (pm.min_length / run.actions_used)
            if pm.optimality == "proven" and run.status == "escaped" and run.actions_used
            else None,
        }


@router.get("/runs")
def list_my_runs(
    request: Request, p: Principal = Depends(require_user), limit: int = Query(50, le=200), offset: int = 0, mode: str | None = None
) -> dict[str, Any]:
    with ctx(request).db.api_session(p.user_id) as s:
        q = select(Run, RoomInstance).join(RoomInstance, RoomInstance.id == Run.instance_id).where(Run.user_id == p.user_id)
        if mode:
            q = q.where(Run.mode == mode)
        rows = s.execute(q.order_by(Run.started_at.desc()).limit(limit).offset(offset)).all()
        return {"runs": [run_summary(r, i, p) for r, i in rows]}


@router.get("/watch")
def watch_list(request: Request, limit: int = Query(30, le=100), room: str | None = None, outcome: str | None = None) -> dict[str, Any]:
    """Recent runs anyone can watch: not embargoed, and owned by a public
    profile (or a first-party reference agent)."""
    from ..models import User

    viewer = _viewer(request)
    now = utcnow()
    with ctx(request).db.api_session(viewer.user_id) as s:
        q = (
            select(Run, RoomInstance, User)
            .join(RoomInstance, RoomInstance.id == Run.instance_id)
            .join(User, User.id == Run.user_id)
            .where((User.profile_public.is_(True)) | (User.is_system.is_(True)))
            .where((Run.embargo_until.is_(None)) | (Run.embargo_until <= now))
            .where(Run.status != IN_PROGRESS)
        )
        if room:
            q = q.where(Run.instance_id == room)
        if outcome == "escaped":
            q = q.where(Run.status == "escaped")
        elif outcome == "failed":
            q = q.where(Run.status != "escaped")
        rows = s.execute(q.order_by(Run.finished_at.desc()).limit(limit)).all()
        out = []
        for r, i, u in rows:
            item = run_summary(r, i, viewer)
            item["handle"] = u.handle
            out.append(item)
        return {"runs": out}


@router.get("/compare")
def compare(request: Request, runs: str = Query(..., description="Two or three run ids, comma separated")) -> dict[str, Any]:
    """Compare: two or three agent versions on the same room instance, synced
    by action number, not by model response time. Independent state per
    agent; no automatic reset of a failed attempt."""
    ids = [r for r in runs.split(",") if r][:3]
    if len(ids) < 2:
        raise APIError(422, "INVALID_REQUEST", "Pick two or three runs.")
    viewer = _viewer(request)
    with ctx(request).db.api_session(viewer.user_id) as s:
        out = []
        instance = None
        for rid in ids:
            run = s.get(Run, rid)
            if run is None:
                raise not_found(f"Unknown run {rid}.")
            inst = s.get(RoomInstance, run.instance_id)
            summary = run_summary(run, inst, viewer)
            if not summary["replay_visible"]:
                raise APIError(403, "EMBARGOED", f"Run {rid} is embargoed.", {"run_id": rid})
            if instance is None:
                instance = run.instance_id
            elif instance != run.instance_id:
                raise APIError(422, "DIFFERENT_INSTANCES", "Compare needs runs on the same room instance, so the comparison is paired.")
            out.append({"run": summary, "replay": build_run_replay(s, run)})
        return {
            "instance_id": instance,
            "runs": out,
            "max_steps": max(len(r["replay"]["steps"]) for r in out),
        }


@router.post("/runs/{run_id}/events")
async def run_event(run_id: str, request: Request) -> dict[str, Any]:
    """First-party view/share counters for H4 (failed versus successful replays)."""
    from ..models import ProductEvent

    body = await json_body(request)
    kind = body.get("type") if isinstance(body, dict) else None
    if kind not in ("view", "share"):
        raise APIError(422, "INVALID_REQUEST", "type must be view or share.")
    p = _viewer(request)
    with ctx(request).db.service_session() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise not_found("Unknown run.")
        if kind == "view":
            run.view_count += 1
        else:
            run.share_count += 1
        s.add(ProductEvent(name=f"replay_{kind}", user_id=p.user_id, run_id=run.id, props={"outcome": run.status, "mode": run.mode}))
    return {"ok": True}
