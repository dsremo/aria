"""Tenant context for multi-tenant isolation.

Every database query and S3 operation MUST use the tenant context.
Missing tenant_id in a WHERE clause = data leak across tenants.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)


def set_tenant(tenant_id: UUID) -> None:
    """Set the current tenant for this request context."""
    _current_tenant.set(tenant_id)


def get_tenant() -> UUID:
    """Get the current tenant ID. Raises if not set."""
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise RuntimeError(
            "Tenant context not set. Every request must have a tenant. "
            "This is a bug — check middleware or dependency injection."
        )
    return tenant_id


def get_tenant_or_none() -> UUID | None:
    """Get the current tenant ID, or None if not set (for health checks)."""
    return _current_tenant.get()


def clear_tenant() -> None:
    """Clear tenant context (call at end of request)."""
    _current_tenant.set(None)
