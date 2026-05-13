"""R261 — postMessage origin validator.

Threat: ``window.postMessage`` between iframes is the classic cross-
origin-comm channel; many handlers omit the origin check, accepting
messages from any frame.  Attackers iframe the victim and call
``postMessage`` with attacker payload.

Defence: a helper for HTML/JS audit that flags handlers without an
explicit origin allow-list, and emits a strict handler template.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_HANDLER_RE = re.compile(
    r'(addEventListener\s*\(\s*["\']message["\'],\s*(?:function\s*\([^)]*\)\s*\{[^}]*\}|[A-Za-z_$][A-Za-z0-9_$]*))',
    re.DOTALL,
)
_ORIGIN_CHECK_RE = re.compile(
    r'\.origin\s*(?:===|==|!==|!=)\s*["\'][^"\']+["\']',
)


def audit_postmessage_handlers(source: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    src = source or ""
    for m in _HANDLER_RE.finditer(src):
        end = m.end()
        nearby = src[max(0, m.start() - 40):min(len(src), end + 240)]
        if not _ORIGIN_CHECK_RE.search(nearby):
            issues.append("postmsg.no_origin_check")
    return not issues, issues


def make_strict_handler_template(allowed_origin: str) -> str:
    return (
        "window.addEventListener('message', function(event) {\n"
        f"  if (event.origin !== '{allowed_origin}') return;\n"
        "  // ... handle event.data here, treat as untrusted JSON\n"
        "}, false);"
    )


register(DefencePlugin(
    round_id="R261",
    name="postmessage_origin",
    description="postMessage handler audit: refuse missing origin allow-list.",
))
