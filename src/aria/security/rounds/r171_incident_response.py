"""R171 — Incident response runbook gate.

Threat: an incident hits and the team realizes there is no playbook
— who decides to invoke kill-switch, who notifies regulators, who
talks to customers.  Mean-time-to-respond doubles; legal exposure
grows hour-over-hour.

Defence: a typed ``Incident`` + ``open_incident`` that records the
event, picks the playbook stage by severity, and refuses to mark
"closed" without the required artefacts (root cause, comms, lessons).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_SEVERITIES = ("SEV1", "SEV2", "SEV3", "SEV4")


@dataclass
class Incident:
    id: str
    severity: str
    summary: str
    detected_at: float
    closed_at: Optional[float] = None
    artefacts: Dict[str, str] = field(default_factory=dict)
    timeline: List[Tuple[float, str]] = field(default_factory=list)


_OPEN: Dict[str, Incident] = {}
_LOCK = threading.Lock()


def open_incident(severity: str, summary: str) -> Incident:
    if severity not in _SEVERITIES:
        raise ValueError(f"R171: severity must be one of {_SEVERITIES}")
    iid = f"INC-{int(time.time())}-{len(_OPEN) + 1:03d}"
    inc = Incident(id=iid, severity=severity, summary=summary, detected_at=time.time())
    inc.timeline.append((inc.detected_at, f"opened:{severity}"))
    with _LOCK:
        _OPEN[iid] = inc
    return inc


def add_artefact(iid: str, name: str, value: str) -> None:
    with _LOCK:
        inc = _OPEN.get(iid)
    if inc is None:
        raise KeyError(iid)
    inc.artefacts[name] = value
    inc.timeline.append((time.time(), f"artefact:{name}"))


def close_incident(iid: str) -> Tuple[bool, str]:
    required = {"SEV1": ("root_cause", "comms", "lessons", "fix_pr"),
                "SEV2": ("root_cause", "comms", "lessons"),
                "SEV3": ("root_cause", "lessons"),
                "SEV4": ("root_cause",)}
    with _LOCK:
        inc = _OPEN.get(iid)
    if inc is None:
        return False, "unknown_incident"
    needed = required[inc.severity]
    missing = [k for k in needed if k not in inc.artefacts]
    if missing:
        return False, f"missing_artefacts:{','.join(missing)}"
    inc.closed_at = time.time()
    inc.timeline.append((inc.closed_at, "closed"))
    return True, "closed"


def list_open() -> List[Incident]:
    with _LOCK:
        return [i for i in _OPEN.values() if i.closed_at is None]


register(DefencePlugin(
    round_id="R171",
    name="incident_response",
    description="Incident open/close gate; refuses close without required artefacts.",
))
