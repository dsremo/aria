"""ARIA CubeSat End-of-Life De-Orbit Advisor.

A *real, tractable* product:

  Operator inputs the current orbit + spacecraft physical parameters +
  propellant remaining + the FCC / NASA compliance deadlines.  ARIA
  produces a single high-stakes recommendation: do nothing
  (natural decay covers compliance), do a propulsive de-orbit burn now,
  or flag infeasibility (insufficient ΔV / propellant / decision time).

The product targets 6U-class CubeSats in 400-700 km LEO — the
population that drove the FCC 22-271 5-year-rule + the NASA
ODMSP 25-year rule.  Inputs are deliberately operator-friendly
(orbit altitude / inclination / mass / Cd / area / propellant), not
TLE bytes.

Public API:
    advise_deorbit(state, params)            -> DeOrbitRecommendation
    natural_decay_lifetime(state, params)    -> NaturalDecayResult
    plan_propulsive_deorbit(state, params, target_re_alt_km=120.0)
                                              -> BurnPlan
    estimate_reentry_footprint(burn_plan)    -> Footprint

CLI:
    python -m aria.products.cubesat_deorbit <config.toml>

References:
    FCC 22-271 (5-year post-mission de-orbit rule, 2024-09-29);
    NASA-STD-8719.14B Orbital Debris Mitigation Standard Practices;
    King-Hele 1987 "Satellite Orbits in an Atmosphere"; Picone et
    al. 2002 (NRLMSISE-00); Vallado 2013 *Fundamentals of
    Astrodynamics* §9 (orbit raising / lowering).
"""

from aria.products.cubesat_deorbit.advisor import (
    BurnPlan,
    ComplianceCheck,
    DeOrbitRecommendation,
    Decision,
    Footprint,
    MissionParams,
    NaturalDecayResult,
    SpacecraftState,
    advise_deorbit,
    estimate_reentry_footprint,
    natural_decay_lifetime,
    plan_propulsive_deorbit,
)

__all__ = [
    "BurnPlan",
    "ComplianceCheck",
    "DeOrbitRecommendation",
    "Decision",
    "Footprint",
    "MissionParams",
    "NaturalDecayResult",
    "SpacecraftState",
    "advise_deorbit",
    "estimate_reentry_footprint",
    "natural_decay_lifetime",
    "plan_propulsive_deorbit",
]
