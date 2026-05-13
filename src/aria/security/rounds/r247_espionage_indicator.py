"""R247 — Espionage indicator detection (UEBA + IoC).

Threat: nation-state intrusions (APT) are characterised by long
dwell-time, low-and-slow exfil, lateral movement to crown-jewels,
data-staging in temp dirs.  CrowdStrike 2024: median dwell 24 days;
SolarWinds 14 months.

Defence: pattern-bank + per-host counter that scores ``low+slow``,
``staging_dir_growth``, ``unusual_admin_share_access``,
``encrypted_egress_to_cloud_storage``.  Pairs with R246 + R195.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_PATTERN_WEIGHTS = {
    "staging_dir_growth": 0.4,
    "admin_share_access": 0.3,
    "encrypted_egress_cloud": 0.3,
    "low_and_slow_exfil": 0.4,
    "credential_dump": 0.5,
    "lateral_movement": 0.4,
}


@dataclass
class _HostState:
    events: Deque[Tuple[float, str]] = field(default_factory=lambda: deque(maxlen=4096))


_STATES: Dict[str, _HostState] = defaultdict(_HostState)
_LOCK = threading.Lock()


def record_event(host_id: str, indicator: str, *, ts: float = 0.0) -> None:
    t = ts or time.time()
    with _LOCK:
        _STATES[host_id].events.append((t, indicator))


def score_host(host_id: str, *, window_seconds: float = 86_400.0, now: float = 0.0) -> Tuple[float, list]:
    t = now or time.time()
    with _LOCK:
        events = list(_STATES.get(host_id, _HostState()).events)
    recent = [(ts, i) for ts, i in events if t - ts <= window_seconds]
    seen_kinds = set()
    score = 0.0
    notes = []
    for _, indicator in recent:
        if indicator not in seen_kinds:
            seen_kinds.add(indicator)
            score += _PATTERN_WEIGHTS.get(indicator, 0.1)
            notes.append(indicator)
    return min(1.0, score), notes


def reset_for_tests() -> None:
    with _LOCK:
        _STATES.clear()


register(DefencePlugin(
    round_id="R247",
    name="espionage_indicator",
    description="APT-style indicator pattern bank + per-host cumulative score.",
))
