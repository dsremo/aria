"""R7 — HTTP Parameter Pollution.

Threat: an attacker sends ``?id=1&id=2`` and depending on the framework
the handler sees ``"1"`` while the auth middleware sees ``"2"`` (or
vice versa).  CWE-235.  Real bypass class — abused against several
WAF + backend pairs in 2023-2024 (SonicWall SSL-VPN advisories).

Defence: a request scorer that flags any query string with duplicate
keys whose values differ; a 403-class block when the query is heading
to an admin endpoint.  Operators may override with an env-var
allow-list for legitimate keys (e.g. ``filter=a&filter=b``).
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Set, Tuple

from aria.security.plugins import DefencePlugin, register


def _allowed_dup_keys() -> Set[str]:
    raw = os.environ.get("ARIA_ALLOWED_DUP_QUERY_KEYS", "filter,tag")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _on_request(request, _body: bytes) -> None:
    qs = request.query_string or ""
    if not qs or "=" not in qs:
        return
    pairs = urllib.parse.parse_qsl(qs, keep_blank_values=True, strict_parsing=False)
    seen: dict = {}
    allow = _allowed_dup_keys()
    for k, v in pairs:
        if k in allow:
            continue
        if k in seen and seen[k] != v:
            raise RuntimeError(
                f"R7.parameter_pollution: duplicate key {k!r} with conflicting values"
            )
        seen[k] = v


register(DefencePlugin(
    round_id="R7",
    name="parameter_pollution",
    description="Block duplicate query keys with conflicting values (CWE-235).",
    on_request=_on_request,
))
