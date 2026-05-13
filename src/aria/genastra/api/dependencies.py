"""FastAPI dependency injection providers."""

from __future__ import annotations

from datetime import UTC
from typing import Annotated

import asyncpg
from fastapi import Depends, Header

from aria.genastra.core.security import AuthContext, extract_bearer_token, hash_api_key
from aria.genastra.core.tenant import set_tenant
from aria.genastra.db.connection import get_pool


async def get_db_pool() -> asyncpg.Pool:
    """Provide the database connection pool."""
    return get_pool()


async def get_auth_context(
    authorization: Annotated[str | None, Header()] = None,
    pool: asyncpg.Pool = Depends(get_db_pool),  # noqa: B008
) -> AuthContext:
    """Authenticate the request and return the auth context.

    Extracts the Bearer token, looks up the API key hash in the database,
    verifies it's active and not expired, and sets the tenant context.
    """
    from aria.genastra.core.exceptions import ApiKeyInvalidError

    token = extract_bearer_token(authorization)
    key_hash = hash_api_key(token)

    row = await pool.fetchrow(
        """
        SELECT ak.id, ak.tenant_id, ak.scopes, ak.is_active, ak.expires_at,
               t.plan
        FROM api_keys ak
        JOIN tenants t ON t.id = ak.tenant_id
        WHERE ak.key_hash = $1
        """,
        key_hash,
    )

    if row is None:
        raise ApiKeyInvalidError("API key not found")

    if not row["is_active"]:
        raise ApiKeyInvalidError("API key has been revoked")

    if row["expires_at"] is not None:
        from datetime import datetime
        if row["expires_at"] < datetime.now(UTC):
            raise ApiKeyInvalidError("API key has expired")

    # Update last_used_at (fire-and-forget)
    await pool.execute(
        "UPDATE api_keys SET last_used_at = now() WHERE id = $1",
        row["id"],
    )

    # Set tenant context for this request
    set_tenant(row["tenant_id"])

    return AuthContext(
        tenant_id=row["tenant_id"],
        api_key_id=row["id"],
        scopes=tuple(row["scopes"]),
        plan=row["plan"],
    )


# Type alias for dependency injection
Auth = Annotated[AuthContext, Depends(get_auth_context)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]
