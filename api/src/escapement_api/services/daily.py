"""The Daily Room (16.4): one Standard-tier instance from a secret-salted date
seed. Humans and agents have separate boards. Up to three attempts per day
per user. Results and the solution replay unlock after the UTC day ends.
Hinted human runs are excluded from the unassisted board (17.5)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from escapement_engine.schemas.endings import ESCAPED, INFRASTRUCTURE_ENDINGS, IN_PROGRESS

from ..models import Run, User
from ..timeutil import as_utc, day_end, iso, utc_today, utcnow
from .rooms import daily_instance_id


def board(s: Session, d: date, which: str, viewer_id: str | None) -> dict[str, Any]:
    iid = daily_instance_id(d)
    types = ["human"] if which == "humans" else ["outside", "reference"]
    runs = s.execute(
        select(Run).where(Run.instance_id == iid, Run.agent_type.in_(types), Run.status != IN_PROGRESS, Run.status.notin_(INFRASTRUCTURE_ENDINGS))
    ).scalars().all()
    unlocked = utcnow() >= day_end(d)
    participants = {r.user_id for r in runs if r.user_id}
    mine = [r for r in runs if viewer_id and r.user_id == viewer_id]
    out: dict[str, Any] = {
        "date": d.isoformat(),
        "board": which,
        "unlocked": unlocked,
        "unlocks_at": iso(day_end(d)),
        "participants": len(participants),
        "attempts": len(runs),
        "my_attempts": [_row(r, None) for r in sorted(mine, key=lambda r: as_utc(r.started_at))],  # type: ignore[arg-type, return-value]
    }
    if not unlocked:
        out["rows"] = None
        out["message"] = "Results are revealed after the UTC day ends, so nobody can copy today's route."
        return out
    best: dict[str, Run] = {}
    assisted_count = 0
    for r in runs:
        if r.user_id is None:
            continue
        if which == "humans" and r.assisted:
            assisted_count += 1
            continue
        cur = best.get(r.user_id)
        if cur is None or _rank(r) < _rank(cur):
            best[r.user_id] = r
    users = {u.id: u for u in s.execute(select(User).where(User.id.in_(list(best)))).scalars()}
    rows = []
    for uid, r in sorted(best.items(), key=lambda kv: _rank(kv[1])):
        u = users.get(uid)
        rows.append(_row(r, u if u and (u.profile_public or u.id == viewer_id or u.is_system) else None))
    for i, row in enumerate(rows):
        row["rank"] = i + 1 if row["escaped"] else None
    out["rows"] = rows
    out["assisted_excluded"] = assisted_count
    return out


def _rank(r: Run) -> tuple[int, int, int]:
    return (0 if r.status == ESCAPED else 1, r.actions_used, r.wall_time_ms or 0)


def _row(r: Run, user: User | None) -> dict[str, Any]:
    return {
        "run_id": r.id,
        "handle": user.handle if user else None,
        "agent": {"name": (r.declared or {}).get("name"), "version": (r.declared or {}).get("version")} if user else None,
        "model": (r.declared or {}).get("model") if user else None,
        "outcome": r.status,
        "escaped": r.status == ESCAPED,
        "actions_used": r.actions_used,
        "wall_time_ms": r.wall_time_ms,
        "assisted": r.assisted,
        "hints_used": r.hints_used,
        "finished_at": iso(r.finished_at),
    }


def today() -> date:
    return utc_today()
