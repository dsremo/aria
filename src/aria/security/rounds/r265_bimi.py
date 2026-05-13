"""R265 — BIMI / VMC certificate audit.

Threat: BIMI (Brand Indicators for Message Identification) attaches a
brand logo to mail in receiver UIs.  A misconfigured BIMI record
without a verified VMC (Verified Mark Certificate) lets attackers
display a forged logo on their spoofed messages.

Defence: parse a BIMI TXT record and require (a) ``v=BIMI1``, (b)
``l=`` SVG URL on HTTPS, (c) ``a=`` VMC URL when DMARC policy is
strict (p=quarantine|reject).
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from urllib.parse import urlparse

from aria.security.plugins import DefencePlugin, register


def parse_bimi(record: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for kv in (record or "").split(";"):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def audit_bimi(record: str, *, dmarc_policy: str = "reject") -> Tuple[bool, List[str]]:
    issues: List[str] = []
    tags = parse_bimi(record)
    if not tags:
        return False, ["bimi.no_record"]
    if tags.get("v") != "BIMI1":
        issues.append("bimi.invalid_version")
    logo_url = tags.get("l", "")
    if not logo_url:
        issues.append("bimi.no_logo_url")
    elif urlparse(logo_url).scheme != "https":
        issues.append("bimi.logo_not_https")
    elif not logo_url.lower().endswith(".svg"):
        issues.append("bimi.logo_not_svg")
    vmc = tags.get("a", "")
    if dmarc_policy.lower() in ("quarantine", "reject"):
        if not vmc:
            issues.append("bimi.no_vmc_with_strict_dmarc")
        elif urlparse(vmc).scheme != "https":
            issues.append("bimi.vmc_not_https")
    return not issues, issues


register(DefencePlugin(
    round_id="R265",
    name="bimi",
    description="BIMI TXT record audit; require HTTPS SVG + VMC under strict DMARC.",
))
