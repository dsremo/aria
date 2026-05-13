"""R15 — XPath injection.

Threat: ``//user[username/text()='{u}' and password/text()='{p}']`` →
attacker sends ``u=' or '1'='1`` and bypasses.  CWE-643.  Particularly
common in XML-driven apps and SOAP services still alive in industrial
SCADA / aerospace ground systems.

Defence: ``escape_xpath_string(value)`` helper and a scorer that
detects classic ``' or '`` / ``") or ("`` / ``//*[`` injection shapes.
"""

from __future__ import annotations

import json
import re
from typing import Any, Tuple

from aria.security.plugins import DefencePlugin, register


def escape_xpath_string(value: str) -> str:
    """Return ``value`` quoted safely for XPath.

    XPath has no escape sequence — the rfc-correct trick is to
    concatenate with ``concat()`` when both quote-types appear; for the
    common case we just refuse if both are present.
    """
    if value is None:
        return "''"
    has_single = "'" in value
    has_double = '"' in value
    if not has_single:
        return f"'{value}'"
    if not has_double:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ",\"'\",".join(f"'{p}'" for p in parts) + ")"


_INJECTION_PATTERNS = (
    re.compile(r"'\s*(?:or|and)\s+'?\d*'?\s*=\s*'?\d*", re.IGNORECASE),
    re.compile(r"\"\s*(?:or|and)\s+\"?\d*\"?\s*=\s*\"?\d*", re.IGNORECASE),
    re.compile(r"//\*\["),
    re.compile(r"\)\s*(?:or|and)\s+\("),
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
    return min(0.85, 0.5 + 0.1 * hits), f"r15.xpath_injection patterns={hits}"


register(DefencePlugin(
    round_id="R15",
    name="xpath_injection",
    description="Detect XPath filter-break sequences in JSON values.",
    on_score=_on_score,
))
