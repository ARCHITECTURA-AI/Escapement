from __future__ import annotations

import re
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from ..deps import SESSION_COOKIE, Principal, ctx, principal, require_session, require_user
from ..errors import APIError, forbidden, not_found
from ..models import AgentVersion, ApiKey, ModerationReport, ProductEvent, Run, User, UserPrivate
from ..models import Session as DbSession
from ..security import new_api_key, new_session_token, sha256_hex
from ..services import account as account_service
from ..services.results import profile as build_profile
from ..services.results import resume_bullet, version_public, version_results
from ..timeutil import iso, utcnow

router = APIRouter(prefix="/api/v1", tags=["account"])

HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")
STATE_COOKIE = "esc_oauth_state"


def _safe_next(path: str | None) -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        return "/"
    return path


def _start_session(c, response: Response, user_id: str) -> None:  # type: ignore[no-untyped-def]
    token, digest = new_session_token()
    with c.db.service_session() as s:
        s.add(DbSession(id=digest, user_id=user_id, expires_at=utcnow() + timedelta(days=c.settings.session_days)))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=c.settings.session_days * 86400,
        httponly=True,
        secure=c.settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _unique_handle(s, wanted: str) -> str:  # type: ignore[no-untyped-def]
    base = re.sub(r"[^a-z0-9-]", "-", wanted.lower()).strip("-")[:30] or "player"
    if len(base) < 2:
        base = f"{base}-player"
    handle, n = base, 1
    while s.execute(select(User.id).where(User.handle == handle)).first():
        n += 1
        handle = f"{base}-{n}"
    return handle


# ----------------------------------------------------------------- GitHub OAuth


