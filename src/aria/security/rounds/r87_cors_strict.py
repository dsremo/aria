"""R87 — Strict CORS / cross-origin policy.

Threat: a wildcard ``Access-Control-Allow-Origin: *`` with credentialed
fetches (or even without) lets any malicious page issue auth'd cross-
origin requests against ARIA.  The classic OWASP "loose CORS" item.
Recent: Twilio Authy 2024 had this as a contributing factor.

Defence: a request hook that refuses any inbound carrying
``Origin: <something>`` whose value isn't in ``ARIA_CORS_ORIGINS``.
For preflight requests (``OPTIONS`` with ``Access-Control-Request-*``),
we emit the strict allow-list reply or 403.  Sites that genuinely want
cross-origin enable it explicitly; default is same-origin only.
"""

from __future__ import annotations

import os
from typing import Set

from aria.security.plugins import DefencePlugin, register


def _allowed_origins() -> Set[str]:
    raw = os.environ.get("ARIA_CORS_ORIGINS", "").strip()
    if not raw:
        return set()
    return {o.strip().lower() for o in raw.split(",") if o.strip()}


def _on_request(request, _body):
    origin = (request.headers.get("Origin", "") or "").lower()
    if not origin:
        return
    allowed = _allowed_origins()
    # Empty allowed = strict same-origin; refuse cross-origin entirely.
    if not allowed:
        raise RuntimeError(f"R87.cors: Origin {origin!r} but no ARIA_CORS_ORIGINS configured")
    if origin not in allowed:
        raise RuntimeError(f"R87.cors: Origin {origin!r} not in allow-list")


def cors_response_headers() -> dict:
    """Return ``Access-Control-Allow-*`` headers for the configured set."""
    allowed = _allowed_origins()
    if not allowed:
        return {}
    return {
        "Vary": "Origin",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-ARIA-Token, X-Request-Id",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "300",
    }


register(DefencePlugin(
    round_id="R87",
    name="cors_strict",
    description="Refuse Origin header outside ARIA_CORS_ORIGINS allow-list.",
    on_request=_on_request,
))
