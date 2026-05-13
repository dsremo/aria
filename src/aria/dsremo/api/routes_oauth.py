"""Google OAuth2 sign-in flow.

Flow:
  1. GET /auth/google          → redirect to Google consent screen
  2. GET /auth/google/callback → exchange code → issue JWT → redirect to /dashboard/

Security:
  - State parameter: HMAC-SHA256(nonce, JWT_SECRET) prevents CSRF.
    The nonce is embedded in the state so the callback can verify it
    without server-side session storage.
  - Google ID token is NOT used — we exchange the code for an access token
    and then call the userinfo endpoint directly. Simpler, no JWT parsing needed.
  - New users get their own tenant (id = "t-{uuid4}") and the 'free' plan.
  - avatar_url and display_name are refreshed on every login.

Environment variables required:
  GOOGLE_CLIENT_ID       — from Google Cloud Console
  GOOGLE_CLIENT_SECRET   — from Google Cloud Console
  GOOGLE_REDIRECT_URI    — must match exactly what's registered in GCP
                           e.g. https://yourdomain.com/api/v1/auth/google/callback
  DSREMO_JWT_SECRET    — already required for existing auth
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import urllib.parse
import uuid

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from aria.dsremo.core.security import create_access_token
from aria.dsremo.db import queries

logger = structlog.get_logger()
oauth_router = APIRouter(prefix="/auth", tags=["auth"])

_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v3/userinfo"

_DEFAULT_ACCESS_TTL  = 900       # 15 min
_DEFAULT_REFRESH_TTL = 604_800   # 7 days


def _google_client_id() -> str:
    v = os.environ.get("GOOGLE_CLIENT_ID", "")
    if not v:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    return v


def _google_client_secret() -> str:
    v = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not v:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    return v


def _redirect_uri() -> str:
    return os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8400/api/v1/auth/google/callback",
    )


def _make_state(nonce: str, secret: str) -> str:
    """HMAC-sign the nonce so the callback can verify it without server-side storage."""
    sig = hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{sig}"


def _verify_state(state: str, secret: str) -> bool:
    """Verify the HMAC-signed state parameter. Constant-time comparison."""
    try:
        nonce, sig = state.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------------------
# GET /auth/google  → redirect to Google
# ---------------------------------------------------------------------------

@oauth_router.get("/google")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the user's browser to Google's OAuth consent screen."""
    secret = getattr(request.app.state, "jwt_secret", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Auth not configured — set DSREMO_JWT_SECRET")

    nonce = secrets.token_urlsafe(16)
    state = _make_state(nonce, secret)

    params = {
        "client_id":     _google_client_id(),
        "redirect_uri":  _redirect_uri(),
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


# ---------------------------------------------------------------------------
# GET /auth/google/callback  → exchange code → issue JWT → redirect to /dashboard/
# ---------------------------------------------------------------------------

@oauth_router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle Google's redirect back after user consents (or denies)."""
    # 1. Handle user-denied case
    if error:
        logger.warning("google_oauth_denied", error=error)
        return RedirectResponse(url="/?error=access_denied", status_code=302)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # 2. Verify CSRF state
    secret = getattr(request.app.state, "jwt_secret", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Auth not configured")

    if not _verify_state(state, secret):
        logger.warning("google_oauth_state_mismatch", state=state[:20])
        raise HTTPException(status_code=400, detail="Invalid state parameter — possible CSRF")

    # 3. Exchange authorization code for Google access token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code":          code,
                    "client_id":     _google_client_id(),
                    "client_secret": _google_client_secret(),
                    "redirect_uri":  _redirect_uri(),
                    "grant_type":    "authorization_code",
                },
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()

            # 4. Fetch Google user profile
            user_resp = await client.get(
                _GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            user_resp.raise_for_status()
            google_user = user_resp.json()

    except httpx.HTTPError as exc:
        logger.error("google_token_exchange_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Failed to communicate with Google")

    google_id    = google_user.get("sub", "")
    email        = google_user.get("email", "")
    display_name = google_user.get("name", "")
    avatar_url   = google_user.get("picture", "")

    if not google_id or not email:
        raise HTTPException(status_code=502, detail="Google did not return user identity")

    # 5. Find or create user
    settings    = getattr(request.app.state, "settings", {})
    access_ttl  = int(settings.get("auth", {}).get("access_token_ttl_seconds", _DEFAULT_ACCESS_TTL))
    refresh_ttl = int(settings.get("auth", {}).get("refresh_token_ttl_seconds", _DEFAULT_REFRESH_TTL))

    existing    = await queries.get_user_by_google_id(google_id)
    is_new_user = False

    if existing:
        user       = existing
        tenant_id  = user["tenant_id"]
    else:
        # New user — create a dedicated tenant and the user record.
        tenant_id  = f"t-{uuid.uuid4().hex[:12]}"
        await queries.create_tenant(tenant_id, name=email, plan="free")
        user = await queries.upsert_google_user(
            google_id=google_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            tenant_id=tenant_id,
            role="admin",   # first user in their own tenant is always admin
            plan="free",
        )
        logger.info("google_signup", email=email[:3] + "***", tenant_id=tenant_id)
        is_new_user = True

    if not user["active"]:
        return RedirectResponse(url="/?error=account_inactive", status_code=302)

    # 6. Issue Dsremo JWT (same structure as email/password login)
    access_token = create_access_token(
        user_id=user["id"],
        tenant_id=tenant_id,
        role=user["role"],
        secret=secret,
        ttl_seconds=access_ttl,
        email=email,
    )

    # 7. Store refresh token
    import hashlib as _hl, secrets as _sec
    from datetime import datetime, timedelta, timezone
    from aria.dsremo.core.tenant import set_tenant

    refresh_token = _sec.token_urlsafe(48)
    token_hash    = _hl.sha256(refresh_token.encode()).hexdigest()
    expires_at    = datetime.now(timezone.utc) + timedelta(seconds=refresh_ttl)

    set_tenant(tenant_id)
    await queries.store_refresh_token(user["id"], token_hash, expires_at)
    await queries.update_last_login(user["id"])

    logger.info("google_login_success", user_id=user["id"], tenant=tenant_id)

    # 8. Redirect to dashboard — tokens passed as URL fragment (never hits server logs)
    #    Dashboard JS reads fragment, stores in localStorage, clears URL.
    fragment = urllib.parse.urlencode({
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "plan":          user.get("plan") or "free",
        "new_user":      "1" if is_new_user else "0",
    })
    return RedirectResponse(url=f"/dashboard/#{fragment}", status_code=302)
