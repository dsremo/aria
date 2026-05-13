"""Dimensionless numbers for habitat CFD (§4.8 of H1 scope and §4 of H3).

Implements Reynolds, Mach, Prandtl, Grashof, Rayleigh, and the
Churchill-Chu vertical-plate Nusselt correlation.

References:
  - Kundu et al. 2016 *Fluid Mechanics* 6th ed §10 (ISBN 978-0124059351).
  - Incropera et al. 2011 *Fundamentals of Heat and Mass Transfer* 7th
    ed §9.6 (ISBN 978-0470501979).
  - Churchill, S.W., Chu, H.H.S. (1975). "Correlating equations for
    laminar and turbulent free convection from a vertical plate".
    *Int J Heat Mass Transfer* 18 1323. DOI 10.1016/0017-9310(75)90222-7.
"""

from __future__ import annotations

import math


def reynolds_number(
    density_kg_m3: float,
    velocity_m_s: float,
    length_m: float,
    dynamic_viscosity_pa_s: float,
) -> float:
    """Re = ρ U L / μ                                          [–]."""
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("dynamic_viscosity_pa_s must be positive")
    return density_kg_m3 * abs(velocity_m_s) * length_m / dynamic_viscosity_pa_s


def mach_number(velocity_m_s: float, speed_of_sound_m_s: float) -> float:
    """M = |u| / c                                             [–]."""
    if speed_of_sound_m_s <= 0.0:
        raise ValueError("speed_of_sound_m_s must be positive")
    return abs(velocity_m_s) / speed_of_sound_m_s


def prandtl_number(
    specific_heat_j_kg_k: float,
    dynamic_viscosity_pa_s: float,
    thermal_conductivity_w_m_k: float,
) -> float:
    """Pr = μ c_p / k                                          [–].

    Dry air at 293 K: 1007·1.82e-5/0.0257 ≈ 0.71 (Incropera Table A.4).
    """
    if specific_heat_j_kg_k <= 0.0:
        raise ValueError("specific_heat_j_kg_k must be positive")
    if dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("dynamic_viscosity_pa_s must be positive")
    if thermal_conductivity_w_m_k <= 0.0:
        raise ValueError("thermal_conductivity_w_m_k must be positive")
    return (
        specific_heat_j_kg_k
        * dynamic_viscosity_pa_s
        / thermal_conductivity_w_m_k
    )


def grashof_number(
    gravity_m_s2: float,
    thermal_expansion_1_k: float,
    delta_t_k: float,
    length_m: float,
    kinematic_viscosity_m2_s: float,
) -> float:
    """Gr = g β ΔT L³ / ν²                                     [–].

    Incropera 2011 eq. 9.12. Buoyancy / viscous force ratio for
    natural convection. Uses the magnitude of ΔT so the result is
    non-negative irrespective of heating direction.
    """
    if gravity_m_s2 < 0.0:
        raise ValueError("gravity_m_s2 must be non-negative")
    if thermal_expansion_1_k <= 0.0:
        raise ValueError("thermal_expansion_1_k must be positive")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if kinematic_viscosity_m2_s <= 0.0:
        raise ValueError("kinematic_viscosity_m2_s must be positive")
    return (
        gravity_m_s2
        * thermal_expansion_1_k
        * abs(delta_t_k)
        * length_m**3
        / (kinematic_viscosity_m2_s * kinematic_viscosity_m2_s)
    )


def rayleigh_number(grashof: float, prandtl: float) -> float:
    """Ra = Gr · Pr                                            [–]."""
    if grashof < 0.0 or prandtl <= 0.0:
        raise ValueError("grashof must be non-negative, prandtl must be positive")
    return grashof * prandtl


def nusselt_churchill_chu_vertical_plate(rayleigh: float, prandtl: float) -> float:
    """Churchill-Chu 1975 correlation for free convection on a
    vertical isothermal plate — valid for 10⁻¹ ≤ Ra ≤ 10¹² and any Pr.

    Nu = { 0.825 + 0.387 · Ra^{1/6} /
           [1 + (0.492/Pr)^{9/16}]^{8/27} }²

    Incropera 2011 eq. 9.26. Canonical benchmark:
    Ra = 10⁹, Pr = 0.7 → Nu ≈ 130.
    """
    if rayleigh < 0.0 or prandtl <= 0.0:
        raise ValueError("rayleigh non-negative, prandtl positive")
    pr_term = (0.492 / prandtl) ** (9.0 / 16.0)
    denom = (1.0 + pr_term) ** (8.0 / 27.0)
    bracket = 0.825 + 0.387 * rayleigh ** (1.0 / 6.0) / denom
    return bracket * bracket
