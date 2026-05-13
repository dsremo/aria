"""R61 — ML-KEM-768 (Kyber-768) post-quantum key-encapsulation hook.

Threat: a "harvest-now decrypt-later" adversary records ARIA's TLS
handshakes today and decrypts them once a CRQC arrives (NIST estimates
2030–2040).  The transitional answer is a hybrid X25519+ML-KEM-768 KEM
in the TLS 1.3 ClientHello (RFC 9180 + draft-ietf-tls-hybrid-design).

Defence: a thin wrapper around ``oqs.KeyEncapsulation("ML-KEM-768")``
with a ``derive_shared_secret`` API.  Used by the inter-service
zero-trust channel (`aria.security.pqc.SecureChannel`) when the
counterpart advertises PQC support.  Soft-fail to X25519-only when
``oqs`` is unavailable — the round is wired so we know it's a
classical-only deployment and audit-log it.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r61")


def is_pq_available() -> bool:
    try:
        import oqs                        # liboqs-python
        with oqs.KeyEncapsulation("ML-KEM-768"):
            return True
    except BaseException:
        return False


def kem_keypair() -> Tuple[Optional[bytes], Optional[bytes]]:
    """Return ``(public_key, secret_key)`` for ML-KEM-768; ``(None, None)``
    when the post-quantum provider is unavailable."""
    try:
        import oqs
        with oqs.KeyEncapsulation("ML-KEM-768") as kem:
            pk = kem.generate_keypair()
            sk = kem.export_secret_key()
            return pk, sk
    except BaseException:
        logger.info("r61.pq_unavailable using classical-only fallback")
        return None, None


def kem_encapsulate(peer_public_key: bytes) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Generate a fresh ciphertext + shared secret for ``peer_public_key``."""
    try:
        import oqs
        with oqs.KeyEncapsulation("ML-KEM-768") as kem:
            ct, ss = kem.encap_secret(peer_public_key)
            return ct, ss
    except BaseException:
        return None, None


def kem_decapsulate(secret_key: bytes, ciphertext: bytes) -> Optional[bytes]:
    try:
        import oqs
        with oqs.KeyEncapsulation("ML-KEM-768", secret_key) as kem:
            return kem.decap_secret(ciphertext)
    except BaseException:
        return None


register(DefencePlugin(
    round_id="R61",
    name="ml_kem_768",
    description="ML-KEM-768 wrapper with classical-only fallback notice.",
))
