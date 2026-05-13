"""R71 — SCIM 2.0 provisioning hardening.

Threat: a SCIM provisioning endpoint that accepts arbitrary
``User``/``Group`` PATCH operations from the IdP can be coerced into
making a low-privilege account into ``role: admin`` — Okta 2024
incidents traced to broken SCIM filters.  RFC 7644 leaves attribute
authority to the implementation; without a strict schema, IdP errors
become privilege escalations.

Defence: a small JSON-PATCH-style validator that refuses any operation
touching a "protected" attribute (``role``, ``permissions``,
``isSuperUser``, ``mfa_enrolled``).  Operators wire the protected set
per deployment; default covers the obvious privilege fields.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_PROTECTED = frozenset({
    "role", "roles", "permissions", "permission_set",
    "isSuperUser", "is_admin", "admin",
    "mfa_enrolled", "mfa_enabled",
    "active",                           # disabling an admin must be deliberate
})


def protected_attrs() -> Set[str]:
    raw = os.environ.get("ARIA_SCIM_PROTECTED_ATTRS", "")
    if not raw:
        return set(_DEFAULT_PROTECTED)
    return set(_DEFAULT_PROTECTED) | {a.strip() for a in raw.split(",") if a.strip()}


def validate_patch_ops(operations: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Walk ``operations`` (the ``Operations`` array of a SCIM PATCH).
    Returns ``(ok, errors)``."""
    errors: List[str] = []
    if not isinstance(operations, list):
        return False, ["operations must be a list"]
    protected = protected_attrs()
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            errors.append(f"op[{i}] not a dict")
            continue
        path = op.get("path", "") or ""
        if any(p in path for p in protected):
            errors.append(f"op[{i}] touches protected attribute: {path}")
            continue
        # Some IdPs put the attribute in `value` keys instead of path
        v = op.get("value")
        if isinstance(v, dict):
            for k in v.keys():
                if k in protected:
                    errors.append(f"op[{i}].value contains protected attribute: {k}")
    return len(errors) == 0, errors


register(DefencePlugin(
    round_id="R71",
    name="scim_provisioning",
    description="Refuse SCIM PATCH ops touching protected attributes.",
))
