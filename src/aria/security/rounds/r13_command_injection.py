"""R13 — OS command injection.

Threat: a parameter that ends up as a shell argument lets the attacker
break out via ``;``, ``|``, backticks, ``$()``, or newlines.  Real
cases: D-Link DIR-823X (CVE-2025-29635, on the CISA KEV catalog as of
this audit), Apache Struts shell-out chains, SimpleHelp path-traversal-
to-RCE (CVE-2024-57728).

Defence: ``safe_shell_arg(value)`` validates a string contains only
``[A-Za-z0-9._/-]`` (the conservative POSIX-friendly subset).  Any
field reaching ``subprocess`` should be passed through this guard
when its origin is operator/user input.  Plus a request-time scorer
for shell-metachar density inside JSON values.
"""

from __future__ import annotations

import json
import re
from typing import Any, Tuple

from aria.security.plugins import DefencePlugin, register


_SAFE_SHELL_RE = re.compile(r"^[A-Za-z0-9._/+\-=:@,]+$")
_METACHARS_RE = re.compile(r"[;&|`\$\(\)<>\\\n]")


def safe_shell_arg(value: str, *, max_len: int = 1024) -> bool:
    if not value or len(value) > max_len:
        return False
    return bool(_SAFE_SHELL_RE.match(value))


def metachar_density(s: str) -> float:
    if not s:
        return 0.0
    hits = len(_METACHARS_RE.findall(s))
    return hits / max(1, len(s))


def _walk(obj: Any, depth: int = 0) -> float:
    if depth > 12:
        return 0.0
    worst = 0.0
    if isinstance(obj, dict):
        for v in obj.values():
            worst = max(worst, _walk(v, depth + 1))
    elif isinstance(obj, list):
        for v in obj:
            worst = max(worst, _walk(v, depth + 1))
    elif isinstance(obj, str):
        if len(obj) >= 6:
            worst = max(worst, metachar_density(obj))
    return worst


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or len(payload) > 4 * 1024 * 1024:
        return 0.0, ""
    try:
        obj = json.loads(payload)
    except Exception:
        s = payload.decode("utf-8", errors="ignore")
        d = metachar_density(s)
        if d >= 0.05:
            return min(0.85, d * 6), f"r13.shell_metadensity={d:.2f}"
        return 0.0, ""
    d = _walk(obj)
    if d >= 0.05:
        return min(0.9, d * 6), f"r13.shell_metadensity={d:.2f}"
    return 0.0, ""


register(DefencePlugin(
    round_id="R13",
    name="command_injection",
    description="Refuse shell metacharacter dense values; safe_shell_arg helper.",
    on_score=_on_score,
))
