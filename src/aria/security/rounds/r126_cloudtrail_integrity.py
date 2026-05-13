"""R126 — CloudTrail digest-validation.

Threat: an attacker with elevated privileges in AWS may delete or edit
CloudTrail logs to hide their footprint.  CloudTrail offers digest
files that chain log entries cryptographically; ``aws cloudtrail
validate-logs`` confirms no entry was modified or removed.

Defence: a small wrapper that runs the validation periodically (per
account / per region), emits ``digest_ok`` or the missing-digest list
into the audit forwarder (R92).  Pairs with R98 immutable logs for
defence in depth.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r126")


def is_aws_cli_available() -> bool:
    return shutil.which("aws") is not None


def validate_cloudtrail(
    *,
    trail_arn: str,
    start_time: str,
    end_time: str,
) -> Tuple[bool, List[str]]:
    """Run ``aws cloudtrail validate-logs`` for the window.  Returns
    ``(ok, missing_or_modified_files)``."""
    if not is_aws_cli_available():
        return False, ["aws_cli_missing"]
    try:
        proc = subprocess.run(                                # nosec B603
            ["aws", "cloudtrail", "validate-logs",
             "--trail-arn", trail_arn,
             "--start-time", start_time,
             "--end-time", end_time],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if proc.returncode != 0:
            return False, [proc.stderr.strip()[:300]]
        # Parse output for "files were verified successfully" / failure summary
        out = proc.stdout
        ok = "verified successfully" in out and "Failure" not in out
        if ok:
            return True, []
        # Extract failure lines
        bads = [line for line in out.splitlines() if "FAIL" in line.upper()]
        return False, bads[:64]
    except Exception as exc:
        return False, [f"exc:{exc}"]


register(DefencePlugin(
    round_id="R126",
    name="cloudtrail_integrity",
    description="aws cloudtrail validate-logs wrapper for digest integrity check.",
))
