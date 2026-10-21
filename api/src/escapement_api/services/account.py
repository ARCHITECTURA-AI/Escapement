"""Privacy (section 22): a user can export their data and delete their
account. Deleting unpublishes the profile and replaces certificates with a
revoked tombstone."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import AgentVersion, ApiKey, Certificate, HintEvent, Run, RunState, Session as DbSession, Transition, User, UserPrivate
from ..timeutil import iso, utcnow
from .certs import tombstone


def export(s: Session, user_id: str) -> dict[str, Any]:
    user = s.get(User, user_id)
    private = s.get(UserPrivate, user_id)
    keys = s.execute(select(ApiKey).where(ApiKey.user_id == user_id)).scalars().all()
    versions = s.execute(select(AgentVersion).where(AgentVersion.user_id == user_id)).scalars().all()
    runs = s.execute(select(Run).where(Run.user_id == user_id).order_by(Run.started_at)).scalars().all()
    certs = s.execute(select(Certificate).where(Certificate.user_id == user_id)).scalars().all()
    run_out = []
    for r in runs:
        steps = s.execute(select(Transition).where(Transition.run_id == r.id).order_by(Transition.seq)).scalars().all()
        run_out.append(
            {
                "id": r.id, "instance_id": r.instance_id, "mode": r.mode, "status": r.status, "actions_used": r.actions_used,
                "started_at": iso(r.started_at), "finished_at": iso(r.finished_at), "declared": r.declared, "usage": r.usage,
                "final_chain_hash": r.final_chain_hash, "certificate_id": r.certificate_id,
                "steps": [{"seq": t.seq, "action": t.action, "result": t.result, "decision_summary": t.decision_summary} for t in steps],
            }
        )
    return {
        "exported_at": iso(utcnow()),
        "user": {"id": user.id, "handle": user.handle, "display_name": user.display_name, "created_at": iso(user.created_at), "profile_public": user.profile_public} if user else None,
        "email": private.email if private else None,
        "api_keys": [{"name": k.name, "prefix": k.prefix, "created_at": iso(k.created_at), "revoked_at": iso(k.revoked_at)} for k in keys],
        "agent_versions": [
            {"id": v.id, "name": v.name, "version": v.version_label, "model": v.declared_model, "framework": v.framework, "memory": v.memory_strategy}
            for v in versions
        ],
        "runs": run_out,
        "certificates": [c.body for c in certs],
    }


def delete_account(s: Session, user_id: str) -> None:
    user = s.get(User, user_id)
    if user is None:
        return
    for cert in s.execute(select(Certificate).where(Certificate.user_id == user_id)).scalars():
        tombstone(cert, "Account deleted by its owner.")
        cert.user_id = None
    run_ids = s.execute(select(Run.id).where(Run.user_id == user_id)).scalars().all()
    if run_ids:
        s.execute(delete(Transition).where(Transition.run_id.in_(run_ids)))
        s.execute(delete(RunState).where(RunState.run_id.in_(run_ids)))
        s.execute(delete(HintEvent).where(HintEvent.run_id.in_(run_ids)))
        # Outcomes stay in season aggregates, without any link to the person.
        s.execute(
            update(Run)
            .where(Run.id.in_(run_ids))
            .values(user_id=None, agent_version_id=None, declared={"name": "Deleted account"}, usage={}, api_key_id=None, replay_key=None)
        )
    s.execute(delete(ApiKey).where(ApiKey.user_id == user_id))
    s.execute(delete(DbSession).where(DbSession.user_id == user_id))
    s.execute(delete(AgentVersion).where(AgentVersion.user_id == user_id))
    s.execute(delete(UserPrivate).where(UserPrivate.user_id == user_id))
    user.handle = f"deleted-{user.id[:8]}"
    user.display_name = None
    user.avatar_url = None
    user.profile_public = False
    user.deleted_at = utcnow()
