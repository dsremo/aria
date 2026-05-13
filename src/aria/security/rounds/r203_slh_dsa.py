"""R203 — SLH-DSA (SPHINCS+) hash-based signature wrapper.

Threat: ML-DSA / Falcon are *lattice* schemes — a future lattice-
oracle break would void them all simultaneously.  Signatures protecting
ten-year code-signing roots need *hash-based* assumptions instead
(SLH-DSA, FIPS-205, 2024).

Defence: a wrapper that picks SLH-DSA-SHA2-128s (small-key/long-sig)
or SLH-DSA-SHA2-128f (fast/big-sig) profile per use; soft-fallback
to a logged warning if the runtime lacks oqs.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r203")


_PROFILES = {
    "small": "SPHINCS+-SHA2-128s-simple",
    "fast":  "SPHINCS+-SHA2-128f-simple",
    "high":  "SPHINCS+-SHA2-256s-simple",
}


def keypair(profile: str = "small") -> Tuple[Optional[bytes], Optional[bytes], str]:
    alg = _PROFILES.get(profile, _PROFILES["small"])
    try:
        from oqs import Signature
    except BaseException:    # oqs raises SystemExit when liboqs is missing
        return None, None, "unavailable"
    try:
        sig = Signature(alg)
        pk = sig.generate_keypair()
        sk = sig.export_secret_key()
        return pk, sk, alg
    except Exception as exc:
        logger.warning("r203.keypair_failed alg=%s exc=%s", alg, exc)
        return None, None, "unavailable"


def sign(secret_key: bytes, message: bytes, profile: str = "small") -> Optional[bytes]:
    alg = _PROFILES.get(profile, _PROFILES["small"])
    try:
        from oqs import Signature
        sig = Signature(alg, secret_key=secret_key)
        return sig.sign(message)
    except BaseException:
        return None


def verify(public_key: bytes, message: bytes, signature: bytes, profile: str = "small") -> bool:
    alg = _PROFILES.get(profile, _PROFILES["small"])
    try:
        from oqs import Signature
        sig = Signature(alg)
        return bool(sig.verify(message, signature, public_key))
    except BaseException:
        return False


register(DefencePlugin(
    round_id="R203",
    name="slh_dsa",
    description="SLH-DSA / SPHINCS+ hash-based signatures (FIPS 205) for code-signing roots.",
))
