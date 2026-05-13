"""R314 — Circuit breaker + bulkhead pattern.

Threat: a flaky downstream's repeated timeouts pin every worker
waiting, exhausting threads / connections — Netflix Hystrix's
canonical motivating story.

Defence: per-resource circuit breaker.  ``call`` runs the callable
when state=closed; opens on consecutive failures; half-open after
cooldown.  Bulkhead: per-resource concurrency cap so a single hot
key cannot drain all workers.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _BreakerState:
    state: str = "closed"   # "closed" | "open" | "half_open"
    failures: int = 0
    last_state_change: float = 0.0
    in_flight: int = 0


_BREAKERS: Dict[str, _BreakerState] = {}
_LOCK = threading.Lock()


def call(
    key: str, fn: Callable[[], Any],
    *,
    failure_threshold: int = 5,
    cooldown_seconds: float = 30.0,
    bulkhead_limit: int = 16,
) -> Tuple[bool, Any, str]:
    """Returns (ok, result_or_None, reason)."""
    t = time.time()
    with _LOCK:
        b = _BREAKERS.setdefault(key, _BreakerState())
        if b.state == "open" and t - b.last_state_change >= cooldown_seconds:
            b.state = "half_open"
            b.last_state_change = t
        if b.state == "open":
            return False, None, f"breaker.open since={int(t - b.last_state_change)}s"
        if b.in_flight >= bulkhead_limit:
            return False, None, f"breaker.bulkhead_full {b.in_flight}/{bulkhead_limit}"
        b.in_flight += 1
    try:
        result = fn()
    except Exception as exc:
        with _LOCK:
            b.failures += 1
            b.in_flight = max(0, b.in_flight - 1)
            if b.failures >= failure_threshold or b.state == "half_open":
                b.state = "open"
                b.last_state_change = t
        return False, None, f"breaker.call_failed:{type(exc).__name__}"
    with _LOCK:
        b.in_flight = max(0, b.in_flight - 1)
        b.failures = 0
        if b.state == "half_open":
            b.state = "closed"
            b.last_state_change = t
    return True, result, "ok"


def state_of(key: str) -> str:
    with _LOCK:
        b = _BREAKERS.get(key)
        return b.state if b else "closed"


def reset_for_tests() -> None:
    with _LOCK:
        _BREAKERS.clear()


register(DefencePlugin(
    round_id="R314",
    name="circuit_breaker",
    description="Per-resource circuit breaker + bulkhead with half-open recovery.",
))
