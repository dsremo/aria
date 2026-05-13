"""R155 — Envoy ext_authz response shape validator.

Threat: a misconfigured ext_authz filter that returns 200 OK with a
malformed body causes Envoy to fail-open for every request behind it
— turning the data-plane authz hook into a global bypass.

Defence: a response builder + validator that emits ALLOW/DENY in the
exact shape Envoy's gRPC ext_authz expects.  Refuses to construct an
ALLOW without explicit principal + scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ExtAuthzDecision:
    allow: bool
    principal: str = ""
    scopes: List[str] = field(default_factory=list)
    deny_reason: str = ""
    headers_to_add: Dict[str, str] = field(default_factory=dict)


def build_decision(*, allow: bool, principal: str, scopes: List[str], reason: str = "") -> ExtAuthzDecision:
    if allow:
        if not principal:
            raise ValueError("R155: ALLOW requires non-empty principal")
        if not scopes:
            raise ValueError("R155: ALLOW requires non-empty scopes")
    else:
        if not reason:
            raise ValueError("R155: DENY requires deny_reason")
    return ExtAuthzDecision(
        allow=allow, principal=principal, scopes=list(scopes), deny_reason=reason
    )


def render_envoy_check_response(d: ExtAuthzDecision) -> Tuple[int, Dict[str, str]]:
    if d.allow:
        return 200, {
            "x-aria-principal": d.principal,
            "x-aria-scopes": ",".join(d.scopes),
            **d.headers_to_add,
        }
    return 403, {"x-aria-deny-reason": d.deny_reason}


register(DefencePlugin(
    round_id="R155",
    name="envoy_extauthz",
    description="Envoy ext_authz decision builder + ALLOW/DENY shape guard.",
))
