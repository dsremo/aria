"""R59 — TLS downgrade refusal (POODLE/BEAST/CRIME/Heartbleed-class).

Threat: a MITM forces the connection down to TLS 1.0 or SSLv3 to enable
known cryptanalysis (POODLE on SSLv3, BEAST on TLS 1.0 CBC, CRIME on
TLS compression, FREAK on export-grade RSA).  Bank policy: TLS 1.2+
only, with TLS 1.3 preferred; refuse weaker.

Defence: a simple negotiation policy enforcer.  ``enforce_tls_policy
(socket_or_ssl_object)`` raises if the negotiated version is < 1.2 or
the cipher is in the deprecated set.  Useful for outbound calls where
ARIA picks the cipher (most cases handled by Python's default ssl
context, but worth a hard check on egress to high-value upstreams).
"""

from __future__ import annotations

import ssl
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_BANNED_VERSIONS = frozenset({
    "SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1",
})

# Subset that historically collapsed under attack.
_BANNED_CIPHER_SUBSTRINGS = (
    "RC4",          # Bar Mitzvah
    "DES",          # 56-bit
    "3DES",         # SWEET32
    "EXPORT",       # FREAK
    "NULL",
    "MD5",
    "anon",
)


def is_safe_negotiation(version: str, cipher: str) -> Tuple[bool, str]:
    if version in _BANNED_VERSIONS:
        return False, f"version_banned:{version}"
    for sub in _BANNED_CIPHER_SUBSTRINGS:
        if sub in cipher:
            return False, f"cipher_banned:{cipher} contains {sub}"
    return True, ""


def enforce_tls_policy(ssl_socket: ssl.SSLSocket) -> None:
    """Raise ``RuntimeError`` if the negotiated session is below policy."""
    try:
        version = ssl_socket.version() or ""
        cipher_tuple = ssl_socket.cipher()
        cipher = cipher_tuple[0] if cipher_tuple else ""
    except Exception:
        return
    ok, reason = is_safe_negotiation(version, cipher)
    if not ok:
        raise RuntimeError(f"R59.tls_downgrade: {reason}")


def make_strict_context() -> ssl.SSLContext:
    """Return a client SSLContext that refuses TLS < 1.2 and weak ciphers."""
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("HIGH:!aNULL:!eNULL:!MD5:!DES:!3DES:!RC4:!EXPORT")
    ctx.options |= ssl.OP_NO_COMPRESSION                 # CRIME defence
    return ctx


register(DefencePlugin(
    round_id="R59",
    name="tls_downgrade",
    description="Refuse TLS < 1.2 + banned cipher families on outbound.",
))
