"""R268 — TLS-RPT (TLS Reporting) audit.

Threat: even with MTA-STS deployed, an operator can't tell whether
peer servers are honouring TLS — or whether an active downgrade is
happening — without aggregate reports.  TLS-RPT (RFC 8460) gives
visibility.

Defence: parse a ``_smtp._tls.<domain>`` TXT record and refuse
configurations missing ``rua=``.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_RUA_RE = re.compile(r"\brua\s*=\s*([^;]+)", re.IGNORECASE)


def audit_tls_rpt(record: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    txt = (record or "").strip()
    if "v=TLSRPTv1" not in txt:
        issues.append("tlsrpt.invalid_version")
    rua = _RUA_RE.search(txt)
    if not rua:
        issues.append("tlsrpt.no_rua")
    else:
        targets = [t.strip() for t in rua.group(1).split(",") if t.strip()]
        if not any(t.startswith("mailto:") or t.startswith("https://") for t in targets):
            issues.append("tlsrpt.no_valid_rua_target")
    return not issues, issues


def recommended_record(*, rua_email: str) -> str:
    return f"v=TLSRPTv1; rua=mailto:{rua_email}"


register(DefencePlugin(
    round_id="R268",
    name="tls_rpt",
    description="TLS-RPT audit (RFC 8460); refuse missing rua aggregate target.",
))
