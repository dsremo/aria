"""R143 — Cross-Site Script Inclusion (XSSI).

Threat: a JSON endpoint that returns ``[{"x":1},{"x":2}]`` (raw
array) or ``var data = …;`` is loadable cross-origin via a
``<script src="...">`` tag — the reading site reads the array via
JS prototype hooks even though SOP nominally blocks it.  Mitigations:
serve JSON as a non-array top-level (object), prepend a parser-breaking
prefix (``)]}'\n``) à la Gmail/Angular.

Defence: ``wrap_json(payload)`` ensures an object-shaped top-level
+ adds the ``)]}'\n`` prefix; ``unwrap_json(text)`` reverses for
trusted same-origin clients.  Plus an ``audit_response_shape(body)``
that flags raw arrays / `var x =` / function-call wrappers.
"""

from __future__ import annotations

import json
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_PREFIX = ")]}'\n"


def wrap_json(payload) -> str:
    """Emit JSON with parser-break prefix; refuses raw array roots."""
    if isinstance(payload, list):
        payload = {"items": payload}        # force object root
    return _PREFIX + json.dumps(payload)


def unwrap_json(text: str):
    if not text:
        return None
    if text.startswith(_PREFIX):
        text = text[len(_PREFIX):]
    return json.loads(text)


def audit_response_shape(body_text: str) -> Tuple[bool, str]:
    """Return ``(safe, reason)`` for a JSON response body."""
    if not body_text:
        return True, "empty"
    head = body_text.lstrip()[:64]
    if head.startswith("["):
        return False, "raw_array_root"
    if head.startswith("var ") or head.startswith("let ") or head.startswith("const "):
        return False, "js_var_assignment"
    if head.startswith(("call(", "callback(")):
        return False, "jsonp_callback"
    return True, "ok"


register(DefencePlugin(
    round_id="R143",
    name="xssi",
    description="Object-only JSON wrap + )]}' prefix; refuse raw-array roots.",
))
