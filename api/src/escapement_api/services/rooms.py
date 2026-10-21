"""Rooms: Practice, the Daily Room, ranked season instances and research
instances. Public room descriptions and private manifests are separate
objects stored separately (19.4)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from escapement_engine.core import CompiledRoom
from escapement_engine.generation import (
    PRACTICE_ROOM_ID,
    GeneratedInstance,
    build_practice,
    daily_seed,
    generate,
    load_manifest,
)
from escapement_engine.rooms.emergency_lockdown import FAMILY, FAMILY_TITLE, TEMPLATE_VERSION, TIERS
from escapement_engine.version import ENGINE_VERSION

from ..config import Settings
from ..errors import APIError, not_found
from ..models import DailyRoom, PublishedManifest, RoomInstance, RoomTemplate, SealedManifest, Season
from ..timeutil import day_end, utc_today, utcnow


def template_id(tier: str, family: str = FAMILY) -> str:
    return f"{family}:{TEMPLATE_VERSION}:{tier}"


def ensure_template(s: Session, tier: str) -> str:
    tid = template_id(tier)
    if s.get(RoomTemplate, tid) is None:
        p = TIERS[tier]
        s.add(
            RoomTemplate(
                id=tid,
                family=FAMILY,
                version=TEMPLATE_VERSION,
                engine_version=ENGINE_VERSION,
                tier=tier,
                difficulty={
                    "locations": p.locations,
                    "irrelevant_objects": p.decoys,
                    "clue_composition_depth": p.depth,
                    "code_digits": p.code_digits,
                    "action_budget": p.budget,
                    "ranked": p.ranked,
                },
                sealed=p.ranked,
            )
        )
        s.flush()
    return tid


def public_meta(g: GeneratedInstance) -> dict[str, Any]:
    m = g.manifest
    return {
        "family": m.family,
        "family_title": FAMILY_TITLE,
        "template_version": m.template_version,
        "engine_version": m.engine_version,
        "intro": m.intro,
        "goal": m.goal_text,
        "action_budget": m.budget.actions,
        "malformed_limit": m.budget.malformed,
        "wrong_code_free_attempts": m.budget.wrong_code_free_attempts,
        "wrong_code_penalty": m.budget.wrong_code_penalty,
        "locations": sum(1 for loc in m.locations if not loc.terminal),
    }


def store_instance(
    s: Session,
    g: GeneratedInstance,
    *,
    kind: str,
    season_id: str | None = None,
    position: int = 0,
    publish: bool = False,
) -> RoomInstance:
    m = g.manifest
    tid = ensure_template(s, m.tier)
    inst = RoomInstance(
        id=m.room_id,
        template_id=tid,
        season_id=season_id,
        kind=kind,
        tier=m.tier,
        title=m.title,
        public_meta=public_meta(g),
        instance_hash=g.instance_hash,
        validation_status="passed" if g.report.passed else "failed",
        optimality=g.optimality,
        position=position,
        manifest_public=publish,
    )
    s.add(inst)
    s.flush()
    s.add(
        SealedManifest(
            instance_id=m.room_id,
            manifest=m.model_dump(mode="json"),
            seed=m.seed,
            solution=g.solution,
            min_length=g.min_length,
            validation=g.report.to_dict(),
        )
    )
    if publish:
        s.add(
            PublishedManifest(
                instance_id=m.room_id,
                manifest=m.model_dump(mode="json"),
                seed=m.seed,
                solution=g.solution,
                min_length=g.min_length,
                optimality=g.optimality,
            )
        )
    s.flush()
    return inst


def ensure_practice(s: Session) -> RoomInstance:
    inst = s.get(RoomInstance, PRACTICE_ROOM_ID)
    if inst is None:
        inst = store_instance(s, _practice(), kind="practice", publish=True)
    return inst


@lru_cache(maxsize=1)
def _practice() -> GeneratedInstance:
    return build_practice()


def daily_instance_id(d: date) -> str:
    return f"daily-{d.isoformat()}"


def get_or_create_daily(s: Session, settings: Settings, d: date | None = None) -> RoomInstance:
    d = d or utc_today()
    row = s.get(DailyRoom, d)
    if row is not None:
        return s.get(RoomInstance, row.instance_id)  # type: ignore[return-value]
    iid = daily_instance_id(d)
    inst = s.get(RoomInstance, iid)
    if inst is None:
        g = generate("standard", daily_seed(settings.seed_secret, d.isoformat()), iid)
        inst = store_instance(s, g, kind="daily")
        inst.title = f"Daily Room · {d.isoformat()}"
    s.add(DailyRoom(date=d, instance_id=iid))
    s.flush()
    return inst


def publish_instance(s: Session, instance_id: str) -> None:
    inst = s.get(RoomInstance, instance_id)
    sealed = s.get(SealedManifest, instance_id)
    if inst is None or sealed is None:
        return
    if s.get(PublishedManifest, instance_id) is None:
        s.add(
            PublishedManifest(
                instance_id=instance_id,
                manifest=sealed.manifest,
                seed=sealed.seed,
                solution=sealed.solution,
                min_length=sealed.min_length,
                optimality=inst.optimality,
            )
        )
    inst.manifest_public = True


def publish_past_dailies(s: Session) -> int:
    today = utc_today()
    rows = s.execute(
        select(DailyRoom).join(RoomInstance, RoomInstance.id == DailyRoom.instance_id).where(
            DailyRoom.date < today, RoomInstance.manifest_public.is_(False)
        )
    ).scalars().all()
    for row in rows:
        publish_instance(s, row.instance_id)
    return len(rows)


_manifest_cache: dict[tuple[str, str], CompiledRoom] = {}


def load_room(s: Session, instance_id: str) -> CompiledRoom:
    """Service-role only: reads the sealed manifest."""
    inst = s.get(RoomInstance, instance_id)
    if inst is None:
        raise not_found("Unknown room.")
    key = (instance_id, inst.instance_hash)
    room = _manifest_cache.get(key)
    if room is None:
        sealed = s.get(SealedManifest, instance_id)
        if sealed is None:
            raise APIError(500, "ENGINE_ERROR", "Room manifest missing.")
        room = CompiledRoom(load_manifest(sealed.manifest))
        if len(_manifest_cache) > 256:
            _manifest_cache.clear()
        _manifest_cache[key] = room
    return room


def sealed_solution(s: Session, instance_id: str) -> tuple[list[Any], int | None]:
    sealed = s.get(SealedManifest, instance_id)
    if sealed is None:
        return [], None
    return list(sealed.solution), sealed.min_length


def room_public(inst: RoomInstance, season: Season | None = None) -> dict[str, Any]:
    meta = dict(inst.public_meta or {})
    out = {
        "id": inst.id,
        "title": inst.title,
        "kind": inst.kind,
        "tier": inst.tier,
        "ranked": inst.kind == "ranked",
        "season_id": inst.season_id,
        "instance_hash": inst.instance_hash,
        "manifest_public": inst.manifest_public,
        "position": inst.position,
        **meta,
    }
    if season is not None:
        out["season"] = {"id": season.id, "name": season.name, "status": season_status(season)}
    if inst.kind == "daily":
        d = date.fromisoformat(inst.id.removeprefix("daily-"))
        out["date"] = d.isoformat()
        out["unlocks_at"] = day_end(d).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def season_status(season: Season) -> str:
    if season.status == "closed":
        return "closed"
    now = utcnow()
    from ..timeutil import as_utc

    if as_utc(season.starts_at) > now:  # type: ignore[operator]
        return "scheduled"
    if as_utc(season.ends_at) <= now:  # type: ignore[operator]
        return "ended"  # awaiting the close job, still embargoed
    return "open"