@router.get("/auth/github/login")
def github_login(request: Request, next: str | None = None) -> Response:
    c = ctx(request)
    if not c.settings.github_client_id:
        raise APIError(503, "GITHUB_NOT_CONFIGURED", "GitHub sign-in is not configured on this server.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": c.settings.github_client_id,
        "redirect_uri": f"{c.settings.web_base_url}/api/v1/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    resp = RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode(params), status_code=302)
    resp.set_cookie(
        STATE_COOKIE, f"{state}|{_safe_next(next)}", max_age=600, httponly=True, secure=c.settings.cookie_secure, samesite="lax", path="/"
    )
    return resp


@router.get("/auth/github/callback")
def github_callback(request: Request, code: str = "", state: str = "") -> Response:
    c = ctx(request)
    cookie = request.cookies.get(STATE_COOKIE, "")
    expected, _, nxt = cookie.partition("|")
    if not code or not state or not secrets.compare_digest(state, expected):
        return RedirectResponse(f"{c.settings.web_base_url}/signin?error=state", status_code=302)
    try:
        with httpx.Client(timeout=10) as http:
            tok = http.post(
                "https://github.com/login/oauth/access_token",
                data={"client_id": c.settings.github_client_id, "client_secret": c.settings.github_client_secret, "code": code},
                headers={"Accept": "application/json"},
            ).json()
            access = tok.get("access_token")
            if not access:
                raise ValueError("no token")
            headers = {"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"}
            gh = http.get("https://api.github.com/user", headers=headers).json()
            emails = http.get("https://api.github.com/user/emails", headers=headers).json()
    except Exception:
        return RedirectResponse(f"{c.settings.web_base_url}/signin?error=github", status_code=302)
    email = (
        next((e["email"] for e in emails if isinstance(e, dict) and e.get("primary") and e.get("verified")), None)
        if isinstance(emails, list)
        else None
    )
    with c.db.service_session() as s:
        priv = s.execute(select(UserPrivate).where(UserPrivate.github_id == int(gh["id"]))).scalar_one_or_none()
        if priv is None:
            user = User(
                handle=_unique_handle(s, gh.get("login") or "player"),
                display_name=(gh.get("name") or None),
                avatar_url=gh.get("avatar_url"),
            )
            s.add(user)
            s.flush()
            s.add(UserPrivate(user_id=user.id, email=email, github_id=int(gh["id"])))
            s.add(ProductEvent(name="signup", user_id=user.id, props={}))
            uid = user.id
        else:
            user = s.get(User, priv.user_id)
            if user is None or user.deleted_at is not None:
                return RedirectResponse(f"{c.settings.web_base_url}/signin?error=deleted", status_code=302)
            priv.email = email or priv.email
            user.avatar_url = gh.get("avatar_url") or user.avatar_url
            uid = user.id
    resp = RedirectResponse(f"{c.settings.web_base_url}{_safe_next(nxt)}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/")
    _start_session(c, resp, uid)
    return resp


@router.post("/auth/local")
async def local_login(request: Request, response: Response) -> dict[str, Any]:
    """Local research mode only: the self-hosted build has no accounts to
    protect and collects nothing, so sign-in is a single click."""
    c = ctx(request)
    if c.settings.mode != "local":
        raise APIError(403, "LOCAL_ONLY", "Local sign-in exists only in local mode. Sign in with GitHub.")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    wanted = str((body or {}).get("handle") or "local").lower()
    with c.db.service_session() as s:
        user = s.execute(select(User).where(User.handle == wanted, User.deleted_at.is_(None))).scalar_one_or_none()
        if user is None:
            if not HANDLE_RE.match(wanted):
                raise APIError(422, "INVALID_HANDLE", "Handles use lowercase letters, digits and hyphens (2 to 39 characters).")
            user = User(handle=_unique_handle(s, wanted), display_name=None, profile_public=True)
            s.add(user)
            s.flush()
            s.add(UserPrivate(user_id=user.id, email=None, github_id=None))
        uid, handle = user.id, user.handle
    _start_session(c, response, uid)
    return {"ok": True, "handle": handle}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        with ctx(request).db.service_session() as s:
            row = s.get(DbSession, sha256_hex(cookie))
            if row is not None:
                s.delete(row)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ----------------------------------------------------------------- me


def _me(s, user: User) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    priv = s.get(UserPrivate, user.id)
    runs = s.execute(select(func.count()).select_from(Run).where(Run.user_id == user.id)).scalar_one()
    certified = s.execute(select(func.count()).select_from(Run).where(Run.user_id == user.id, Run.certificate_id.isnot(None))).scalar_one()
    return {
        "id": user.id,
        "handle": user.handle,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "email": priv.email if priv else None,
        "profile_public": user.profile_public,
        "created_at": iso(user.created_at),
        "is_system": user.is_system,
        "runs": runs,
        "certified_runs": certified,
    }


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    p = principal(request)
    c = ctx(request)
    if not p.signed_in:
        return {"user": None, "mode": c.settings.mode}
    with c.db.api_session(p.user_id) as s:
        user = s.get(User, p.user_id)
        return {"user": _me(s, user), "mode": c.settings.mode, "via": p.via}  # type: ignore[arg-type]


@router.patch("/me")
async def update_me(request: Request, p: Principal = Depends(require_session)) -> dict[str, Any]:
    body = await request.json()
    with ctx(request).db.api_session(p.user_id) as s:
        user = s.get(User, p.user_id)
        if user is None:
            raise not_found()
        if "handle" in body:
            handle = str(body["handle"]).lower()
            if not HANDLE_RE.match(handle):
                raise APIError(422, "INVALID_HANDLE", "Handles use lowercase letters, digits and hyphens (2 to 39 characters).")
            if handle != user.handle and s.execute(select(User.id).where(User.handle == handle)).first():
                raise APIError(409, "HANDLE_TAKEN", "That handle is taken.")
            user.handle = handle
        if "display_name" in body:
            user.display_name = (str(body["display_name"]).strip()[:80] or None) if body["display_name"] else None
        if "profile_public" in body:
            user.profile_public = bool(body["profile_public"])
        s.flush()
        return {"user": _me(s, user)}


@router.get("/me/export")
def export_me(request: Request, response: Response, p: Principal = Depends(require_session)) -> dict[str, Any]:
    response.headers["Content-Disposition"] = 'attachment; filename="escapement-export.json"'
    with ctx(request).db.service_session() as s:
        return account_service.export(s, p.user_id)  # type: ignore[arg-type]


@router.post("/me/delete")
async def delete_me(request: Request, response: Response, p: Principal = Depends(require_session)) -> dict[str, Any]:
    body = await request.json()
    if body.get("confirm_handle") != p.handle:
        raise APIError(422, "CONFIRM", "Type your handle to confirm account deletion.")
    with ctx(request).db.service_session() as s:
        account_service.delete_account(s, p.user_id)  # type: ignore[arg-type]
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ----------------------------------------------------------------- API keys


def _key_public(k: ApiKey) -> dict[str, Any]:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": iso(k.created_at),
        "last_used_at": iso(k.last_used_at),
        "revoked_at": iso(k.revoked_at),
    }


