"""Tenant management routes — create, list, view, update tenants.

All routes require dsremo_admin or superuser role. These are internal
Dsremo staff endpoints; tenant admins do not have access here.

Routes:
  POST   /tenants           — Create a new tenant
  GET    /tenants           — List all tenants
  GET    /tenants/{id}      — Get a single tenant by ID
  PATCH  /tenants/{id}      — Update tenant name / active flag
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

import aria.dsremo.db.queries as queries
from aria.dsremo.api.dependencies import require_dsremo_admin
from aria.dsremo.api.errors import handle_unique_constraint
from aria.dsremo.api.schemas import TenantIn, TenantOut, TenantPatch

logger = structlog.get_logger()
tenants_router = APIRouter(prefix="/tenants", tags=["tenants"])


@tenants_router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantIn,
    _user: dict = Depends(require_dsremo_admin),
) -> TenantOut:
    """Create a new customer tenant.

    The tenant ID must be lowercase alphanumeric + hyphens (used as the RLS
    context value — no spaces or special chars).
    """
    row = await handle_unique_constraint(
        queries.create_tenant(body.id, body.name, body.plan),
        conflict_msg=f"Tenant '{body.id}' already exists",
        log_ctx={"tenant_id": body.id},
    )
    logger.info("tenant_created", tenant_id=row["id"], by=_user.get("user_id"))
    return TenantOut(**row)


@tenants_router.get("", response_model=list[TenantOut])
async def list_tenants(
    _user: dict = Depends(require_dsremo_admin),
) -> list[TenantOut]:
    """List all tenants."""
    rows = await queries.list_tenants()
    return [TenantOut(**r) for r in rows]


@tenants_router.get("/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: str,
    _user: dict = Depends(require_dsremo_admin),
) -> TenantOut:
    """Get a single tenant by ID."""
    row = await queries.get_tenant_by_id(tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return TenantOut(**row)


@tenants_router.patch("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: str,
    body: TenantPatch,
    _user: dict = Depends(require_dsremo_admin),
) -> TenantOut:
    """Update a tenant's name and/or active status."""
    if body.name is None and body.active is None:
        raise HTTPException(status_code=422, detail="No fields to update")

    found = await queries.update_tenant(tenant_id, name=body.name, active=body.active)
    if not found:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

    row = await queries.get_tenant_by_id(tenant_id)
    logger.info("tenant_updated", tenant_id=tenant_id, by=_user.get("user_id"))
    return TenantOut(**row)
