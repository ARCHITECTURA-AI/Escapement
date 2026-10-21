"""Administrative endpoints: generate, validate, publish a season, revoke a
certificate, jobs. They exist only in local mode. In public mode the backend
rejects every one of them (FR-11, AC-17); hiding buttons is not enough.
Hosted operators use the `escapement-api ops` commands with database access."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from escapement_engine.generation import GenerationError, generate, load_manifest, manifest_json
from escapement_engine.validation import validate
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from ..deps import ctx
from ..errors import APIError, not_found
from ..models import Certificate, Job, ModerationReport, RoomInstance, Run, SealedManifest, Season, Setting, User
from ..services import jobs as job_service
from ..services.rooms import store_instance
from ..timeutil import iso, utcnow


def require_local(request: Request) -> None:
    if ctx(request).settings.mode != "local":
        raise APIError(403, "ADMIN_DISABLED", "Administrative calls are rejected in public mode.")


router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_local)])


@router.get("/overview")
def overview(request: Request) -> dict[str, Any]:
    c = ctx(request)
    with c.db.service_session() as s:
        jobs = dict(s.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        return {
            "users": s.execute(select(func.count()).select_from(User)).scalar_one(),
            "runs": s.execute(select(func.count()).select_from(Run)).scalar_one(),
            "live_runs": s.execute(select(func.count()).select_from(Run).where(Run.status == "in_progress")).scalar_one(),
            "instances": dict(s.execute(select(RoomInstance.kind, func.count()).group_by(RoomInstance.kind)).all()),
            "jobs": jobs,
            "kill_switch": c.runs.kill_switch_on(s),
            "open_reports": s.execute(
                select(func.count()).select_from(ModerationReport).where(ModerationReport.resolved_at.is_(None))
            ).scalar_one(),
        }


@router.post("/generate")
async def admin_generate(request: Request) -> dict[str, Any]:
    body = await request.json()
    tier = body.get("tier", "standard")
    if tier not in ("practice", "standard", "hard"):
        raise APIError(422, "INVALID_REQUEST", "tier must be practice, standard or hard.")
    count = max(1, min(int(body.get("count", 1)), 20))
    seed = str(body.get("seed") or "")
    out = []
    with ctx(request).db.service_session() as s:
        for i in range(count):
            this_seed = (seed or f"research-{utcnow().strftime('%Y%m%d%H%M%S')}") + (f"-{i}" if count > 1 or not seed else "")
            iid = f"research-{tier}-{this_seed}"[:80].lower().replace(" ", "-")
            if s.get(RoomInstance, iid) is not None:
                raise APIError(409, "EXISTS", f"Instance {iid} already exists.")
            try:
                g = generate(tier, this_seed, iid)
            except GenerationError as exc:
                raise APIError(422, "GENERATION_FAILED", str(exc))
            store_instance(s, g, kind="research", publish=True)
            out.append(g.summary())
    return {"instances": out}


@router.post("/validate")
async def admin_validate(request: Request) -> dict[str, Any]:
    body = await request.json()
    try:
        manifest = load_manifest(body.get("manifest") or body)
    except Exception as exc:
        raise APIError(422, "INVALID_MANIFEST", f"Not a valid manifest: {exc}")
    report = validate(manifest)
    return {"report": report.to_dict(), "solution": report.solution}


@router.get("/instances")
def instances(request: Request, kind: str | None = None) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        q = select(RoomInstance, SealedManifest).join(SealedManifest, SealedManifest.instance_id == RoomInstance.id)
        if kind:
            q = q.where(RoomInstance.kind == kind)
        rows = s.execute(q.order_by(RoomInstance.created_at.desc()).limit(200)).all()
        return {
            "instances": [
                {
                    "id": i.id,
                    "kind": i.kind,
                    "tier": i.tier,
                    "title": i.title,
                    "season_id": i.season_id,
                    "instance_hash": i.instance_hash,
                    "optimality": i.optimality,
                    "min_length": m.min_length,
                    "validation": m.validation,
                    "created_at": iso(i.created_at),
                    "manifest_public": i.manifest_public,
                }
                for i, m in rows
            ]
        }


@router.get("/instances/{instance_id}/manifest")
def instance_manifest(instance_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        m = s.get(SealedManifest, instance_id)
        if m is None:
            raise not_found()
        return {
            "manifest": m.manifest,
            "solution": m.solution,
            "seed": m.seed,
            "validation": m.validation,
            "json": manifest_json(load_manifest(m.manifest)),
        }


@router.get("/jobs")
def list_jobs(request: Request, status: str | None = None, limit: int = Query(100, le=500)) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        q = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if status:
            q = q.where(Job.status == status)
        return {"jobs": [job_service.job_public(j) for j in s.execute(q).scalars()]}


JOB_KINDS = {"batch_run", "generate_season", "close_season", "reference_baselines", "reference_run", "sweep"}


@router.post("/jobs", status_code=201)
async def create_job(request: Request) -> dict[str, Any]:
    body = await request.json()
    kind = body.get("kind")
    if kind not in JOB_KINDS:
        raise APIError(422, "INVALID_REQUEST", f"kind must be one of {sorted(JOB_KINDS)}.")
    with ctx(request).db.service_session() as s:
        job = job_service.enqueue(s, kind, body.get("payload") or {}, priority=int(body.get("priority", 100)))
        return job_service.job_public(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise not_found()
        if job.status in ("queued", "running"):
            job.status = "cancelled"
            job.updated_at = utcnow()
        return job_service.job_public(job)


@router.post("/seasons", status_code=202)
async def create_season(request: Request) -> dict[str, Any]:
    body = await request.json()
    sid = str(body.get("id") or "").strip().lower()
    if not sid or len(sid) > 20:
        raise APIError(422, "INVALID_REQUEST", "Give the season a short id such as s1.")
    starts = body.get("starts_at")
    try:
        starts_at = datetime.fromisoformat(starts.replace("Z", "+00:00")) if starts else utcnow()
    except ValueError:
        raise APIError(422, "INVALID_REQUEST", "starts_at must be an ISO timestamp.")
    with ctx(request).db.service_session() as s:
        if s.get(Season, sid) is not None:
            raise APIError(409, "EXISTS", "That season already exists.")
        job = job_service.enqueue(
            s,
            "generate_season",
            {
                "season_id": sid,
                "name": body.get("name") or f"Season {sid.upper()}",
                "starts_at": starts_at.isoformat(),
                "weeks": body.get("weeks"),
                "instances": body.get("instances"),
            },
            priority=10,
        )
        return {"job": job_service.job_public(job)}


@router.post("/seasons/{season_id}/close")
def close_season(season_id: str, request: Request) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        if s.get(Season, season_id) is None:
            raise not_found()
        job = job_service.enqueue(s, "close_season", {"season_id": season_id}, priority=10)
        return {"job": job_service.job_public(job)}


@router.post("/certificates/{cert_id}/revoke")
async def revoke_certificate(cert_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    reason = str(body.get("reason") or "").strip()[:300]
    if not reason:
        raise APIError(422, "INVALID_REQUEST", "A revocation needs a reason; it is shown on the certificate page.")
    with ctx(request).db.service_session() as s:
        cert = s.get(Certificate, cert_id)
        if cert is None:
            raise not_found()
        cert.revoked_at = utcnow()
        cert.revocation_reason = reason
        return {"id": cert.id, "revoked_at": iso(cert.revoked_at), "reason": reason}


@router.post("/kill-switch")
async def kill_switch(request: Request) -> dict[str, Any]:
    body = await request.json()
    on = bool(body.get("on"))
    c = ctx(request)
    with c.db.service_session() as s:
        row = s.get(Setting, "kill_switch")
        if row is None:
            s.add(Setting(key="kill_switch", value=on))
        else:
            row.value = on
            row.updated_at = utcnow()
    cancelled = c.runs.cancel_live() if on else 0
    return {"kill_switch": on, "cancelled_runs": cancelled}


@router.get("/reports")
def reports(request: Request) -> dict[str, Any]:
    with ctx(request).db.service_session() as s:
        rows = s.execute(select(ModerationReport).order_by(ModerationReport.created_at.desc()).limit(200)).scalars().all()
        return {
            "reports": [
                {
                    "id": r.id,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "reason": r.reason,
                    "created_at": iso(r.created_at),
                    "resolved_at": iso(r.resolved_at),
                }
                for r in rows
            ]
        }
