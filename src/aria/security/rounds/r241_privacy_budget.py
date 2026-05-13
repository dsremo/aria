"""R241 — Cross-query privacy budget aggregator.

Threat: even with per-query DP (R232), the cumulative privacy loss
across queries / models / publications grows.  Without a single
ledger, an organisation can spend 100x its declared epsilon over a
year and not notice.

Defence: a single per-subject ledger that accumulates epsilon spent
across all DP-protected releases.  ``charge`` returns refused when
adding the spend would exceed a configurable annual ceiling.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _SubjectLedger:
    epsilon_total: float = 0.0
    last_reset: float = 0.0
    history: List[Tuple[float, float, str]] = field(default_factory=list)


_LEDGERS: Dict[str, _SubjectLedger] = defaultdict(_SubjectLedger)
_LOCK = threading.Lock()
_ANNUAL_CEILING = 10.0


def charge(
    subject_id: str,
    epsilon: float,
    *,
    purpose: str = "",
    now: float = 0.0,
    annual_ceiling: float = _ANNUAL_CEILING,
) -> Tuple[bool, float, str]:
    """Returns ``(charged_ok, remaining, reason)``."""
    t = now or time.time()
    with _LOCK:
        ledger = _LEDGERS[subject_id]
        if t - ledger.last_reset >= 86_400 * 365:
            ledger.epsilon_total = 0.0
            ledger.last_reset = t
            ledger.history.clear()
        if ledger.epsilon_total + epsilon > annual_ceiling:
            return False, annual_ceiling - ledger.epsilon_total, "budget.annual_exceeded"
        ledger.epsilon_total += epsilon
        ledger.history.append((t, epsilon, purpose))
        remaining = annual_ceiling - ledger.epsilon_total
    return True, remaining, "ok"


def remaining_budget(subject_id: str, *, annual_ceiling: float = _ANNUAL_CEILING) -> float:
    with _LOCK:
        ledger = _LEDGERS.get(subject_id)
    if ledger is None:
        return annual_ceiling
    return annual_ceiling - ledger.epsilon_total


def reset_subject(subject_id: str) -> None:
    with _LOCK:
        _LEDGERS.pop(subject_id, None)


register(DefencePlugin(
    round_id="R241",
    name="privacy_budget",
    description="Cross-query subject-level epsilon budget with annual ceiling.",
))
