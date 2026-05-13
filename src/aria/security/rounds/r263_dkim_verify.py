"""R263 — DKIM signature verifier.

Threat: an inbound message with a forged DKIM signature, or a missing
DKIM tag, slips past content filters and lands in the inbox.  Phish-
attribute lookalikes rely on incomplete validation.

Defence: ``audit_dkim_header`` parses the DKIM-Signature header and
refuses signatures that are missing required tags (v= a= d= s= b= bh=
h=) or use deprecated algorithms (rsa-sha1).
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_TAG_RE = re.compile(r"\b([a-zA-Z]+)=([^;]+)")
_REQUIRED_TAGS = {"v", "a", "d", "s", "b", "bh", "h"}
_WEAK_ALGORITHMS = {"rsa-sha1"}
_MIN_KEY_BITS = 1024


def parse_dkim_header(header: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for k, v in _TAG_RE.findall(header or ""):
        result[k.strip()] = v.strip()
    return result


def audit_dkim_header(header: str, *, key_size_bits: int = 2048) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    tags = parse_dkim_header(header)
    if not tags:
        return False, ["dkim.no_tags"]
    missing = _REQUIRED_TAGS - set(tags.keys())
    if missing:
        issues.append(f"dkim.missing_tags:{','.join(sorted(missing))}")
    algo = tags.get("a", "").lower()
    if algo in _WEAK_ALGORITHMS:
        issues.append(f"dkim.weak_algo:{algo}")
    if tags.get("v") and tags["v"] != "1":
        issues.append(f"dkim.invalid_version:{tags['v']}")
    if key_size_bits < _MIN_KEY_BITS:
        issues.append(f"dkim.key_too_small:{key_size_bits}")
    return not issues, issues


register(DefencePlugin(
    round_id="R263",
    name="dkim_verify",
    description="DKIM-Signature header audit; refuse missing tags or weak algorithms.",
))
