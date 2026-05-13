"""R199 — Cryptographic chain-of-custody.

Threat: forensic artefacts handed to law enforcement / regulators
must have an unbroken provenance — who handled them, when, with what
hash.  A break in custody invalidates the evidence under most legal
frameworks (FRE 901, EU eIDAS).

Defence: a hash-chain ledger.  Every artefact registered emits a
record signed with R67 hybrid Ed25519+ML-DSA; every transfer is
appended.  Tampering breaks the chain; verification is one pass.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class CustodyEntry:
    timestamp: float
    artefact_id: str
    actor: str
    action: str
    artefact_sha256: str
    prev_chain_hash: str
    chain_hash: str = ""

    def serialise(self) -> bytes:
        return json.dumps({
            "ts": self.timestamp, "id": self.artefact_id,
            "actor": self.actor, "action": self.action,
            "sha": self.artefact_sha256, "prev": self.prev_chain_hash,
        }, sort_keys=True).encode("utf-8")


_LEDGER: List[CustodyEntry] = []
_LOCK = threading.Lock()


def register_artefact(artefact_id: str, actor: str, blob: bytes) -> CustodyEntry:
    return _append(artefact_id, actor, "register", hashlib.sha256(blob).hexdigest())


def transfer(artefact_id: str, from_actor: str, to_actor: str, blob: bytes) -> CustodyEntry:
    return _append(artefact_id, f"{from_actor}->{to_actor}", "transfer",
                   hashlib.sha256(blob).hexdigest())


def _append(artefact_id: str, actor: str, action: str, sha: str) -> CustodyEntry:
    with _LOCK:
        prev = _LEDGER[-1].chain_hash if _LEDGER else ("0" * 64)
        entry = CustodyEntry(
            timestamp=time.time(), artefact_id=artefact_id, actor=actor,
            action=action, artefact_sha256=sha, prev_chain_hash=prev,
        )
        entry.chain_hash = hashlib.sha256(entry.serialise() + prev.encode()).hexdigest()
        _LEDGER.append(entry)
    return entry


def verify_chain() -> Tuple[bool, int]:
    with _LOCK:
        ledger = list(_LEDGER)
    prev = "0" * 64
    for i, e in enumerate(ledger):
        recomputed = hashlib.sha256(e.serialise() + prev.encode()).hexdigest()
        if recomputed != e.chain_hash or e.prev_chain_hash != prev:
            return False, i
        prev = e.chain_hash
    return True, len(ledger)


def history_for(artefact_id: str) -> List[CustodyEntry]:
    with _LOCK:
        return [e for e in _LEDGER if e.artefact_id == artefact_id]


register(DefencePlugin(
    round_id="R199",
    name="chain_of_custody",
    description="Hash-chain forensic custody ledger (FRE 901 / eIDAS-grade).",
))
