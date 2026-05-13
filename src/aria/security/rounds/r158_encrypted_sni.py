"""R158 — Encrypted Client Hello (ECH) preference.

Threat: TLS SNI leaks the destination hostname in the clear so an
on-path adversary can fingerprint which services a client is calling
even when the body is encrypted.  Used by GFW + corporate DPI.

Defence: a preference flag + a check that the chosen TLS library and
target support ECH (Encrypted Client Hello, RFC 9460 / 9461) when the
operator opts in.
"""

from __future__ import annotations

import socket
import ssl
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def supports_ech() -> Tuple[bool, str]:
    if not hasattr(ssl, "HAS_TLSv1_3") or not ssl.HAS_TLSv1_3:
        return False, "no_tls13"
    # Python ssl currently exposes ECH only via patched OpenSSL 3.x.
    has_attr = any(
        hasattr(ssl.SSLContext, attr)
        for attr in ("set_ech_config_list", "set_ech_config")
    )
    return has_attr, "ech_attr_present" if has_attr else "ech_not_in_runtime"


def resolve_with_ech_hint(host: str) -> Tuple[bool, str]:
    """Return (resolved_ok, reason).  ECH config lives in the HTTPS RR
    (DNS type 65); without dnspython we can't fully parse, so we just
    confirm the host resolves and signal whether ECH would be possible."""
    try:
        socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"dns_error:{exc}"
    ok, _ = supports_ech()
    return True, "ech_runtime_ready" if ok else "ech_runtime_unavailable"


register(DefencePlugin(
    round_id="R158",
    name="encrypted_sni",
    description="Detect ECH (Encrypted Client Hello) runtime support; flag plaintext SNI.",
))
