"""R347 — Bug bounty intake plumbing.

Threat: a security researcher emailing a serious finding to the
generic ``support@`` address has it triaged by a tier-1 agent who
miscategorises it; mean-time-to-triage measures in days, not hours.
Bug-bounty plumbing routes findings directly to security.

Defence: a structured intake helper that validates a submission
against the SECURITY.md disclosure policy + emits an acknowledgement
within minutes.  Pairs with R348 (coordinated disclosure).
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Tuple

from aria.security.plugins import DefencePlugin, register


_VALID_SEVERITIES = ("low", "medium", "high", "critical")


@dataclass
class BountyReport:
    submission_id: str
    severity: str
    title: str
    summary: str
    received_at: float = 0.0
    contact: str = ""
    pgp_present: bool = False
    accepted: bool = False
    rejection_reason: str = ""


_QUEUE: Deque[BountyReport] = deque(maxlen=4096)
_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def submit_report(
    *, submission_id: str, severity: str, title: str, summary: str,
    contact: str = "", pgp_present: bool = False,
) -> Tuple[BountyReport, str]:
    rec = BountyReport(
        submission_id=submission_id, severity=severity.lower(),
        title=title, summary=summary, received_at=time.time(),
        contact=contact, pgp_present=pgp_present,
    )
    if rec.severity not in _VALID_SEVERITIES:
        rec.rejection_reason = f"invalid_severity:{severity}"
    elif not rec.title or len(rec.summary) < 30:
        rec.rejection_reason = "summary_too_short"
    elif rec.contact and not _EMAIL_RE.match(rec.contact):
        rec.rejection_reason = "contact_not_email"
    else:
        rec.accepted = True
    with _LOCK:
        _QUEUE.append(rec)
    return rec, "accepted" if rec.accepted else f"rejected:{rec.rejection_reason}"


def queue_depth() -> int:
    with _LOCK:
        return len(_QUEUE)


def critical_pending() -> List[BountyReport]:
    with _LOCK:
        return [r for r in _QUEUE if r.accepted and r.severity == "critical"]


def reset_for_tests() -> None:
    with _LOCK:
        _QUEUE.clear()


register(DefencePlugin(
    round_id="R347",
    name="bug_bounty",
    description="Structured bug-bounty intake; reject malformed; track queue depth.",
))
