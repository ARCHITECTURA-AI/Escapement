"""Canonical JSON and hashing (section 9.5).

canonical_json = UTF-8, sorted keys, no extra whitespace, integers only.
Floats are rejected outright so that no platform-dependent number formatting
can ever reach a hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class CanonicalError(ValueError):
    """Raised when a value cannot be represented canonically."""


def _check(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise CanonicalError(f"float at {path}: canonical JSON allows integers only")
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"non-string key at {path}")
            _check(item, f"{path}.{key}")
        return
    raise CanonicalError(f"unsupported type {type(value).__name__} at {path}")


def canonical_json(value: Any) -> str:
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_value(value: Any) -> str:
    return sha256_hex(canonical_bytes(value))
