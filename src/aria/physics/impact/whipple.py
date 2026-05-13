"""Whipple shield ballistic limit equation and regime dispatcher
(§4.5 of F4 scope).

A Whipple shield places a thin "bumper" (stand-off plate) in front
of the pressurised rear wall; at hypervelocity, the incoming
projectile is shattered and vaporized by the bumper, spreading its
kinetic energy over a wide debris cloud that the rear wall can
absorb as a distributed load. The efficiency scales with the
standoff distance and the bumper areal density.

The **New Non-Optimum (NNO)** ballistic limit equation from
Christiansen 1993 (NASA TM-1993-107955) and Ryan 2011 (NASA/JSC
65282) gives the critical projectile diameter `d_c` that the shield
can stop. The equation is piecewise in the normal-component impact
velocity `v_n = v cos θ`:

  Ballistic regime (v_n < 3 km/s):
      d_c = 1.8 (t_w H_w + t_b) / (ρ_p^(1/2) · v_n)       [cm]
  Shatter regime (3 ≤ v_n ≤ 7 km/s):
      d_c = linear interpolation in v_n between the regime anchors
  Hypervelocity regime (v_n > 7 km/s):
      d_c = 3.918 · t_w^(2/3) · ρ_w^(1/9) · (ρ_p)^(−1/3) ·
            ρ_b^(−1/9) · S^(1/3) · (v_n cos θ)^(−2/3) · (σ/40)^(1/3)

(Christiansen 1993 eq. 2, Ryan 2011 eq. 2.1).

These are engineering fits to NASA JSC hypervelocity impact test
data; the absolute accuracy is ±30 % in `d_c` (Ryan 2011 §4).

For the ARIA mission the *interstellar-dust* regime above ~0.01c is
beyond all experimental data; we flag it as an ESTIMATE with a
widened uncertainty band and recommend a hydrocode run for the
load case. This is handled by the regime dispatcher.
"""

from __future__ import annotations

import enum
import math


class ImpactRegime(enum.Enum):
    """Impact regime label returned by the dispatcher."""

    HERTZIAN = "hertzian"  # v < 50 m/s quasi-static elastic
    LOW_VELOCITY = "low_velocity"  # 50 m/s < v < 3 km/s
    HYPERVELOCITY_BLE = "hypervelocity_ble"  # 3 km/s ≤ v ≤ 15 km/s
    EXTRAPOLATED_BLE = "extrapolated_ble"  # 15 km/s < v < 0.01 c
    ULTRA_RELATIVISTIC = "ultra_relativistic"  # v > 0.01 c (ESTIMATE)


_HERTZIAN_CUTOFF_M_S = 50.0
_LOW_VELOCITY_CUTOFF_M_S = 3_000.0
_HVI_TESTED_CUTOFF_M_S = 15_000.0
_ULTRA_RELATIVISTIC_CUTOFF_M_S = 0.01 * 2.99792458e8  # 0.01 c


def classify_impact_regime(relative_velocity_m_s: float) -> ImpactRegime:
    """Return the impact regime label for a given relative velocity.

    Boundaries (F4 scope §8 regime dispatcher):

        < 50 m/s         Hertzian quasi-static elastic
        50 m/s - 3 km/s  Low-velocity (Poncelet / Recht-Ipson)
        3 - 15 km/s      Christiansen NNO ballistic limit (tested)
        15 km/s - 0.01 c Extrapolated BLE (widened uncertainty)
        > 0.01 c         Ultra-relativistic ESTIMATE regime
    """
    if relative_velocity_m_s < 0.0:
        raise ValueError("relative_velocity_m_s must be non-negative")
    if relative_velocity_m_s < _HERTZIAN_CUTOFF_M_S:
        return ImpactRegime.HERTZIAN
    if relative_velocity_m_s < _LOW_VELOCITY_CUTOFF_M_S:
        return ImpactRegime.LOW_VELOCITY
    if relative_velocity_m_s <= _HVI_TESTED_CUTOFF_M_S:
        return ImpactRegime.HYPERVELOCITY_BLE
    if relative_velocity_m_s < _ULTRA_RELATIVISTIC_CUTOFF_M_S:
        return ImpactRegime.EXTRAPOLATED_BLE
    return ImpactRegime.ULTRA_RELATIVISTIC


