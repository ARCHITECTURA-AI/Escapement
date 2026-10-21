from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import overload


def utcnow() -> datetime:
    return datetime.now(UTC)


@overload
def as_utc(dt: datetime) -> datetime: ...
@overload
def as_utc(dt: None) -> None: ...
def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    dt = as_utc(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def utc_today() -> date:
    return utcnow().date()


def day_end(d: date) -> datetime:
    """The instant a UTC day ends (the next midnight)."""
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=UTC)


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)
