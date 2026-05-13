"""R154 — SPIFFE/SPIRE workload identity wrapper.

Threat: services that authenticate by IP + token can be spoofed by any
pod that captures the token.  SPIFFE bind cryptographic identity to
the *workload* (process + namespace + service-account) instead of the
network.

Defence: parse and validate ``spiffe://trust-domain/path`` URIs from
SVID certs.  Refuse calls whose SAN URI doesn't match the expected
trust-domain or path prefix.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_SPIFFE_RE = re.compile(r"^spiffe://([a-z0-9.\-]+)(/[A-Za-z0-9._\-/]+)$")


def parse_spiffe_id(uri: str) -> Tuple[bool, str, str]:
    m = _SPIFFE_RE.match(uri or "")
    if not m:
        return False, "", ""
    return True, m.group(1), m.group(2)


def verify_svid_against(uri: str, *, trust_domain: str, path_prefix: str) -> Tuple[bool, str]:
    ok, td, path = parse_spiffe_id(uri)
    if not ok:
        return False, "invalid_spiffe_uri"
    if td != trust_domain:
        return False, f"trust_domain_mismatch got={td} expected={trust_domain}"
    if not path.startswith(path_prefix):
        return False, f"path_prefix_mismatch path={path} expected_prefix={path_prefix}"
    return True, "ok"


register(DefencePlugin(
    round_id="R154",
    name="spiffe_svid",
    description="SPIFFE SVID URI parser + trust-domain/path-prefix verifier.",
))
