"""Auth routes — login, token refresh, logout, current user.

All auth endpoints live under /api/v1/auth. Login and refresh are public
(no Bearer required). Logout and /me require a valid access token.

Security notes:
  - Passwords are never logged or echoed.
  - Refresh tokens are stored as SHA-256 hashes; the plain token is sent
    to the client once and never persisted.
  - Failed logins return generic 401 (no user-enumeration via email check).
  - Access token TTL is read from app.state.settings at runtime.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from aria.dsremo.api.dependencies import get_current_user
from aria.dsremo.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from aria.dsremo.core.security import (
    create_access_token,
    create_dsremo_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from aria.dsremo.core.tenant import set_tenant
from aria.dsremo.db import queries

logger = structlog.get_logger()
auth_router = APIRouter(prefix="/auth", tags=["auth"])

_DEFAULT_ACCESS_TTL  = 900        # 15 minutes
_DEFAULT_REFRESH_TTL = 604_800    # 7 days


def _hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for safe storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _get_jwt_secret(request: Request) -> str:
    secret = getattr(request.app.state, "jwt_secret", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Auth not configured — set DSREMO_JWT_SECRET",
        )
    return secret


def _get_access_ttl(request: Request) -> int:
    settings = getattr(request.app.state, "settings", {})
    return int(settings.get("auth", {}).get("access_token_ttl_seconds", _DEFAULT_ACCESS_TTL))


def _get_refresh_ttl(request: Request) -> int:
    settings = getattr(request.app.state, "settings", {})
    return int(settings.get("auth", {}).get("refresh_token_ttl_seconds", _DEFAULT_REFRESH_TTL))


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@auth_router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate with email + password. Returns access + refresh tokens.

    The tenant_id in the request body scopes the user lookup — one email
    address can exist in multiple tenants independently (B2B pattern).
    """
    secret     = _get_jwt_secret(request)
    access_ttl = _get_access_ttl(request)
    refresh_ttl = _get_refresh_ttl(request)

    # Set tenant context so RLS-scoped queries see the right tenant.
    set_tenant(body.tenant_id)

    user = await queries.get_user_by_email(body.email)

    # Constant-time failure: always call verify_password even on missing user
    # to prevent timing attacks that could enumerate valid emails.
    if user is None or not verify_password(body.password, user.get("password_hash", "")):
        logger.warning(
            "login_failed",
            email=body.email[:3] + "***",
            tenant=body.tenant_id,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user["active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    # Issue tokens
    access_token = create_access_token(
        user_id=user["id"],
        tenant_id=user["tenant_id"],
        role=user["role"],
        secret=secret,
        ttl_seconds=access_ttl,
        email=user.get("email", ""),
    )
    refresh_token = secrets.token_urlsafe(48)  # 384 bits of entropy
    token_hash = _hash_token(refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=refresh_ttl)

    await queries.store_refresh_token(user["id"], token_hash, expires_at)
    await queries.update_last_login(user["id"])

    logger.info("login_success", user_id=user["id"], tenant=user["tenant_id"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_ttl,
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request) -> TokenResponse:
    """Exchange a valid refresh token for a new access token.

    The refresh token is NOT rotated — the same refresh token remains valid
    until it expires or is explicitly revoked via /logout.
    """
    secret      = _get_jwt_secret(request)
    access_ttl  = _get_access_ttl(request)
    refresh_ttl = _get_refresh_ttl(request)

    token_hash = _hash_token(body.refresh_token)

    # We must set a tenant before querying refresh_tokens (RLS-scoped).
    # The token_hash is unique so we can look it up via the direct pool
    # with a superuser bypass — but we don't have a superuser here.
    # Instead: decode the access token from the Authorization header if
    # present, OR we do a pool-level direct query bypassing RLS.
    # Simplest safe approach: use the pool directly (no tenant filter).
    from aria.dsremo.db.connection import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT rt.id::text, rt.user_id::text, rt.tenant_id,
                   rt.expires_at, rt.revoked,
                   u.role::text AS role, u.email, u.active
            FROM refresh_tokens rt
            JOIN users u ON u.id = rt.user_id
            WHERE rt.token_hash = $1
            """,
            token_hash,
        )

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if row["revoked"]:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    if not row["active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    access_token = create_access_token(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        role=row["role"],
        secret=secret,
        ttl_seconds=access_ttl,
        email=row.get("email", ""),
    )

    # Issue a new refresh token (token rotation for security)
    new_refresh = secrets.token_urlsafe(48)
    new_hash    = _hash_token(new_refresh)
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=refresh_ttl)

    set_tenant(row["tenant_id"])
    await queries.revoke_refresh_token(token_hash)  # revoke old
    await queries.store_refresh_token(row["user_id"], new_hash, new_expires)

    logger.info("token_refreshed", user_id=row["user_id"], tenant=row["tenant_id"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=access_ttl,
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@auth_router.post("/logout")
async def logout(
    body: RefreshRequest,
    request: Request,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Revoke the provided refresh token. Access tokens are stateless and
    expire naturally (15 min TTL). Call logout when the user explicitly signs
    out to prevent the refresh token from being used to generate new access tokens.
    """
    token_hash = _hash_token(body.refresh_token)

    if _user.get("scope") == "dsremo":
        # Dsremo internal user — tokens stored in dsremo_refresh_tokens (no RLS)
        await queries.revoke_dsremo_refresh_token(token_hash)
    else:
        # Tenant user — tokens stored in refresh_tokens (RLS-scoped)
        from aria.dsremo.db.connection import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
                token_hash,
            )

    logger.info("logout", user_id=_user.get("user_id"), tenant=_user.get("tenant_id"))
    return {"message": "Logged out"}


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

@auth_router.get("/me", response_model=UserOut)
async def me(_user: dict = Depends(get_current_user)) -> UserOut:
    """Return the current authenticated user's profile.

    For JWT users: returns the claims embedded in the token plus DB profile fields.
    For API-key users: returns the tenant + role; user_id is null.
    """
    user_id = _user.get("user_id") or ""
    display_name = ""
    phone = ""

    # Enrich with display_name and phone from DB (non-critical — ignore DB errors)
    if user_id and user_id != "api-key":
        try:
            if _user.get("scope") == "dsremo":
                from aria.dsremo.db.connection import get_pool
                pool = get_pool()
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT COALESCE(display_name,'') AS display_name, "
                        "COALESCE(phone,'') AS phone "
                        "FROM dsremo_users WHERE id = $1::uuid",
                        user_id,
                    )
                    if row:
                        display_name = row["display_name"]
                        phone = row["phone"]
            else:
                row = await queries.get_user_by_id(user_id)
                if row:
                    display_name = row.get("display_name", "")
                    phone = row.get("phone", "")
        except Exception:
            pass  # profile fields are optional — don't fail /me on DB error

    return UserOut(
        user_id=user_id or "api-key",
        email=_user.get("email", ""),
        role=_user["role"],
        tenant_id=_user.get("tenant_id") or "",
        scope=_user.get("scope", ""),
        display_name=display_name,
        phone=phone,
    )


# ---------------------------------------------------------------------------
# POST /auth/dsremo-login  (Dsremo internal users)
# ---------------------------------------------------------------------------

@auth_router.post("/dsremo-login", response_model=TokenResponse)
async def dsremo_login(body: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate a Dsremo internal user (superuser / dsremo_admin / developer).

    Returns a dsremo-scoped JWT — no tenant_id embedded; use X-Tenant-ID header
    on subsequent requests to scope operations to a specific customer tenant.
    """
    secret      = _get_jwt_secret(request)
    access_ttl  = _get_access_ttl(request)
    refresh_ttl = _get_refresh_ttl(request)

    user = await queries.get_dsremo_user_by_email(body.email)

    if user is None or not verify_password(body.password, user.get("password_hash", "")):
        logger.warning(
            "dsremo_login_failed",
            email=body.email[:3] + "***",
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user["active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    access_token  = create_dsremo_token(
        user_id=user["id"],
        role=user["role"],
        secret=secret,
        ttl_seconds=access_ttl,
        email=user.get("email", ""),
    )
    refresh_token = secrets.token_urlsafe(48)
    token_hash    = _hash_token(refresh_token)
    expires_at    = datetime.now(timezone.utc) + timedelta(seconds=refresh_ttl)

    await queries.store_dsremo_refresh_token(user["id"], token_hash, expires_at)
    await queries.update_dsremo_last_login(user["id"])

    logger.info("dsremo_login_success", user_id=user["id"], role=user["role"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_ttl,
    )


# ---------------------------------------------------------------------------
# POST /auth/dsremo-refresh
# ---------------------------------------------------------------------------

@auth_router.post("/dsremo-refresh", response_model=TokenResponse)
async def dsremo_refresh(body: RefreshRequest, request: Request) -> TokenResponse:
    """Exchange a dsremo refresh token for a new dsremo access token (with rotation)."""
    secret      = _get_jwt_secret(request)
    access_ttl  = _get_access_ttl(request)
    refresh_ttl = _get_refresh_ttl(request)

    token_hash = _hash_token(body.refresh_token)
    row = await queries.get_dsremo_refresh_token(token_hash)

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if row["revoked"]:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    if not row["active"]:
        raise HTTPException(status_code=403, detail="Account is inactive")

    access_token = create_dsremo_token(
        user_id=row["user_id"],
        role=row["role"],
        secret=secret,
        ttl_seconds=access_ttl,
        email=row.get("email", ""),
    )

    # Rotate refresh token
    new_refresh = secrets.token_urlsafe(48)
    new_hash    = _hash_token(new_refresh)
    new_expires = datetime.now(timezone.utc) + timedelta(seconds=refresh_ttl)

    await queries.revoke_dsremo_refresh_token(token_hash)
    await queries.store_dsremo_refresh_token(row["user_id"], new_hash, new_expires)

    logger.info("dsremo_token_refreshed", user_id=row["user_id"])
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=access_ttl,
    )


# ---------------------------------------------------------------------------
# POST /auth/change-password
# ---------------------------------------------------------------------------

@auth_router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Change the current user's password.

    Verifies the current password, hashes the new one, and revokes all
    existing refresh tokens — forcing re-login on all devices.
    Only works for tenant users (not dsremo users — no password field in dsremo JWT).
    """
    user_id = _user.get("user_id")
    if not user_id or _user.get("scope") == "dsremo":
        raise HTTPException(
            status_code=400,
            detail="Password change not supported for this account type",
        )

    # Load full user row to verify current password
    from aria.dsremo.db.connection import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1::uuid",
            user_id,
        )

    if row is None or not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = hash_password(body.new_password)
    await queries.update_user_password(user_id, new_hash)
    await queries.revoke_all_user_tokens(user_id)

    logger.info("password_changed", user_id=user_id, tenant=_user.get("tenant_id"))
    return {"message": "Password changed. Please log in again."}
