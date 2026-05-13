"""R260 — Service Worker registration audit.

Threat: a registered Service Worker becomes a persistent man-in-the-
middle on the origin — intercepting fetch, cache, push notifications.
A short-lived XSS that registers a SW persists for weeks.

Defence: ``audit_sw_registration`` ensures (a) only same-origin
script paths register, (b) scope is locked to a sub-path, (c) the
script bytes match a SHA-256 baseline.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from aria.security.plugins import DefencePlugin, register


def audit_sw_registration(
    *,
    origin: str,
    script_url: str,
    scope: str,
    script_bytes: bytes,
    expected_sha256: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    issues: List[str] = []

    parsed_origin = urlparse(origin)
    parsed_script = urlparse(script_url)
    if parsed_origin.scheme != "https":
        issues.append(f"sw.non_https_origin:{parsed_origin.scheme}")
    if parsed_script.netloc and parsed_script.netloc != parsed_origin.netloc:
        issues.append(f"sw.cross_origin_script:{parsed_script.netloc}")

    if not scope or scope == "/":
        issues.append("sw.scope_too_broad")

    if expected_sha256:
        actual = hashlib.sha256(script_bytes or b"").hexdigest()
        if actual != expected_sha256:
            issues.append(f"sw.sha256_mismatch actual={actual[:16]}…")

    return not issues, issues


register(DefencePlugin(
    round_id="R260",
    name="service_worker",
    description="Service Worker registration audit: same-origin + bounded scope + pinned SHA-256.",
))
