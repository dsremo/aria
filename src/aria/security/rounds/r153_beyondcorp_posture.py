"""R153 — BeyondCorp device posture (zero-trust client).

Threat: a stolen laptop or unmanaged BYOD device with a valid user
session is the easiest way past corporate VPN.  Google's BeyondCorp
moved trust off the network and onto the *device + user + context*
axis.

Defence: a posture struct + ``evaluate_posture`` returning ALLOW /
ALLOW_LIMITED / DENY.  Inputs: managed-device certificate present,
OS up-to-date, disk encrypted, screen-lock enabled, last-attestation
freshness.  Operators wire this into the auth gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class DevicePosture:
    managed_cert: bool = False
    os_patch_age_days: int = 999
    disk_encrypted: bool = False
    screen_lock_enabled: bool = False
    attestation_age_seconds: int = 10**9


def evaluate_posture(p: DevicePosture) -> Tuple[str, List[str]]:
    """Returns ('ALLOW' | 'LIMITED' | 'DENY', reasons[])."""
    reasons: List[str] = []
    if not p.managed_cert:
        reasons.append("device_not_managed")
    if p.os_patch_age_days > 30:
        reasons.append(f"os_patch_age_days={p.os_patch_age_days}")
    if not p.disk_encrypted:
        reasons.append("disk_not_encrypted")
    if not p.screen_lock_enabled:
        reasons.append("screen_lock_off")
    if p.attestation_age_seconds > 86_400:
        reasons.append("attestation_stale")
    if not reasons:
        return "ALLOW", []
    if len(reasons) <= 1 and p.managed_cert and p.disk_encrypted:
        return "LIMITED", reasons
    return "DENY", reasons


register(DefencePlugin(
    round_id="R153",
    name="beyondcorp_posture",
    description="BeyondCorp device-posture evaluator: managed cert + OS patch + disk crypt.",
))
