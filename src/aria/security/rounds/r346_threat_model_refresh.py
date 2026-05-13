"""R346 — Continuous threat-model refresh tracker.

Threat: a threat model written six months ago has missed at least one
new attack class.  Without a refresh cadence, the model drifts from
reality and detection coverage degrades silently.

Defence: a per-domain ``ThreatModelRecord`` with last-refreshed
timestamp; ``audit_freshness`` flags domains older than the operator-
set window for review.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ThreatModelRecord:
    domain: str
    last_refreshed_at: float = 0.0
    next_due_at: float = 0.0
    refresh_period_seconds: float = 90 * 86_400.0
    notable_changes: List[str] = field(default_factory=list)


_RECORDS: Dict[str, ThreatModelRecord] = {}
_LOCK = threading.Lock()


def register_domain(domain: str, *, period_days: float = 90.0) -> None:
    with _LOCK:
        _RECORDS.setdefault(domain, ThreatModelRecord(
            domain=domain,
            refresh_period_seconds=period_days * 86_400.0,
        ))


def record_refresh(domain: str, *, notable_changes: List[str] = None,
                   now: float = 0.0) -> None:
    t = now or time.time()
    with _LOCK:
        rec = _RECORDS.setdefault(domain, ThreatModelRecord(domain=domain))
        rec.last_refreshed_at = t
        rec.next_due_at = t + rec.refresh_period_seconds
        if notable_changes:
            rec.notable_changes = list(notable_changes)


def audit_freshness(*, now: float = 0.0) -> Tuple[bool, List[str]]:
    t = now or time.time()
    issues: List[str] = []
    with _LOCK:
        records = list(_RECORDS.values())
    for r in records:
        if r.last_refreshed_at == 0.0:
            issues.append(f"threat_model.never_refreshed:{r.domain}")
            continue
        if t > r.next_due_at:
            issues.append(
                f"threat_model.overdue:{r.domain} by_days={int((t - r.next_due_at) / 86_400)}"
            )
    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _RECORDS.clear()


register(DefencePlugin(
    round_id="R346",
    name="threat_model_refresh",
    description="Per-domain threat-model refresh ledger; overdue audit.",
))
