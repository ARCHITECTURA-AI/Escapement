"""Seasons (16.3): twelve weeks, Standard and Hard tiers, ten sealed instances
each. At season end the sealed templates, seeds and replays are published so
anyone can re-verify the season (12.6, 21.4)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from escapement_engine.generation import generate, season_seed
from escapement_engine.rooms.emergency_lockdown import TIERS
from escapement_engine.schemas.endings import ESCAPED, IN_PROGRESS
from escapement_engine.version import ENGINE_VERSION
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..errors import APIError
from ..models import PublishedManifest, RoomInstance, Run, Season, User
from ..timeutil import as_utc, iso, utcnow
from .results import endings_breakdown, leaderboard
from .rooms import publish_instance, season_status, store_instance

RANKED_TIERS = ("standard", "hard")


def instance_id(season_id: str, tier: str, index: int) -> str:
    return f"{season_id}-{tier}-{index + 1:02d}"


def create_season(
    s: Session,
    settings,  # type: ignore[no-untyped-def]
    season_id: str,
    name: str,
    starts_at: datetime,
    weeks: int | None = None,
    tiers: tuple[str, ...] = RANKED_TIERS,
    instances: int | None = None,
    progress=None,  # type: ignore[no-untyped-def]
) -> Season:
    if s.get(Season, season_id) is not None:
        raise APIError(409, "EXISTS", f"Season {season_id} already exists.")
    weeks = weeks or settings.season_weeks
    n = instances or settings.season_instances_per_tier
    season = Season(
        id=season_id,
        name=name,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(weeks=weeks),
        status="scheduled",
        tiers=list(tiers),
        instances_per_tier=n,
    )
    s.add(season)
    s.flush()
    done = 0
    for tier in tiers:
        if not TIERS[tier].ranked:
            raise APIError(422, "INVALID_REQUEST", f"Tier {tier} is not ranked.")
        for i in range(n):
            iid = instance_id(season_id, tier, i)
            g = generate(tier, season_seed(settings.seed_secret, season_id, tier, i), iid)
            inst = store_instance(s, g, kind="ranked", season_id=season_id, position=i + 1)
            inst.title = f"{name} · {tier.title()} {i + 1:02d}"
            done += 1
            if progress:
                progress(f"generated {done}/{len(tiers) * n}")
    return season


def refresh_statuses(s: Session) -> list[str]:
    """Open scheduled seasons and close ended ones. Returns closed ids."""
    closed = []
    for season in s.execute(select(Season).where(Season.status != "closed")).scalars().all():
        status = season_status(season)
        if status == "open" and season.status != "open":
            season.status = "open"
        elif status == "ended":
            close_season(s, season.id)
            closed.append(season.id)
    return closed


def close_season(s: Session, season_id: str) -> Season:
    season = s.get(Season, season_id)
    if season is None:
        raise APIError(404, "NOT_FOUND", "Unknown season.")
    if season.status == "closed":
        return season
    now = utcnow()
    # Live ranked runs in a closing season end as cancelled by the close job's caller.
    season.status = "closed"
    season.released_at = now
    for inst in s.execute(select(RoomInstance).where(RoomInstance.season_id == season_id)).scalars():
        publish_instance(s, inst.id)
    s.execute(update(Run).where(Run.season_id == season_id).values(embargo_until=now))
    s.flush()
    season.report = season_report(s, season)
    return season


def season_report(s: Session, season: Season) -> dict[str, Any]:
    """The published season report (FR-20, AC-14): instance counts, runs,
    intervals, budgets and agent configurations, failures included."""
    tiers = {}
    for tier in season.tiers:
        instances = (
            s.execute(
                select(RoomInstance).where(RoomInstance.season_id == season.id, RoomInstance.tier == tier).order_by(RoomInstance.position)
            )
            .scalars()
            .all()
        )
        published = {
            p.instance_id: p
            for p in s.execute(select(PublishedManifest).where(PublishedManifest.instance_id.in_([i.id for i in instances]))).scalars()
        }
        runs = (
            s.execute(
                select(Run).where(Run.season_id == season.id, Run.instance_id.in_([i.id for i in instances]), Run.status != IN_PROGRESS)
            )
            .scalars()
            .all()
        )
        tiers[tier] = {
            "budget": TIERS[tier].budget,
            "parameters": {
                "locations": TIERS[tier].locations,
                "irrelevant_objects": TIERS[tier].decoys,
                "clue_composition_depth": TIERS[tier].depth,
                "code_digits": TIERS[tier].code_digits,
            },
            "instances": [
                {
                    "id": i.id,
                    "instance_hash": i.instance_hash,
                    "optimality": i.optimality,
                    "min_length": published[i.id].min_length if i.id in published else None,
                    "seed": published[i.id].seed if i.id in published else None,
                    "runs": sum(1 for r in runs if r.instance_id == i.id),
                    "escapes": sum(1 for r in runs if r.instance_id == i.id and r.status == ESCAPED),
                }
                for i in instances
            ],
            "endings": endings_breakdown(list(runs)),
            "leaderboard": leaderboard(s, season, tier),
        }
    participants = s.execute(select(Run.user_id).where(Run.season_id == season.id).distinct()).scalars().all()
    humans = s.execute(select(User.id).where(User.id.in_([p for p in participants if p]), User.is_system.is_(False))).scalars().all()
    return {
        "season_id": season.id,
        "name": season.name,
        "starts_at": iso(season.starts_at),
        "ends_at": iso(season.ends_at),
        "released_at": iso(season.released_at),
        "engine_version": ENGINE_VERSION,
        "generalization_level": "instance (same template, new placements and code values)",
        "participants": len(humans),
        "tiers": tiers,
        "reproduce": "Install the pinned engine, download the published manifests and replays, and run `escapement verify` on any certificate with --replay and --manifest.",
        "limits": [
            "Fresh model inference may vary even with identical settings; a certificate is evidence of one run set.",
            "Outside-agent certificates prove the actions, not which model or person chose them.",
            "Success rates are reported per tier with instance-level intervals; there is no single combined score.",
        ],
    }


def season_public(s: Session, season: Season) -> dict[str, Any]:
    instances = (
        s.execute(select(RoomInstance).where(RoomInstance.season_id == season.id).order_by(RoomInstance.tier, RoomInstance.position))
        .scalars()
        .all()
    )
    now = utcnow()
    return {
        "id": season.id,
        "name": season.name,
        "status": season_status(season),
        "starts_at": iso(season.starts_at),
        "ends_at": iso(season.ends_at),
        "released_at": iso(season.released_at),
        "tiers": season.tiers,
        "instances_per_tier": season.instances_per_tier,
        "days_left": max(0, (as_utc(season.ends_at) - now).days) if season.status != "closed" else 0,  # type: ignore[operator]
        "rules": {
            "certified_runs_per_instance": 3,
            "budgets": {t: TIERS[t].budget for t in season.tiers},
            "embargo": "Ranked replays are visible only to their owner until the season closes.",
        },
        "instances": [
            {
                "id": i.id,
                "title": i.title,
                "tier": i.tier,
                "position": i.position,
                "instance_hash": i.instance_hash,
                "manifest_public": i.manifest_public,
                "action_budget": (i.public_meta or {}).get("action_budget"),
            }
            for i in instances
        ],
        "has_report": season.report is not None,
    }
