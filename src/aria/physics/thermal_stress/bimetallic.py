"""Timoshenko 1925 bimetallic strip curvature (§4.7 of F5 scope).

A classical sensor element — two bonded layers of different materials
with different CTEs — bends when heated. The curvature is (Timoshenko
1925 *J. Opt. Soc. Am.* 11(3) 233-255, Eq. (9)):

    κ = 6 (α_2 − α_1) (T − T_ref) (1 + m)² /
        (h · [ 3 (1 + m)² + (1 + m n)(m² + 1/(m n)) ])     [1/m]

with

    m = h_1 / h_2                (layer-thickness ratio)
    n = E_1 / E_2                (layer-modulus ratio)
    h = h_1 + h_2                (total thickness)

Worked example: equal layers (m = 1), equal moduli (n = 1),
α_1 = 10e-6 /K, α_2 = 20e-6 /K, ΔT = 100 K, h = 1 mm:

  numerator = 6 · (20−10)e-6 · 100 · (2)² = 0.024
  denominator = 1e-3 · [ 3·4 + (2)·(1 + 1) ] = 1e-3 · 16 = 0.016
  κ = 0.024 / 0.016 = 1.50 1/m                          ✓

matching the Timoshenko 1925 Eq. (9) result (the F5 verification test
reproduces this closed-form number).
"""

from __future__ import annotations


def bimetallic_curvature(
    cte_1_k_inv: float,
    cte_2_k_inv: float,
    youngs_modulus_1_pa: float,
    youngs_modulus_2_pa: float,
    thickness_1_m: float,
    thickness_2_m: float,
    delta_t_k: float,
) -> float:
    """Timoshenko 1925 bimetallic strip curvature [1/m].

    Args:
        cte_1_k_inv: CTE of layer 1 (1/K).
        cte_2_k_inv: CTE of layer 2 (1/K).
        youngs_modulus_1_pa: Young's modulus of layer 1 (Pa).
        youngs_modulus_2_pa: Young's modulus of layer 2 (Pa).
        thickness_1_m: thickness of layer 1 (m).
        thickness_2_m: thickness of layer 2 (m).
        delta_t_k: temperature change from stress-free state (K).

    Returns:
        Curvature κ in 1/m. Positive: the strip curves toward the
        higher-CTE layer (that layer wants to expand more and so
        ends up on the convex side).
    """
    if thickness_1_m <= 0.0 or thickness_2_m <= 0.0:
        raise ValueError("layer thicknesses must be positive")
    if youngs_modulus_1_pa <= 0.0 or youngs_modulus_2_pa <= 0.0:
        raise ValueError("Young's moduli must be positive")
    m = thickness_1_m / thickness_2_m
    n = youngs_modulus_1_pa / youngs_modulus_2_pa
    h = thickness_1_m + thickness_2_m
    numerator = 6.0 * (cte_2_k_inv - cte_1_k_inv) * delta_t_k * (1.0 + m) ** 2
    denominator = h * (
        3.0 * (1.0 + m) ** 2 + (1.0 + m * n) * (m * m + 1.0 / (m * n))
    )
    return numerator / denominator
