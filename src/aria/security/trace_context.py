"""trace_context — process-wide trace_id propagation via contextvars.

R35. Closes the gap where the audit chain only correlated events
**within an incident**. A trace_id is generated at the *origin* of a
flow (HTTP request, bus-event publish, scheduler tick) and rides
through every downstream subsystem on a Python ``contextvars.ContextVar``.
``contextvars`` are async-safe and thread-local-equivalent — they
follow the call into ``asyncio.create_task`` and ``run_in_executor``
without explicit plumbing.

Everywhere the chain touches:

  HTTP request           ──► auth_middleware reads `X-Trace-Id` (or mints
                              one), seeds the ContextVar for the handler
                          ──► every audit entry written during the request
                              picks up the trace_id automatically
                          ──► response carries `X-Trace-Id` so the
                              client can correlate

  Bus event publish      ──► simulator.EventBus.publish() snapshots the
                              current trace_id into Event.trace_id
                          ──► dispatch sets the ContextVar to the event's
                              trace_id before each subscriber, so a
                              chain of fan-out events all share the
                              originator's trace

  ApprovalQueue.propose  ──► proposal stores trace_id; when the executor
                              fires after cooling-off, the trace_id is
                              restored into the ContextVar so the
                              eventual mutation is reachable from the
                              original detection event

  IncidentRegistry.open  ──► captures the current trace_id; every
                              follow-up audit entry tagged with both
                              `incident_id` AND `trace_id`

The generated id is ``trc_`` + 16 hex chars (64 bits) — short enough to
read aloud, long enough to be collision-free for a multi-year mission.

Usage::

    from aria.security.trace_context import (
        current_trace_id, set_trace_id, trace_scope, new_trace_id,
    )

    # Read the active trace; mints one if none has been set yet.
    tid = current_trace_id()

    # Context manager — pushes a trace_id, restores on exit.
    with trace_scope() as tid:
        ...   # all audit / bus events inside share `tid`

    with trace_scope(trace_id="trc_<imported-from-upstream>"):
        ...
"""

from __future__ import annotations

import contextvars
import secrets
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import structlog

logger = structlog.get_logger()


# Token format: prefix `trc_` + 16 hex chars (64-bit random) so
# trace ids stand out in audit log streams next to incident ids
# (`inc_xxxxxxxxxxxx`) and capability-token nonces.
_TOKEN_PREFIX = "trc_"
_TOKEN_BYTES = 8


# ContextVar — per-async-task, per-thread (via contextvars.copy_context)
# scoping. The default is "" so a missing context cannot leak a stale
# id from another flow. Callers that want a real trace either set it
# explicitly or use ``current_trace_id()`` which mints lazily.
_trace_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "aria.trace_id", default="",
)


def new_trace_id() -> str:
    """Mint a fresh trace_id. Does NOT install it into the context."""
    return _TOKEN_PREFIX + secrets.token_hex(_TOKEN_BYTES)


def current_trace_id(*, mint_if_absent: bool = True) -> str:
    """Return the trace_id active for the current task / thread.

    With ``mint_if_absent=True`` (the default), generates a new one and
    installs it into the context so subsequent calls in the same flow
    pick up the same id. With ``mint_if_absent=False``, returns the
    raw ContextVar value (empty string if unset) — used by the bus
    publisher to detect "I'm at the origin of a flow, mint my own".
    """
    tid = _trace_var.get()
    if tid:
        return tid
    if not mint_if_absent:
        return ""
    tid = new_trace_id()
    _trace_var.set(tid)
    return tid


def set_trace_id(trace_id: str) -> contextvars.Token:
    """Force the current context to a specific trace_id. Returns a
    Token that ``reset_trace_id`` can use to restore the prior value.

    Caller is responsible for calling ``reset_trace_id(token)`` (or
    using the ``trace_scope`` context manager which does it
    automatically) — leaking a token on a long-lived asyncio task can
    cause unrelated events to share an id.
    """
    return _trace_var.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    """Restore the trace_id ContextVar to whatever it was before the
    matching ``set_trace_id`` call."""
    _trace_var.reset(token)


@contextmanager
def trace_scope(trace_id: Optional[str] = None) -> Iterator[str]:
    """Context manager: install ``trace_id`` (or a freshly minted one)
    on the ContextVar; yield it; restore on exit.

    Use at every flow origin point: HTTP request handler, scheduler
    tick start, externally-triggered bus event, top of an async task.
    """
    tid = trace_id or new_trace_id()
    token = _trace_var.set(tid)
    try:
        yield tid
    finally:
        _trace_var.reset(token)


# ── Test helpers ──────────────────────────────────────────────────


_TEST_LOCK = threading.Lock()


def reset_for_test() -> None:
    """Drop any stashed context state. Tests don't need this often
    (trace_scope cleans up) but the helper exists for parametrised
    tests that bypass scoping."""
    with _TEST_LOCK:
        try:
            _trace_var.set("")
        except Exception:
            # ContextVar.set never fails, but keep the safety net.
            logger.warning("trace_context.reset_failed")
