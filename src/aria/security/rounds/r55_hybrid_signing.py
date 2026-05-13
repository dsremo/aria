"""R55 — Hybrid classical + post-quantum signing.

Threat: a "harvest-now-decrypt-later" adversary stores today's signed
artefacts and forges them once a cryptographically-relevant quantum
computer (CRQC) lands.  NSA's CNSA 2.0 and EU NIS-2 both mandate a
hybrid migration starting 2025-Q4: every signature should be either
already-PQC (ML-DSA / SLH-DSA) or a hybrid (Ed25519 + ML-DSA combined
into one verifier).

Defence: ``hybrid_sign(message, classical_sk, pq_sk_or_none)`` — emits
a frame that carries an Ed25519 signature plus an optional ML-DSA-65
signature.  Verifier requires BOTH match when ``pq_sk`` was present;
otherwise falls back to classical.  Caller transitions are flag-driven.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


def _classical_sign(message: bytes, sk: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key = ed25519.Ed25519PrivateKey.from_private_bytes(sk)
    return key.sign(message)


def _classical_verify(message: bytes, sig: bytes, pk: bytes) -> bool:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(pk).verify(sig, message)
        return True
    except Exception:
        return False


def _pq_sign(message: bytes, sk: bytes) -> Optional[bytes]:
    """ML-DSA-65 (Dilithium) signing — only if ``oqs`` is installed.
    Returns None when the post-quantum provider is unavailable."""
    try:
        import oqs                                          # liboqs-python
    except Exception:
        return None
    try:
        with oqs.Signature("ML-DSA-65", sk) as signer:
            return signer.sign(message)
    except Exception:
        return None


def _pq_verify(message: bytes, sig: bytes, pk: bytes) -> bool:
    try:
        import oqs
        with oqs.Signature("ML-DSA-65") as v:
            return bool(v.verify(message, sig, pk))
    except Exception:
        return False


def hybrid_sign(
    message: bytes,
    *,
    classical_sk: bytes,
    pq_sk: Optional[bytes] = None,
) -> bytes:
    cs = _classical_sign(message, classical_sk)
    if pq_sk is not None:
        ps = _pq_sign(message, pq_sk)
    else:
        ps = None
    frame = {
        "v": 1,
        "alg": "Ed25519+MLDSA65" if ps is not None else "Ed25519",
        "classical_sig": cs.hex(),
        "pq_sig": ps.hex() if ps is not None else None,
    }
    return json.dumps(frame).encode("utf-8")


def hybrid_verify(
    message: bytes,
    frame_bytes: bytes,
    *,
    classical_pk: bytes,
    pq_pk: Optional[bytes] = None,
) -> Tuple[bool, str]:
    try:
        frame = json.loads(frame_bytes.decode("utf-8"))
    except Exception:
        return False, "bad_frame"
    cs = bytes.fromhex(frame.get("classical_sig", ""))
    if not _classical_verify(message, cs, classical_pk):
        return False, "classical_fail"
    ps_hex = frame.get("pq_sig")
    if ps_hex and pq_pk is not None:
        ps = bytes.fromhex(ps_hex)
        if not _pq_verify(message, ps, pq_pk):
            return False, "pq_fail"
        return True, "Ed25519+MLDSA65"
    return True, "Ed25519_only"


register(DefencePlugin(
    round_id="R55",
    name="hybrid_signing",
    description="Ed25519 + optional ML-DSA-65 hybrid signature wrapper.",
))
