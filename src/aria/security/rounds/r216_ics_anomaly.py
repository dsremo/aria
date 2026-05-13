"""R216 — ICS process-variable anomaly detector.

Threat: an attacker with control of a PLC / RTU writes setpoints
that look syntactically valid but are operationally insane (negative
flow rate, pressure above MAWP, temperature drop in milliseconds).
Stuxnet rewrote centrifuge frequencies inside a "normal" band.

Defence: a simple per-tag bound + rate-of-change check.  Operator
declares ``min, max, max_rate_per_second`` per process tag; the
checker flags excursions and rate spikes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _TagBound:
    min_value: float
    max_value: float
    max_rate_per_second: float
    last_value: float = 0.0
    last_ts: float = 0.0
    has_seen: bool = False


_BOUNDS: Dict[str, _TagBound] = {}
_LOCK = threading.Lock()


def configure_tag(tag: str, *, min_value: float, max_value: float, max_rate_per_second: float) -> None:
    with _LOCK:
        _BOUNDS[tag] = _TagBound(min_value, max_value, max_rate_per_second)


def check_value(tag: str, value: float, *, ts: float = 0.0) -> Tuple[bool, str]:
    t = ts or time.time()
    with _LOCK:
        b = _BOUNDS.get(tag)
        if b is None:
            return True, "unconfigured"
        if value < b.min_value or value > b.max_value:
            return False, f"ics.out_of_bounds tag={tag} v={value} [{b.min_value},{b.max_value}]"
        if b.has_seen and t > b.last_ts:
            dt = t - b.last_ts
            rate = abs(value - b.last_value) / max(dt, 1e-3)
            if rate > b.max_rate_per_second:
                return False, f"ics.rate_excess tag={tag} rate={rate:.2f}>{b.max_rate_per_second}"
        b.last_value = value
        b.last_ts = t
        b.has_seen = True
    return True, "ok"


register(DefencePlugin(
    round_id="R216",
    name="ics_anomaly",
    description="Per-tag bound + rate-of-change anomaly checker for SCADA process variables.",
))
