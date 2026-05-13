"""R249 — FISMA-High / NSS audit-trail enforcement.

Threat: NSS / FISMA-High require complete, tamper-evident audit
trails for *every* privileged action, with retention beyond the
agency's lifetime.  Gaps are weaponised by adversaries to deny
forensic reconstruction.

Defence: ``record_high_action`` enriches an action record with the
full chain of (actor, source_ip, sis_classification, hash chain,
two-person ID).  Refuses to record incomplete entries.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class HighActionRecord:
    timestamp: float
    actor: str
    source_ip: str
    classification: str
    action: str
    target: str
    two_person_id: str
    chain_hash: str = ""


_PREV: List[str] = ["0" * 64]
_LEDGER: List[HighActionRecord] = []
_LOCK = threading.Lock()


def record_high_action(
    *, actor: str, source_ip: str, classification: str,
    action: str, target: str, two_person_id: str,
) -> Tuple[bool, str]:
    if not all([actor, source_ip, classification, action, target, two_person_id]):
        return False, "fisma.incomplete_record"
    if classification.lower() not in ("unclassified", "secret", "top_secret", "ts_sci"):
        return False, f"fisma.invalid_classification:{classification}"
    rec = HighActionRecord(
        timestamp=time.time(), actor=actor, source_ip=source_ip,
        classification=classification, action=action, target=target,
        two_person_id=two_person_id,
    )
    with _LOCK:
        prev = _PREV[-1]
        rec.chain_hash = hashlib.sha256(
            f"{rec.timestamp}|{rec.actor}|{rec.action}|{rec.target}|{prev}".encode()
        ).hexdigest()
        _LEDGER.append(rec)
        _PREV.append(rec.chain_hash)
    return True, rec.chain_hash


def verify_fisma_chain() -> Tuple[bool, int]:
    prev = "0" * 64
    with _LOCK:
        ledger = list(_LEDGER)
    for i, r in enumerate(ledger):
        recomputed = hashlib.sha256(
            f"{r.timestamp}|{r.actor}|{r.action}|{r.target}|{prev}".encode()
        ).hexdigest()
        if recomputed != r.chain_hash:
            return False, i
        prev = r.chain_hash
    return True, len(ledger)


def reset_for_tests() -> None:
    with _LOCK:
        _PREV.clear()
        _PREV.append("0" * 64)
        _LEDGER.clear()


register(DefencePlugin(
    round_id="R249",
    name="fisma_high_audit",
    description="FISMA-High / NSS audit ledger; refuses incomplete records, tamper-evident chain.",
))
