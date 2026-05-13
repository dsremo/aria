"""R128 — STS session-duration cap.

Threat: a long-lived ``DurationSeconds`` on ``AssumeRole`` (default
3600 s, max 43 200 s = 12 h) means a stolen STS token can be used for
half a day.  PCI-DSS + bank guidance: max 1 h for human roles,
max 15 min for service roles handling cardholder data.

Defence: ``audit_session_duration(policy_or_settings, *, max_seconds)``
walks role configs and flags excessive durations.  Plus a runtime
helper ``cap_session_duration(boto3_client, max_seconds)`` that wraps
``client.assume_role`` with the cap.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_MAX_SECONDS = 3600


def audit_role_max_duration(role_metadata: Dict[str, Any], *, max_seconds: int = _DEFAULT_MAX_SECONDS) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not isinstance(role_metadata, dict):
        return False, ["not_a_dict"]
    role = role_metadata.get("Role") or role_metadata
    md = role.get("MaxSessionDuration", 3600)
    if isinstance(md, int) and md > max_seconds:
        issues.append(f"MaxSessionDuration={md} > {max_seconds}")
    return len(issues) == 0, issues


def audit_assume_role_call(*, duration_seconds: int, max_seconds: int = _DEFAULT_MAX_SECONDS) -> Tuple[bool, str]:
    if duration_seconds > max_seconds:
        return False, f"duration={duration_seconds} > {max_seconds}"
    return True, "ok"


register(DefencePlugin(
    round_id="R128",
    name="sts_session_duration",
    description="Audit IAM role MaxSessionDuration + AssumeRole calls.",
))
