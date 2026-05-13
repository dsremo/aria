"""R176 — Firmware signing chain verification.

Threat: a malicious or unsigned firmware image flashed onto a device
becomes persistent code.  LoJax / BlackLotus class.  IoT vendors
often ship debug firmware to production by accident.

Defence: a verifier that ingests a firmware blob + signature + public
key, returns OK only if the Ed25519 (or hybrid Ed25519+ML-DSA)
signature validates over the *exact* blob bytes.  Pairs with R67.
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def verify_firmware_blob(
    blob: bytes,
    signature: bytes,
    *,
    ed25519_pubkey: bytes,
    expected_sha256: bytes = b"",
) -> Tuple[bool, str]:
    if expected_sha256:
        if hashlib.sha256(blob).digest() != expected_sha256:
            return False, "firmware.sha256_mismatch"

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False, "firmware.cryptography_missing"

    try:
        pk = Ed25519PublicKey.from_public_bytes(ed25519_pubkey)
        pk.verify(signature, blob)
        return True, "firmware.signature_ok"
    except Exception as exc:
        return False, f"firmware.signature_invalid:{type(exc).__name__}"


def boot_check_firmware_chain(*chain: Tuple[bytes, bytes, bytes]) -> Tuple[bool, str]:
    """``chain`` is a list of (blob, sig, pubkey) tuples — boot,
    bootloader, kernel, app — each verified in order."""
    for i, (blob, sig, pk) in enumerate(chain):
        ok, why = verify_firmware_blob(blob, sig, ed25519_pubkey=pk)
        if not ok:
            return False, f"stage_{i}:{why}"
    return True, f"chain_verified n={len(chain)}"


register(DefencePlugin(
    round_id="R176",
    name="firmware_signing",
    description="Multi-stage firmware Ed25519 signature chain verifier.",
))
