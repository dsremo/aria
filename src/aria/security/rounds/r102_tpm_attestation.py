"""R102 — TPM 2.0 quote-based remote attestation.

Threat: a compromised host may run a tampered ARIA binary or load
hostile shared libraries.  Bank + classified deployments use TPM 2.0
to sign a *quote* over Platform Configuration Registers (PCRs) that
measure the boot chain; a remote verifier then knows whether the
software state matches the expected baseline.

Defence: a thin Python wrapper around the ``tpm2_quote`` binary (or
the in-tree ``tss2`` Python bindings when present).  ``request_quote
(nonce, pcrs)`` returns the quote bytes; ``verify_quote(quote, ek_pub,
expected_pcrs)`` confirms signature + PCR equality.  Falls back to a
software-PCR (R29 attestation.py) when no TPM is present so dev work
isn't blocked.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r102")


@dataclass
class Quote:
    raw: bytes
    signature: bytes
    pcrs_digest: bytes
    nonce: bytes


def _has_tpm() -> bool:
    return Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()


def request_quote(nonce: bytes, *, pcrs: List[int] | None = None) -> Optional[Quote]:
    """Issue a TPM 2.0 quote.  Returns None when no TPM is available
    (caller falls back to R29 software-PCR)."""
    if not _has_tpm():
        return None
    pcr_list = ",".join(str(p) for p in (pcrs or [0, 1, 2, 3, 4, 5, 6, 7, 11]))
    nonce_hex = nonce.hex()
    try:
        proc = subprocess.run(                                  # nosec B603
            ["tpm2_quote", "-c", "ek.handle", "-l", f"sha256:{pcr_list}",
             "-q", nonce_hex, "-m", "/tmp/quote.msg",
             "-s", "/tmp/quote.sig", "-o", "/tmp/quote.pcrs"],
            capture_output=True, timeout=10, check=False,
        )
        if proc.returncode != 0:
            logger.warning("r102.tpm2_quote_failed rc=%d", proc.returncode)
            return None
        return Quote(
            raw=Path("/tmp/quote.msg").read_bytes(),
            signature=Path("/tmp/quote.sig").read_bytes(),
            pcrs_digest=Path("/tmp/quote.pcrs").read_bytes(),
            nonce=nonce,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        logger.info("r102.tpm2_quote_unavailable %s", exc)
        return None


def verify_quote(
    quote: Quote,
    *,
    expected_pcrs_digest: bytes,
    ek_pub_pem: str,
) -> Tuple[bool, str]:
    """Verify the quote signature against ``ek_pub_pem`` AND that the
    quoted PCR digest matches ``expected_pcrs_digest``."""
    if quote.pcrs_digest != expected_pcrs_digest:
        return False, "pcrs_digest_mismatch"
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        pk = serialization.load_pem_public_key(ek_pub_pem.encode())
        pk.verify(quote.signature, quote.raw, padding.PKCS1v15(), hashes.SHA256())
        return True, "ok"
    except Exception as exc:
        return False, f"sig_verify_failed:{exc}"


register(DefencePlugin(
    round_id="R102",
    name="tpm_attestation",
    description="TPM 2.0 quote/verify with software-PCR fallback when no TPM.",
))
