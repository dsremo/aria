"""R262 — SPF record audit.

Threat: a missing or permissive SPF record (``+all``) lets any host
forge mail from your domain.  Phishing campaigns specifically scan
for ``v=spf1 +all`` and weaponise lookalike domains.

Defence: parse a candidate SPF TXT record, count DNS lookups (must
be ≤ 10 per RFC 7208), refuse ``+all``, and recommend the strict
``-all`` terminator.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_LOOKUP_MECHANISMS = ("a", "mx", "include", "exists", "redirect", "ptr")


def audit_spf_record(record: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    txt = (record or "").strip()
    if not txt.startswith("v=spf1"):
        return False, ["spf.invalid_version"]
    parts = txt.split()
    if "+all" in parts:
        issues.append("spf.permissive_plus_all")
    if "?all" in parts:
        issues.append("spf.neutral_qmark_all")
    if not any(p in ("-all", "~all") for p in parts):
        issues.append("spf.no_terminator")
    if "-all" not in parts and "~all" in parts:
        issues.append("spf.softfail_only")

    lookup_count = 0
    for p in parts:
        token = p.lstrip("+-~?").split(":", 1)[0].split("=", 1)[0].lower()
        if token in _LOOKUP_MECHANISMS:
            lookup_count += 1
    if lookup_count > 10:
        issues.append(f"spf.too_many_lookups:{lookup_count}")

    if re.search(r"\bptr\b", txt):
        issues.append("spf.ptr_mechanism_deprecated")

    return not issues, issues


def recommended_record(*, sender_hosts: List[str]) -> str:
    parts = ["v=spf1"]
    parts.extend(f"include:{h}" for h in sender_hosts)
    parts.append("-all")
    return " ".join(parts)


register(DefencePlugin(
    round_id="R262",
    name="spf_audit",
    description="SPF TXT record audit: refuse +all, count lookups, prefer -all terminator.",
))
