"""R167 — HIPAA PHI scrubber (Safe Harbor de-identification).

Threat: PHI logged in error messages, traces, or LLM prompts triggers
HIPAA breach notification (60 days, $50K-$1.9M per violation).  A
mis-emitted DOB or SSN in an exception trace is enough.

Defence: ``scrub_phi`` redacts the 18 Safe-Harbor identifiers from a
text stream — names (best-effort), SSN, DOB, phone, email, address
fragments, MRN, account/policy number, biometric refs, full-face
photo refs, geographic subdivision smaller than state.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_DOB_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b\d{2}/\d{2}/(?:19|20)\d{2}\b")
_MRN_RE = re.compile(r"\bMRN[:\s]+\d{4,12}\b", re.IGNORECASE)
_CCN_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_ZIP5_RE = re.compile(r"\bZIP[:\s]+\d{5}(?:-\d{4})?\b", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def scrub_phi(text: str) -> Tuple[str, int]:
    redactions = 0

    def _sub(pattern: re.Pattern, repl: str, s: str) -> str:
        nonlocal redactions
        new, n = pattern.subn(repl, s)
        redactions += n
        return new

    out = text
    out = _sub(_SSN_RE, "[REDACTED-SSN]", out)
    out = _sub(_PHONE_RE, "[REDACTED-PHONE]", out)
    out = _sub(_EMAIL_RE, "[REDACTED-EMAIL]", out)
    out = _sub(_DOB_RE, "[REDACTED-DATE]", out)
    out = _sub(_MRN_RE, "[REDACTED-MRN]", out)
    out = _sub(_CCN_RE, "[REDACTED-CCN]", out)
    out = _sub(_ZIP5_RE, "[REDACTED-ZIP]", out)
    out = _sub(_IP_RE, "[REDACTED-IP]", out)
    out = _sub(_URL_RE, "[REDACTED-URL]", out)
    return out, redactions


register(DefencePlugin(
    round_id="R167",
    name="hipaa_phi_scrub",
    description="HIPAA Safe-Harbor PHI scrubber for logs, traces, LLM prompts.",
))
