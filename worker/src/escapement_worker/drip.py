"""The drip queue (15.3 #1): reads rate-limit headers and retry-after, never
bursts, and stops at 90% of the daily token limit. Usage is persisted per
provider, model and UTC day so restarts do not reset the count.

Groq free-tier limits for its main chat models at the time of checking
(section 15.1): 30 requests/minute, 1,000 requests/day, 8,000 tokens/minute,
200,000 tokens/day, per organization. Treat them as likely to change.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from escapement_api.models import Setting


@dataclass
class Limits:
    requests_per_minute: int = 30
    requests_per_day: int = 1000
    tokens_per_minute: int = 8000
    tokens_per_day: int = 200_000
    stop_fraction: float = 0.9


class DailyLimitReached(Exception):
    def __init__(self, resume_at: datetime) -> None:
        super().__init__(f"daily provider budget reached; resume at {resume_at.isoformat()}")
        self.resume_at = resume_at


def next_utc_midnight() -> datetime:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class Drip:
    def __init__(self, db, provider: str, model: str, limits: Limits | None = None, sleep=time.sleep) -> None:  # type: ignore[no-untyped-def]
        self.db = db
        self.provider = provider
        self.model = model
        self.limits = limits or Limits()
        self.sleep = sleep
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._minute_tokens: list[tuple[float, int]] = []
        self._header_wait = 0.0

    def _key(self) -> str:
        return f"reference_usage:{self.provider}:{self.model}:{datetime.now(timezone.utc).date().isoformat()}"

    def usage_today(self) -> dict[str, int]:
        with self.db.owner_session() as s:
            row = s.get(Setting, self._key())
            return dict(row.value) if row else {"tokens": 0, "requests": 0}

    def _record(self, tokens: int) -> None:
        with self.db.owner_session() as s:
            row = s.get(Setting, self._key())
            if row is None:
                s.add(Setting(key=self._key(), value={"tokens": tokens, "requests": 1}))
            else:
                row.value = {"tokens": row.value.get("tokens", 0) + tokens, "requests": row.value.get("requests", 0) + 1}

    def before_request(self, expected_tokens: int) -> None:
        """Block until a request may go out; raise when today's budget is spent."""
        lim = self.limits
        used = self.usage_today()
        if used["tokens"] + expected_tokens > lim.stop_fraction * lim.tokens_per_day or used["requests"] + 1 > lim.stop_fraction * lim.requests_per_day:
            raise DailyLimitReached(next_utc_midnight())
        with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_at - now, self._header_wait - now)
            # Token-per-minute window, kept below the published limit.
            self._minute_tokens = [(t, n) for t, n in self._minute_tokens if now - t < 60]
            window = sum(n for _, n in self._minute_tokens)
            if window + expected_tokens > lim.stop_fraction * lim.tokens_per_minute and self._minute_tokens:
                wait = max(wait, 60 - (now - self._minute_tokens[0][0]))
            if wait > 0:
                self.sleep(wait)
            # Never burst: evenly spaced requests.
            self._next_at = time.monotonic() + 60.0 / lim.requests_per_minute

    def after_response(self, tokens: int, headers: dict[str, str]) -> None:
        from .providers import parse_duration

        self._record(tokens)
        with self._lock:
            self._minute_tokens.append((time.monotonic(), tokens))
            remaining_tokens = headers.get("x-ratelimit-remaining-tokens")
            remaining_requests = headers.get("x-ratelimit-remaining-requests")
            if remaining_tokens is not None and remaining_tokens.isdigit() and int(remaining_tokens) < 1500:
                reset = headers.get("x-ratelimit-reset-tokens")
                self._header_wait = time.monotonic() + (parse_duration(reset) if reset else 15)
            if remaining_requests is not None and remaining_requests.isdigit() and int(remaining_requests) < 2:
                reset = headers.get("x-ratelimit-reset-requests")
                self._header_wait = max(self._header_wait, time.monotonic() + (parse_duration(reset) if reset else 30))

    def backoff(self, seconds: float) -> None:
        with self._lock:
            self._header_wait = max(self._header_wait, time.monotonic() + seconds)
