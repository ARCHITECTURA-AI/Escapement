"""A Postgres-backed jobs table with no separate broker (19.1). Workers claim
with FOR UPDATE SKIP LOCKED; SQLite falls back to a guarded update."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Job
from ..timeutil import iso, utcnow


def enqueue(s: Session, kind: str, payload: dict[str, Any] | None = None, priority: int = 100, run_after: datetime | None = None, max_attempts: int = 3) -> Job:
    job = Job(kind=kind, payload=payload or {}, priority=priority, run_after=run_after or utcnow(), max_attempts=max_attempts)
    s.add(job)
    s.flush()
    return job


def claim(s: Session, worker_id: str, kinds: list[str] | None = None) -> Job | None:
    q = select(Job).where(Job.status == "queued", Job.run_after <= utcnow()).order_by(Job.priority, Job.created_at).limit(1)
    if kinds:
        q = q.where(Job.kind.in_(kinds))
    if s.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    job = s.execute(q).scalar_one_or_none()
    if job is None:
        return None
    updated = s.execute(
        update(Job).where(Job.id == job.id, Job.status == "queued").values(
            status="running", locked_at=utcnow(), locked_by=worker_id, attempts=Job.attempts + 1, updated_at=utcnow()
        )
    )
    if updated.rowcount != 1:  # lost a race on SQLite
        return None
    s.refresh(job)
    return job


def complete(s: Session, job_id: str, result: dict[str, Any] | None = None) -> None:
    s.execute(update(Job).where(Job.id == job_id).values(status="done", result=result or {}, updated_at=utcnow(), error=None))


def fail(s: Session, job_id: str, error: str, retry_in: timedelta | None = None) -> None:
    job = s.get(Job, job_id)
    if job is None:
        return
    if job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = utcnow() + (retry_in or timedelta(seconds=30 * job.attempts))
    else:
        job.status = "failed"
    job.error = error[:4000]
    job.updated_at = utcnow()


def defer(s: Session, job_id: str, until: datetime, note: str) -> None:
    """Put a job back without counting an attempt (e.g. provider daily limit)."""
    s.execute(
        update(Job).where(Job.id == job_id).values(
            status="queued", run_after=until, attempts=Job.attempts - 1, progress=note, updated_at=utcnow()
        )
    )


def reclaim_stuck(s: Session, older_than: timedelta = timedelta(minutes=30)) -> int:
    """A restarted worker never repeats a completed action: runs are resumed by
    the API's idempotency, so re-queueing an abandoned job is safe."""
    res = s.execute(
        update(Job).where(Job.status == "running", Job.locked_at < utcnow() - older_than).values(status="queued", locked_by=None)
    )
    return res.rowcount or 0


def job_public(j: Job) -> dict[str, Any]:
    return {
        "id": j.id, "kind": j.kind, "payload": j.payload, "status": j.status, "priority": j.priority,
        "attempts": j.attempts, "max_attempts": j.max_attempts, "run_after": iso(j.run_after),
        "result": j.result, "error": j.error, "progress": j.progress, "created_at": iso(j.created_at), "updated_at": iso(j.updated_at),
    }
