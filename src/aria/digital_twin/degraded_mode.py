"""Degraded-mode survival analysis for ARIA ship (Al-Rashidi R6 PDR).

What happens when major systems fail? This module enumerates failure
scenarios, crew survival time, and mitigation procedures.

SCENARIOS MODELED:
  1. Reactor scram — 200 MW → 10 kWe RTG backup insufficient
  2. Half radiator loss — 67 MW vs 134 MW waste → cabin overheats
  3. Hull breach (single compartment) — pressure loss isolated
  4. Magsail deployment failure — cannot decelerate from 0.1c
  5. ECLSS total failure — CO2 buildup kills crew in hours
  6. Fusion fuel depletion — ship drifts with limited maneuverability

REFERENCES:
  NASA-STD-8729.1A (2017): Failure Modes and Effects Analysis
  Brown et al. (2018): ISS Contingency Operations Handbook, JSC-65840
  ECSS-Q-ST-30C: Dependability requirements for space systems
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class DegradedScenario:
    """A single ship failure scenario."""
    name: str
    severity: Literal["recoverable", "critical", "fatal"]
    crew_survival_hours: float  # math.inf = indefinite
    probability_per_year: float
    mitigation: str
    references: str = ""


DEGRADED_SCENARIOS: list[DegradedScenario] = [
    DegradedScenario(
        name="reactor_scram",
        severity="fatal",
        crew_survival_hours=48.0,  # ~2 days on RTG + emergency batteries
        probability_per_year=0.05,  # ITER estimate for mature fusion (de Vries 2011)
        mitigation="Emergency RTG (10 kWe) can power minimal life support for "
                   "~50 crew in shelter zone. 850 kW ECLSS for 1000 crew cannot "
                   "be sustained. Must restart reactor within 48 hours or evacuate "
                   "non-essential crew to torpor to conserve O2/power.",
        references="de Vries 2011 (ITER disruption rate); NASA-STD-8729.1A",
    ),
    DegradedScenario(
        name="half_radiator_loss",
        severity="critical",
        crew_survival_hours=168.0,  # 1 week before cabin > 40°C
        probability_per_year=0.02,
        mitigation="Reduce reactor to 50% thermal output. Cabin temperature "
                   "rises ~2°C/day without full radiator capacity. Crew evacuates "
                   "non-essential sections and concentrates in shelter zones "
                   "with passive cooling via coolant loop bypass.",
        references="thermal_management.py + Messerschmid 2013",
    ),
    DegradedScenario(
        name="hull_breach_single_compartment",
        severity="recoverable",
        crew_survival_hours=math.inf,
        probability_per_year=0.01,
        mitigation="Compartment isolation via pressure bulkhead hatches. "
                   "Crew in affected zone have ~5 minutes to evacuate (1 atm → "
                   "vacuum equalization). Expected casualties: 1-3% of zone "
                   "population. Repair from inside using EVA suits.",
        references="ISS MMOD strikes; Christiansen 2003",
    ),
    DegradedScenario(
        name="magsail_deployment_failure",
        severity="fatal",
        crew_survival_hours=math.inf,
        probability_per_year=0.001,
        mitigation="Mission failure — fly-through at 0.1c, no orbital insertion "
                   "possible. Ship drifts through target system and exits into "
                   "interstellar space. D-T fusion alone cannot decelerate "
                   "(mass ratio = 10^13). Colony becomes sublight generation "
                   "ship with indefinite mission.",
        references="Zubrin 1991 (magsail); Forward 1984 (staged sail)",
    ),
    DegradedScenario(
        name="eclss_total_failure",
        severity="fatal",
        crew_survival_hours=12.0,  # LiOH backup scrubbers
        probability_per_year=0.01,
        mitigation="Emergency LiOH cartridges provide ~12 hours of CO2 scrubbing "
                   "for full crew. Portable O2 supplies (50 × 1hr) sustain "
                   "critical personnel during repair. Must restore Sabatier "
                   "or electrolysis within 12 hours.",
        references="ISS ECLSS contingency procedures",
    ),
    DegradedScenario(
        name="fusion_fuel_depletion",
        severity="critical",
        crew_survival_hours=math.inf,  # Ship survives but immobile
        probability_per_year=0.0,  # Only at end of mission
        mitigation="Loss of thrust capability. Ship continues on cruise velocity "
                   "until magsail braking. Orbital insertion requires remaining "
                   "propellant reserves. If fully depleted, fly-through.",
        references="deltav_budget.py; fusion fuel 1,518t initial",
    ),
]


def get_scenario(name: str) -> DegradedScenario:
    """Look up a scenario by name."""
    for s in DEGRADED_SCENARIOS:
        if s.name == name:
            return s
    raise KeyError(f"Unknown scenario: {name}")


# Mitigation credit: each scenario has backup systems that reduce
# P(crew death | scenario occurred). NASA PRA standard practice.
MITIGATION_CREDITS = {
    "reactor_scram":              0.05,  # 95% reduction from RTG + torpor + restart procedures
    "half_radiator_loss":         0.02,  # 98% reduction — recoverable with power reduction
    "hull_breach_single_compartment": 0.01,  # Already recoverable
    "magsail_deployment_failure": 0.10,  # 90% reduction — secondary magsail, redundant deploy
    "eclss_total_failure":        0.05,  # 95% reduction — LiOH backup + repair
    "fusion_fuel_depletion":      0.01,  # Not fatal, ship drifts
}


def total_fatal_risk_per_year() -> float:
    """Sum of probabilities of fatal scenarios per year (raw, no mitigation)."""
    return sum(s.probability_per_year for s in DEGRADED_SCENARIOS
               if s.severity == "fatal")


def mitigated_fatal_risk_per_year() -> float:
    """Fatal risk per year WITH mitigation credit applied.

    P(crew death) = P(scenario occurs) × P(death | scenario after mitigation)
    """
    total = 0.0
    for s in DEGRADED_SCENARIOS:
        if s.severity == "fatal":
            mitigation = MITIGATION_CREDITS.get(s.name, 0.5)  # Default 50% if unknown
            total += s.probability_per_year * mitigation
    return total


def survival_probability(mission_years: float, include_mitigation: bool = True) -> float:
    """Probability of crew survival over the full mission.

    Uses Poisson process: P(survival) = exp(-λ × t)
    With mitigation: λ reflects P(death) not P(scenario occurs).

    Args:
        mission_years: Mission duration in years
        include_mitigation: If True, applies backup/redundancy credits
    """
    if include_mitigation:
        rate = mitigated_fatal_risk_per_year()
    else:
        rate = total_fatal_risk_per_year()
    return math.exp(-rate * mission_years)


def get_fatal_scenarios() -> list[DegradedScenario]:
    """Return only the fatal scenarios."""
    return [s for s in DEGRADED_SCENARIOS if s.severity == "fatal"]


def get_recoverable_scenarios() -> list[DegradedScenario]:
    """Return only the recoverable scenarios."""
    return [s for s in DEGRADED_SCENARIOS if s.severity == "recoverable"]
