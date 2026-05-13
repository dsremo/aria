"""Young-Laplace statics and Jurin capillary rise (§4.2, §4.3 of H2).

Landau & Lifshitz 1987 *Fluid Mechanics* §61 gives the Young-Laplace
pressure jump across a curved interface:

    Δp = σ (1/R₁ + 1/R₂)                                      [Pa]

which for a spherical cap (R₁ = R₂ = R) collapses to Δp = 2σ/R.
Jurin 1718 (Phil Trans 30 739; reproduced in Adamson & Gast 1997
*Physical Chemistry of Surfaces* 6th ed §2.4) derived the equilibrium
liquid column height in a cylindrical tube of radius r, contact angle
θ, immersed in a gravity field g:

    h = 2 σ cos θ / (ρ g r)                                   [m]

by balancing the capillary force 2π r σ cos θ against the weight
ρ g π r² h.

The capillary length ℓ_c = √(σ / (ρ g)) sets the natural crossover
scale between capillary and gravity regimes. Tanks with
characteristic L < ℓ_c behave as capillary-dominated even at
full gravity; in microgravity (g ~ 10⁻⁶ m/s²) ℓ_c is hundreds of
meters, so *every* real tank is capillary-dominated.
"""

from __future__ import annotations

import math

# Handbook rule-of-thumb crossover. Bo ≲ 1 → capillary-dominated
# (Myshkis et al. 1987 §1). The specific threshold of 1 is not sharp;
# practical codes use Bo < 10 as a conservative switch.
BOND_CAPILLARY_THRESHOLD: float = 1.0


def young_laplace_pressure_jump(
    surface_tension_n_m: float,
    radius_of_curvature_1_m: float,
    radius_of_curvature_2_m: float | None = None,
) -> float:
    """Δp = σ (1/R₁ + 1/R₂)                                    [Pa].

    If `R₂` is omitted the interface is assumed spherical
    (R₁ = R₂), so Δp = 2σ/R.
    """
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    if radius_of_curvature_1_m == 0.0:
        raise ValueError("radius_of_curvature_1_m must be nonzero")
    r2 = radius_of_curvature_2_m if radius_of_curvature_2_m is not None else radius_of_curvature_1_m
    if r2 == 0.0:
        raise ValueError("radius_of_curvature_2_m must be nonzero")
    return surface_tension_n_m * (1.0 / radius_of_curvature_1_m + 1.0 / r2)


def capillary_pressure_spherical_cap(
    surface_tension_n_m: float, radius_m: float
) -> float:
    """Δp = 2σ/r                                               [Pa]."""
    return young_laplace_pressure_jump(surface_tension_n_m, radius_m, radius_m)


def jurin_capillary_rise(
    surface_tension_n_m: float,
    contact_angle_rad: float,
    tube_radius_m: float,
    density_kg_m3: float,
    gravity_m_s2: float,
) -> float:
    """Jurin 1718 capillary rise height `h = 2σcosθ/(ρgr)` [m].

    Returns 0 when g = 0 (would be infinite; flag to caller rather
    than raising so regime-detection code can branch cleanly).

    Canonical check: σ = 0.0728 N/m, θ = 0, r = 0.5 mm, water, g =
    9.81 m/s² → h ≈ 29.7 mm (Adamson & Gast 1997 §2.4 Example).
    """
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    if tube_radius_m <= 0.0:
        raise ValueError("tube_radius_m must be positive")
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if gravity_m_s2 < 0.0:
        raise ValueError("gravity_m_s2 must be non-negative")
    if gravity_m_s2 == 0.0:
        return 0.0
    return (
        2.0 * surface_tension_n_m * math.cos(contact_angle_rad)
        / (density_kg_m3 * gravity_m_s2 * tube_radius_m)
    )


def capillary_length(
    surface_tension_n_m: float, density_kg_m3: float, gravity_m_s2: float
) -> float:
    """ℓ_c = √(σ / (ρ g))                                      [m].

    Water at 1 g: ℓ_c ≈ 2.7 mm (handbook value, Adamson & Gast 1997).
    In microgravity ℓ_c diverges as g → 0.
    """
    if surface_tension_n_m <= 0.0:
        raise ValueError("surface_tension_n_m must be positive")
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if gravity_m_s2 <= 0.0:
        raise ValueError("gravity_m_s2 must be positive")
    return math.sqrt(surface_tension_n_m / (density_kg_m3 * gravity_m_s2))


def is_capillary_regime(
    bond_number_value: float,
    threshold: float = BOND_CAPILLARY_THRESHOLD,
) -> bool:
    """Return True iff Bo ≤ threshold (capillary-dominated).

    Defaults to the Myshkis 1987 §1 handbook rule Bo ≤ 1. Callers
    that want a conservative switch should pass threshold = 10.
    """
    if bond_number_value < 0.0:
        raise ValueError("bond_number_value must be non-negative")
    return bond_number_value <= threshold
