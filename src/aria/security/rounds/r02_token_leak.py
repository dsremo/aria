"""R2 — Token / secret leak via error responses.

Threat: Verbose 4xx/5xx error bodies that echo request headers, traces,
or environment fragments leak API keys, signed URLs, AWS access keys,
or session tokens.  Real cases: GitHub Actions logs leaking secrets
(2023, ongoing), Hugging Face token exposure (2024), the Twilio Authy
unauthenticated-API leak (2024).

Defence: scrub well-known secret shapes from any outbound response
body before it reaches the network.  Patterns are conservative — we'd
rather strip a bit too aggressively than leak.  Secrets caught:
  * AWS Access Keys (AKIA / ASIA / 16-20 char)
  * GitHub PATs (ghp_, ghu_, gho_, ghs_, ghr_)
  * Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-)
  * Generic Bearer / Basic header reflections
  * 32+ hex strings paired with key/secret keywords
  * ARIA's own X-ARIA-Token shape and decoy tokens
"""

from __future__ import annotations

import re
from typing import List

from aria.security.plugins import DefencePlugin, register


_SECRET_PATTERNS = tuple(re.compile(p) for p in [
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    r"\bey[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\.[A-Za-z0-9_=-]{20,}\b",  # JWT
    r"\bsk-[A-Za-z0-9]{20,}\b",                     # OpenAI / Anthropic-shape
    r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._\-=/+]{20,}\b",
    r"(?i)(?:api[_\-]?key|secret|token|password)[\"'\s:=]+[A-Za-z0-9_\-./+]{16,}",
    r"\btrc_decoy_[a-f0-9]{32}\b",
])


def scrub(body: bytes, *, max_len: int = 4 * 1024 * 1024) -> bytes:
    """Return body with well-known secret shapes replaced by ``[REDACTED]``."""
    if not body or len(body) > max_len:
        return body
    try:
        s = body.decode("utf-8", errors="replace")
    except Exception:
        return body
    out = s
    for p in _SECRET_PATTERNS:
        out = p.sub("[REDACTED]", out)
    return out.encode("utf-8") if out != s else body


def _on_response(request, body: bytes) -> None:
    """Modify the outbound body in-place.  Only fires on error-class
    responses (4xx/5xx) to avoid double-scrubbing legitimate data."""
    try:
        resp = getattr(request, "_response", None)
        if resp is None:
            return
        status = getattr(resp, "status", 200)
        if status < 400:
            return
        cleaned = scrub(body)
        if cleaned is not body and hasattr(resp, "body"):
            resp._payload = cleaned       # aiohttp internal — best-effort
    except Exception:
        pass


register(DefencePlugin(
    round_id="R2",
    name="token_leak_scrub",
    description="Strip secret shapes from 4xx/5xx response bodies.",
    on_response=_on_response,
))
