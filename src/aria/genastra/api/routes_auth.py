"""API key management endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Response

from aria.genastra.api.schemas import ApiKeyInfo, CreateApiKeyRequest, CreateApiKeyResponse
from aria.genastra.core.security import generate_api_key

if TYPE_CHECKING:
    from uuid import UUID

    from aria.genastra.api.dependencies import Auth, DbPool

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()


@router.post("/keys", response_model=CreateApiKeyResponse, status_code=201)
async def create_api_key(
    body: CreateApiKeyRequest,
    auth: Auth,
    pool: DbPool,
) -> CreateApiKeyResponse:
    """Create a new API key. The full key is returned ONCE — store it securely."""
    auth.require_scope("auth:admin")

    full_key, key_hash = generate_api_key()
    prefix = full_key[:16]

    key_id = await pool.fetchval(
        """
        INSERT INTO api_keys (tenant_id, key_hash, prefix, label, scopes)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        auth.tenant_id,
        key_hash,
        prefix,
        body.label,
        body.scopes,
    )

    logger.info("api_key_created", tenant_id=str(auth.tenant_id), key_id=str(key_id))

    return CreateApiKeyResponse(key=full_key, id=key_id, prefix=prefix)


@router.get("/keys", response_model=list[ApiKeyInfo])
async def list_api_keys(auth: Auth, pool: DbPool) -> list[ApiKeyInfo]:
    """List all API keys for the current tenant (prefix + label, NOT full key)."""
    rows = await pool.fetch(
        """
        SELECT id, prefix, label, scopes, is_active, last_used_at, created_at
        FROM api_keys
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        """,
        auth.tenant_id,
    )
    return [
        ApiKeyInfo(
            id=row["id"],
            prefix=row["prefix"],
            label=row["label"],
            scopes=row["scopes"],
            is_active=row["is_active"],
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.delete("/keys/{key_id}", status_code=204, response_model=None)
async def revoke_api_key(
    key_id: UUID,
    auth: Auth,
    pool: DbPool,
) -> Response:
    """Revoke an API key."""
    auth.require_scope("auth:admin")

    result = await pool.execute(
        "UPDATE api_keys SET is_active = false WHERE id = $1 AND tenant_id = $2",
        key_id,
        auth.tenant_id,
    )

    if result == "UPDATE 0":
        from aria.genastra.core.exceptions import JobNotFoundError
        raise JobNotFoundError(f"API key {key_id} not found")

    logger.info("api_key_revoked", tenant_id=str(auth.tenant_id), key_id=str(key_id))
    return Response(status_code=204)
