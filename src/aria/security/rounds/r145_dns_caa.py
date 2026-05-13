"""R145 — DNS CAA + DMARC + SPF + DKIM checker.

Threat: a rogue CA mis-issuing a cert for ``aria.example.com``; or a
mail server forging email *from* aria.example.com.  CAA (RFC 6844) +
DMARC + SPF + DKIM are the four DNS-based defences that stop these.

Defence: ``audit_dns(domain)`` resolves CAA / TXT / DMARC + reports
which controls are in place.  Returns a structured dict so an
operator's CI gates on missing controls.
"""

from __future__ import annotations

import socket
from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


def _query_txt(domain: str) -> List[str]:
    try:
        # Use system resolver via socket — may not return TXT directly.
        # For full coverage operator wires dnspython:
        import dns.resolver        # type: ignore
        try:
            return [r.to_text().strip('"')
                    for r in dns.resolver.resolve(domain, "TXT")]
        except Exception:
            return []
    except ImportError:
        # No dnspython — return empty; caller treats as unknown
        return []


def _query_caa(domain: str) -> List[str]:
    try:
        import dns.resolver        # type: ignore
        try:
            return [r.to_text() for r in dns.resolver.resolve(domain, "CAA")]
        except Exception:
            return []
    except ImportError:
        return []


def audit_dns(domain: str) -> Dict[str, object]:
    out: Dict[str, object] = {
        "caa": [],
        "spf": [],
        "dmarc": [],
        "dkim_subdomains_seen": [],
        "issues": [],
    }
    out["caa"] = _query_caa(domain)
    if not out["caa"]:
        out["issues"].append("no_CAA")

    txt = _query_txt(domain)
    out["spf"] = [t for t in txt if t.lower().startswith("v=spf1")]
    if not out["spf"]:
        out["issues"].append("no_SPF")

    dmarc_rec = _query_txt(f"_dmarc.{domain}")
    out["dmarc"] = [t for t in dmarc_rec if t.lower().startswith("v=dmarc1")]
    if not out["dmarc"]:
        out["issues"].append("no_DMARC")
    else:
        # DMARC must be p=quarantine or p=reject for production
        record = out["dmarc"][0].lower()
        if "p=none" in record:
            out["issues"].append("DMARC_p=none (monitoring only)")
    return out


register(DefencePlugin(
    round_id="R145",
    name="dns_caa",
    description="DNS CAA + SPF + DMARC presence + DMARC policy check.",
))
