"""Shield ballistic-limit bridge (Phase 4 consumer layer).

Takes the actual layer thicknesses stored in
:class:`simulation/shield_system.py` ``WhippleShieldLayer`` and
computes a proper Christiansen 1993 New-Non-Optimum (NNO) ballistic
limit diameter against a user-supplied projectile. Also returns the
impact-regime classification from :mod:`aria.physics.impact` so
downstream consumers can branch on the Hertzian / low-velocity /
hypervelocity / relativistic-ESTIMATE regimes.

This module is a *consumer* of the F4 pod primitives — it does not
add new physics, it ties together `whipple_critical_diameter_nno`,
`classify_impact_regime`, and `relativistic_impact_kinetic_energy`
into a single :class:`ShieldBLEReport` that simulation code can log
at mission start without reaching into the primitives directly.
"""

from __future__ import annotations

from .bridge import (
    ShieldBLEReport,
    ShieldLayerSpec,
    assess_shield_against_particle,
    relativistic_kinetic_energy_mt_tnt,
)

__all__ = [
    "ShieldBLEReport",
    "ShieldLayerSpec",
    "assess_shield_against_particle",
    "relativistic_kinetic_energy_mt_tnt",
]
