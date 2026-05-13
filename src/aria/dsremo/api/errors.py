"""HTTP error helpers — eliminate duplicate try/except patterns in route handlers.

Usage:
    row = await handle_unique_constraint(
        queries.create_tenant(body.id, body.name, body.plan),
        conflict_msg=f"Tenant '{body.id}' already exists",
        log_ctx={"tenant_id": body.id},
    )
"""

from __future__ import annotations

from typing import Any, Coroutine

import structlog
from fastapi import HTTPException

logger = structlog.get_logger()


async def handle_unique_constraint(
    coro: Coroutine[Any, Any, Any],
    conflict_msg: str,
    log_ctx: dict[str, Any],
) -> Any:
    """Await `coro`; translate unique-constraint errors → 409, anything else → 500."""
    try:
        return await coro
    except Exception as exc:
        exc_lower = str(exc).lower()
        if "unique" in exc_lower or "duplicate" in exc_lower:
            raise HTTPException(status_code=409, detail=conflict_msg) from exc
        logger.error("db_operation_failed", **log_ctx, error=str(exc))
        raise HTTPException(status_code=500, detail="Database operation failed") from exc


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)
