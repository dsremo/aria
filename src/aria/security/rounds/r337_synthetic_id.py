"""R337 — Synthetic identity in onboarding.

Threat: synthetic-identity fraud (combining real SSN with fabricated
name/DOB/address) is the fastest-growing fraud class — Federal
Reserve estimated $20B+/yr.  Hard to catch because no single record
is wrong.

Defence: a feature-engineered scorer over onboarding signals — name
+ DOB + SSN consistency, recent address velocity, device-graph
sharing with known-fraud devices, bureau-data depth (synthetic IDs
have shallow bureaus).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class OnboardingSignals:
    name_dob_consistent_with_ssn: bool = True
    bureau_records_count: int = 5
    address_changes_last_12mo: int = 0
    device_shared_with_known_fraud: bool = False
    employer_history_present: bool = True
    age_years: int = 30
    ssn_issued_state_matches_history: bool = True


def score_synthetic_identity(s: OnboardingSignals) -> Tuple[float, List[str]]:
    notes: List[str] = []
    score = 0.0

    if not s.name_dob_consistent_with_ssn:
        score += 0.4
        notes.append("ssn_inconsistency")
    if s.bureau_records_count < 3:
        score += 0.25
        notes.append(f"shallow_bureau:{s.bureau_records_count}")
    if s.address_changes_last_12mo >= 4:
        score += 0.15
        notes.append(f"high_address_velocity:{s.address_changes_last_12mo}")
    if s.device_shared_with_known_fraud:
        score += 0.5
        notes.append("device_graph_fraud")
    if not s.employer_history_present and s.age_years > 25:
        score += 0.15
        notes.append("no_employment_history_for_age")
    if not s.ssn_issued_state_matches_history:
        score += 0.2
        notes.append("ssn_geography_mismatch")
    return min(1.0, score), notes


register(DefencePlugin(
    round_id="R337",
    name="synthetic_id",
    description="Synthetic-identity onboarding scorer (bureau depth + device graph + SSN geo).",
))