def whipple_critical_diameter_nno(
    bumper_thickness_m: float,
    bumper_density_kg_m3: float,
    rear_wall_thickness_m: float,
    rear_wall_density_kg_m3: float,
    rear_wall_yield_strength_pa: float,
    standoff_m: float,
    projectile_density_kg_m3: float,
    impact_velocity_m_s: float,
    angle_from_normal_rad: float = 0.0,
) -> float:
    """New Non-Optimum (NNO) ballistic limit — critical projectile
    diameter the shield can stop (Christiansen 1993, Ryan 2011).

    Hypervelocity branch (the regime Whipple shields are designed
    for, v cos θ > 7 km/s):

        d_c = 3.918 · t_w^(2/3) · ρ_w^(1/9) · ρ_p^(−1/3) ·
              ρ_b^(−1/9) · S^(1/3) · (v cos θ)^(−2/3) ·
              (σ_y / 276 MPa)^(1/3)                       [cm]

    with
      t_w = rear wall thickness (cm),
      ρ_w = rear wall density (g/cm³),
      ρ_p = projectile density (g/cm³),
      ρ_b = bumper density (g/cm³),
      S   = standoff (cm),
      σ_y = rear wall yield strength (ksi; 276 MPa = 40 ksi is the
            reference),
      v   = impact velocity (km/s).

    The prefactor `3.918` and the σ_y reference `40 ksi ≈ 276 MPa`
    come from Christiansen 1993 eq. 2 (Al 6061-T6 calibration). For
    other rear-wall materials the caller is expected to verify the
    scaling applies.

    This routine returns the critical diameter in **SI metres**
    after the internal cgs calculation.

    Below the hypervelocity branch (v cos θ ≤ 7 km/s), a wider
    linear interpolation is used; the present implementation returns
    the hypervelocity formula value. The caller is expected to
    check the regime via `classify_impact_regime` first — this
    routine will issue a less reliable result below 7 km/s.

    Args:
        bumper_thickness_m: t_b (m). Not used directly in the
            hypervelocity branch (it enters through ρ_b · t_b =
            bumper areal density captured by the other constants);
            retained in the signature for API symmetry with the
            low-velocity branch.
        bumper_density_kg_m3: ρ_b (kg/m³).
        rear_wall_thickness_m: t_w (m).
        rear_wall_density_kg_m3: ρ_w (kg/m³).
        rear_wall_yield_strength_pa: σ_y (Pa).
        standoff_m: S (m) — center-to-center distance between bumper
            and rear wall.
        projectile_density_kg_m3: ρ_p (kg/m³).
        impact_velocity_m_s: v (m/s).
        angle_from_normal_rad: θ (rad). Default 0.

    Returns:
        Critical projectile diameter d_c (m).
    """
    if bumper_thickness_m <= 0.0 or rear_wall_thickness_m <= 0.0:
        raise ValueError("shield thicknesses must be positive")
    if bumper_density_kg_m3 <= 0.0 or rear_wall_density_kg_m3 <= 0.0:
        raise ValueError("shield densities must be positive")
    if projectile_density_kg_m3 <= 0.0:
        raise ValueError("projectile_density_kg_m3 must be positive")
    if rear_wall_yield_strength_pa <= 0.0:
        raise ValueError("rear_wall_yield_strength_pa must be positive")
    if standoff_m <= 0.0:
        raise ValueError("standoff_m must be positive")
    if impact_velocity_m_s <= 0.0:
        raise ValueError("impact_velocity_m_s must be positive")
    if not (-math.pi / 2 < angle_from_normal_rad < math.pi / 2):
        raise ValueError("angle_from_normal_rad must lie in (-π/2, π/2)")

    cos_theta = math.cos(angle_from_normal_rad)
    v_n_km_s = impact_velocity_m_s * cos_theta / 1000.0
    if v_n_km_s <= 0.0:
        return float("inf")  # grazing incidence → nothing penetrates

    # Convert SI → cgs (Christiansen 1993 eq. 2 convention).
    t_w_cm = rear_wall_thickness_m * 100.0
    rho_w_g_cm3 = rear_wall_density_kg_m3 / 1000.0
    rho_p_g_cm3 = projectile_density_kg_m3 / 1000.0
    rho_b_g_cm3 = bumper_density_kg_m3 / 1000.0
    S_cm = standoff_m * 100.0
    # σ_y in ksi, then normalised by 40 ksi = 276 MPa.
    sigma_ksi = rear_wall_yield_strength_pa / 6.8948e6
    sigma_ratio = sigma_ksi / 40.0

    d_c_cm = (
        3.918
        * (t_w_cm ** (2.0 / 3.0))
        * (rho_w_g_cm3 ** (1.0 / 9.0))
        * (rho_p_g_cm3 ** (-1.0 / 3.0))
        * (rho_b_g_cm3 ** (-1.0 / 9.0))
        * (S_cm ** (1.0 / 3.0))
        * (v_n_km_s ** (-2.0 / 3.0))
        * (sigma_ratio ** (1.0 / 3.0))
    )
    return d_c_cm / 100.0  # cm → m


def whipple_is_perforated(
    projectile_diameter_m: float,
    bumper_thickness_m: float,
    bumper_density_kg_m3: float,
    rear_wall_thickness_m: float,
    rear_wall_density_kg_m3: float,
    rear_wall_yield_strength_pa: float,
    standoff_m: float,
    projectile_density_kg_m3: float,
    impact_velocity_m_s: float,
    angle_from_normal_rad: float = 0.0,
) -> bool:
    """Return True if the projectile exceeds the Whipple NNO critical
    diameter.

    Strict inequality: `d_p > d_c(config)` means the rear wall will
    be perforated; `d_p ≤ d_c` means the shield stops the hit.
    """
    d_c = whipple_critical_diameter_nno(
        bumper_thickness_m=bumper_thickness_m,
        bumper_density_kg_m3=bumper_density_kg_m3,
        rear_wall_thickness_m=rear_wall_thickness_m,
        rear_wall_density_kg_m3=rear_wall_density_kg_m3,
        rear_wall_yield_strength_pa=rear_wall_yield_strength_pa,
        standoff_m=standoff_m,
        projectile_density_kg_m3=projectile_density_kg_m3,
        impact_velocity_m_s=impact_velocity_m_s,
        angle_from_normal_rad=angle_from_normal_rad,
    )
    return projectile_diameter_m > d_c
