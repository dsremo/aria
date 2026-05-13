"""R236 — ML model-inversion guard.

Threat: an attacker repeatedly queries a deployed model and
reconstructs the training data (Fredrikson 2015).  The risk is high
for models trained on small, sensitive corpora — medical, biometric,
behavioural.

Defence: a per-IP (or per-API-key) query-rate limiter that triggers
when the same caller submits N high-confidence-extracting queries
within a window.  Pairs with R232 DP noise on the model's outputs.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Window:
    queries: Deque[float] = field(default_factory=lambda: deque(maxlen=1024))


_WINDOWS: Dict[str, _Window] = {}
_LOCK = threading.Lock()


def record_query(caller: str, *, now: float = 0.0) -> None:
    t = now or time.time()
    with _LOCK:
        _WINDOWS.setdefault(caller, _Window()).queries.append(t)


def query_rate(caller: str, *, window_seconds: float = 60.0, now: float = 0.0) -> int:
    t = now or time.time()
    with _LOCK:
        window = _WINDOWS.get(caller)
        if not window:
            return 0
        return sum(1 for q in window.queries if t - q <= window_seconds)


def is_inversion_attack(
    caller: str, *, threshold: int = 200, window_seconds: float = 60.0,
    now: float = 0.0,
) -> Tuple[bool, str]:
    rate = query_rate(caller, window_seconds=window_seconds, now=now)
    if rate >= threshold:
        return True, f"model_inversion rate={rate}/{window_seconds}s"
    return False, f"ok rate={rate}"


def reset_for_tests(caller: str = "") -> None:
    with _LOCK:
        if caller:
            _WINDOWS.pop(caller, None)
        else:
            _WINDOWS.clear()


register(DefencePlugin(
    round_id="R236",
    name="model_inversion",
    description="Per-caller query-rate limiter for ML model-inversion defence.",
))
