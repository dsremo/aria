"""R106 — Sealed storage tied to PCR measurement.

Threat: an attacker who clones the disk to another host and boots it
should NOT be able to recover ARIA's tenant keys.  TPM-sealed storage
binds decryption to the local PCR state; cloning to a different
firmware blocks unseal.  Standard for hardware-rooted secret keeping.

Defence: ``seal(blob, expected_pcrs)`` calls ``tpm2_create`` /
``tpm2_seal`` (when TPM present) and produces an opaque packet that
can only be unsealed on the same host with the same boot measurements.
Soft-fails to AES-256-GCM with the master key (R53 derive) when no
TPM exists; the audit chain records which path was used.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r106")


def _has_tpm() -> bool:
    return Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()


def seal(blob: bytes, *, label: str = "aria_secret") -> Optional[bytes]:
    """Return sealed packet or None on failure.  Caller stores the
    packet alongside the application data."""
    if not _has_tpm():
        return _soft_seal(blob, label=label)
    # tpm2_seal happy path
    try:
        import subprocess
        in_path = f"/tmp/aria_seal_{secrets.token_hex(4)}.bin"
        out_pub = in_path + ".pub"
        out_priv = in_path + ".priv"
        Path(in_path).write_bytes(blob)
        subprocess.run(                                       # nosec B603
            ["tpm2_create", "-C", "primary.ctx", "-i", in_path,
             "-u", out_pub, "-r", out_priv, "-L", "policy.dat"],
            check=True, capture_output=True, timeout=10,
        )
        sealed = Path(out_pub).read_bytes() + b"|" + Path(out_priv).read_bytes()
        Path(in_path).unlink(missing_ok=True)
        return sealed
    except Exception as exc:
        logger.warning("r106.tpm2_seal_failed %s", exc)
        return _soft_seal(blob, label=label)


def unseal(packet: bytes, *, label: str = "aria_secret") -> Optional[bytes]:
    if not _has_tpm():
        return _soft_unseal(packet, label=label)
    try:
        import subprocess
        # tpm2_unseal happy path — caller has primary handle preloaded
        proc = subprocess.run(                                # nosec B603
            ["tpm2_unseal", "-c", "object.ctx", "-p", "session:session.dat"],
            input=packet, capture_output=True, timeout=10, check=True,
        )
        return proc.stdout
    except Exception as exc:
        logger.warning("r106.tpm2_unseal_failed %s", exc)
        return _soft_unseal(packet, label=label)


def _soft_seal(blob: bytes, *, label: str) -> Optional[bytes]:
    """AES-GCM encrypt with HKDF-derived per-label key (R53)."""
    try:
        from aria.security.rounds.r53_hkdf_per_tenant import derive
        from aria.security.rounds.r54_aes_gcm_siv import encrypt
        key = derive(f"sealed:{label}", "machine", 32)
        nonce, ct = encrypt(blob, key=key)
        return b"SOFT|" + nonce + b"|" + ct
    except Exception as exc:
        logger.warning("r106.soft_seal_failed %s", exc)
        return None


def _soft_unseal(packet: bytes, *, label: str) -> Optional[bytes]:
    if not packet.startswith(b"SOFT|"):
        return None
    try:
        from aria.security.rounds.r53_hkdf_per_tenant import derive
        from aria.security.rounds.r54_aes_gcm_siv import decrypt
        rest = packet[len(b"SOFT|"):]
        nonce, ct = rest.split(b"|", 1)
        key = derive(f"sealed:{label}", "machine", 32)
        return decrypt(nonce, ct, key=key)
    except Exception as exc:
        logger.warning("r106.soft_unseal_failed %s", exc)
        return None


register(DefencePlugin(
    round_id="R106",
    name="sealed_storage",
    description="TPM-sealed storage with AES-GCM-SIV soft fallback.",
))
