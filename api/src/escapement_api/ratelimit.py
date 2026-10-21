"""Fixed-window rate limits stored in Postgres, so they hold across processes.
Every refusal carries Retry-After (section 20.4)."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from .errors import APIError
from .models import RateCounter


def hit(session: Session, key: str, limit: int, window_s: int = 60, now: float | None = None) -> None:
    now = time.time() if now is None else now
    window = int(now // window_s) * window_s
    dialect = session.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    stmt = insert(RateCounter).values(key=key, window_start=window, count=1)
    stmt = stmt.on_conflict_do_update(index_elements=["key", "window_start"], set_={"count": RateCounter.count + 1})
    session.execute(stmt)
    count = session.execute(select(RateCounter.count).where(RateCounter.key == key, RateCounter.window_start == window)).scalar_one()
    if count > limit:
        retry = max(1, int(window + window_s - now))
        raise APIError(
            429,
            "RATE_LIMITED",
            f"Rate limit of {limit} requests per {window_s}s reached for this {key.split(':')[0]}.",
            {"retry_after": retry},
            {"Retry-After": str(retry)},
        )
