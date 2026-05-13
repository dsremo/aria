"""R6 — Mass assignment / unexpected-field exploits.

Threat: a JSON body shipped to a handler carries fields the API
contract did not advertise — ``"role": "admin"``, ``"is_paid": true``,
``"tenant_id": "victim"``.  If the handler blindly merges body into a
DB row, the attacker escalates.  Real cases: GitHub Rails-class
``Mass Assignment`` (2012, still seen in 2024 audits), Mongoose schema
laxity defects.

Defence: a single ``strict_fields(body, allowed)`` helper that fails
closed.  Plus a request-time scorer that flags a request whose body
contains ARIA-internal field names (``tenant_id``, ``role``,
``api_key_hex`` …) as 0.7-threat — high but not auto-blocking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


# Field names that should NEVER appear in an inbound request body
# (they are internal and only set by the server).
_INTERNAL_FIELDS = frozenset({
    "tenant_id", "owner_tenant_id", "api_key_hex",
    "role", "principal_role", "permission_set",
    "_canary", "_internal", "_audit_chain",
    "is_admin", "admin", "is_paid", "is_superuser",
    "created_at", "updated_at",  # operator may want; keep here as a flag
})


def strict_fields(body: Dict[str, Any], allowed: Iterable[str]) -> Dict[str, Any]:
    """Return a copy of ``body`` containing only ``allowed`` keys.  Raise
    ``ValueError`` if the original body had fields outside the allow-list.
    """
    if not isinstance(body, dict):
        raise ValueError("body must be a dict")
    allowed_set = set(allowed)
    extra = set(body.keys()) - allowed_set
    if extra:
        raise ValueError(f"unexpected fields: {sorted(extra)}")
    return {k: body[k] for k in allowed_set if k in body}


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or len(payload) > 4 * 1024 * 1024:
        return 0.0, ""
    try:
        obj = json.loads(payload)
    except Exception:
        return 0.0, ""
    if not isinstance(obj, dict):
        return 0.0, ""
    hits = [k for k in obj.keys() if k in _INTERNAL_FIELDS]
    if not hits:
        return 0.0, ""
    return min(0.8, 0.4 + 0.1 * len(hits)), f"r06.mass_assignment:{hits[:3]}"


register(DefencePlugin(
    round_id="R6",
    name="mass_assignment",
    description="Reject inbound JSON containing ARIA-internal field names.",
    on_score=_on_score,
))
