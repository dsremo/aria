"""R65 — Risk-based step-up authentication.

Threat: low-friction primary auth (token in header) is fine for routine
reads but inadequate for irreversible mutations.  Banking standard:
prompt for an extra factor when risk score crosses a threshold —
"step up" the auth instead of forcing it everywhere.

Defence: ``required_factor(action, principal, risk_signals)`` returns
the minimum factor level required for the requested action given the
current risk picture (geo anomaly from R9, behaviour score from
R-foundation, drift from R29).  Caller refuses or prompts for the
upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


class FactorLevel(IntEnum):
    NONE = 0
    PASSWORD = 1
    TOTP = 2
    HARDWARE = 3        # FIDO2 / WebAuthn / smartcard
    DUAL_PERSON = 4     # R47 two-person rule


_ACTION_BASELINE: Dict[str, FactorLevel] = {
    "read": FactorLevel.PASSWORD,
    "write": FactorLevel.TOTP,
    "rotate_key": FactorLevel.HARDWARE,
    "rotate_master_key": FactorLevel.DUAL_PERSON,
    "delete_tenant": FactorLevel.DUAL_PERSON,
    "modify_constitution": FactorLevel.DUAL_PERSON,
}


@dataclass
class RiskSignals:
    geo_anomaly: float = 0.0
    behaviour_score: float = 0.0
    drift_score: float = 0.0
    is_after_hours: bool = False
    new_device: bool = False


def required_factor(action: str, signals: RiskSignals) -> FactorLevel:
    base = _ACTION_BASELINE.get(action, FactorLevel.PASSWORD)
    bumps = 0
    if signals.geo_anomaly >= 0.5 or signals.behaviour_score >= 0.5:
        bumps += 1
    if signals.drift_score >= 0.5:
        bumps += 1
    if signals.new_device:
        bumps += 1
    if signals.is_after_hours:
        bumps += 1
    return FactorLevel(min(int(FactorLevel.DUAL_PERSON), int(base) + bumps))


def can_proceed(presented: FactorLevel, action: str, signals: RiskSignals) -> Tuple[bool, FactorLevel]:
    needed = required_factor(action, signals)
    return (presented >= needed), needed


register(DefencePlugin(
    round_id="R65",
    name="step_up_auth",
    description="Compute required factor level for an action given risk signals.",
))
