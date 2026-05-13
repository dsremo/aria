"""R318 — Dependency outage simulator (game-day).

Threat: critical-dependency failure paths only exercised in real
incidents leave teams unprepared.  Outage simulators (Netflix
GameDays, Google DiRT) deliberately take dependencies offline in
controlled windows so teams build muscle memory.

Defence: a registry of dependencies + ``simulate_outage`` that
returns a fail-mode tag (timeout / 5xx / partial_success / total)
and records the simulation in an audit trail for post-game review.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class OutageEvent:
    timestamp: float
    dependency: str
    fail_mode: str
    duration_seconds: float
    operator: str


_AUDIT: Deque[OutageEvent] = deque(maxlen=4096)
_REGISTRY: Dict[str, List[str]] = {}
_LOCK = threading.Lock()


def register_dependency(name: str, fail_modes: List[str]) -> None:
    with _LOCK:
        _REGISTRY[name] = list(fail_modes) or ["timeout", "5xx"]


def simulate_outage(
    dependency: str, fail_mode: str, *, duration_seconds: float = 60.0,
    operator: str = "unknown",
) -> Tuple[bool, str]:
    if os.environ.get("ARIA_ENV") == "prod" and not os.environ.get("ARIA_GAMEDAY_ALLOWED"):
        return False, "gameday.prod_blocked"
    with _LOCK:
        modes = _REGISTRY.get(dependency)
    if modes is None:
        return False, f"gameday.unregistered_dependency:{dependency}"
    if fail_mode not in modes:
        return False, f"gameday.unsupported_mode:{fail_mode}"
    event = OutageEvent(
        timestamp=time.time(), dependency=dependency,
        fail_mode=fail_mode, duration_seconds=duration_seconds,
        operator=operator,
    )
    with _LOCK:
        _AUDIT.append(event)
    return True, f"simulated dep={dependency} mode={fail_mode}"


def history(*, limit: int = 50) -> List[OutageEvent]:
    with _LOCK:
        return list(_AUDIT)[-limit:]


def reset_for_tests() -> None:
    with _LOCK:
        _AUDIT.clear()
        _REGISTRY.clear()


register(DefencePlugin(
    round_id="R318",
    name="dependency_outage_sim",
    description="Game-day outage simulator; refuses prod without explicit allow.",
))
