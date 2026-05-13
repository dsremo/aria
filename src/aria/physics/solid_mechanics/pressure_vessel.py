"""Thin-walled pressure vessel closed forms (§4.6 of F1 scope).

For a thin-walled cylinder of inner radius `R` and wall thickness `t`
under internal gauge pressure `p`, with R/t ≥ 10 so that the
through-thickness stress gradient is small, the membrane stresses
are (Timoshenko & Goodier 1970 *Theory of Elasticity* 3rd ed §113,
ISBN 978-0070858053):

    σ_hoop   = p R / t                                  [Pa]   (circumferential)
    σ_axial  = p R / (2 t)                              [Pa]   (longitudinal, capped ends)

Hoop is twice the axial stress — the reason cylindrical pressure
vessels fail with longitudinal splits, not circumferential ones.
The Lamé 1852 solution gives the exact radial distribution for
thick walls; for R/t < 10 the thin-wall expression above
under-predicts peak stress by ~5 % (Timoshenko §113 Fig. 196).

These are the two scalar expressions every F1 test uses as its
closed-form reference when checking the full BVP solver.
"""

from __future__ import annotations


def thin_wall_hoop_stress(
    pressure_pa: float, radius_m: float, wall_thickness_m: float
) -> float:
    """σ_hoop = p R / t [Pa] — thin-wall circumferential stress.

    Valid for R/t ≥ 10 to ~5 % per Timoshenko 1970 §113.

    Args:
        pressure_pa: internal gauge pressure (Pa). Positive.
        radius_m: inner radius (m). Positive.
        wall_thickness_m: wall thickness (m). Positive.

    Returns:
        Hoop stress in Pa.
    """
    _check(pressure_pa, radius_m, wall_thickness_m)
    return pressure_pa * radius_m / wall_thickness_m


def thin_wall_axial_stress(
    pressure_pa: float, radius_m: float, wall_thickness_m: float
) -> float:
    """σ_axial = p R / (2 t) [Pa] — thin-wall longitudinal stress.

    Timoshenko 1970 §113 eq. (q). Exactly half the hoop stress for
    the same vessel geometry — a canonical engineering mnemonic.
    """
    _check(pressure_pa, radius_m, wall_thickness_m)
    return pressure_pa * radius_m / (2.0 * wall_thickness_m)


def _check(p: float, r: float, t: float) -> None:
    if p < 0.0:
        raise ValueError("pressure_pa must be non-negative")
    if r <= 0.0:
        raise ValueError("radius_m must be positive")
    if t <= 0.0:
        raise ValueError("wall_thickness_m must be positive")
