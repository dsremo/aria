"""R264 — DMARC policy enforcement.

Threat: a domain without DMARC (or DMARC policy ``none``) cannot
instruct receivers to reject spoofed mail.  Government and bank
domains were ~30% non-DMARC as of 2024 (Valimail) — major phishing
infrastructure.

Defence: parse a DMARC record and refuse ``p=none`` for production
domains.  Recommend ``p=reject`` with ``rua=`` aggregate reporting.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def parse_dmarc(record: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for kv in (record or "").split(";"):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out


def audit_dmarc(record: str, *, is_production: bool = True) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    tags = parse_dmarc(record)
    if not tags:
        return False, ["dmarc.no_record"]
    if tags.get("v") != "DMARC1":
        issues.append("dmarc.invalid_version")
    policy = tags.get("p", "").lower()
    if policy not in ("none", "quarantine", "reject"):
        issues.append(f"dmarc.invalid_policy:{policy}")
    if is_production and policy == "none":
        issues.append("dmarc.policy_none_in_prod")
    if "rua" not in tags:
        issues.append("dmarc.no_rua")
    pct = tags.get("pct")
    if pct and pct.isdigit() and int(pct) < 100 and is_production:
        issues.append(f"dmarc.partial_rollout:{pct}")
    return not issues, issues


def recommended_record(*, rua_email: str, ruf_email: str = "") -> str:
    parts = [f"v=DMARC1", f"p=reject", f"rua=mailto:{rua_email}"]
    if ruf_email:
        parts.append(f"ruf=mailto:{ruf_email}")
    parts.append("aspf=s")
    parts.append("adkim=s")
    return "; ".join(parts)


register(DefencePlugin(
    round_id="R264",
    name="dmarc_policy",
    description="DMARC record audit; refuse p=none in prod, require rua aggregate reports.",
))
