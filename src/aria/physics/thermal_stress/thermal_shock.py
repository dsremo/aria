"""Kingery 1955 thermal shock figure of merit (§4.5 of F5 scope).

A brittle plate subjected to an instantaneous surface ΔT sustains a
thermal shock crack when the induced thermal stress exceeds the
fracture strength. The threshold (Kingery 1955 *J. Am. Ceram. Soc.*
38(1) 3-15) is

    ΔT_crit = σ_f (1 − ν) / (E α)                        [K]

Derivation: the plane-stress thermal stress for a uniform ΔT is
`σ^θ = −E α ΔT / (1−ν)` (from `constrained_stress.py`); setting
`|σ^θ| = σ_f` and solving for ΔT yields the figure of merit above.

This is an order-of-magnitude criterion only. The true thermal-shock
response depends on heat-transfer kinetics (Biot number) and the
stress-wave propagation through the thickness; a Biot-number-based
correction (Kingery 1955 Table II) multiplies ΔT_crit by a factor
~0.3 at low Biot and ~1.0 at high Biot. F5 reports the plane-stress
asymptote and leaves the dynamic correction to the caller.

Worked example: Ti-6Al-4V radiator with a 250 K instantaneous
shutdown cooldown:

  σ_f = 895 MPa (UTS, MMPDS-17 §5.3.0.3)
  E = 113.8 GPa
  α = 8.6e-6 /K
  ν = 0.342
  ΔT_crit = 895e6 · (1 − 0.342) / (113.8e9 · 8.6e-6)
          = 895e6 · 0.658 / 978.7
          = 601 K

Applied 250 K → margin factor 601/250 ≈ 2.4, i.e. the radiator is
safe but not over-designed. Confirms the radiator sizing closure
called out in P0-6 of `PHYSICS_COMPLETENESS_PLAN.md`.
"""

from __future__ import annotations


def thermal_shock_delta_t_crit(
    fracture_strength_pa: float,
    youngs_modulus_pa: float,
    cte_k_inv: float,
    poissons_ratio: float,
) -> float:
    """Kingery critical ΔT for thermal-shock crack initiation [K].

    ΔT_crit = σ_f (1 − ν) / (E α)

    Args:
        fracture_strength_pa: σ_f, the brittle fracture strength
            (Pa). For ductile metals this is typically the UTS.
        youngs_modulus_pa: E (Pa).
        cte_k_inv: α (1/K).
        poissons_ratio: ν (0 ≤ ν < 0.5).

    Returns:
        Critical ΔT in K (positive).
    """
    if fracture_strength_pa <= 0.0:
        raise ValueError("fracture_strength_pa must be positive")
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    if cte_k_inv <= 0.0:
        raise ValueError(
            "cte_k_inv must be positive for this formula; negative-CTE "
            "materials (carbon fiber fiber-axis) do not see thermal "
            "shock in the same way"
        )
    if not (0.0 <= poissons_ratio < 0.5):
        raise ValueError("poissons_ratio must satisfy 0 <= ν < 0.5")
    return fracture_strength_pa * (1.0 - poissons_ratio) / (youngs_modulus_pa * cte_k_inv)


def thermal_shock_margin(
    fracture_strength_pa: float,
    youngs_modulus_pa: float,
    cte_k_inv: float,
    poissons_ratio: float,
    delta_t_applied_k: float,
) -> float:
    """Thermal-shock safety factor `ΔT_crit / ΔT_applied` [dimensionless].

    Values > 1 indicate the applied thermal shock is below the
    Kingery threshold; a margin of 1.5 is commonly required for
    ceramic components and 2.0 for spacecraft structural metals.

    Raises:
        ValueError: if ΔT_applied is zero or negative (no shock).
    """
    if delta_t_applied_k <= 0.0:
        raise ValueError(
            "delta_t_applied_k must be positive; use the absolute "
            "magnitude of the shock"
        )
    dt_crit = thermal_shock_delta_t_crit(
        fracture_strength_pa, youngs_modulus_pa, cte_k_inv, poissons_ratio
    )
    return dt_crit / delta_t_applied_k
