"""Run Certificates (section 14.1).

| Field                                                        | Source                               |
| certificate id, run id, issued time                          | server                               |
| room tier, season, instance hash, engine/protocol versions  | server                               |
| outcome, actions used, budget, malformed count, wall time    | server                               |
| final chain hash                                             | server                               |
| run set summary (runs and escapes on this instance)          | server                               |
| agent name and version                                       | declared                             |
| model, framework, memory strategy                            | declared, labelled self-reported     |
| tokens and cost                                              | client-reported, labelled            |
| key id and signature                                         | server                               |
"""

from __future__ import annotations

from typing import Any

from escapement_engine.certificate import DOES_NOT_PROVE, PROVES, SELF_REPORTED_FIELDS, verify
from escapement_engine.core.world import CompiledRoom
from escapement_engine.generation import load_manifest
from escapement_engine.replay import verify_chain
from escapement_engine.schemas.endings import ESCAPED, IN_PROGRESS, INFRASTRUCTURE_ENDINGS
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Certificate, PublishedManifest, RoomInstance, Run, Season
from ..security import new_certificate_id
from ..timeutil import as_utc, iso, utcnow


def run_set(s: Session, run: Run) -> dict[str, Any]:
    q = select(Run.status).where(
        Run.instance_id == run.instance_id,
        Run.status != IN_PROGRESS,
        Run.status.notin_(INFRASTRUCTURE_ENDINGS),
    )
    if run.agent_version_id:
        q = q.where(Run.agent_version_id == run.agent_version_id)
    else:
        q = q.where(Run.user_id == run.user_id, Run.agent_type == run.agent_type)
    statuses = s.execute(q).scalars().all()
    return {"runs": len(statuses), "escapes": sum(1 for x in statuses if x == ESCAPED)}


def issue_certificate(ctx, s: Session, run: Run, room: CompiledRoom) -> Certificate:  # type: ignore[no-untyped-def]
    inst = s.get(RoomInstance, run.instance_id)
    declared = run.declared or {}
    usage = run.usage or {}
    reference = run.agent_type == "reference"
    body = {
        "certificate_id": new_certificate_id(),
        "run_id": run.id,
        "issued_at": iso(utcnow()),
        "room": {
            "room_id": inst.id,  # type: ignore[union-attr]
            "title": inst.title,  # type: ignore[union-attr]
            "tier": inst.tier,  # type: ignore[union-attr]
            "kind": inst.kind,  # type: ignore[union-attr]
            "family": room.manifest.family,
            "season": run.season_id,
            "instance_hash": inst.instance_hash,  # type: ignore[union-attr]
        },
        "mode": run.mode,
        "engine_version": run.engine_version,
        "protocol_version": run.protocol_version,
        "outcome": run.status,
        "actions_used": run.actions_used,
        "action_budget": run.action_budget,
        "malformed_count": run.malformed_count,
        "wall_time_ms": run.wall_time_ms,
        "chain_length": run.seq,
        "final_chain_hash": run.chain_hash,
        "run_set": run_set(s, run),
        "agent": {
            "name": declared.get("name"),
            "version": declared.get("version"),
            "agent_type": run.agent_type,
            "model": declared.get("model"),
            "framework": declared.get("framework"),
            "memory": declared.get("memory"),
            "provider": declared.get("provider") if reference else None,
            "model_attested": reference,
        },
        "usage": {
            "tokens_in": usage.get("tokens_in"),
            "tokens_out": usage.get("tokens_out"),
            "cost_usd_micros": usage.get("cost_usd_micros"),
            "model_decisions": usage.get("model_decisions"),
        },
        "assisted": run.assisted,
        "self_reported_fields": [] if reference else list(SELF_REPORTED_FIELDS),
        "proves": PROVES,
        "does_not_prove": DOES_NOT_PROVE
        if not reference
        else "Escapement ran this first-party reference agent through its own queue, so the provider and model are named with confidence.",
    }
    signed = ctx.signer.sign(body)
    cert = Certificate(
        id=body["certificate_id"],
        run_id=run.id,
        user_id=run.user_id,
        body=signed,
        signature=signed["signature"],
        key_id=signed["key_id"],
    )
    s.add(cert)
    run.certificate_id = cert.id
    s.flush()
    return cert


def verification_level(s: Session, cert: Certificate) -> dict[str, Any]:
    """Which level of verification anyone can perform, and why (14.2)."""
    room = cert.body.get("room", {})
    inst = s.get(RoomInstance, room.get("room_id"))
    public = bool(inst and inst.manifest_public)
    season = s.get(Season, room.get("season")) if room.get("season") else None
    if public:
        level, text = "full", "Room manifest is public: anyone can re-simulate this run through the pinned engine."
    elif inst and inst.kind == "ranked":
        until = iso(season.ends_at) if season else None
        level, text = (
            "chain",
            f"Ranked room: the manifest stays sealed until the season closes ({until}). The signature and hash chain can be checked now.",
        )
    elif inst and inst.kind == "daily":
        level, text = "chain", "Daily Room: the manifest is published after the UTC day ends; then the run can be fully re-simulated."
    else:
        level, text = "chain", "The signature and hash chain can be checked offline."
    return {"available": level, "explanation": text, "manifest_public": public}


def server_verify(ctx, s: Session, cert: Certificate, replay: dict[str, Any] | None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    keyset = ctx.signer.keyset()
    manifest = None
    pm = s.get(PublishedManifest, cert.body.get("room", {}).get("room_id"))
    if pm is not None:
        manifest = load_manifest(pm.manifest)
    report = verify(cert.body, keyset, replay, manifest).to_dict()
    if replay is not None and report["level"] == "signature":
        chain = verify_chain(replay)
        report["chain_ok"] = chain.ok
    report["revoked"] = cert.revoked_at is not None
    if cert.revoked_at is not None:
        report["ok"] = False
        report["problems"] = report.get("problems", []) + [f"Revoked {iso(cert.revoked_at)}: {cert.revocation_reason}"]
    return report


def certificate_public(s: Session, cert: Certificate) -> dict[str, Any]:
    out = {
        "certificate": cert.body,
        "revoked": cert.revoked_at is not None,
        "revoked_at": iso(cert.revoked_at),
        "revocation_reason": cert.revocation_reason,
        "verification": verification_level(s, cert),
        "issued_at": iso(cert.issued_at),
    }
    run = s.get(Run, cert.run_id) if cert.run_id else None
    if run is not None:
        out["run"] = {
            "id": run.id,
            "embargo_until": iso(run.embargo_until) if run.embargo_until and as_utc(run.embargo_until) > utcnow() else None,
        }
    return out


def tombstone(cert: Certificate, reason: str) -> None:
    cert.revoked_at = utcnow()
    cert.revocation_reason = reason
    cert.body = {
        "format": cert.body.get("format"),
        "certificate_id": cert.id,
        "tombstone": True,
        "reason": reason,
        "key_id": cert.key_id,
        "signature": cert.signature,
    }


def count_certificates(s: Session, user_id: str) -> int:
    return s.execute(select(func.count()).select_from(Certificate).where(Certificate.user_id == user_id)).scalar_one()
