"""R49 — Debug-endpoint refusal in production.

Threat: ``/debug/`` , ``/_internal/`` , ``/dump/`` , ``/admin/diag``
exposed in production give an attacker server-side state.  Twilio
Authy 2024, multiple Spring Boot incidents (``/actuator/heapdump``).

Defence: a request hook that flat-out refuses ANY path matching the
debug-shaped patterns when ``ARIA_ENV=production``.  Operators who
need diagnostics in prod use the dedicated ``/v1/healthz`` and the
admin-authenticated endpoints under ``/v1/admin/`` — never any
``/debug`` path.
"""

from __future__ import annotations

import os
import re

from aria.security.plugins import DefencePlugin, register


_DEBUG_PATH_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"^/debug(/|$)",
    r"^/_debug(/|$)",
    r"^/dev(/|$)",
    r"^/dump(/|$)",
    r"^/_internal(/|$)",
    r"^/admin/diag(/|$)",
    r"^/actuator(/|$)",
    r"^/__profile",
    r"^/__pdb",
    r"\.pdb$",
])


def is_debug_path(path: str) -> bool:
    return any(p.search(path or "") for p in _DEBUG_PATH_PATTERNS)


def _on_request(request, _body: bytes) -> None:
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return
    path = request.path or "/"
    if is_debug_path(path):
        raise RuntimeError(f"R49.debug_endpoint refused path={path!r}")


register(DefencePlugin(
    round_id="R49",
    name="debug_endpoint_block",
    description="Refuse /debug, /_internal, /actuator, /dump in production.",
    on_request=_on_request,
))
