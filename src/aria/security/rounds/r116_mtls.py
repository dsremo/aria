"""R116 — Mutual-TLS (mTLS) helper for inter-service.

Threat: service-to-service traffic on the cluster network goes
plaintext or one-way TLS by default.  Banking + zero-trust enterprise
networks REQUIRE mTLS — both endpoints prove identity per connection.
Without mTLS, a compromised pod can pretend to be ARIA's screener and
receive admin tokens from the dashboard.

Defence: a small ``make_mtls_context(cert, key, ca)`` returning a
strict ``ssl.SSLContext`` with peer-cert verification + minimum-TLS
1.3 + the cipher allow-list from R59.  Plus ``verify_peer_san(sock,
expected_san)`` that confirms the peer cert's SubjectAlternativeName
matches the expected service identity (defends against valid-but-
wrong-cert MITM).
"""

from __future__ import annotations

import ssl
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def make_mtls_context(
    *,
    cert_path: str,
    key_path: str,
    ca_path: str,
    server_side: bool = False,
) -> ssl.SSLContext:
    if server_side:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    try:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    except Exception:
        pass
    ctx.set_ciphers("HIGH:!aNULL:!eNULL:!MD5:!DES:!3DES:!RC4:!EXPORT")
    ctx.options |= ssl.OP_NO_COMPRESSION
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    ctx.load_verify_locations(cafile=ca_path)
    return ctx


def verify_peer_san(sock: ssl.SSLSocket, *, expected_san: str) -> Tuple[bool, str]:
    """Confirm the peer certificate's SubjectAlternativeName contains
    ``expected_san``.  Defends against an attacker holding a valid cert
    for a DIFFERENT service identity."""
    try:
        cert = sock.getpeercert()
    except Exception as exc:
        return False, f"no_peer_cert:{exc}"
    sans = []
    for typ, val in (cert or {}).get("subjectAltName") or []:
        if typ in ("DNS", "URI", "IP Address"):
            sans.append(val)
    if not sans:
        return False, "no_san"
    if expected_san not in sans:
        return False, f"san_mismatch expected={expected_san!r} got={sans}"
    return True, "ok"


register(DefencePlugin(
    round_id="R116",
    name="mtls",
    description="mTLS context factory + SAN verifier for inter-service.",
))
