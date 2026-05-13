"""R202 — ML-DSA-87 (CNSA 2.0 highest level) signing wrapper.

Threat: NSA CNSA 2.0 (2024) mandates ML-DSA-87 for "Top Secret" by
2030.  R67 wired ML-DSA-65 (Level 3); deployments exporting to NSS
fleets need Level 5.

Defence: a thin wrapper that prefers ML-DSA-87 from ``oqs`` /
``pqcrypto`` if the runtime supplies it; otherwise softly falls back
to ML-DSA-65 + an explicit "level=3" tag so downstream agents see
the gap.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r202")


def keypair() -> Tuple[Optional[bytes], Optional[bytes], str]:
    """Returns ``(public_key, secret_key, backend_tag)``.  Tag is one
    of ``ml_dsa_87``, ``ml_dsa_65_fallback``, or ``unavailable``."""
    try:
        from oqs import Signature
    except BaseException:    # noqa: BLE001 — oqs raises SystemExit when liboqs is missing
        return _fallback_keypair()

    for alg in ("ML-DSA-87", "Dilithium5"):
        try:
            sig = Signature(alg)
            pk = sig.generate_keypair()
            sk = sig.export_secret_key()
            return pk, sk, "ml_dsa_87" if "ML-DSA-87" in alg else "ml_dsa_87_alias"
        except Exception:
            continue
    return _fallback_keypair()


def _fallback_keypair() -> Tuple[Optional[bytes], Optional[bytes], str]:
    try:
        from aria.security.rounds.r67_pq_signing import keypair as fallback_keypair
        pk, sk = fallback_keypair()
        return pk, sk, "ml_dsa_65_fallback"
    except Exception:
        return None, None, "unavailable"


def sign(secret_key: bytes, message: bytes) -> Optional[bytes]:
    try:
        from oqs import Signature
        sig = Signature("ML-DSA-87", secret_key=secret_key)
        return sig.sign(message)
    except BaseException:
        return None


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        from oqs import Signature
        sig = Signature("ML-DSA-87")
        return bool(sig.verify(message, signature, public_key))
    except BaseException:
        return False


register(DefencePlugin(
    round_id="R202",
    name="ml_dsa_87",
    description="ML-DSA-87 (CNSA 2.0 Level 5) signing; soft-fallback to ML-DSA-65.",
))
