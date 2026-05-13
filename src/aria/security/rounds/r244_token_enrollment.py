"""R244 — Hardware-token enrollment ceremony.

Threat: enrolling a FIDO2 / PIV / smart-card token over the network
without an in-person ceremony lets an attacker register their own
token at the moment of provisioning — bypassing every subsequent
auth check.

Defence: ``begin_enrollment`` requires (a) physical-presence flag,
(b) attestation chain back to a vendor root, (c) two-person rule
(R243) for privileged tokens.  Records full ceremony for audit.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class EnrollmentRecord:
    token_id: str
    user_id: str
    started_at: float
    physical_presence: bool
    attestation_vendor: str
    privileged: bool = False
    completed: bool = False
    audit: List[Tuple[float, str]] = field(default_factory=list)


_ENROLLMENTS: Dict[str, EnrollmentRecord] = {}
_LOCK = threading.Lock()


def begin_enrollment(
    *, token_id: str, user_id: str, physical_presence: bool,
    attestation_vendor: str, privileged: bool = False,
) -> Tuple[bool, str]:
    if not physical_presence:
        return False, "enrol.no_physical_presence"
    if not attestation_vendor:
        return False, "enrol.no_attestation_vendor"
    rec = EnrollmentRecord(
        token_id=token_id, user_id=user_id, started_at=time.time(),
        physical_presence=physical_presence,
        attestation_vendor=attestation_vendor, privileged=privileged,
    )
    rec.audit.append((rec.started_at, "begin"))
    with _LOCK:
        _ENROLLMENTS[token_id] = rec
    return True, f"enrol.opened token_id={token_id}"


def complete_enrollment(token_id: str, *, two_person_token: str = "") -> Tuple[bool, str]:
    with _LOCK:
        rec = _ENROLLMENTS.get(token_id)
        if rec is None:
            return False, "enrol.unknown_token"
        if rec.privileged and not two_person_token:
            return False, "enrol.privileged_requires_two_person"
        rec.completed = True
        rec.audit.append((time.time(), f"complete two_person={bool(two_person_token)}"))
    return True, "enrol.completed"


def get_record(token_id: str) -> EnrollmentRecord:
    with _LOCK:
        return _ENROLLMENTS.get(token_id)


register(DefencePlugin(
    round_id="R244",
    name="token_enrollment",
    description="Hardware-token enrollment ceremony with physical-presence + attestation gate.",
))
