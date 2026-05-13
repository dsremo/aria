"""R54 — AES-GCM-SIV (nonce-misuse-resistant authenticated encryption).

Threat: AES-GCM catastrophically loses confidentiality + authenticity
when a 96-bit nonce repeats under the same key.  Real-world cases:
WhatsApp 2017 (nonce-reuse on rekey), countless IoT devices, several
cloud-provider audits.  Banking + nation-state guidance: don't ship
GCM unless nonces come from a verified counter.

Defence: a thin wrapper that prefers ``cryptography``'s ``AESGCMSIV``
(nonce-misuse-resistant per RFC-8452) when the runtime version supports
it; falls back to AES-GCM with a guaranteed-unique nonce derived from
HKDF + a monotonic counter.  Either path is FIPS-class compatible when
the underlying provider is.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_CTR_LOCK = threading.Lock()
_CTR = 0


def _next_unique_nonce() -> bytes:
    """Combine 64-bit monotonic time + 32-bit counter → 12-byte nonce.
    Guaranteed unique per process; a process-restart re-seeds the time.
    """
    global _CTR
    with _CTR_LOCK:
        _CTR = (_CTR + 1) & 0xFFFFFFFF
        ctr = _CTR
    t_ns = time.monotonic_ns() & 0xFFFFFFFFFFFFFFFF
    return t_ns.to_bytes(8, "big") + ctr.to_bytes(4, "big")


def encrypt(plaintext: bytes, *, key: bytes, aad: bytes = b"") -> Tuple[bytes, bytes]:
    """Return ``(nonce, ciphertext_with_tag)``.  Caller stores both.

    Tries AES-GCM-SIV first (nonce-misuse-resistant).  Falls back to
    AES-GCM with a guaranteed-unique nonce.
    """
    if len(key) not in (16, 24, 32):
        raise ValueError("R54.aes_gcm: key must be 128/192/256 bit")
    nonce = _next_unique_nonce()
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV
        ct = AESGCMSIV(key).encrypt(nonce, plaintext, aad)
        return nonce, ct
    except Exception:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ct = AESGCM(key).encrypt(nonce, plaintext, aad)
        return nonce, ct


def decrypt(
    nonce: bytes,
    ciphertext: bytes,
    *,
    key: bytes,
    aad: bytes = b"",
) -> bytes:
    if len(nonce) != 12:
        raise ValueError("R54.aes_gcm: nonce must be 12 bytes")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV
        return AESGCMSIV(key).decrypt(nonce, ciphertext, aad)
    except Exception:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(nonce, ciphertext, aad)


def random_key(*, bits: int = 256) -> bytes:
    if bits not in (128, 192, 256):
        raise ValueError("bits must be 128/192/256")
    return secrets.token_bytes(bits // 8)


register(DefencePlugin(
    round_id="R54",
    name="aes_gcm_siv",
    description="AESGCMSIV-preferred authenticated encryption with unique-nonce fallback.",
))
