"""R125 — Cloud KMS key-rotation policy.

Threat: a master key that's never rotated stays unchanged for years
even after operator turnover, audit findings, or low-impact key leaks.
PCI-DSS 3.6.4: rotate at least annually.  AWS KMS supports automatic
yearly rotation; banks rotate quarterly.

Defence: an audit helper that walks an AWS KMS key's metadata and
reports whether rotation is enabled + when last rotated.  Soft-fails
when ``boto3`` isn't installed; the helper is primarily a CI gate that
runs once per deploy.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r125")


def audit_kms_key(key_id: str, *, region: Optional[str] = None) -> Tuple[bool, str]:
    has_aws_env = any(
        os.environ.get(k) for k in (
            "AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN",
            "AWS_PROFILE", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
        )
    )
    if not has_aws_env:
        return False, "no_aws_env"
    try:
        import boto3
    except ImportError:
        return False, "boto3_missing"
    try:
        client = boto3.client("kms", region_name=region or os.environ.get("AWS_REGION", "us-east-1"))
        rot = client.get_key_rotation_status(KeyId=key_id)
        if not rot.get("KeyRotationEnabled"):
            return False, f"key_rotation_disabled_for_{key_id}"
        return True, "rotation_enabled"
    except Exception as exc:
        return False, f"audit_failed:{exc}"


def boot_check_keys(*key_ids: str) -> Tuple[bool, list]:
    failures: list = []
    for kid in key_ids:
        ok, why = audit_kms_key(kid)
        if not ok:
            failures.append(f"{kid}: {why}")
    return len(failures) == 0, failures


register(DefencePlugin(
    round_id="R125",
    name="kms_rotation",
    description="Confirm AWS KMS key rotation is enabled (PCI-DSS 3.6.4).",
))