@router.get("/me/keys")
def list_keys(request: Request, p: Principal = Depends(require_session)) -> dict[str, Any]:
    with ctx(request).db.api_session(p.user_id) as s:
        keys = s.execute(select(ApiKey).where(ApiKey.user_id == p.user_id).order_by(ApiKey.created_at.desc())).scalars().all()
        return {"keys": [_key_public(k) for k in keys]}


@router.post("/me/keys", status_code=201)
async def create_key(request: Request, p: Principal = Depends(require_session)) -> dict[str, Any]:
    body = await request.json()
    name = str(body.get("name") or "default").strip()[:80] or "default"
    c = ctx(request)
    with c.db.api_session(p.user_id) as s:
        active = s.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.user_id == p.user_id, ApiKey.revoked_at.is_(None))
        ).scalar_one()
        if active >= c.settings.max_api_keys:
            raise APIError(409, "TOO_MANY_KEYS", f"You can hold {c.settings.max_api_keys} active keys. Revoke one first.")
        key, prefix, digest = new_api_key()
        row = ApiKey(user_id=p.user_id, name=name, prefix=prefix, key_hash=digest)  # type: ignore[arg-type]
        s.add(row)
        s.flush()
        out = _key_public(row)
        out["key"] = key
        out["note"] = "Copy this key now. Escapement stores only a hash and cannot show it again."
        return out


@router.delete("/me/keys/{key_id}")
def revoke_key(key_id: str, request: Request, p: Principal = Depends(require_session)) -> dict[str, Any]:
    with ctx(request).db.api_session(p.user_id) as s:
        key = s.get(ApiKey, key_id)
        if key is None or key.user_id != p.user_id:
            raise not_found("Unknown key.")
        if key.revoked_at is None:
            key.revoked_at = utcnow()
        return _key_public(key)


# ----------------------------------------------------------------- agent versions


@router.get("/me/agents")
def my_agents(request: Request, p: Principal = Depends(require_user)) -> dict[str, Any]:
    with ctx(request).db.api_session(p.user_id) as s:
        versions = (
            s.execute(select(AgentVersion).where(AgentVersion.user_id == p.user_id).order_by(AgentVersion.created_at.desc()))
            .scalars()
            .all()
        )
        return {"agents": [version_results(s, v) for v in versions]}


@router.post("/me/agents", status_code=201)
async def create_agent(request: Request, p: Principal = Depends(require_user)) -> dict[str, Any]:
    from ..services.runs import NAME_RE, clean_text

    body = await request.json()
    name = clean_text(body.get("name"), 60)
    version = clean_text(body.get("version"), 40)
    if not name or not version or not NAME_RE.match(name) or not NAME_RE.match(version):
        raise APIError(422, "INVALID_REQUEST", "Give the agent a name and a version label (letters, digits, spaces, ._-+/).")
    with ctx(request).db.api_session(p.user_id) as s:
        if s.execute(
            select(AgentVersion.id).where(
                AgentVersion.user_id == p.user_id, AgentVersion.name == name, AgentVersion.version_label == version
            )
        ).first():
            raise APIError(409, "EXISTS", "You already have that agent version.")
        fields = {
            "declared_model": clean_text(body.get("model"), 120),
            "framework": clean_text(body.get("framework"), 120),
            "memory_strategy": clean_text(body.get("memory"), 120),
        }
        v = AgentVersion(
            user_id=p.user_id,
            name=name,
            version_label=version,
            agent_type="outside",  # type: ignore[arg-type]
            config_hash=sha256_hex(repr(sorted((k, x or "") for k, x in fields.items())) + name + version),
            notes=clean_text(body.get("notes"), 2000),
            **fields,
        )
        s.add(v)
        s.flush()
        return version_public(v)


