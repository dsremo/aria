"""R258 — Referrer-Policy strict-origin enforcement.

Threat: the default browser Referer header leaks the full URL — query
params containing tokens, password reset hashes, search terms — to
every cross-origin resource.  Single-page apps with token-in-URL
patterns are the worst-affected.

Defence: emit ``Referrer-Policy: strict-origin-when-cross-origin``
(or stricter); audit response and refuse open / no-referrer-when-
downgrade in production.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_ALLOWED = {
    "no-referrer", "no-referrer-when-downgrade",
    "same-origin", "origin", "strict-origin",
    "origin-when-cross-origin", "strict-origin-when-cross-origin",
}

_PRIVATE_OK = {"no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin"}


def strict_referrer_policy() -> str:
    return "strict-origin-when-cross-origin"


def audit_referrer(headers: Dict[str, str]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    norm = {k.lower(): v for k, v in (headers or {}).items()}
    rp = (norm.get("referrer-policy") or "").lower().strip()
    if not rp:
        issues.append("referrer.no_header")
    elif rp not in _ALLOWED:
        issues.append(f"referrer.invalid:{rp}")
    elif os.environ.get("ARIA_ENV") == "prod" and rp not in _PRIVATE_OK:
        issues.append(f"referrer.too_permissive:{rp}")
    return not issues, issues


register(DefencePlugin(
    round_id="R258",
    name="referrer_policy",
    description="Referrer-Policy strict-origin emitter + production audit.",
))
