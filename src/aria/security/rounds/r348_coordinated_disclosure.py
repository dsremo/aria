"""R348 — Coordinated vulnerability disclosure timeline.

Threat: a vendor with no documented disclosure policy + no SLA tells
researchers nothing about when to expect a fix or whether to
coordinate.  Researchers default to 90-day full-disclosure (Project
Zero).  Without policy, the vendor argues bad faith; with policy,
both sides have a clock.

Defence: a per-finding state machine — ``acknowledged``, ``fix_in_progress``,
``patched``, ``disclosed``.  ``advance_state`` refuses out-of-order
transitions; ``overdue`` flags findings whose deadline has elapsed.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_STATES = ("submitted", "acknowledged", "fix_in_progress", "patched", "disclosed", "withdrawn")


@dataclass
class DisclosureRecord:
    finding_id: str
    state: str = "submitted"
    submitted_at: float = 0.0
    target_disclosure_at: float = 0.0
    history: List[Tuple[float, str]] = field(default_factory=list)


_RECORDS: Dict[str, DisclosureRecord] = {}
_LOCK = threading.Lock()


def open_finding(finding_id: str, *, sla_days: float = 90.0) -> DisclosureRecord:
    t = time.time()
    rec = DisclosureRecord(
        finding_id=finding_id, state="submitted",
        submitted_at=t, target_disclosure_at=t + sla_days * 86_400.0,
    )
    rec.history.append((t, "submitted"))
    with _LOCK:
        _RECORDS[finding_id] = rec
    return rec


def advance_state(finding_id: str, target_state: str) -> Tuple[bool, str]:
    if target_state not in _STATES:
        return False, f"disclosure.invalid_state:{target_state}"
    with _LOCK:
        rec = _RECORDS.get(finding_id)
        if rec is None:
            return False, "disclosure.unknown_finding"
        cur_idx = _STATES.index(rec.state)
        target_idx = _STATES.index(target_state)
        if target_state == "withdrawn":
            rec.state = "withdrawn"
            rec.history.append((time.time(), "withdrawn"))
            return True, "ok"
        if target_idx <= cur_idx:
            return False, f"disclosure.cannot_regress:{rec.state}->{target_state}"
        if target_idx - cur_idx > 1:
            return False, f"disclosure.skip_state:{rec.state}->{target_state}"
        rec.state = target_state
        rec.history.append((time.time(), target_state))
    return True, "ok"


def overdue(*, now: float = 0.0) -> List[DisclosureRecord]:
    t = now or time.time()
    out: List[DisclosureRecord] = []
    with _LOCK:
        for r in _RECORDS.values():
            if r.state in ("disclosed", "withdrawn"):
                continue
            if t > r.target_disclosure_at:
                out.append(r)
    return out


def reset_for_tests() -> None:
    with _LOCK:
        _RECORDS.clear()


register(DefencePlugin(
    round_id="R348",
    name="coordinated_disclosure",
    description="CVD state machine with SLA clock; refuse skip-state transitions.",
))
