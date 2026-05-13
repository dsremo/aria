"""R97 — Data classification + automatic PII / secret tagging.

Threat: ARIA logs everything for forensics, but unstructured logs leak
PII (operator email, IP, phone) and secrets (API keys, JWTs) — GDPR /
CCPA / HIPAA fines.  Bank stacks classify data at the schema layer +
mask in-transit.

Defence: ``classify(text)`` returns a tag set
``{"public", "pii", "secret"}`` based on regex shapes.  ``redact(text,
keep="public")`` masks anything classified at or above the threshold.
Wired into the audit trail so every entry can be filtered by tier
when an auditor reads it.
"""

from __future__ import annotations

import re
from typing import Set, Tuple

from aria.security.plugins import DefencePlugin, register


_PII_PATTERNS = (
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email
    re.compile(r"\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{2,4}[\s-]?\d{2,4}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),                       # IPv4
    re.compile(r"\b[A-F0-9]{1,4}(?::[A-F0-9]{1,4}){2,}\b", re.IGNORECASE),  # IPv6
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                             # SSN-shape
    re.compile(r"\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13})\b"),  # PAN
)

_SECRET_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bey[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
)


def classify(text: str) -> Set[str]:
    if not text:
        return {"public"}
    tags: Set[str] = {"public"}
    if any(p.search(text) for p in _PII_PATTERNS):
        tags.add("pii")
    if any(p.search(text) for p in _SECRET_PATTERNS):
        tags.add("secret")
    return tags


_REDACT_LEVEL = {"public": 0, "pii": 1, "secret": 2}


def redact(text: str, *, keep: str = "public") -> Tuple[str, int]:
    """Return ``(masked_text, n_redactions)``.  Default keep="public" =
    mask anything classified higher than public."""
    if not text:
        return text, 0
    threshold = _REDACT_LEVEL.get(keep, 0)
    out = text
    n = 0
    if threshold < _REDACT_LEVEL["secret"]:
        for p in _SECRET_PATTERNS:
            new = p.sub("[REDACTED:secret]", out)
            if new != out:
                n += 1
            out = new
    if threshold < _REDACT_LEVEL["pii"]:
        for p in _PII_PATTERNS:
            new = p.sub("[REDACTED:pii]", out)
            if new != out:
                n += 1
            out = new
    return out, n


register(DefencePlugin(
    round_id="R97",
    name="data_classification",
    description="Tag {public/pii/secret} + threshold-based redact for audit logs.",
))
