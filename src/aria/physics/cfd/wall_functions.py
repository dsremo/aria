"""Wall functions, Blasius boundary layer, CFL, and habitat-turnover
primitives (§4.7, §4.9 of H1 scope).

References:
  - Pope 2000 *Turbulent Flows* §7.1 eq. 7.43 (log-law).
  - Schlichting & Gersten 2017 *Boundary-Layer Theory* 9th ed §6.2
    (Blasius).
  - Hirsch 2007 *Numerical Computation of Internal and External
    Flows* 2nd ed §11.6 (CFL bound).
  - Son, Zhang, Lu 2015 SAE 2015-01-2443 (ISS US-Lab cabin turnover).
"""

from __future__ import annotations

import math


# Log-law constants (Pope 2000 §7.1 eq. 7.43; von Kármán 1930).
VON_KARMAN_KAPPA: float = 0.41
LOG_LAW_B: float = 5.2

# Explicit-scheme CFL bound (Hirsch 2007 §11.6).
CFL_EXPLICIT_LIMIT: float = 1.0


def law_of_the_wall_u_plus(y_plus: float) -> float:
    """Universal velocity profile u⁺(y⁺).

    u⁺ = y⁺                          (viscous sublayer, y⁺ < 5)
    u⁺ = (1/κ) ln y⁺ + B             (log layer, y⁺ > 30)
    Linear interpolation between 5 and 30 (a handbook bridge — more
    accurate blending functions exist in Reichardt 1951 *ZAMM* 31
    208 but are out of scope for a primitive library).
    """
    if y_plus < 0.0:
        raise ValueError("y_plus must be non-negative")
    if y_plus < 5.0:
        return y_plus
    if y_plus > 30.0:
        return math.log(y_plus) / VON_KARMAN_KAPPA + LOG_LAW_B
    # Linear bridge on [5, 30] between the two canonical branches.
    u_lo = 5.0
    u_hi = math.log(30.0) / VON_KARMAN_KAPPA + LOG_LAW_B
    frac = (y_plus - 5.0) / (30.0 - 5.0)
    return u_lo + frac * (u_hi - u_lo)


def friction_velocity(wall_shear_stress_pa: float, density_kg_m3: float) -> float:
    """u_τ = √(τ_w / ρ)                                        [m/s]."""
    if wall_shear_stress_pa < 0.0:
        raise ValueError("wall_shear_stress_pa must be non-negative")
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    return math.sqrt(wall_shear_stress_pa / density_kg_m3)


def blasius_skin_friction_coefficient(reynolds_x: float) -> float:
    """Local skin-friction coefficient on a laminar flat plate.

    C_f(x) = 0.664 / √Re_x     (Schlichting & Gersten 2017 §6.2)
    """
    if reynolds_x <= 0.0:
        raise ValueError("reynolds_x must be positive")
    return 0.664 / math.sqrt(reynolds_x)


def blasius_displacement_thickness_over_x(reynolds_x: float) -> float:
    """δ*/x = 1.7208 / √Re_x (Blasius; Schlichting & Gersten 2017
    §6.2 Table 6.1)."""
    if reynolds_x <= 0.0:
        raise ValueError("reynolds_x must be positive")
    return 1.7208 / math.sqrt(reynolds_x)


def cfl_time_step_bound(
    cell_size_m: float,
    velocity_m_s: float,
    speed_of_sound_m_s: float,
    cfl: float = CFL_EXPLICIT_LIMIT,
) -> float:
    """Explicit compressible CFL bound
    Δt ≤ CFL · Δx / (|u| + c)                                 [s]
    (Hirsch 2007 §11.6 eq. 11.19)."""
    if cell_size_m <= 0.0:
        raise ValueError("cell_size_m must be positive")
    if speed_of_sound_m_s <= 0.0:
        raise ValueError("speed_of_sound_m_s must be positive")
    if cfl <= 0.0:
        raise ValueError("cfl must be positive")
    return cfl * cell_size_m / (abs(velocity_m_s) + speed_of_sound_m_s)


def iss_cabin_turnover_time_s(
    volume_m3: float, volumetric_flow_m3_s: float
) -> float:
    """Cabin turnover time τ = V / Q̇                          [s].

    Canonical ISS US-Lab value from Son et al. 2015 SAE 2015-01-2443:
    V ≈ 76 m³, Q̇ = 4.5 m³/min ≈ 0.075 m³/s → τ ≈ 1013 s ≈ 17 min.
    This contradicts the earlier "1 turnover / hour" ISS rule of
    thumb but matches the Son et al. CFD result — the 1 hr figure
    applies to a larger envelope volume (multiple modules).
    """
    if volume_m3 <= 0.0:
        raise ValueError("volume_m3 must be positive")
    if volumetric_flow_m3_s <= 0.0:
        raise ValueError("volumetric_flow_m3_s must be positive")
    return volume_m3 / volumetric_flow_m3_s
