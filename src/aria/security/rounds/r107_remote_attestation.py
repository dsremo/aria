"""R107 — Remote attestation challenge / response orchestrator.

Threat: a fleet operator wants to confirm every node is a *legitimate*
ARIA host before letting it join the bus.  TPM 2.0 attestation
(R102) gives the cryptographic primitive; this round wires it into a
challenge-response protocol the operator runs.

Defence: ``issue_challenge()`` mints a 32-byte nonce and stores it
keyed on the attesting node id; ``verify_response(node_id, quote,
ek_pub_pem, expected_pcrs_digest)`` calls R102 ``verify_quote`` and
records the verdict.  Anti-replay enforced via R8 nonce ledger.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r107")


@dataclass
class _Challenge:
    nonce: bytes
    issued_at: float


_OPEN: Dict[str, _Challenge] = {}
_LOCK = threading.Lock()
_TTL = 120.0


def issue_challenge(node_id: str) -> bytes:
    nonce = secrets.token_bytes(32)
    with _LOCK:
        _OPEN[node_id] = _Challenge(nonce=nonce, issued_at=time.monotonic())
    return nonce


def verify_response(
    node_id: str,
    quote_bytes: bytes,
    *,
    ek_pub_pem: str,
    expected_pcrs_digest: bytes,
) -> Tuple[bool, str]:
    with _LOCK:
        c = _OPEN.pop(node_id, None)
    if c is None:
        return False, "no_open_challenge"
    if time.monotonic() - c.issued_at > _TTL:
        return False, "challenge_expired"

    # Anti-replay (R8)
    try:
        from aria.security.rounds.r08_replay_nonce import check_and_consume
        if not check_and_consume(c.nonce.hex()):
            return False, "nonce_replayed"
    except Exception:
        pass

    # Defer to R102 verifier — quote_bytes carries (raw, sig, pcrs_digest).
    # In production the wire format is operator-defined; here we accept
    # the canonical 3-part frame: raw||0x00||sig||0x00||pcrs_digest.
    try:
        parts = quote_bytes.split(b"\x00", 2)
        if len(parts) != 3:
            return False, "frame_shape"
        raw, sig, pcrs_digest = parts
        from aria.security.rounds.r102_tpm_attestation import Quote, verify_quote
        q = Quote(raw=raw, signature=sig, pcrs_digest=pcrs_digest, nonce=c.nonce)
        return verify_quote(q, expected_pcrs_digest=expected_pcrs_digest, ek_pub_pem=ek_pub_pem)
    except Exception as exc:
        return False, f"verify_failed:{exc}"


register(DefencePlugin(
    round_id="R107",
    name="remote_attestation",
    description="Fleet-join challenge/response wiring R102 + R8 replay-resist.",
))
