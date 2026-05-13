"""R205 — Post-quantum hybrid TLS preference.

Threat: classical TLS 1.3 with X25519 falls to a CRQC.  IETF +
Cloudflare + Google have shipped X25519MLKEM768 as a TLS 1.3 hybrid
group; deployments need to *prefer* it when both peers support it.

Defence: a config helper that returns the hybrid-group string for
the local SSL/OpenSSL build, plus a probe that checks whether the
runtime knows the hybrid name.
"""

from __future__ import annotations

import ssl
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_HYBRID_GROUPS = (
    "X25519MLKEM768",   # current IETF wire name (Cloudflare/Chrome 2024)
    "X25519Kyber768Draft00",
    "x25519_kyber768",
)


def runtime_hybrid_groups_supported() -> Tuple[bool, List[str]]:
    found: List[str] = []
    if not hasattr(ssl, "HAS_TLSv1_3") or not ssl.HAS_TLSv1_3:
        return False, []
    ctx = ssl.create_default_context()
    setter = getattr(ctx, "set_groups", None) or getattr(ctx, "set_ecdh_curve", None)
    if setter is None:
        return False, []
    for g in _HYBRID_GROUPS:
        try:
            setter(g)
            found.append(g)
        except Exception:
            continue
    return bool(found), found


def configure_context(ctx: "ssl.SSLContext") -> Tuple[bool, str]:
    setter = getattr(ctx, "set_groups", None) or getattr(ctx, "set_ecdh_curve", None)
    if setter is None:
        return False, "no_set_groups"
    for g in _HYBRID_GROUPS:
        try:
            setter(g)
            return True, g
        except Exception:
            continue
    return False, "no_hybrid_supported"


register(DefencePlugin(
    round_id="R205",
    name="pq_hybrid_tls",
    description="Prefer X25519+ML-KEM-768 hybrid TLS 1.3 group when supported.",
))
