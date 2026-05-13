"""Tenant context — propagated via asyncio ContextVar.

Each HTTP request (asyncio task) carries its own copy of the ContextVar.
Middleware sets it after API key validation; connection.acquire() reads it
to enforce Row Level Security on every query.

Default: 'default' — existing CLI scripts and tests work with zero changes.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="default")


def set_tenant(tenant_id: str) -> None:
    """Set the active tenant for the current asyncio task."""
    _tenant_id.set(tenant_id)


def get_tenant() -> str:
    """Return the active tenant ID (defaults to 'default')."""
    return _tenant_id.get()


# ── Lightweight distributed trace ID ─────────────────────────────────────────
# Propagated through the pipeline via ContextVar so every log entry in a
# single request/detection cycle can be correlated without full OpenTelemetry.

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def new_trace_id() -> str:
    """Generate and set a new trace_id for this request."""
    tid = uuid.uuid4().hex[:16]
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str:
    return _trace_id.get()
