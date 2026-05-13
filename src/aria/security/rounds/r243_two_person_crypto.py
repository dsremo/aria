"""R243 — Two-person rule for cryptographic operations.

Threat: a single rogue admin with the master KEK can re-sign
malicious code, exfiltrate signed builds, or rotate keys to
attacker-controlled values.  Banks, NSA, CIA all require two-person
integrity (TPI) for sensitive crypto.

Defence: extends R47 (two-person rule for prod actions) with a
crypto-operations specialisation — each high-impact crypto op
(master-key rotation, code-signing key issuance, HSM unwrap of root)
must collect two distinct signing tokens.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _CeremonyState:
    operation: str
    quorum: int
    approvers: Set[str] = field(default_factory=set)
    opened_at: float = 0.0


_OPEN_CEREMONIES: Dict[str, _CeremonyState] = {}
_LOCK = threading.Lock()
_TIMEOUT_SECONDS = 600.0


def open_ceremony(operation: str, *, quorum: int = 2) -> str:
    if quorum < 2:
        raise ValueError("R243: quorum < 2 violates two-person rule")
    cid = f"ceremony-{int(time.time())}-{operation}"
    with _LOCK:
        _OPEN_CEREMONIES[cid] = _CeremonyState(
            operation=operation, quorum=quorum, opened_at=time.time(),
        )
    return cid


def approve(ceremony_id: str, approver_id: str) -> Tuple[bool, str]:
    if not approver_id:
        return False, "empty_approver"
    with _LOCK:
        cer = _OPEN_CEREMONIES.get(ceremony_id)
        if cer is None:
            return False, "unknown_ceremony"
        if time.time() - cer.opened_at > _TIMEOUT_SECONDS:
            _OPEN_CEREMONIES.pop(ceremony_id, None)
            return False, "ceremony_expired"
        cer.approvers.add(approver_id)
        ready = len(cer.approvers) >= cer.quorum
    return True, f"ok approvers={len(cer.approvers)}/{cer.quorum} ready={ready}"


def is_approved(ceremony_id: str) -> Tuple[bool, Optional[List[str]]]:
    with _LOCK:
        cer = _OPEN_CEREMONIES.get(ceremony_id)
        if cer is None:
            return False, None
        if len(cer.approvers) < cer.quorum:
            return False, list(cer.approvers)
        return True, list(cer.approvers)


def close_ceremony(ceremony_id: str) -> None:
    with _LOCK:
        _OPEN_CEREMONIES.pop(ceremony_id, None)


register(DefencePlugin(
    round_id="R243",
    name="two_person_crypto",
    description="Two-person quorum enforcement for sensitive crypto operations.",
))
