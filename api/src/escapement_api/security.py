from __future__ import annotations

import hashlib
import hmac
import secrets


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """Return (full_key, visible_prefix, key_hash). Keys are hashed at rest
    with a visible prefix (section 22)."""
    ident = secrets.token_hex(4)
    secret = secrets.token_urlsafe(24)
    key = f"esk_{ident}_{secret}"
    return key, f"esk_{ident}", sha256_hex(key)


def new_run_token() -> tuple[str, str]:
    token = "ert_" + secrets.token_urlsafe(32)
    return token, sha256_hex(token)


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, sha256_hex(token)


def matches(value: str, digest: str) -> bool:
    return hmac.compare_digest(sha256_hex(value), digest)


def new_certificate_id() -> str:
    return "cert_" + secrets.token_hex(10)
