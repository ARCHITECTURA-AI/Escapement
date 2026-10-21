"""Profiles, leaderboards and the resume bullet (sections 14.3, 14.4, 16).

Statistical rules (16.6): show sample counts, report per tier, pair
comparisons on identical instances, separate variation across rooms from
variation across repeated runs, publish intervals, never present repeated
attempts on one room as many independent structures.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from escapement_engine.schemas.endings import ENDINGS, ESCAPED, INFRASTRUCTURE_ENDINGS, IN_PROGRESS
from escapement_engine.stats import floor_pct, interval_text, rank_bands, summarize
from escapement_engine.version import ENGINE_VERSION

from ..models import AgentVersion, RoomInstance, Run, Season, User
from ..timeutil import as_utc, iso, utcnow

STALE_AFTER = timedelta(days=14)


def _finished(q):  # type: ignore[no-untyped-def]
    return q.where(Run.status != IN_PROGRESS, Run.status.notin_(INFRASTRUCTURE_ENDINGS))


def _group(runs: list[tuple[Run, RoomInstance]]) -> dict[str, list[tuple[bool, int]]]:
    out: dict[str, list[tuple[bool, int]]] = defaultdict(list)
    for run, _inst in sorted(runs, key=lambda r: as_utc(r[0].started_at)):  # type: ignore[arg-type, return-value]
        out[run.instance_id].append((run.status == ESCAPED, run.actions_used))
    return out


def _cost(runs: list[Run]) -> dict[str, Any]:
    costs = [r.usage.get("cost_usd_micros") for r in runs if r.usage and r.usage.get("cost_usd_micros") is not None]
    tokens = [
        (r.usage.get("tokens_in") or 0) + (r.usage.get("tokens_out") or 0)
        for r in runs
        if r.usage and (r.usage.get("tokens_in") is not None or r.usage.get("tokens_out") is not None)
    ]
    return {
        "self_reported": True,
        "runs_reporting_cost": len(costs),
        "median_cost_usd": (median(costs) / 1_000_000) if costs else None,
        "median_tokens": median(tokens) if tokens else None,
    }


def endings_breakdown(runs: list[Run]) -> dict[str, int]:
    out = {e: 0 for e in ENDINGS}
    for r in runs:
        if r.status in out:
            out[r.status] += 1
    return {k: v for k, v in out.items() if v}


def version_results(s: Session, version: AgentVersion) -> dict[str, Any]:
    rows = s.execute(
        _finished(select(Run, RoomInstance).join(RoomInstance, RoomInstance.id == Run.instance_id).where(Run.agent_version_id == version.id))
    ).all()
    buckets: dict[tuple[str, str | None, str], list[tuple[Run, RoomInstance]]] = defaultdict(list)
    for run, inst in rows:
        buckets[(run.mode, run.season_id, inst.tier)].append((run, inst))
    groups = []
    for (mode, season_id, tier), items in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2])):
        summary = summarize(_group(items))
        groups.append(
            {
                "mode": mode,
                "season_id": season_id,
                "tier": tier,
                "summary": summary.to_dict(),
                "endings": endings_breakdown([r for r, _ in items]),
                "cost": _cost([r for r, _ in items]),
            }
        )
    all_runs = s.execute(select(Run).where(Run.agent_version_id == version.id)).scalars().all()
    return {
        "agent_version": version_public(version),
        "results": groups,
        "endings": endings_breakdown(list(all_runs)),
        "total_runs": len(all_runs),
    }


def version_public(v: AgentVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "name": v.name,
        "version": v.version_label,
        "agent_type": v.agent_type,
        "model": v.declared_model,
        "framework": v.framework,
        "memory": v.memory_strategy,
        "provider": v.provider,
        "config_hash": v.config_hash,
        "self_reported": ["model", "framework", "memory"] if v.agent_type != "reference" else [],
        "created_at": iso(v.created_at),
        "notes": v.notes,
    }


def leaderboard(s: Session, season: Season, tier: str, viewer_id: str | None = None) -> dict[str, Any]:
    rows = s.execute(
        _finished(
            select(Run, RoomInstance)
            .join(RoomInstance, RoomInstance.id == Run.instance_id)
            .where(Run.season_id == season.id, RoomInstance.tier == tier, Run.mode.in_(("ranked", "reference")))
        )
    ).all()
    per_version: dict[str, list[tuple[Run, RoomInstance]]] = defaultdict(list)
    for run, inst in rows:
        if run.agent_version_id:
            per_version[run.agent_version_id].append((run, inst))
    versions = {v.id: v for v in s.execute(select(AgentVersion).where(AgentVersion.id.in_(list(per_version)))).scalars()}
    users = {u.id: u for u in s.execute(select(User).where(User.id.in_([v.user_id for v in versions.values()]))).scalars()}
    out_rows = []
    for vid, items in per_version.items():
        v = versions.get(vid)
        if v is None:
            continue
        owner = users.get(v.user_id)
        summary = summarize(_group(items))
        visible = bool(owner and (owner.profile_public or owner.is_system or owner.id == viewer_id) and owner.deleted_at is None)
        last = max(as_utc(r.finished_at) for r, _ in items if r.finished_at)  # type: ignore[type-var]
        engine_versions = {r.engine_version for r, _ in items}
        out_rows.append(
            {
                "agent_version_id": vid if visible else None,
                "handle": owner.handle if visible and owner else None,
                "agent": {"name": v.name, "version": v.version_label} if visible else {"name": "Private agent", "version": None},
                "agent_type": v.agent_type,
                "reference": v.agent_type == "reference",
                "model": v.declared_model if visible else None,
                "provider": v.provider if v.agent_type == "reference" else None,
                "model_label": "verified (first-party run)" if v.agent_type == "reference" else "self-reported",
                "framework": v.framework if visible else None,
                "memory": v.memory_strategy if visible else None,
                "summary": summary.to_dict(),
                "rate_text": floor_pct(summary.rate),
                "interval_text": interval_text(summary.ci_low, summary.ci_high),
                "endings": endings_breakdown([r for r, _ in items]),
                "cost": _cost([r for r, _ in items]),
                "last_run_at": iso(last),
                "stale": v.agent_type == "reference" and (utcnow() - last > STALE_AFTER or engine_versions != {ENGINE_VERSION}),
                "_key": vid,
            }
        )
    bands = rank_bands(
        [(r["_key"], r["summary"]["rate"] or 0.0, r["summary"]["ci_low"] or 0.0, r["summary"]["ci_high"] or 0.0) for r in out_rows]
    )
    for r in out_rows:
        r["band"] = bands.get(r["_key"])
        del r["_key"]
    out_rows.sort(key=lambda r: (r["band"] or 99, -(r["summary"]["rate"] or 0), -(r["summary"]["runs"])))
    instances = s.execute(select(RoomInstance).where(RoomInstance.season_id == season.id, RoomInstance.tier == tier)).scalars().all()
    return {
        "season_id": season.id,
        "tier": tier,
        "instances": len(instances),
        "rows": out_rows,
        "generated_at": iso(utcnow()),
        "notes": [
            "Success rate is escapes over certified runs; the 95% interval resamples instances.",
            "Agents whose intervals overlap heavily share a rank band instead of a false strict order.",
            "pass^3 is the share of instances where all three runs escaped.",
            "Model, framework, memory, tokens and cost are self-reported unless the row is a first-party reference run.",
        ],
    }


def resume_bullet(s: Session, version: AgentVersion, settings) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Measured numbers only, self-reported ones labelled; refuses below the
    floor; never rounds a rate upward or drops the interval (14.4)."""
    rows = s.execute(
        _finished(
            select(Run, RoomInstance)
            .join(RoomInstance, RoomInstance.id == Run.instance_id)
            .where(Run.agent_version_id == version.id, Run.mode == "ranked", Run.certificate_id.isnot(None))
        )
    ).all()
    by_tier: dict[tuple[str | None, str], list[tuple[Run, RoomInstance]]] = defaultdict(list)
    for run, inst in rows:
        by_tier[(run.season_id, inst.tier)].append((run, inst))
    candidates = []
    for (season_id, tier), items in by_tier.items():
        grouped = _group(items)
        eligible = {k: v for k, v in grouped.items() if len(v) >= settings.bullet_min_runs_per_instance}
        candidates.append((season_id, tier, grouped, eligible, items))
    ok = [c for c in candidates if len(c[3]) >= settings.bullet_min_instances]
    floor = (
        f"at least {settings.bullet_min_runs_per_instance} certified ranked runs on each of at least "
        f"{settings.bullet_min_instances} instances in one season and tier"
    )
    if not ok:
        best = max(candidates, key=lambda c: len(c[3]), default=None)
        return {
            "available": False,
            "reason": f"The generator writes a bullet only after {floor}.",
            "progress": {
                "eligible_instances": len(best[3]) if best else 0,
                "needed_instances": settings.bullet_min_instances,
                "season_id": best[0] if best else None,
                "tier": best[1] if best else None,
            },
        }
    season_id, tier, grouped, eligible, items = max(ok, key=lambda c: (sum(len(v) for v in c[3].values())))
    summary = summarize(eligible)
    season = s.get(Season, season_id) if season_id else None
    season_name = season.name if season else "an Escapement season"
    p3 = floor_pct(summary.pass3) if summary.pass3 is not None else "n/a"
    measured = (
        f"Built {version.name} {version.version_label}, an AI agent that escaped {summary.escapes} of {summary.runs} certified runs "
        f"({floor_pct(summary.rate)}, 95% CI {interval_text(summary.ci_low, summary.ci_high)}) across {summary.instances} sealed "
        f"{season_name} {tier.title()}-tier Escapement rooms; pass^3 {p3} over {summary.pass3_instances} rooms"
    )
    if summary.median_actions_success is not None:
        measured += f"; median {summary.median_actions_success:g} actions per escape"
    measured += "."
    self_reported = []
    if version.declared_model:
        self_reported.append(f"model {version.declared_model}")
    cost = _cost([r for r, _ in items])
    if cost["median_cost_usd"] is not None:
        self_reported.append(f"median cost ${cost['median_cost_usd']:.4f} per run")
    text = measured + (f" Self-reported: {', '.join(self_reported)}." if self_reported else "")
    return {
        "available": True,
        "text": text,
        "measured_part": measured,
        "self_reported_part": self_reported,
        "summary": summary.to_dict(),
        "season_id": season_id,
        "tier": tier,
        "floor": floor,
        "note": "Numbers are server-measured except where labelled self-reported. Rates are rounded down and intervals rounded outward.",
    }


