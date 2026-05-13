"""User management routes — CRUD for tenant users.

Tenant admins manage users within their own tenant (RLS enforces scoping).
Dsremo admins can operate on any tenant via X-Tenant-ID header.

Routes:
  POST  /users                  — Create a new user
  GET   /users                  — List all users in current tenant
  GET   /users/{id}             — Get user by ID
  PATCH /users/{id}/role        — Change a user's role
  POST  /users/{id}/deactivate  — Deactivate a user
  POST  /users/{id}/reactivate  — Reactivate a deactivated user

RBAC:
  All routes require at minimum tenant_admin level (admin, superuser, dsremo_admin).
  Role escalation guard: a requester cannot assign a role higher than their own tier.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

import aria.dsremo.db.queries as queries
from aria.dsremo.api.dependencies import require_tenant_admin
from aria.dsremo.api.errors import handle_unique_constraint
from aria.dsremo.api.schemas import (
    AdminResetPasswordRequest,
    UpdateRoleRequest,
    UserCreateRequest,
    UserDetailOut,
)
from aria.dsremo.core.security import hash_password

logger = structlog.get_logger()
users_router = APIRouter(prefix="/users", tags=["users"])

# ---------------------------------------------------------------------------
# Role escalation guard
# ---------------------------------------------------------------------------

_TENANT_ROLE_TIER: dict[str, int] = {
    "report_only":   0,
    "viewer":        1,
    "operator":      2,
    "tenant_manager": 3,
    "admin":         4,
}
_DSREMO_ROLES = frozenset({"developer", "dsremo_admin", "superuser"})


def _max_assignable_tier(requester_role: str) -> int:
    """Return the highest role tier a requester may assign.

    Dsremo users (any dsremo role) can assign any tenant role (up to tier 4).
    Tenant admins can assign up to their own tier.
    """
    if requester_role in _DSREMO_ROLES:
        return 4
    return _TENANT_ROLE_TIER.get(requester_role, -1)


def _check_role_escalation(requester_role: str, target_role: str) -> None:
    """Raise 403 if assigning target_role would be an escalation for the requester."""
    target_tier = _TENANT_ROLE_TIER.get(target_role, -1)
    max_tier    = _max_assignable_tier(requester_role)
    if target_tier < 0:
        raise HTTPException(status_code=422, detail=f"Unknown role: {target_role}")
    if target_tier > max_tier:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot assign role '{target_role}': "
                f"it exceeds your own permission tier"
            ),
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@users_router.post("", response_model=UserDetailOut, status_code=201)
async def create_user(
    body: UserCreateRequest,
    _user: dict = Depends(require_tenant_admin),
) -> UserDetailOut:
    """Create a new user in the current tenant.

    Role escalation guard: you cannot create a user with a higher role than your own.
    """
    _check_role_escalation(_user["role"], body.role)

    password_hash = hash_password(body.password)
    row = await handle_unique_constraint(
        queries.create_user(
            body.email, password_hash, body.role,
            display_name=body.display_name,
            phone=body.phone,
        ),
        conflict_msg=f"User '{body.email}' already exists in this tenant",
        log_ctx={"email": body.email},
    )
    logger.info(
        "user_created",
        email=body.email,
        role=body.role,
        tenant=_user.get("tenant_id"),
        by=_user.get("user_id"),
    )
    return UserDetailOut(**row)


@users_router.get("", response_model=list[UserDetailOut])
async def list_users(
    _user: dict = Depends(require_tenant_admin),
) -> list[UserDetailOut]:
    """List all users in the current tenant (active and inactive)."""
    rows = await queries.list_users(limit=500)
    return [UserDetailOut(**r) for r in rows]


@users_router.get("/{user_id}", response_model=UserDetailOut)
async def get_user(
    user_id: str,
    _user: dict = Depends(require_tenant_admin),
) -> UserDetailOut:
    """Get a single user by ID within the current tenant."""
    row = await queries.get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserDetailOut(**row)


@users_router.patch("/{user_id}/role", response_model=UserDetailOut)
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    _user: dict = Depends(require_tenant_admin),
) -> UserDetailOut:
    """Change the role of a user.

    Role escalation guard: you cannot promote a user above your own tier.
    """
    _check_role_escalation(_user["role"], body.role)

    found = await queries.update_user_role(user_id, body.role)
    if not found:
        raise HTTPException(status_code=404, detail="User not found or already inactive")

    row = await queries.get_user_by_id(user_id)
    logger.info("user_role_updated", user_id=user_id, new_role=body.role, by=_user.get("user_id"))
    return UserDetailOut(**row)


@users_router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    _user: dict = Depends(require_tenant_admin),
) -> dict:
    """Deactivate a user and revoke all their refresh tokens."""
    # Prevent self-deactivation
    if user_id == _user.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    await queries.revoke_all_user_tokens(user_id)
    found = await queries.deactivate_user_by_id(user_id)
    if not found:
        raise HTTPException(status_code=404, detail="User not found or already inactive")

    logger.info("user_deactivated", user_id=user_id, by=_user.get("user_id"))
    return {"message": f"User {user_id} deactivated"}


@users_router.post("/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    _user: dict = Depends(require_tenant_admin),
) -> dict:
    """Re-enable a previously deactivated user."""
    found = await queries.reactivate_user(user_id)
    if not found:
        raise HTTPException(status_code=404, detail="User not found or already active")

    logger.info("user_reactivated", user_id=user_id, by=_user.get("user_id"))
    return {"message": f"User {user_id} reactivated"}


@users_router.post("/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    body: AdminResetPasswordRequest,
    _user: dict = Depends(require_tenant_admin),
) -> dict:
    """Admin sets a new password for any user in scope.

    Does not require the current password — intended for account recovery.
    Revokes all existing refresh tokens, forcing re-login on all devices.
    """
    new_hash = hash_password(body.new_password)
    ok = await queries.update_user_password(user_id, new_hash)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    await queries.revoke_all_user_tokens(user_id)

    logger.info("admin_password_reset", target_user=user_id, by=_user.get("user_id"))
    return {"message": "Password reset. User must sign in again."}
