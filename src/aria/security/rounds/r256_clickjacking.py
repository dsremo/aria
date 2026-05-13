"""R256 — Clickjacking guard (X-Frame-Options + frame-ancestors).

Threat: an attacker iframes the target site and overlays a transparent
UI to trick users into clicking buttons.  Banking transfers, social
posts, and OAuth grants have all been weaponised this way.

Defence: emit X-Frame-Options DENY (legacy browsers) and CSP frame-
ancestors 'none' (modern); audit response to refuse if neither
present.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def strict_clickjack_headers() -> Dict[str, str]:
    return {
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none'",
    }


def audit_response_headers(headers: Dict[str, str]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    norm = {k.lower(): v for k, v in (headers or {}).items()}

    xfo = (norm.get("x-frame-options") or "").upper()
    csp = (norm.get("content-security-policy") or "").lower()

    has_xfo_strict = xfo in ("DENY", "SAMEORIGIN")
    has_csp_frame_ancestors = "frame-ancestors" in csp and "'none'" in csp

    if not (has_xfo_strict or has_csp_frame_ancestors):
        issues.append("clickjack.no_protection")
    if xfo == "ALLOW-FROM" or xfo == "ALLOWALL":
        issues.append(f"clickjack.weak_xfo:{xfo}")

    return not issues, issues


register(DefencePlugin(
    round_id="R256",
    name="clickjacking",
    description="X-Frame-Options DENY + CSP frame-ancestors 'none'; audit response headers.",
))
