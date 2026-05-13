"""R18 — HTTP Host-header injection / cache poisoning.

Threat: an attacker sends ``Host: evil.example.com`` to ARIA.  If the
service uses the Host header to build absolute URLs (password-reset
links, OAuth redirect-URIs, image src-set), the link points at
``evil.example.com``.  Cache layers then keep a poisoned response.
CWE-444 + CWE-348.

Defence: ``allowed_hosts`` env var + a request-time hook that 421s any
inbound whose Host doesn't match the allow-list.  Defence is opt-in
because dev / loopback should not 421 ``Host: localhost``; production
operators MUST set ``ARIA_ALLOWED_HOSTS``.
"""

from __future__ import annotations

import os
from typing import Set

from aria.security.plugins import DefencePlugin, register


def _allowed_hosts() -> Set[str]:
    raw = os.environ.get("ARIA_ALLOWED_HOSTS", "").strip()
    if not raw:
        return set()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _on_request(request, _body: bytes) -> None:
    allowed = _allowed_hosts()
    if not allowed:
        return                       # opt-in only
    host = (request.headers.get("Host", "") or "").split(":")[0].strip().lower()
    if host and host not in allowed:
        raise RuntimeError(f"R18.host_header host={host!r} not in allow-list")


register(DefencePlugin(
    round_id="R18",
    name="host_header",
    description="421 any inbound Host header outside ARIA_ALLOWED_HOSTS.",
    on_request=_on_request,
))
