"""R173 — iOS App Transport Security exception audit.

Threat: ATS exceptions (NSAllowsArbitraryLoads,
NSExceptionAllowsInsecureHTTPLoads) reintroduce cleartext HTTP on a
per-domain or app-wide basis.  Apple's review still rubber-stamps
many; runtime detection is the real gate.

Defence: parse an Info.plist-derived dict and refuse arbitrary loads
in release.  Allows scoped exceptions for localhost/test only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_ats(plist: Dict[str, Any], *, is_release: bool = True) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    ats = plist.get("NSAppTransportSecurity", {}) if isinstance(plist, dict) else {}
    if not isinstance(ats, dict):
        return False, ["ats.invalid_dict"]

    if ats.get("NSAllowsArbitraryLoads") and is_release:
        issues.append("ats.arbitrary_loads_release")
    if ats.get("NSAllowsArbitraryLoadsForMedia"):
        issues.append("ats.arbitrary_loads_media")
    if ats.get("NSAllowsArbitraryLoadsInWebContent") and is_release:
        issues.append("ats.arbitrary_loads_webcontent_release")

    domains = ats.get("NSExceptionDomains", {})
    if isinstance(domains, dict):
        for d, conf in domains.items():
            if not isinstance(conf, dict):
                continue
            if conf.get("NSExceptionAllowsInsecureHTTPLoads") and not _is_localhost(d):
                issues.append(f"ats.exception_insecure:{d}")
            if conf.get("NSExceptionMinimumTLSVersion") in ("TLSv1.0", "TLSv1.1"):
                issues.append(f"ats.weak_tls:{d}")

    return not issues, issues


def _is_localhost(d: str) -> bool:
    return d in ("localhost", "127.0.0.1") or d.endswith(".local")


register(DefencePlugin(
    round_id="R173",
    name="ios_ats",
    description="iOS App Transport Security plist audit; refuse arbitrary loads in release.",
))
