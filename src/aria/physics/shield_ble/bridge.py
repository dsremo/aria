"""Shield BLE bridge — assess a Whipple shield against a real particle.

Given the concrete layer thicknesses stored in
`simulation/shield_system.py` ``WhippleShieldLayer``, compute:

  - The Christiansen 1993 NNO critical-projectile diameter the
    shield can stop at the mission cruise velocity.
  - The impact regime classification (Hertzian / low-velocity /
    hypervelocity / extrapolated / ultra-relativistic) from the F4
    scope-note dispatcher.
  - The projectile kinetic energy in joules and in megatons of TNT
    (a useful mental-model unit for generation-ship threat
    assessment).
  - A Boolean perforation verdict for a given projectile diameter.

This module is a pure consumer; no new physics.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..impact import (
    ImpactRegime,
    classify_impact_regime,
    relativistic_impact_kinetic_energy,
    whipple_critical_diameter_nno,
    whipple_is_perforated,
)


# 1 megaton TNT = 4.184×10¹⁵ J (Sutton 1969 Nuclear weapons yield).
_JOULES_PER_MT_TNT: float = 4.184e15


@dataclass(frozen=True)
class ShieldLayerSpec:
    """Geometric + material parameters of a Whipple layer stack.

    Attributes match the ``WhippleShieldLayer`` dataclass in
    :mod:`aria.simulation.shield_system` so callers can build a
    spec directly from the simulator's existing config. All inputs
    are in SI units.
    """

    bumper_thickness_m: float
    bumper_density_kg_m3: float
    standoff_m: float
    rear_wall_thickness_m: float
    rear_wall_density_kg_m3: float
    rear_wall_yield_strength_pa: float

    def __post_init__(self) -> None:
        if self.bumper_thickness_m <= 0.0:
            raise ValueError("bumper_thickness_m must be positive")
        if self.bumper_density_kg_m3 <= 0.0:
            raise ValueError("bumper_density_kg_m3 must be positive")
        if self.standoff_m <= 0.0:
            raise ValueError("standoff_m must be positive")
        if self.rear_wall_thickness_m <= 0.0:
            raise ValueError("rear_wall_thickness_m must be positive")
        if self.rear_wall_density_kg_m3 <= 0.0:
            raise ValueError("rear_wall_density_kg_m3 must be positive")
        if self.rear_wall_yield_strength_pa <= 0.0:
            raise ValueError("rear_wall_yield_strength_pa must be positive")


@dataclass(frozen=True)
class ShieldBLEReport:
    """Result of ``assess_shield_against_particle``.

    Attributes:
        regime: impact classification (Hertzian .. ultra-relativistic).
        critical_diameter_m: Christiansen 1993 NNO d_c value. Returns
            ``None`` if the projectile is in a regime outside the
            hypervelocity / extrapolated envelope (Hertzian or
            ultra-relativistic), where the NNO formula does not
            apply.
        projectile_kinetic_energy_j: classical or relativistic KE of
            the projectile, using the
            ``relativistic_impact_kinetic_energy`` dispatcher.
        projectile_kinetic_energy_mt_tnt: kinetic energy in megatons
            of TNT.
        perforated: True iff the projectile diameter exceeds the
            critical diameter (only defined when the regime is
            hypervelocity or extrapolated).
        notes: free-form warning string for regimes where the answer
            should be treated as an ESTIMATE.
    """

    regime: ImpactRegime
    critical_diameter_m: float | None
    projectile_kinetic_energy_j: float
    projectile_kinetic_energy_mt_tnt: float
    perforated: bool | None
    notes: str


def relativistic_kinetic_energy_mt_tnt(
    projectile_mass_kg: float, velocity_m_s: float
) -> float:
    """Convenience: KE in megatons-of-TNT equivalent."""
    ke_j = relativistic_impact_kinetic_energy(
        rest_mass_kg=projectile_mass_kg,
        velocity_m_s=velocity_m_s,
    )
    return ke_j / _JOULES_PER_MT_TNT


def assess_shield_against_particle(
    shield: ShieldLayerSpec,
    projectile_diameter_m: float,
    projectile_density_kg_m3: float,
    projectile_mass_kg: float,
    impact_velocity_m_s: float,
    angle_from_normal_rad: float = 0.0,
) -> ShieldBLEReport:
    """Run the full shield assessment for a single impactor.

    Workflow:
      1. classify_impact_regime(v) → regime label.
      2. If the regime is hypervelocity / extrapolated, call
         whipple_critical_diameter_nno to get d_c and compare.
      3. Compute projectile KE (relativistic dispatcher honours
         the 0.01 c cutoff from the F4 scope note).

    Args:
        shield: layer geometry + materials.
        projectile_diameter_m: d_p (m, positive).
        projectile_density_kg_m3: ρ_p (kg/m³, positive).
        projectile_mass_kg: m_p (kg, positive). Supplied separately
            so non-spherical / composite projectiles can be handled
            — no consistency check is imposed between m_p and d_p.
        impact_velocity_m_s: v (m/s, positive).
        angle_from_normal_rad: θ (rad).

    Returns:
        ShieldBLEReport.
    """
    if projectile_diameter_m <= 0.0:
        raise ValueError("projectile_diameter_m must be positive")
    if projectile_density_kg_m3 <= 0.0:
        raise ValueError("projectile_density_kg_m3 must be positive")
    if projectile_mass_kg <= 0.0:
        raise ValueError("projectile_mass_kg must be positive")
    if impact_velocity_m_s <= 0.0:
        raise ValueError("impact_velocity_m_s must be positive")

    regime = classify_impact_regime(impact_velocity_m_s)
    ke_j = relativistic_impact_kinetic_energy(
        rest_mass_kg=projectile_mass_kg,
        velocity_m_s=impact_velocity_m_s,
    )
    ke_mt = ke_j / _JOULES_PER_MT_TNT

    # The NNO formula is calibrated on 3-15 km/s HVI data; we
    # extend its use up to the 0.01 c ultra-relativistic cutoff with
    # a widened-uncertainty annotation. Below 3 km/s and in the
    # relativistic regime we return None for d_c so the caller can
    # branch on a more appropriate model.
    d_c: float | None
    perforated: bool | None
    if regime in (ImpactRegime.HYPERVELOCITY_BLE, ImpactRegime.EXTRAPOLATED_BLE):
        d_c = whipple_critical_diameter_nno(
            bumper_thickness_m=shield.bumper_thickness_m,
            bumper_density_kg_m3=shield.bumper_density_kg_m3,
            rear_wall_thickness_m=shield.rear_wall_thickness_m,
            rear_wall_density_kg_m3=shield.rear_wall_density_kg_m3,
            rear_wall_yield_strength_pa=shield.rear_wall_yield_strength_pa,
            standoff_m=shield.standoff_m,
            projectile_density_kg_m3=projectile_density_kg_m3,
            impact_velocity_m_s=impact_velocity_m_s,
            angle_from_normal_rad=angle_from_normal_rad,
        )
        perforated = whipple_is_perforated(
            projectile_diameter_m=projectile_diameter_m,
            bumper_thickness_m=shield.bumper_thickness_m,
            bumper_density_kg_m3=shield.bumper_density_kg_m3,
            rear_wall_thickness_m=shield.rear_wall_thickness_m,
            rear_wall_density_kg_m3=shield.rear_wall_density_kg_m3,
            rear_wall_yield_strength_pa=shield.rear_wall_yield_strength_pa,
            standoff_m=shield.standoff_m,
            projectile_density_kg_m3=projectile_density_kg_m3,
            impact_velocity_m_s=impact_velocity_m_s,
            angle_from_normal_rad=angle_from_normal_rad,
        )
        notes = (
            "NNO formula calibrated 3-15 km/s (Christiansen 1993)"
            if regime == ImpactRegime.HYPERVELOCITY_BLE
            else (
                "EXTRAPOLATED: velocity > 15 km/s beyond experimental "
                "calibration — NNO value is ±factor-of-2 at best."
            )
        )
    else:
        d_c = None
        perforated = None
        if regime == ImpactRegime.ULTRA_RELATIVISTIC:
            notes = (
                "ULTRA-RELATIVISTIC: v > 0.01 c — Christiansen NNO does "
                "not apply. Hydrocode or plasma-shock model required."
            )
        elif regime == ImpactRegime.HERTZIAN:
            notes = "HERTZIAN: v < 50 m/s — use quasi-static contact mechanics."
        else:  # LOW_VELOCITY
            notes = "LOW-VELOCITY: v < 3 km/s — use Poncelet / Recht-Ipson."

    return ShieldBLEReport(
        regime=regime,
        critical_diameter_m=d_c,
        projectile_kinetic_energy_j=ke_j,
        projectile_kinetic_energy_mt_tnt=ke_mt,
        perforated=perforated,
        notes=notes,
    )
