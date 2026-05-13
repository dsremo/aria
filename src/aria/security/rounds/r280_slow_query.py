"""R280 — Database slow-query + query-log audit.

Threat: an attacker post-foothold runs expensive queries to either
exfil bulk data, mine for indexed PII, or simply DoS the DB.  Without
slow-query logging on, the abuse is invisible to defenders.

Defence: per-DB-session query duration tracker.  Records every query
> threshold; ``audit_slow_queries`` flags repetitive expensive queries
from a single principal as exfil-pattern.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class QueryRecord:
    timestamp: float
    duration_ms: float
    principal: str
    fingerprint: str
    rows_returned: int = 0


_HISTORY: Deque[QueryRecord] = deque(maxlen=131_072)
_LOCK = threading.Lock()
_SLOW_MS = 500.0


def record_query(
    *, duration_ms: float, principal: str, fingerprint: str,
    rows_returned: int = 0, ts: float = 0.0,
) -> None:
    if duration_ms < _SLOW_MS:
        return
    rec = QueryRecord(
        timestamp=ts or time.time(),
        duration_ms=duration_ms,
        principal=principal,
        fingerprint=fingerprint,
        rows_returned=rows_returned,
    )
    with _LOCK:
        _HISTORY.append(rec)


def audit_slow_queries(
    *, principal: str = "", window_seconds: float = 300.0, now: float = 0.0,
) -> Tuple[bool, List[str]]:
    t = now or time.time()
    with _LOCK:
        records = list(_HISTORY)
    relevant = [
        r for r in records
        if t - r.timestamp <= window_seconds
        and (principal == "" or r.principal == principal)
    ]
    if not relevant:
        return True, []

    issues: List[str] = []
    by_principal: Dict[str, List[QueryRecord]] = defaultdict(list)
    for r in relevant:
        by_principal[r.principal].append(r)

    for p, recs in by_principal.items():
        total_ms = sum(r.duration_ms for r in recs)
        total_rows = sum(r.rows_returned for r in recs)
        if total_ms > 60_000:
            issues.append(f"slowq.principal_burn principal={p} total_ms={int(total_ms)}")
        if total_rows > 1_000_000:
            issues.append(f"slowq.principal_bulk_pull principal={p} rows={total_rows}")
        fingerprints = {r.fingerprint for r in recs}
        if len(recs) > 20 and len(fingerprints) <= 2:
            issues.append(f"slowq.repeated_fingerprint principal={p} count={len(recs)}")

    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _HISTORY.clear()


register(DefencePlugin(
    round_id="R280",
    name="slow_query",
    description="Slow-query ledger; flag bulk-pull or repeat-fingerprint exfil patterns.",
))
