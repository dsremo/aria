"""R124 — IAM policy least-privilege lint.

Threat: an IAM policy with ``Action: "*"`` or a wildcard ``Resource:
"*"`` gives the role full account access.  CWE-269.  CISA finding on
80%+ of audited cloud accounts.

Defence: ``audit_iam_policy(policy)`` flags wildcard actions / wildcard
resources for an Allow statement, plus the dangerous-action set that
should always require a tightened resource ARN
(``iam:PassRole``, ``s3:DeleteBucket``, ``kms:Decrypt``, …).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DANGEROUS_ACTIONS = frozenset({
    "iam:PassRole", "iam:CreateUser", "iam:CreateAccessKey",
    "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:PutBucketAcl",
    "kms:Decrypt", "kms:ReEncrypt", "kms:GenerateDataKey",
    "ec2:RunInstances", "lambda:InvokeFunction", "sts:AssumeRole",
    "logs:DeleteLogGroup", "logs:PutResourcePolicy",
})


def audit_iam_policy(policy: Dict[str, Any]) -> Tuple[bool, List[str]]:
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
        resources = stmt.get("Resource") or []
        if isinstance(resources, str):
            resources = [resources]
        # Wildcard action with wildcard resource = full account access
        if "*" in actions and "*" in resources:
            issues.append(f"stmt[{i}].action=*_and_resource=*")
            continue
        # Wildcard service-action (e.g., "s3:*") with "*"  resource
        if any(a.endswith(":*") for a in actions) and "*" in resources:
            issues.append(f"stmt[{i}].service_wildcard_with_resource=*")
        # Dangerous action without specific resource ARN
        for a in actions:
            if a in _DANGEROUS_ACTIONS and "*" in resources:
                issues.append(f"stmt[{i}].dangerous_with_resource=*:{a}")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R124",
    name="iam_least_privilege",
    description="Refuse Action=*+Resource=* and dangerous-actions with wildcard resource.",
))
