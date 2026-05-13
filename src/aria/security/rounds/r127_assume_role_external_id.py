"""R127 — Cross-account ``sts:AssumeRole`` with ExternalId.

Threat: the *confused deputy* class — a customer's IAM role trusts
``arn:aws:iam::AcmeProvider:role/Service`` but Acme is multi-tenant;
without ExternalId, Acme's other tenants can assume the role.  AWS
documents this exact gotcha + ExternalId mitigation.

Defence: ``audit_trust_policy(policy)`` flags any cross-account
``sts:AssumeRole`` trust that lacks the ``ExternalId`` condition.
Plus a ``random_external_id()`` helper that mints a 32-byte random
value the operator passes when they're the customer.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def random_external_id() -> str:
    return secrets.token_urlsafe(32)


def audit_trust_policy(
    policy: Dict[str, Any],
    *,
    own_account_id: str = "",
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not isinstance(policy, dict):
        return False, ["not_a_dict"]
    statements = policy.get("Statement") or []
    if isinstance(statements, dict):
        statements = [statements]
    for i, stmt in enumerate(statements):
        if stmt.get("Effect") != "Allow":
            continue
        actions = stmt.get("Action") or []
        if isinstance(actions, str):
            actions = [actions]
        if "sts:AssumeRole" not in actions:
            continue
        principal = stmt.get("Principal") or {}
        aws = principal.get("AWS") if isinstance(principal, dict) else None
        if not aws:
            continue
        if isinstance(aws, str):
            aws = [aws]
        # Cross-account if any principal arn account != own
        cross = False
        for arn in aws:
            try:
                acct = arn.split(":")[4]
            except IndexError:
                continue
            if acct and acct != own_account_id:
                cross = True
                break
        if cross:
            cond = stmt.get("Condition") or {}
            ext_id = (cond.get("StringEquals") or {}).get("sts:ExternalId")
            if not ext_id:
                issues.append(f"stmt[{i}].cross_account_AssumeRole_missing_ExternalId")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R127",
    name="assume_role_external_id",
    description="Cross-account sts:AssumeRole policies must require ExternalId.",
))
