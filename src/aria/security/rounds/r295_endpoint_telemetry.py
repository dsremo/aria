"""R295 — Endpoint-telemetry consent + opt-in gate.

Threat: insider monitoring (keyloggers, screen recording, app
telemetry) is potent against insiders but legally sensitive — EU
worker-protection laws, US ECPA, GDPR Art. 6 + 9.  Deploying without
explicit consent invalidates the evidence and triggers fines.

Defence: a consent-gate helper.  ``consume_telemetry_event`` refuses
to record unless the user has an active, dated consent record + the
event class is in the disclosed catalog.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ConsentRecord:
    user_id: str
    granted_at: float
    expires_at: float
    disclosed_event_classes: Set[str]
    revoked_at: float = 0.0


_CONSENTS: Dict[str, ConsentRecord] = {}
_LOCK = threading.Lock()


def record_consent(user_id: str, *, valid_for_days: float = 365.0,
                   disclosed_event_classes: List[str]) -> ConsentRecord:
    t = time.time()
    rec = ConsentRecord(
        user_id=user_id, granted_at=t,
        expires_at=t + valid_for_days * 86_400.0,
        disclosed_event_classes=set(disclosed_event_classes),
    )
    with _LOCK:
        _CONSENTS[user_id] = rec
    return rec


def revoke_consent(user_id: str) -> None:
    with _LOCK:
        rec = _CONSENTS.get(user_id)
        if rec:
            rec.revoked_at = time.time()


def consume_telemetry_event(user_id: str, event_class: str, *, now: float = 0.0) -> Tuple[bool, str]:
    t = now or time.time()
    with _LOCK:
        rec = _CONSENTS.get(user_id)
    if rec is None:
        return False, "consent.absent"
    if rec.revoked_at:
        return False, "consent.revoked"
    if t > rec.expires_at:
        return False, "consent.expired"
    if event_class not in rec.disclosed_event_classes:
        return False, f"consent.event_class_undisclosed:{event_class}"
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _CONSENTS.clear()


register(DefencePlugin(
    round_id="R295",
    name="endpoint_telemetry",
    description="Endpoint-telemetry consent gate with explicit event-class catalog + expiry.",
))
