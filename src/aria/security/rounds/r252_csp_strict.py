"""R252 — CSP strict-dynamic + nonce generator.

Threat: a Content-Security-Policy that uses ``script-src 'unsafe-inline'``
or wildcard hosts is a stored-XSS waiting to happen.  CSP Level 3
``strict-dynamic`` + per-response nonces is the modern correct shape;
many headers ship Level 1 due to legacy concerns.

Defence: emit a strict CSP with a fresh per-response nonce; audit a
candidate CSP string and refuse ``'unsafe-inline'`` / ``*`` /
``data:`` for script-src in production.
"""

from __future__ import annotations

import secrets
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_FORBIDDEN_SCRIPT_SRC_TOKENS = ("'unsafe-inline'", "'unsafe-eval'", "*", "data:")


def make_strict_csp(*, report_uri: str = "") -> Tuple[str, str]:
    nonce = secrets.token_urlsafe(16)
    parts = [
        f"default-src 'self'",
        f"script-src 'nonce-{nonce}' 'strict-dynamic'",
        f"style-src 'self' 'nonce-{nonce}'",
        f"img-src 'self' data:",
        f"connect-src 'self'",
        f"object-src 'none'",
        f"base-uri 'self'",
        f"frame-ancestors 'none'",
        f"upgrade-insecure-requests",
    ]
    if report_uri:
        parts.append(f"report-uri {report_uri}")
    return "; ".join(parts), nonce


def audit_csp(header: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    h = (header or "").lower()
    if "default-src" not in h:
        issues.append("csp.no_default_src")
    if "object-src" not in h or "object-src 'none'" not in h:
        issues.append("csp.object_src_not_none")
    if "frame-ancestors" not in h:
        issues.append("csp.no_frame_ancestors")
    script_src = ""
    for clause in (header or "").split(";"):
        if clause.strip().lower().startswith("script-src"):
            script_src = clause
            break
    for tok in _FORBIDDEN_SCRIPT_SRC_TOKENS:
        if tok in script_src.lower():
            issues.append(f"csp.script_src_forbidden:{tok}")
    return not issues, issues


register(DefencePlugin(
    round_id="R252",
    name="csp_strict",
    description="CSP Level 3 strict-dynamic + per-response nonce; audit refuses unsafe-inline.",
))
