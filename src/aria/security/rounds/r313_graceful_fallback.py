"""R313 — Service-degradation graceful fallback.

Threat: a hard-fail when one upstream is down cascades into a full
outage.  Graceful degradation (return cached / degraded / safe-default
result) keeps the rest of the system alive.

Defence: ``with_fallback`` runs the primary callable; on raise it
attempts the fallback, records the degraded path in a per-key
counter, and returns a tagged result so callers see ``mode=degraded``
explicitly.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r313")


@dataclass
class FallbackResult:
    value: Any
    mode: str               # "primary" | "degraded" | "exhausted"
    primary_exc: str = ""
    degraded_at: float = 0.0


_COUNTERS: Dict[str, int] = defaultdict(int)
_LOCK = threading.Lock()


def with_fallback(
    primary: Callable[[], Any],
    fallback: Callable[[], Any],
    *,
    key: str = "default",
) -> FallbackResult:
    try:
        return FallbackResult(value=primary(), mode="primary")
    except Exception as exc:
        logger.warning("r313.primary_failed key=%s exc=%s", key, exc)
        with _LOCK:
            _COUNTERS[key] += 1
        try:
            return FallbackResult(
                value=fallback(),
                mode="degraded",
                primary_exc=f"{type(exc).__name__}:{exc}",
                degraded_at=time.time(),
            )
        except Exception as exc2:
            logger.warning("r313.fallback_failed key=%s exc=%s", key, exc2)
            return FallbackResult(
                value=None,
                mode="exhausted",
                primary_exc=f"{type(exc).__name__}:{exc};fallback={type(exc2).__name__}:{exc2}",
                degraded_at=time.time(),
            )


def degraded_count(key: str) -> int:
    with _LOCK:
        return _COUNTERS.get(key, 0)


def reset_for_tests() -> None:
    with _LOCK:
        _COUNTERS.clear()


register(DefencePlugin(
    round_id="R313",
    name="graceful_fallback",
    description="Run primary; on failure invoke fallback; record degraded mode in counter.",
))
