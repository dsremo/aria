"""R315 — Backpressure semaphore.

Threat: an unbounded queue + slow consumer = unbounded memory growth
+ unbounded latency.  The classic queue-overflow OOM that crashes
production at the worst moment.

Defence: ``acquire`` returns False immediately when the queue depth
exceeds a configured ceiling — the producer must shed load (return
429, drop, or sample) instead of accumulating work.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Semaphore:
    capacity: int
    in_flight: int = 0
    high_water: int = 0


_SEMAPHORES: Dict[str, _Semaphore] = {}
_LOCK = threading.Lock()


def configure(key: str, capacity: int) -> None:
    if capacity < 1:
        raise ValueError("R315: capacity must be >= 1")
    with _LOCK:
        _SEMAPHORES[key] = _Semaphore(capacity=capacity)


def acquire(key: str) -> Tuple[bool, str]:
    with _LOCK:
        s = _SEMAPHORES.get(key)
        if s is None:
            return False, f"backpressure.unknown_key:{key}"
        if s.in_flight >= s.capacity:
            return False, f"backpressure.shed_load {s.in_flight}/{s.capacity}"
        s.in_flight += 1
        s.high_water = max(s.high_water, s.in_flight)
    return True, "ok"


def release(key: str) -> None:
    with _LOCK:
        s = _SEMAPHORES.get(key)
        if s and s.in_flight > 0:
            s.in_flight -= 1


def high_water_mark(key: str) -> int:
    with _LOCK:
        s = _SEMAPHORES.get(key)
        return s.high_water if s else 0


def reset_for_tests() -> None:
    with _LOCK:
        _SEMAPHORES.clear()


register(DefencePlugin(
    round_id="R315",
    name="backpressure",
    description="Bounded-capacity semaphore; producer sheds load past ceiling.",
))
