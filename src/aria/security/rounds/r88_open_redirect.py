"""R88 — Open-redirect detector.

Threat: any endpoint that takes a ``next`` / ``return_to`` / ``url``
parameter and 302's to it without validation is an open-redirect —
attacker phishes via ARIA's own domain.  Cited OWASP A1 unvalidated-
forward / redirect.

Defence: ``safe_redirect_target(presented, allowlist)`` — accepts only
relative paths or fully-qualified URLs whose origin is in
``allowlist``.  Refuses ``//evil.com/path`` (protocol-relative
redirect class), ``http:`` schemes, and JavaScript URIs.
"""

from __future__ import annotations

import urllib.parse
from typing import Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


def safe_redirect_target(presented: str, allowed_origins: Iterable[str]) -> Tuple[bool, str]:
    if not presented:
        return False, "empty"
    if presented.startswith("//"):
        return False, "protocol_relative"
    if presented.lower().startswith("javascript:"):
        return False, "javascript_uri"
    if presented.lower().startswith("data:"):
        return False, "data_uri"
    if presented.startswith("/") and not presented.startswith("//"):
        return True, "relative_path"
    parsed = urllib.parse.urlparse(presented)
    if parsed.scheme not in ("https",):
        return False, f"scheme_banned:{parsed.scheme}"
    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed = {o.strip().rstrip("/").lower() for o in allowed_origins}
    if origin in allowed:
        return True, "origin_match"
    return False, f"origin_not_allowed:{origin}"


register(DefencePlugin(
    round_id="R88",
    name="open_redirect",
    description="Refuse next/return-to URLs outside allow-list (relative / scheme / origin).",
))
