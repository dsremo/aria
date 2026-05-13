"""R246 — Insider-threat user behaviour analytics.

Threat: an employee with valid credentials slowly exfils — Snowden,
Reality Winner, Manning.  Indicators: off-hours bulk reads, unusual
geographic access, downloads of untouched-for-months datasets,
sudden interest in unrelated systems.

Defence: a lightweight UEBA scorer that builds a per-user baseline
(allowed hours, typical access volume, typical data classes touched)
and returns a deviation score per session.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class UserBaseline:
    typical_hours: Set[int] = field(default_factory=set)
    typical_data_classes: Set[str] = field(default_factory=set)
    avg_volume_mb_day: float = 0.0
    samples: int = 0


_BASELINES: Dict[str, UserBaseline] = {}
_LOCK = threading.Lock()


def update_baseline(
    user_id: str, *, hour_of_day: int, data_class: str, volume_mb: float,
) -> None:
    with _LOCK:
        b = _BASELINES.setdefault(user_id, UserBaseline())
        b.typical_hours.add(hour_of_day)
        b.typical_data_classes.add(data_class)
        b.avg_volume_mb_day = (b.avg_volume_mb_day * b.samples + volume_mb) / (b.samples + 1)
        b.samples += 1


def score_session(
    user_id: str, *, hour_of_day: int, data_class: str, volume_mb: float,
) -> Tuple[float, str]:
    with _LOCK:
        b = _BASELINES.get(user_id)
    if b is None or b.samples < 5:
        return 0.0, "no_baseline"
    score = 0.0
    notes = []
    if hour_of_day not in b.typical_hours:
        score += 0.3
        notes.append(f"off_hours:{hour_of_day}")
    if data_class not in b.typical_data_classes:
        score += 0.4
        notes.append(f"new_class:{data_class}")
    if b.avg_volume_mb_day > 0 and volume_mb > 5 * b.avg_volume_mb_day:
        score += 0.4
        notes.append(f"vol_excess {volume_mb:.0f}MB")
    return min(1.0, score), ",".join(notes) or "ok"


register(DefencePlugin(
    round_id="R246",
    name="insider_uba",
    description="Per-user behavioural-baseline UEBA insider-threat scorer.",
))
