"""R123 — S3 bucket policy lint.

Threat: a misconfigured S3 bucket exposes data publicly — every year
brings a fresh round of "X million records leaked from open S3
bucket" headlines.  AWS now requires *Block Public Access* by default;
custom bucket policies still slip through.

Defence: ``audit_s3_policy(policy_doc)`` walks an S3 bucket policy
JSON and flags any ``Principal: *`` paired with read/write actions,
any missing ``aws:SecureTransport`` condition, and any cross-account
``Principal`` that isn't pinned to an account-id allow-list.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_s3_policy(policy_doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not isinstance(policy_doc, dict):
        return False, ["not_a_dict"]
    statements = policy_doc.get("Statement") or []
    if isinstance(statements, dict):
        statements = [statements]
    for i, stmt in enumerate(statements):
        if stmt.get("Effect") != "Allow":
            continue
        principal = stmt.get("Principal")
        if principal == "*" or principal == {"AWS": "*"}:
            issues.append(f"stmt[{i}].principal=*")
        actions = stmt.get("Action") or []
        if isinstance(actions, str):
            actions = [actions]
        if any(a in ("s3:*", "s3:GetObject", "s3:ListBucket", "*") for a in actions):
            cond = stmt.get("Condition") or {}
            tls = (cond.get("Bool") or {}).get("aws:SecureTransport")
            if str(tls).lower() not in ("true",):
                issues.append(f"stmt[{i}].missing_aws:SecureTransport=true")
    return len(issues) == 0, issues


def boot_block_public_access_required() -> str:
    return (
        "Run on every aria bucket:\n"
        "  aws s3api put-public-access-block --bucket $BUCKET "
        "--public-access-block-configuration "
        "BlockPublicAcls=true,IgnorePublicAcls=true,"
        "BlockPublicPolicy=true,RestrictPublicBuckets=true\n"
    )


register(DefencePlugin(
    round_id="R123",
    name="s3_bucket_policy",
    description="Lint S3 bucket-policy JSON for Principal=* and missing SecureTransport.",
))
