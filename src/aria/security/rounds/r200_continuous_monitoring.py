"""R200 — Continuous control monitoring (CCM).

Threat: point-in-time audits give a false sense of security.  Drift
between audits is the dominant threat vector — a control passes Q1
audit and silently fails by Q3.  CCM continuously verifies controls
at a sampling rate the cost-budget supports.

Defence: a registry of (control_id, check_callable, sample_rate)
triples + ``run_due_checks`` that executes whichever checks are due
and records the result.  Pairs with R162 NIST mapping.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ControlCheck:
    control_id: str
    callable_: Callable[[], Tuple[bool, str]]
    period_seconds: float
    last_run_ts: float = 0.0
    last_result: bool = True
    last_reason: str = ""


_CHECKS: Dict[str, ControlCheck] = {}
_HISTORY: List[Tuple[float, str, bool, str]] = []
_LOCK = threading.Lock()


def register_check(control_id: str, fn: Callable[[], Tuple[bool, str]], *, period_seconds: float = 3600.0) -> None:
    with _LOCK:
        _CHECKS[control_id] = ControlCheck(control_id, fn, period_seconds)


def run_due_checks(*, now: float = 0.0) -> List[Tuple[str, bool, str]]:
    t = now or time.time()
    results: List[Tuple[str, bool, str]] = []
    with _LOCK:
        due = [c for c in _CHECKS.values() if t - c.last_run_ts >= c.period_seconds]
    for chk in due:
        try:
            ok, why = chk.callable_()
        except Exception as exc:
            ok, why = False, f"exc:{type(exc).__name__}:{exc}"
        with _LOCK:
            chk.last_run_ts = t
            chk.last_result = ok
            chk.last_reason = why
            _HISTORY.append((t, chk.control_id, ok, why))
            if len(_HISTORY) > 10_000:
                _HISTORY.pop(0)
        results.append((chk.control_id, ok, why))
    return results


def snapshot_state() -> Dict[str, Dict[str, object]]:
    with _LOCK:
        return {
            cid: {
                "last_run_ts": c.last_run_ts,
                "last_result": c.last_result,
                "last_reason": c.last_reason,
                "period_seconds": c.period_seconds,
            }
            for cid, c in _CHECKS.items()
        }


register(DefencePlugin(
    round_id="R200",
    name="continuous_monitoring",
    description="Continuous control monitoring registry; periodic verification of controls.",
))
