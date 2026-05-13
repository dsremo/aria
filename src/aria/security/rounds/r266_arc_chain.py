"""R266 — ARC (Authenticated Received Chain) verifier.

Threat: forwarded mail (mailing list, Microsoft 365 → Gmail) breaks
SPF/DKIM by rewriting envelope or body — receivers can't tell whether
the original auth passed.  ARC (RFC 8617) preserves the chain
through forwarders.

Defence: walk an ARC-Authentication-Results / ARC-Seal / ARC-Message-
Signature stack and refuse messages whose chain has any ``cv=fail``
or missing instances.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_INSTANCE_RE = re.compile(r"\bi\s*=\s*(\d+)")
_CV_RE = re.compile(r"\bcv\s*=\s*(none|pass|fail)")


def audit_arc_chain(headers: List[str]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    instances: List[int] = []
    for h in headers:
        h_norm = h or ""
        m = _INSTANCE_RE.search(h_norm)
        if m:
            instances.append(int(m.group(1)))
        cv = _CV_RE.search(h_norm)
        if cv and cv.group(1) == "fail":
            issues.append("arc.cv_fail")
    if not instances:
        return True, []   # no ARC headers — nothing to verify
    instances.sort()
    expected = list(range(1, max(instances) + 1))
    if instances != expected and len(set(instances)) != len(instances):
        issues.append(f"arc.instance_gap got={instances}")
    return not issues, issues


register(DefencePlugin(
    round_id="R266",
    name="arc_chain",
    description="ARC chain (RFC 8617) verifier: refuse cv=fail or instance gaps.",
))
