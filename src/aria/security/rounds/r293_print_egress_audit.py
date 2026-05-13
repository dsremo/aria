"""R293 — Print-job / data-egress audit.

Threat: print + screenshot are the two egress paths most insider-
threat programs miss.  Snowden, Reality Winner — both used printing.
A reliable audit + reasonable rate-cap forces the attacker to be
loud.

Defence: a per-user print-job ledger with byte-count + page-count.
``audit_print_burst`` flags users whose 24h print volume exceeds the
operator-set ceiling.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class PrintJob:
    timestamp: float
    user_id: str
    pages: int
    bytes_estimated: int
    document_classification: str = "internal"


@dataclass
class _UserState:
    jobs: Deque[PrintJob] = field(default_factory=lambda: deque(maxlen=1024))


_STATES: Dict[str, _UserState] = defaultdict(_UserState)
_LOCK = threading.Lock()


def record_print_job(user_id: str, pages: int, bytes_estimated: int,
                     *, classification: str = "internal", ts: float = 0.0) -> None:
    job = PrintJob(
        timestamp=ts or time.time(), user_id=user_id,
        pages=pages, bytes_estimated=bytes_estimated,
        document_classification=classification,
    )
    with _LOCK:
        _STATES[user_id].jobs.append(job)


def audit_print_burst(user_id: str, *,
                      max_pages_per_24h: int = 500,
                      max_bytes_per_24h: int = 200 * 1024 * 1024,
                      now: float = 0.0) -> Tuple[bool, List[str]]:
    t = now or time.time()
    with _LOCK:
        jobs = list(_STATES.get(user_id, _UserState()).jobs)
    recent = [j for j in jobs if t - j.timestamp <= 86_400]
    issues: List[str] = []
    pages = sum(j.pages for j in recent)
    payload = sum(j.bytes_estimated for j in recent)
    if pages > max_pages_per_24h:
        issues.append(f"print.pages_burst pages={pages}/{max_pages_per_24h}")
    if payload > max_bytes_per_24h:
        issues.append(f"print.bytes_burst bytes={payload}/{max_bytes_per_24h}")
    if any(j.document_classification in ("confidential", "secret", "top_secret") for j in recent):
        if pages > max_pages_per_24h // 4:
            issues.append("print.classified_burst")
    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _STATES.clear()


register(DefencePlugin(
    round_id="R293",
    name="print_egress_audit",
    description="Per-user print-job ledger; flag 24h burst + classified-doc spike.",
))
