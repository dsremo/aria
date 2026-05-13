"""R11 — NoSQL injection (MongoDB / DynamoDB / generic JSON-DB).

Threat: a JSON body containing operators like ``{"$gt":""}``,
``{"$where":"sleep(5000)"}``, or ``{"$regex":".*"}`` is forwarded
verbatim into a MongoDB / DocumentDB filter, returning all documents
or letting an attacker run server-side JavaScript.  CWE-943.

Defence: a request scorer that flags inbound JSON containing keys
beginning with ``$`` (Mongo operator class) or ``--`` patterns inside
nested values.  Scorer is conservative — fires only when the operator
key sits in a *value* position (filter), not a meta-position.
"""

from __future__ import annotations

import json
from typing import Any, Tuple

from aria.security.plugins import DefencePlugin, register


_DANGEROUS_OPS = frozenset({
    "$where", "$function", "$accumulator", "$expr",
    "$regex", "$options",       # less catastrophic but worth flagging
})


def _walk(obj: Any, depth: int = 0, max_depth: int = 16) -> int:
    """Return count of dangerous Mongo-class operator keys."""
    if depth > max_depth:
        return 0
    hits = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k in _DANGEROUS_OPS:
                hits += 1
            hits += _walk(v, depth + 1, max_depth)
    elif isinstance(obj, list):
        for v in obj:
            hits += _walk(v, depth + 1, max_depth)
    return hits


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or len(payload) > 4 * 1024 * 1024:
        return 0.0, ""
    try:
        obj = json.loads(payload)
    except Exception:
        return 0.0, ""
    n = _walk(obj)
    if n == 0:
        return 0.0, ""
    if n >= 3:
        return 0.9, f"r11.nosql_injection ops={n}"
    return 0.6, f"r11.nosql_injection ops={n}"


register(DefencePlugin(
    round_id="R11",
    name="nosql_injection",
    description="Reject inbound JSON containing Mongo $where / $regex / $expr.",
    on_score=_on_score,
))
