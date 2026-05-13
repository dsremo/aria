"""R321 — RED-metrics saturation alert.

Threat: services without RED (Rate / Errors / Duration) metrics fly
blind — by the time customers complain, the SLO has been breached
for hours.  Saturation in particular (CPU, memory, threads, file
handles) precedes every failure.

Defence: a tiny in-process aggregator that counts request rate +
errors + duration p50/p99 and emits an alert tag when error-rate or
p99 latency cross thresholds.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Aggregator:
    rate_window: Deque[float] = field(default_factory=lambda: deque(maxlen=4096))
    errors_window: Deque[float] = field(default_factory=lambda: deque(maxlen=4096))
    durations: Deque[float] = field(default_factory=lambda: deque(maxlen=4096))


_AGG: Dict[str, _Aggregator] = defaultdict(_Aggregator)
_LOCK = threading.Lock()


def record_request(service: str, *, success: bool, duration_ms: float, ts: float = 0.0) -> None:
    t = ts or time.time()
    with _LOCK:
        a = _AGG[service]
        a.rate_window.append(t)
        if not success:
            a.errors_window.append(t)
        a.durations.append(duration_ms)


def evaluate(
    service: str, *, window_seconds: float = 60.0,
    error_rate_threshold: float = 0.01,
    p99_threshold_ms: float = 1000.0,
    now: float = 0.0,
) -> Tuple[bool, Dict[str, float]]:
    t = now or time.time()
    with _LOCK:
        a = _AGG.get(service)
        if a is None:
            return True, {"reason": 0.0}
        rate = sum(1 for ts in a.rate_window if t - ts <= window_seconds)
        errors = sum(1 for ts in a.errors_window if t - ts <= window_seconds)
        durations = list(a.durations)[-1024:]
    if rate == 0:
        return True, {"rate": 0.0}
    err_rate = errors / rate
    p99 = _percentile(durations, 99) if durations else 0.0
    healthy = err_rate <= error_rate_threshold and p99 <= p99_threshold_ms
    return healthy, {
        "rate_per_window": float(rate),
        "error_rate": err_rate,
        "p99_ms": p99,
    }


def _percentile(values: List[float], pct: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(len(s) * pct / 100)))
    return s[idx]


def reset_for_tests() -> None:
    with _LOCK:
        _AGG.clear()


register(DefencePlugin(
    round_id="R321",
    name="red_metrics",
    description="RED-metrics aggregator: rate + error-rate + p99 latency saturation alert.",
))
