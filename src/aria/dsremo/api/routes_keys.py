"""API key management routes — self-serve key generation for tenant admins.

Tenant admins can generate, list, and revoke API keys for their tenant
directly via the API (no CLI required). The in-memory key→tenant map
(app.state.api_key_tenant_map) is hot-updated on create/delete so new
keys work immediately without a server restart.

Routes:
  POST   /keys              — Generate a new API key (plaintext shown ONCE)
  GET    /keys              — List active API keys for current tenant
  DELETE /keys/{prefix}     — Revoke key(s) matching a hash prefix
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import aria.dsremo.db.queries as queries
from aria.dsremo.api.dependencies import require_tenant_admin
from aria.dsremo.api.schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyOut
from aria.dsremo.core.security import generate_api_key

logger = structlog.get_logger()
keys_router = APIRouter(prefix="/keys", tags=["api-keys"])


@keys_router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    request: Request,
    _user: dict = Depends(require_tenant_admin),
) -> ApiKeyCreateResponse:
    """Generate a new API key for the current tenant.

    The full plaintext key is returned ONCE. Store it securely — it cannot
    be retrieved again. Only the SHA-256 hash is persisted in the database.
    """
    tenant_id = _user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="X-Tenant-ID header required when operating as a dsremo user",
        )

    plaintext, key_hash = generate_api_key()

    await queries.store_api_key(key_hash, body.label)

    # Hot-update the in-memory map so the new key works immediately.
    request.app.state.api_key_tenant_map[key_hash] = tenant_id

    logger.info("api_key_created", label=body.label, tenant=tenant_id, by=_user.get("user_id"))
    return ApiKeyCreateResponse(
        key=plaintext,
        label=body.label,
        hash_prefix=key_hash[:16],
        tenant_id=tenant_id,
    )


@keys_router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    _user: dict = Depends(require_tenant_admin),
) -> list[ApiKeyOut]:
    """List all API keys for the current tenant.

    Returns label and hash_prefix (first 16 chars of hash) for identification.
    The full hash is never returned.
    """
    rows = await queries.list_api_keys_for_tenant()
    return [
        ApiKeyOut(
            label=r["label"],
            hash_prefix=r["hash_prefix"],
            created_at=r["created_at"],
            last_used_at=r.get("last_used_at"),
            active=r["active"],
        )
        for r in rows
    ]


@keys_router.delete("/{prefix}", status_code=204, response_model=None, response_class=Response)
async def revoke_api_key(
    prefix: str,
    request: Request,
    _user: dict = Depends(require_tenant_admin),
) -> None:
    """Revoke API key(s) whose hash starts with the given prefix.

    The prefix is the first 16 characters of the hash (as shown in GET /keys).
    Removes the key from the in-memory auth map immediately.
    """
    if len(prefix) < 8:
        raise HTTPException(
            status_code=422,
            detail="Prefix must be at least 8 characters for safety",
        )

    found = await queries.revoke_api_key_by_prefix(prefix)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"No active key found with prefix '{prefix}'",
        )

    # Remove from in-memory map (evict any key whose hash starts with prefix).
    request.app.state.api_key_tenant_map = {
        k: v
        for k, v in request.app.state.api_key_tenant_map.items()
        if not k.startswith(prefix)
    }

    logger.info("api_key_revoked", prefix=prefix, tenant=_user.get("tenant_id"), by=_user.get("user_id"))
