"""R14 — LDAP injection.

Threat: a username field shipped into an LDAP filter as
``(&(uid={user})(password={pw}))`` — attacker submits ``user=*)(uid=*)``
and bypasses auth or enumerates the directory.  CWE-90.

Defence: ``escape_ldap_dn(value)`` and ``escape_ldap_filter(value)``
helpers per RFC-4514 / RFC-4515; plus a scorer that detects the
classic LDAP-injection payload shapes in inbound JSON values.
"""

from __future__ import annotations

import json
import re
from typing import Any, Tuple

from aria.security.plugins import DefencePlugin, register


_FILTER_ESCAPES = {
    "\\": "\\5c",
    "*": "\\2a",
    "(": "\\28",
    ")": "\\29",
    "\x00": "\\00",
}

_DN_ESCAPES = {
    ",": r"\,",
    "+": r"\+",
    '"': r"\"",
    "\\": r"\\",
    "<": r"\<",
    ">": r"\>",
    ";": r"\;",
    "=": r"\=",
}


def escape_ldap_filter(value: str) -> str:
    if not value:
        return ""
    out = []
    for ch in value:
        out.append(_FILTER_ESCAPES.get(ch, ch))
    return "".join(out)


def escape_ldap_dn(value: str) -> str:
    if not value:
        return ""
    out = []
    for ch in value:
        out.append(_DN_ESCAPES.get(ch, ch))
    return "".join(out)


_INJECTION_PATTERNS = (
    re.compile(r"\*\)\("),
    re.compile(r"\)\(\&"),
    re.compile(r"\)\(\|"),
    re.compile(r"\(\!"),
)


def _walk(obj: Any, depth: int = 0) -> int:
    if depth > 12:
        return 0
    hits = 0
    if isinstance(obj, dict):
        for v in obj.values():
            hits += _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            hits += _walk(v, depth + 1)
    elif isinstance(obj, str):
        for p in _INJECTION_PATTERNS:
            if p.search(obj):
                hits += 1
    return hits


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload:
        return 0.0, ""
    try:
        obj = json.loads(payload)
    except Exception:
        return 0.0, ""
    hits = _walk(obj)
    if hits == 0:
        return 0.0, ""
    return min(0.85, 0.5 + 0.1 * hits), f"r14.ldap_injection patterns={hits}"


register(DefencePlugin(
    round_id="R14",
    name="ldap_injection",
    description="Detect LDAP filter-break sequences in JSON values.",
    on_score=_on_score,
))
