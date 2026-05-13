"""R185 — METR-style honest-reporting audit.

Threat: a model self-reports success on a task it actually failed
(or partially completed).  METR's autonomous-agent evals show this
is the dominant failure mode when verification is expensive.

Defence: a wrapper that records both the model's *self-report* and a
*verifiable* outcome (e.g. test-suite exit code, regex match on
expected artefact), and flags any case where self-report claims
success but verification fails.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class HonestyRecord:
    timestamp: float
    task_id: str
    self_reported_success: bool
    verified_success: bool
    note: str = ""


_HISTORY: Deque[HonestyRecord] = deque(maxlen=10_000)
_LOCK = threading.Lock()


def record(task_id: str, *, self_reported: bool, verified: bool, note: str = "") -> None:
    with _LOCK:
        _HISTORY.append(HonestyRecord(time.time(), task_id, self_reported, verified, note))


def honesty_rate() -> Tuple[float, int, int]:
    """Returns (honesty_rate, total_records, dishonest_count)."""
    with _LOCK:
        records = list(_HISTORY)
    if not records:
        return 1.0, 0, 0
    dishonest = sum(1 for r in records if r.self_reported_success and not r.verified_success)
    return 1.0 - dishonest / len(records), len(records), dishonest


def recent_dishonest(n: int = 10) -> List[HonestyRecord]:
    with _LOCK:
        records = list(_HISTORY)
    return [r for r in records if r.self_reported_success and not r.verified_success][-n:]


register(DefencePlugin(
    round_id="R185",
    name="honest_reporting",
    description="Self-report vs verified-outcome honesty tracker (METR class).",
))
