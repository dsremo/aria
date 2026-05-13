"""R63 — RFC-6238 TOTP (the standard 6-digit / 30-s code).

Threat: weak second-factor — SMS is phishable, email is phishable, but
TOTP from a paired authenticator app (Google Authenticator, Authy,
1Password) is the standards-compliant minimum.

Defence: a lightweight TOTP generator + verifier (the constants in
:mod:`aria.security.guard.mfa_admin_check` were a cheap shape; this
round ships the real RFC-6238 with HMAC-SHA-1 (default) plus
HMAC-SHA-256 / SHA-512 alternatives.  Constant-time compare on each
verify; ±1 step window for clock skew.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import struct
import time
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def base32_secret(seed_bytes: bytes) -> str:
    """RFC-4226 secret encoding: base32, padding stripped."""
    return base64.b32encode(seed_bytes).decode("ascii").rstrip("=")


def _hotp(secret_bytes: bytes, counter: int, *, digits: int = 6, alg: str = "SHA1") -> str:
    msg = struct.pack(">Q", counter)
    digest = _hmac.new(secret_bytes, msg, alg.lower()).digest()
    offset = digest[-1] & 0x0F
    code = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )
    return str(code % (10 ** digits)).zfill(digits)


def totp(
    base32_secret_str: str,
    *,
    digits: int = 6,
    step_s: int = 30,
    t0: int = 0,
    when: float | None = None,
    alg: str = "SHA1",
) -> str:
    when = when if when is not None else time.time()
    counter = int((when - t0) // step_s)
    secret = base64.b32decode(base32_secret_str + "=" * (-len(base32_secret_str) % 8))
    return _hotp(secret, counter, digits=digits, alg=alg)


def verify(
    code: str,
    base32_secret_str: str,
    *,
    digits: int = 6,
    step_s: int = 30,
    window: int = 1,
    when: float | None = None,
) -> bool:
    when = when if when is not None else time.time()
    counter = int(when // step_s)
    secret = base64.b32decode(base32_secret_str + "=" * (-len(base32_secret_str) % 8))
    for delta in range(-window, window + 1):
        cand = _hotp(secret, counter + delta, digits=digits)
        if _hmac.compare_digest(cand, str(code).strip()):
            return True
    return False


def provisioning_uri(
    *,
    secret_b32: str,
    label: str,
    issuer: str = "ARIA",
) -> str:
    """RFC-6238 ``otpauth://`` URI suitable for QR encoding."""
    import urllib.parse
    label = urllib.parse.quote(label)
    issuer_enc = urllib.parse.quote(issuer)
    return (
        f"otpauth://totp/{issuer_enc}:{label}"
        f"?secret={secret_b32}&issuer={issuer_enc}&digits=6&period=30"
    )


register(DefencePlugin(
    round_id="R63",
    name="totp",
    description="RFC-6238 TOTP generator + verifier with ±1 step skew window.",
))
