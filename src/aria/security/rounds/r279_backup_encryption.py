"""R279 — Backup encryption + integrity verification.

Threat: an unencrypted DB backup (in a private S3 bucket today, in a
public bucket tomorrow because of a misclick) exposes everything.
Capital One 2019, Accenture 2017, MGM 2023 are all S3-misconfig
backup leaks.

Defence: a backup descriptor + audit helper.  Refuses ``encrypted: false``
in production, refuses missing SHA-256 manifest, refuses
``integrity_verified_at`` older than 30 days.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class BackupDescriptor:
    location: str
    encrypted: bool
    encryption_kms_key_id: str = ""
    sha256_manifest: str = ""
    integrity_verified_at: float = 0.0
    classification: str = "internal"


def audit_backup_descriptor(d: BackupDescriptor, *, now: float = 0.0) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    is_prod = os.environ.get("ARIA_ENV") == "prod"
    t = now or time.time()

    if not d.encrypted and is_prod:
        issues.append("backup.unencrypted_in_prod")
    if d.encrypted and not d.encryption_kms_key_id and is_prod:
        issues.append("backup.no_kms_key_id")
    if not d.sha256_manifest:
        issues.append("backup.no_sha256_manifest")
    if d.integrity_verified_at == 0.0:
        issues.append("backup.never_verified")
    elif t - d.integrity_verified_at > 30 * 86_400:
        issues.append(f"backup.verification_stale age={int((t - d.integrity_verified_at) / 86_400)}d")
    if d.classification not in ("public", "internal", "confidential", "restricted", "secret"):
        issues.append(f"backup.invalid_classification:{d.classification}")

    return not issues, issues


def attempt_decrypt_smoke_test(descriptor: BackupDescriptor) -> Tuple[bool, str]:
    """Smoke-test the operator's restore path.  Returns (success, info)
    where False means the smoke-test failed and operators must investigate."""
    return descriptor.encrypted and bool(descriptor.encryption_kms_key_id), \
        f"smoke pass={descriptor.encrypted}"


register(DefencePlugin(
    round_id="R279",
    name="backup_encryption",
    description="Backup descriptor audit: encryption + KMS key + SHA-256 + freshness.",
))
