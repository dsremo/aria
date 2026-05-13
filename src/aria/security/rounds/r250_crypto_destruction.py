"""R250 — Cryptographic destruction (key rollover with secure erase).

Threat: at end-of-life, a system that simply marks a key "retired"
leaves the bytes recoverable from disk / RAM / backup.  Crypto-erase
(NIST 800-88) requires the key to be unrecoverable so wrapped
ciphertext is permanently destroyed.

Defence: a secure-erase helper that overwrites memory + zeroises
file-backed key material + emits a destruction certificate signed
via R67 hybrid signing.  Pairs with R210 inventory.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class DestructionCertificate:
    key_id: str
    destroyed_at: float
    method: str
    signature_hex: str
    issued_by: str


def secure_erase_buffer(buffer: bytearray) -> None:
    if not isinstance(buffer, bytearray):
        return
    n = len(buffer)
    for _ in range(3):
        rand = secrets.token_bytes(n)
        for i in range(n):
            buffer[i] = rand[i]
    for i in range(n):
        buffer[i] = 0


def secure_erase_file(path: str, *, passes: int = 3) -> Tuple[bool, str]:
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return False, f"file_unavailable:{exc}"
    try:
        with open(path, "r+b") as fh:
            for _ in range(passes):
                fh.seek(0)
                fh.write(secrets.token_bytes(size))
                fh.flush()
                os.fsync(fh.fileno())
            fh.seek(0)
            fh.write(b"\x00" * size)
            fh.flush()
            os.fsync(fh.fileno())
        os.unlink(path)
        return True, f"erased size={size}"
    except OSError as exc:
        return False, f"erase_failed:{exc}"


def issue_destruction_certificate(
    *, key_id: str, method: str = "secure_overwrite",
    issued_by: str = "ARIA_R250",
) -> Optional[DestructionCertificate]:
    try:
        from aria.security.rounds.r67_pq_signing import sign as pq_sign, keypair as pq_keypair
        _, sk = pq_keypair()
    except Exception:
        return None
    try:
        payload = f"{key_id}|{method}|{int(time.time())}".encode()
        sig = pq_sign(sk, payload)
        return DestructionCertificate(
            key_id=key_id, destroyed_at=time.time(), method=method,
            signature_hex=sig.hex() if sig else "",
            issued_by=issued_by,
        )
    except Exception:
        return None


register(DefencePlugin(
    round_id="R250",
    name="crypto_destruction",
    description="Secure-erase buffer/file + signed destruction certificate (NIST 800-88).",
))
