"""R253 — Trusted Types DOM XSS guard.

Threat: DOM-XSS sinks (innerHTML, document.write, eval) accept strings
the browser then parses as HTML/JS.  Trusted Types (Chrome, Edge, Web
Platform) refuse string assignments to those sinks unless wrapped by
a registered policy.

Defence: emit a CSP fragment requiring Trusted Types (``require-trusted-
types-for 'script'``) + a default policy allow-list; audit a candidate
header.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def trusted_types_directive(*, allowed_policies: List[str]) -> str:
    if not allowed_policies:
        allowed_policies = ["aria-default"]
    policies = " ".join(allowed_policies)
    return (
        f"trusted-types {policies}; "
        f"require-trusted-types-for 'script'"
    )


def audit_trusted_types(csp_header: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    h = (csp_header or "").lower()
    if "require-trusted-types-for 'script'" not in h:
        issues.append("tt.require_directive_missing")
    if "trusted-types " not in h:
        issues.append("tt.policy_directive_missing")
    if "trusted-types *" in h:
        issues.append("tt.policy_wildcard")
    return not issues, issues


register(DefencePlugin(
    round_id="R253",
    name="trusted_types",
    description="Trusted Types CSP directive emitter + audit.",
))
