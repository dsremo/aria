"""FastAPI auth dependencies — JWT + API key, unified interface.

Every protected route declares one of these as a Depends parameter.
The dependency checks Bearer JWT first, then falls back to X-API-Key,
so both human users (JWT) and machine clients (API key) work transparently.
"""

from __future__ import annotations

import hashlib

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from aria.dsremo.core.security import decode_access_token
from aria.dsremo.core.tenant import set_tenant

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Validate Bearer JWT or X-API-Key. Returns {user_id, tenant_id, role}.

    Priority:
      1. Bearer JWT — for human users / dashboard login
      2. X-API-Key  — for machine clients (CLI scripts, external integrations)

    On success, sets the tenant ContextVar so RLS filters DB queries correctly.
    """
    # 1. Try JWT Bearer token
    if credentials:
        secret = getattr(request.app.state, "jwt_secret", "")
        if not secret:
            raise HTTPException(
                status_code=503,
                detail="Auth not configured — set DSREMO_JWT_SECRET",
            )
        try:
            payload = decode_access_token(credentials.credentials, secret)
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid or expired token: {exc}",
            ) from exc

        if payload.get("scope") == "dsremo":
            # Dsremo internal user — cross-tenant; X-Tenant-ID header sets context.
            x_tenant = request.headers.get("X-Tenant-ID", "")
            if x_tenant:
                set_tenant(x_tenant)
            return {
                "user_id": payload["sub"],
                "tenant_id": x_tenant or None,
                "role": payload["role"],
                "scope": "dsremo",
                "email": payload.get("email", ""),
            }

        # Normal tenant JWT
        set_tenant(payload["tid"])
        return {
            "user_id": payload["sub"],
            "tenant_id": payload["tid"],
            "role": payload["role"],
            "email": payload.get("email", ""),
        }

    # 2. Fall back to X-API-Key (machine clients / service accounts)
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        key_hash = hashlib.sha256(f"dsremo::{api_key}".encode()).hexdigest()
        key_tenant_map: dict[str, str] = getattr(
            request.app.state, "api_key_tenant_map", {}
        )
        tenant_id = key_tenant_map.get(key_hash)
        if tenant_id:
            set_tenant(tenant_id)
            # API key holders are treated as operator-level service accounts.
            return {"user_id": None, "tenant_id": tenant_id, "role": "operator"}

    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(*allowed_roles: str):
    """RBAC Depends factory.

    Usage:
        @router.get("/protected")
        async def handler(_user: dict = Depends(require_role("admin", "operator"))):
            ...

    Returns a FastAPI dependency function that delegates to get_current_user and
    then checks the role. Re-uses the same user dict so there's no double auth.
    """
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Role '{user['role']}' is not permitted. "
                    f"Required: {', '.join(allowed_roles)}"
                ),
            )
        return user
    return checker


# ---------------------------------------------------------------------------
# Convenience shortcuts — import directly in route files
# ---------------------------------------------------------------------------

# Dsremo-internal routes (cross-tenant, no X-Tenant-ID needed)
require_dsremo        = require_role("superuser", "dsremo_admin", "developer")
require_dsremo_admin  = require_role("superuser", "dsremo_admin")

# Tenant admin-level — includes dsremo roles so they can operate via X-Tenant-ID
require_tenant_admin    = require_role("admin", "superuser", "dsremo_admin")
require_tenant_manager  = require_role("admin", "tenant_manager", "superuser", "dsremo_admin")

# Updated to include dsremo roles (they can act as any tenant role via X-Tenant-ID)
require_admin    = require_role("admin", "superuser", "dsremo_admin")
require_operator = require_role("admin", "tenant_manager", "operator", "superuser", "dsremo_admin")
require_viewer   = require_role(
    "admin", "tenant_manager", "operator", "viewer", "report_only",
    "superuser", "dsremo_admin", "developer",
)
