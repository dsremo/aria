"""R37 — Per-request memory cap.

Threat: a handler that builds a response in memory (e.g., a screening
job that accumulates 50 K results) can OOM the process if the request
asks for too much.  R31 caps body size at the front; this round caps
allocation budget *during* handler execution.

Defence: ``memory_budget(request_id, max_bytes)`` context manager that
records a high-water mark via ``tracemalloc``.  At yield-out, raises
``MemoryError`` if the peak exceeded the budget.  Real-time enforcement
on CPython is not feasible without subinterpreters; the budget is
*post-hoc* — it kills runaway requests retroactively so the next
identical request gets a different verdict (refuse upfront).
"""

from __future__ import annotations

import contextlib
import threading
import tracemalloc
from typing import Iterator

from aria.security.plugins import DefencePlugin, register


_TRACE_LOCK = threading.Lock()
_TRACE_REFCOUNT = 0


def _enable_tracemalloc():
    global _TRACE_REFCOUNT
    with _TRACE_LOCK:
        if _TRACE_REFCOUNT == 0 and not tracemalloc.is_tracing():
            tracemalloc.start(20)
        _TRACE_REFCOUNT += 1


def _disable_tracemalloc():
    global _TRACE_REFCOUNT
    with _TRACE_LOCK:
        _TRACE_REFCOUNT = max(0, _TRACE_REFCOUNT - 1)
        if _TRACE_REFCOUNT == 0 and tracemalloc.is_tracing():
            tracemalloc.stop()


@contextlib.contextmanager
def memory_budget(*, max_bytes: int) -> Iterator[None]:
    _enable_tracemalloc()
    snap_before = tracemalloc.take_snapshot()
    try:
        yield
        snap_after = tracemalloc.take_snapshot()
        # Sum of (size_after - size_before) per allocation.
        delta = 0
        for stat in snap_after.compare_to(snap_before, "filename"):
            delta += max(0, stat.size_diff)
        if delta > max_bytes:
            raise MemoryError(
                f"R37.memory_cap: handler allocated ~{delta} bytes > {max_bytes}"
            )
    finally:
        _disable_tracemalloc()


register(DefencePlugin(
    round_id="R37",
    name="memory_cap",
    description="memory_budget context manager — kill runaway handlers post-hoc.",
))
