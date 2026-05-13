"""R336 — Liveness verification gate (anti-spoof).

Threat: photo / video / mask spoofing of biometric checks is the #1
KYC-onboarding bypass.  ISO/IEC 30107-3 PAD (Presentation Attack
Detection) is the framework; vendors implement different levels.

Defence: a policy gate over a vendor's PAD result.  Refuses any
session where the score is below a configured threshold OR the
vendor PAD level is below ``min_level`` (e.g. PAD-2 for KYC).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class LivenessResult:
    vendor: str
    pad_level: int           # 1 / 2 / 3 per ISO 30107-3
    score: float             # 0..1, higher = more confident genuine
    challenge_passed: bool = False
    spoof_attack_class: str = ""


def gate_liveness_session(
    result: LivenessResult,
    *,
    min_score: float = 0.85,
    min_pad_level: int = 2,
    require_active_challenge: bool = True,
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if result.pad_level < min_pad_level:
        issues.append(f"liveness.pad_level_too_low:{result.pad_level}<{min_pad_level}")
    if result.score < min_score:
        issues.append(f"liveness.score_too_low:{result.score:.2f}<{min_score:.2f}")
    if require_active_challenge and not result.challenge_passed:
        issues.append("liveness.no_active_challenge")
    if result.spoof_attack_class:
        issues.append(f"liveness.spoof_detected:{result.spoof_attack_class}")
    return not issues, issues


register(DefencePlugin(
    round_id="R336",
    name="liveness",
    description="ISO 30107-3 PAD-based liveness gate; refuse low-score / no-active-challenge.",
))
