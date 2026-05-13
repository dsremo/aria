"""R240 — Right-to-be-forgotten propagation tracker.

Threat: GDPR Art. 17 (and CCPA, DPDP) mandate erasure across *all*
copies — primary DB, search index, analytics warehouse, vendor
caches, ML training corpora, S3 backups.  An incomplete propagation
is non-compliant.

Defence: ``register_erasure_request`` opens a tracker; each downstream
sink reports completion via ``record_erasure_complete``; refuses to
mark fully-complete until every declared sink reports.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ErasureTracker:
    request_id: str
    subject_id: str
    requested_at: float
    sinks: Set[str]
    completed_sinks: Set[str] = field(default_factory=set)
    deadline_seconds: float = 30.0 * 86_400


_TRACKERS: Dict[str, ErasureTracker] = {}
_LOCK = threading.Lock()


def register_erasure_request(
    request_id: str, subject_id: str, sinks: List[str], *, deadline_days: float = 30.0,
) -> ErasureTracker:
    tr = ErasureTracker(
        request_id=request_id, subject_id=subject_id,
        requested_at=time.time(), sinks=set(sinks),
        deadline_seconds=deadline_days * 86_400,
    )
    with _LOCK:
        _TRACKERS[request_id] = tr
    return tr


def record_erasure_complete(request_id: str, sink: str) -> Tuple[bool, str]:
    with _LOCK:
        tr = _TRACKERS.get(request_id)
        if tr is None:
            return False, "unknown_request"
        if sink not in tr.sinks:
            return False, f"unknown_sink:{sink}"
        tr.completed_sinks.add(sink)
    return True, "ok"


def is_complete(request_id: str) -> Tuple[bool, List[str]]:
    with _LOCK:
        tr = _TRACKERS.get(request_id)
        if tr is None:
            return False, ["unknown_request"]
        outstanding = sorted(tr.sinks - tr.completed_sinks)
    return not outstanding, outstanding


def overdue_requests(*, now: float = 0.0) -> List[str]:
    t = now or time.time()
    out: List[str] = []
    with _LOCK:
        for tr in _TRACKERS.values():
            if tr.completed_sinks == tr.sinks:
                continue
            if t - tr.requested_at > tr.deadline_seconds:
                out.append(tr.request_id)
    return out


register(DefencePlugin(
    round_id="R240",
    name="rtbf_propagation",
    description="Right-to-be-forgotten propagation tracker; per-sink completion ledger.",
))