def profile(s: Session, user: User, viewer_id: str | None) -> dict[str, Any]:
    versions = s.execute(
        select(AgentVersion).where(AgentVersion.user_id == user.id).order_by(AgentVersion.created_at)
    ).scalars().all()
    out_versions = [version_results(s, v) for v in versions]
    timeline = []
    for vr in out_versions:
        best = None
        for g in vr["results"]:
            if g["summary"]["runs"] and (best is None or (g["mode"] == "ranked") > (best["mode"] == "ranked")):
                best = g
        timeline.append(
            {
                "agent_version_id": vr["agent_version"]["id"],
                "label": f"{vr['agent_version']['name']} {vr['agent_version']['version']}",
                "created_at": vr["agent_version"]["created_at"],
                "mode": best["mode"] if best else None,
                "tier": best["tier"] if best else None,
                "rate": best["summary"]["rate"] if best else None,
                "ci_low": best["summary"]["ci_low"] if best else None,
                "ci_high": best["summary"]["ci_high"] if best else None,
                "runs": best["summary"]["runs"] if best else 0,
            }
        )
    human_runs = s.execute(
        _finished(select(Run, RoomInstance).join(RoomInstance, RoomInstance.id == Run.instance_id).where(Run.user_id == user.id, Run.agent_type == "human"))
    ).all()
    return {
        "user": {
            "id": user.id,
            "handle": user.handle,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "profile_public": user.profile_public,
            "joined": iso(user.created_at),
            "is_self": viewer_id == user.id,
            "is_system": user.is_system,
        },
        "versions": out_versions,
        "timeline": timeline,
        "human_play": {
            "runs": len(human_runs),
            "escapes": sum(1 for r, _ in human_runs if r.status == ESCAPED),
        },
    }
