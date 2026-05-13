"""R12 — Server-Side Template Injection (SSTI).

Threat: a string field rendered through a templating engine
(Jinja2, Mako, Twig, …) lets the attacker break out: ``{{7*7}}`` →
``49`` proves injection; ``{{config.SECRET_KEY}}`` exfiltrates; on
some engines ``{{''.__class__.__mro__[1].__subclasses__()}}`` reaches
``subprocess.Popen`` and is full RCE.  CWE-1336.  Cases: Confluence
SSTI 2022 (still scanned for in 2024), Spring4Shell.

Defence: pattern scorer for the four common template-engine markers
in inbound JSON / form bodies and query strings: ``{{ }}``, ``{% %}``,
``${ }``, ``<%= %>``.  Operators rendering legitimate templated text
opt out per endpoint via env-var.
"""

from __future__ import annotations

import os
import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_PATTERNS = (
    re.compile(r"\{\{\s*\S.{0,200}?\s*\}\}"),
    re.compile(r"\{%\s*\S.{0,200}?\s*%\}"),
    re.compile(r"\$\{\s*\S.{0,200}?\s*\}"),
    re.compile(r"<%=\s*\S.{0,200}?\s*%>"),
)


def _excluded(endpoint: str) -> bool:
    raw = os.environ.get("ARIA_SSTI_EXEMPT_ENDPOINTS", "")
    excludes = {p.strip() for p in raw.split(",") if p.strip()}
    return endpoint in excludes


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or _excluded(endpoint):
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    hits = 0
    for p in _PATTERNS:
        if p.search(s):
            hits += 1
    if hits == 0:
        return 0.0, ""
    if hits >= 2:
        return 0.85, f"r12.ssti markers={hits}"
    return 0.5, f"r12.ssti markers={hits}"


register(DefencePlugin(
    round_id="R12",
    name="ssti",
    description="Detect Jinja/Mako/JSP template-engine injection markers in payloads.",
    on_score=_on_score,
))
