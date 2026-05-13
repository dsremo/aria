"""R267 — MTA-STS policy audit.

Threat: SMTP between MTAs falls back to plaintext when STARTTLS
negotiation fails.  Active downgrade attacks (LightBasin 2021 telco
intrusion) actively strip STARTTLS to read mail in clear.  MTA-STS
(RFC 8461) lets a receiving domain say "always require TLS".

Defence: validate a candidate MTA-STS policy — must be HTTPS-served
at ``mta-sts.<domain>/.well-known/mta-sts.txt``, must have
``mode: enforce`` in production, must list at least one MX pattern.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_mta_sts_policy(text: str, *, is_production: bool = True) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    body = text or ""
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if not any(l.lower().startswith("version:") for l in lines):
        issues.append("mtasts.no_version")
    mode = ""
    mxs: List[str] = []
    max_age = ""
    for l in lines:
        low = l.lower()
        if low.startswith("mode:"):
            mode = l.split(":", 1)[1].strip().lower()
        elif low.startswith("mx:"):
            mxs.append(l.split(":", 1)[1].strip())
        elif low.startswith("max_age:"):
            max_age = l.split(":", 1)[1].strip()

    if mode not in ("enforce", "testing", "none"):
        issues.append(f"mtasts.invalid_mode:{mode}")
    if is_production and mode != "enforce":
        issues.append(f"mtasts.mode_not_enforce_in_prod:{mode}")
    if not mxs:
        issues.append("mtasts.no_mx_patterns")
    if max_age and max_age.isdigit() and int(max_age) < 86_400:
        issues.append(f"mtasts.max_age_too_short:{max_age}")
    return not issues, issues


register(DefencePlugin(
    round_id="R267",
    name="mta_sts",
    description="MTA-STS policy audit (RFC 8461); refuse mode!=enforce in prod.",
))
