from __future__ import annotations

from typing import Any


class EscapementError(Exception):
    """An error response from the Escapement API."""

    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.retry_after = retry_after


class RunFinished(EscapementError):
    """The run has ended; no further actions execute."""
