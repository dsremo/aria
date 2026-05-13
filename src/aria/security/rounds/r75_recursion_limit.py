"""R75 — Per-call-stack recursion limit guard.

Threat: an attacker submits a deeply-nested input that pushes a parser
into > 1 000 frames; Python raises ``RecursionError`` on most platforms
at the default 1 000-frame ceiling, but a frame leak can DoS the worker
before that.  R39 caps JSON depth at parse time; this round is the
*per-process* recursion budget for cases where a parser hands deep
structure to recursive code (TLE → Lambert → ephemeris).

Defence: a context manager ``with bounded_recursion(max_depth=200):``
that lowers ``sys.setrecursionlimit`` for the scope and restores it on
exit.  Also provides ``track_depth(handle)`` for instrumentation: every
recursive call advertises its depth so a worker can decide to bail.
"""

from __future__ import annotations

import contextlib
import sys
import threading
from typing import Iterator

from aria.security.plugins import DefencePlugin, register


@contextlib.contextmanager
def bounded_recursion(*, max_depth: int = 200) -> Iterator[None]:
    if max_depth < 32 or max_depth > 4000:
        raise ValueError("R75.bounded_recursion: max_depth out of range")
    prev = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(max_depth)
        yield
    finally:
        sys.setrecursionlimit(prev)


_DEPTH_TLS = threading.local()


def enter() -> int:
    """Increment the per-thread depth counter; return the new depth."""
    cur = getattr(_DEPTH_TLS, "depth", 0) + 1
    _DEPTH_TLS.depth = cur
    return cur


def leave() -> int:
    cur = max(0, getattr(_DEPTH_TLS, "depth", 0) - 1)
    _DEPTH_TLS.depth = cur
    return cur


def current_depth() -> int:
    return getattr(_DEPTH_TLS, "depth", 0)


register(DefencePlugin(
    round_id="R75",
    name="recursion_limit",
    description="bounded_recursion context manager + per-thread depth counter.",
))