@router.patch("/me/agents/{version_id}")
async def update_agent(version_id: str, request: Request, p: Principal = Depends(require_user)) -> dict[str, Any]:
    from ..services.runs import clean_text

    body = await request.json()
    with ctx(request).db.api_session(p.user_id) as s:
        v = s.get(AgentVersion, version_id)
        if v is None or v.user_id != p.user_id:
            raise not_found("Unknown agent version.")
        if "notes" in body:
            v.notes = clean_text(body.get("notes"), 2000)
        return version_public(v)


def _visible_owner(s, user_id: str, viewer: str | None) -> User:  # type: ignore[no-untyped-def]
    user = s.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise not_found("Unknown profile.")
    if not (user.profile_public or user.is_system or viewer == user.id):
        raise forbidden("This profile is private.")
    return user


@router.get("/agents/{version_id}")
def agent_version(version_id: str, request: Request) -> dict[str, Any]:
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        v = s.get(AgentVersion, version_id)
        if v is None:
            raise not_found("Unknown agent version.")
        owner = _visible_owner(s, v.user_id, p.user_id)
        out = version_results(s, v)
        out["owner"] = {"handle": owner.handle}
        runs = s.execute(select(Run).where(Run.agent_version_id == v.id).order_by(Run.started_at.desc()).limit(100)).scalars().all()
        now = utcnow()
        out["runs"] = [
            {
                "id": r.id,
                "instance_id": r.instance_id,
                "mode": r.mode,
                "status": r.status,
                "actions_used": r.actions_used,
                "action_budget": r.action_budget,
                "certificate_id": r.certificate_id,
                "finished_at": iso(r.finished_at),
                "embargoed": bool(
                    r.embargo_until
                    and r.embargo_until.replace(tzinfo=r.embargo_until.tzinfo or now.tzinfo) > now
                    and p.user_id != r.user_id
                ),
            }
            for r in runs
        ]
        return out


@router.get("/agents/{version_id}/bullet")
def agent_bullet(version_id: str, request: Request) -> dict[str, Any]:
    p = principal(request)
    c = ctx(request)
    with c.db.api_session(p.user_id) as s:
        v = s.get(AgentVersion, version_id)
        if v is None:
            raise not_found("Unknown agent version.")
        _visible_owner(s, v.user_id, p.user_id)
        return resume_bullet(s, v, c.settings)


@router.get("/profiles/{handle}")
def profile(handle: str, request: Request) -> dict[str, Any]:
    p = principal(request)
    with ctx(request).db.api_session(p.user_id) as s:
        user = s.execute(select(User).where(User.handle == handle.lower())).scalar_one_or_none()
        if user is None or user.deleted_at is not None:
            raise not_found("Unknown profile.")
        if not (user.profile_public or user.is_system or user.id == p.user_id):
            raise forbidden("This profile is private. Its owner can make it public in settings.")
        return build_profile(s, user, p.user_id)


@router.get("/profiles")
def profiles(request: Request, limit: int = Query(50, le=200)) -> dict[str, Any]:
    with ctx(request).db.api_session(principal(request).user_id) as s:
        users = (
            s.execute(
                select(User).where(User.profile_public.is_(True), User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        return {
            "profiles": [
                {"handle": u.handle, "display_name": u.display_name, "avatar_url": u.avatar_url, "is_system": u.is_system} for u in users
            ]
        }


# ----------------------------------------------------------------- moderation


@router.post("/reports", status_code=201)
async def report(request: Request, p: Principal = Depends(require_user)) -> dict[str, Any]:
    body = await request.json()
    target_type = body.get("target_type")
    if target_type not in ("user", "agent_version"):
        raise APIError(422, "INVALID_REQUEST", "target_type must be user or agent_version.")
    reason = str(body.get("reason") or "").strip()[:500]
    if not reason:
        raise APIError(422, "INVALID_REQUEST", "Say briefly what is wrong.")
    with ctx(request).db.api_session(p.user_id) as s:
        r = ModerationReport(reporter_id=p.user_id, target_type=target_type, target_id=str(body.get("target_id"))[:80], reason=reason)
        s.add(r)
        s.flush()
        return {"id": r.id, "ok": True}
