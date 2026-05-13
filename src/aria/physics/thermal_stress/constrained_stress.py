"""Closed-form constrained thermal stresses (§4.3 of F5 scope).

Three standard configurations, all derived from the elastic
constitutive law `σ_ij = C_ijkl (ε^total_kl − ε^θ_kl)` with
prescribed zero total strain in the directions of constraint
(Boley & Weiner 1960 §3.1, ISBN 978-0486695792; Timoshenko & Goodier
1970 §148, ISBN 978-0070858053):

  1. **Uniaxial bar, both ends fixed** (1D constraint):

        σ = −E α ΔT                                      [Pa]

     A compressive stress if ΔT > 0.

  2. **Plane-stress plate, edges fixed** (biaxial in-plane constraint):

        σ_x = σ_y = −E α ΔT / (1 − ν)                    [Pa]

     The (1−ν) factor accounts for Poisson contraction: a uniformly
     heated plate tries to expand isotropically, but the constrained
     edges produce an in-plane biaxial stress.

  3. **Fully triaxial constraint** (cubic block with all faces fixed):

        σ_x = σ_y = σ_z = −E α ΔT / (1 − 2ν)             [Pa]

     The (1−2ν) factor reflects the full three-dimensional
     volumetric response.

These are *diagnostic* expressions. The real stress distribution in
a structure with mixed boundary conditions comes from F1 after it
solves the full elasticity BVP using F5's thermal strain as an
eigenstrain input. F5's closed forms exist as quick sanity checks
and as the analytic reference for the verification test suite.
"""

from __future__ import annotations


def uniaxial_constrained_stress(
    youngs_modulus_pa: float,
    cte_k_inv: float,
    delta_t_k: float,
) -> float:
    """Axial stress in a fully restrained 1D bar: `σ = −E α ΔT` [Pa].

    Positive ΔT (heating) produces a negative (compressive) stress
    because the bar is prevented from expanding.

    Args:
        youngs_modulus_pa: Young's modulus E (Pa).
        cte_k_inv: coefficient of thermal expansion α (1/K).
        delta_t_k: temperature change from stress-free state (K).

    Returns:
        Axial stress σ in Pa (signed).
    """
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    return -youngs_modulus_pa * cte_k_inv * delta_t_k


def plane_stress_constrained(
    youngs_modulus_pa: float,
    cte_k_inv: float,
    delta_t_k: float,
    poissons_ratio: float,
) -> float:
    """In-plane biaxial stress for a plane-stress plate with fixed edges.

    σ_x = σ_y = −E α ΔT / (1 − ν)                          [Pa]

    (Timoshenko & Goodier 1970 §150 p. 445.) Heating (ΔT > 0) gives a
    compressive in-plane stress.

    Args:
        youngs_modulus_pa: Young's modulus (Pa).
        cte_k_inv: CTE (1/K).
        delta_t_k: temperature change (K).
        poissons_ratio: ν (dimensionless). Must satisfy 0 ≤ ν < 0.5.

    Returns:
        In-plane biaxial stress σ_x = σ_y (Pa, signed).
    """
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    if not (-1.0 < poissons_ratio < 0.5):
        raise ValueError("poissons_ratio must satisfy -1 < ν < 0.5")
    return -youngs_modulus_pa * cte_k_inv * delta_t_k / (1.0 - poissons_ratio)


def triaxial_constrained_stress(
    youngs_modulus_pa: float,
    cte_k_inv: float,
    delta_t_k: float,
    poissons_ratio: float,
) -> float:
    """Hydrostatic stress for a fully confined (all-faces-fixed) cube.

    σ_x = σ_y = σ_z = −E α ΔT / (1 − 2ν)                   [Pa]

    (Boley & Weiner 1960 §3.1.) For ν → 0.5 (incompressible) the
    stress diverges — a physically correct statement that an
    incompressible body cannot absorb any thermal expansion without
    infinite stress.

    Args:
        youngs_modulus_pa: Young's modulus (Pa).
        cte_k_inv: CTE (1/K).
        delta_t_k: ΔT from reference (K).
        poissons_ratio: ν (must be strictly < 0.5).

    Returns:
        Hydrostatic stress (Pa, signed).
    """
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    if not (-1.0 < poissons_ratio < 0.5):
        raise ValueError("poissons_ratio must satisfy -1 < ν < 0.5")
    return -youngs_modulus_pa * cte_k_inv * delta_t_k / (1.0 - 2.0 * poissons_ratio)
