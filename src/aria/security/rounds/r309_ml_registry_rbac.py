"""R309 — ML registry RBAC.

Threat: many ML registries (MLflow, Weights & Biases, custom) ship
with broad write access — anyone with a valid token can publish or
overwrite a model.  A compromised CI runner becomes an arbitrary-
model-publish primitive.

Defence: per-action permission gate.  ``can`` returns whether a
principal may perform action X on resource Y, given role bindings
(``read``, ``write``, ``promote``, ``delete``, ``admin``).  Refuses
``promote`` to ``production`` without two-person rule (R243).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_ROLES: Dict[str, Set[str]] = {
    "viewer":     {"read"},
    "publisher":  {"read", "write"},
    "promoter":   {"read", "write", "promote_staging"},
    "admin":      {"read", "write", "promote_staging", "promote_production", "delete"},
}


@dataclass
class _BindingStore:
    bindings: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))


_STORE = _BindingStore()
_LOCK = threading.Lock()


def grant(principal: str, role: str) -> None:
    if role not in _ROLES:
        raise ValueError(f"R309: unknown role:{role}")
    with _LOCK:
        _STORE.bindings[principal].add(role)


def revoke(principal: str, role: str) -> None:
    with _LOCK:
        _STORE.bindings[principal].discard(role)


def can(principal: str, action: str, *, two_person_token: str = "") -> Tuple[bool, str]:
    with _LOCK:
        roles = set(_STORE.bindings.get(principal, set()))
    perms: Set[str] = set()
    for r in roles:
        perms |= _ROLES.get(r, set())
    if action == "promote_production" and not two_person_token:
        return False, "rbac.promote_production_requires_two_person"
    if action in perms:
        return True, "ok"
    return False, f"rbac.permission_missing:{action}"


def reset_for_tests() -> None:
    with _LOCK:
        _STORE.bindings.clear()


register(DefencePlugin(
    round_id="R309",
    name="ml_registry_rbac",
    description="ML registry RBAC: per-action gate with two-person rule on production promotion.",
))
