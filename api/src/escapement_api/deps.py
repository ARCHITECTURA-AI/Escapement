"""Request authentication.

* `Authorization: Bearer esk_...`  API key (outside agents, SDK, MCP).
* `esc_session` cookie             signed-in browser (web play, settings).
* neither                          anonymous; allowed only for Practice play
                                   and public reads.

Cookie-authenticated writes must carry `X-Escapement-Client: web`. Browsers
cannot add that header cross-site without a CORS preflight, which the API
never grants, so it doubles as CSRF protection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from sqlalchemy import select, update

from .errors import APIError, unauthorized
from .models import ApiKey, Session, User
from .security import sha256_hex
from .timeutil import as_utc, utcnow

SESSION_COOKIE = "esc_session"
CSRF_HEADER = "x-escapement-client"


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    handle: str | None = None
    via: str = "anonymous"  # api_key | session | anonymous
    api_key_id: str | None = None
    is_system: bool = False
    created_at: datetime | None = None

    @property
    def signed_in(self) -> bool:
        return self.user_id is not None


ANONYMOUS = Principal(user_id=None)


def ctx(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.ctx


def client_fingerprint(request: Request) -> str:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")
    return sha256_hex("anon:" + ip)


def resolve_principal(request: Request) -> Principal:
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    c = ctx(request)
    principal = ANONYMOUS
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token.startswith("esk_"):
            principal = _from_api_key(c, token)
        elif token.startswith("ert_"):
            principal = ANONYMOUS  # run tokens are checked per run
        else:
            raise unauthorized("Unrecognised bearer token. API keys start with esk_.")
    else:
        cookie = request.cookies.get(SESSION_COOKIE)
        if cookie:
            principal = _from_session(c, cookie)
            if principal.signed_in and request.method not in ("GET", "HEAD", "OPTIONS"):
                if request.headers.get(CSRF_HEADER) != "web":
                    raise APIError(403, "CSRF", "Cookie-authenticated writes need the X-Escapement-Client header.")
    request.state.principal = principal
    return principal


def _from_api_key(c, token: str) -> Principal:  # type: ignore[no-untyped-def]
    digest = sha256_hex(token)
    with c.db.service_session() as s:
        row = s.execute(
            select(ApiKey, User).join(User, User.id == ApiKey.user_id).where(ApiKey.key_hash == digest)
        ).first()
        if row is None:
            raise unauthorized("Unknown API key.")
        key, user = row
        if key.revoked_at is not None:
            raise unauthorized("This API key has been revoked.")
        if user.deleted_at is not None:
            raise unauthorized("This account has been deleted.")
        s.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=utcnow()))
        return Principal(user.id, user.handle, "api_key", key.id, user.is_system, as_utc(user.created_at))


def _from_session(c, cookie: str) -> Principal:  # type: ignore[no-untyped-def]
    digest = sha256_hex(cookie)
    with c.db.service_session() as s:
        row = s.execute(select(Session, User).join(User, User.id == Session.user_id).where(Session.id == digest)).first()
        if row is None:
            return ANONYMOUS
        sess, user = row
        if as_utc(sess.expires_at) < utcnow() or user.deleted_at is not None:
            return ANONYMOUS
        return Principal(user.id, user.handle, "session", None, user.is_system, as_utc(user.created_at))


def principal(request: Request) -> Principal:
    return resolve_principal(request)


def require_user(request: Request) -> Principal:
    p = resolve_principal(request)
    if not p.signed_in:
        raise unauthorized()
    return p


def require_session(request: Request) -> Principal:
    p = resolve_principal(request)
    if p.via != "session":
        raise unauthorized("Sign in with GitHub in the browser to do this.")
    return p
