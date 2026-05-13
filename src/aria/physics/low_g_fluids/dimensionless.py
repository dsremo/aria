"""Dimensionless-number regime detection (§4.1 of H2 scope).

References: Myshkis et al. 1987 *Low-Gravity Fluid Mechanics* (Springer,
ISBN 978-3642708329); Bird, Stewart & Lightfoot 2007 *Transport
Phenomena* 2nd ed; Pearson 1958 *J Fluid Mech* 4 489.
"""

from __future__ import annotations

import math


def bond_number(
    density_kg_m3: float,
    gravity_m_s2: float,
    length_m: float,
    surface_tension_n_m: float,
) -> float:
    """Bo = ρ g L² / σ                                         [–].

    Gravity to surface-tension ratio. Bo ≫ 1 → gravity dominates,
    Bo ≪ 1 → capillary dominates (Myshkis 1987 §1).
    """
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if gravity_m_s2 < 0.0:
        raise ValueError("gravity_m_s2 must be non-negative")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    return density_kg_m3 * gravity_m_s2 * length_m * length_m / surface_tension_n_m


def weber_number(
    density_kg_m3: float,
    velocity_m_s: float,
    length_m: float,
    surface_tension_n_m: float,
) -> float:
    """We = ρ U² L / σ                                         [–].

    Inertial vs surface-tension force; breakup threshold We_crit ≈ 12
    for secondary drop breakup (Pilch & Erdman 1987
    *Int J Multiphase Flow* 13 741).
    """
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    return (
        density_kg_m3
        * velocity_m_s * velocity_m_s
        * length_m
        / surface_tension_n_m
    )


def capillary_number(
    dynamic_viscosity_pa_s: float,
    velocity_m_s: float,
    surface_tension_n_m: float,
) -> float:
    """Ca = μ U / σ                                            [–]."""
    if dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("dynamic_viscosity_pa_s must be positive")
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    return dynamic_viscosity_pa_s * abs(velocity_m_s) / surface_tension_n_m


def ohnesorge_number(
    dynamic_viscosity_pa_s: float,
    density_kg_m3: float,
    surface_tension_n_m: float,
    length_m: float,
) -> float:
    """Oh = μ / √(ρ σ L)                                       [–].

    Ratio of viscous to √(inertia · surface-tension). Oh < 0.1 →
    inviscid capillary flow; Oh > 1 → viscous-dominated
    (Ohnesorge 1936 *Z Angew Math Mech* 16 355).
    """
    if dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("dynamic_viscosity_pa_s must be positive")
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    return dynamic_viscosity_pa_s / math.sqrt(
        density_kg_m3 * surface_tension_n_m * length_m
    )


def marangoni_number(
    dsigma_dt_n_m_k: float,
    delta_t_k: float,
    length_m: float,
    dynamic_viscosity_pa_s: float,
    thermal_diffusivity_m2_s: float,
) -> float:
    """Ma = |dσ/dT| ΔT L / (μ α)                               [–].

    Critical Marangoni-Bénard onset at Ma_c ≈ 80 (Pearson 1958
    *J Fluid Mech* 4 489).
    """
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if dynamic_viscosity_pa_s <= 0.0:
        raise ValueError("dynamic_viscosity_pa_s must be positive")
    if thermal_diffusivity_m2_s <= 0.0:
        raise ValueError("thermal_diffusivity_m2_s must be positive")
    return (
        abs(dsigma_dt_n_m_k)
        * abs(delta_t_k)
        * length_m
        / (dynamic_viscosity_pa_s * thermal_diffusivity_m2_s)
    )
