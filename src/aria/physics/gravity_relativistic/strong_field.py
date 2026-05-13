"""R42 §2.2 — strong-field general-relativistic gravity.

Closes the entire black-hole gap: ISCO (Schwarzschild + Kerr,
Bardeen 1972 closed form), photon sphere, Roche limit, the *full*
gravitational redshift formula `1/√(1 - r_s/r)` (the existing
`grav_redshift.py` truncates to weak-field), and Hawking T_H.

Why a separate module
---------------------

`grav_redshift.py` is correct only when r ≫ r_s.  Inside ~10 r_s the
truncation introduces multi-percent errors that change navigation
budgets.  Strong-field formulas are closed-form; no integrator
needed.  The module is pure (no global state) so it composes cleanly
with the existing PN tidal-tensor code.

References:
    Misner-Thorne-Wheeler 1973 *Gravitation* §31.5;
    Bardeen-Press-Teukolsky 1972 ApJ 178, 347;
    Hawking 1974 Nature 248, 30 (T_H);
    Roche 1849 (Roche limit, fluid form per Wahl 2017 ApJ 851, L15).
"""

from __future__ import annotations

import math


# Universal constants (CODATA 2018, Tiesinga et al. 2021).
G = 6.674_30e-11               # N·m²/kg²
C = 2.997_924_58e8             # m/s, exact
HBAR = 1.054_571_817e-34       # J·s
KB = 1.380_649e-23             # J/K, exact (SI 2019)
M_SUN = 1.988_47e30            # kg (IAU 2015 nominal)


def schwarzschild_radius_m(M_kg: float) -> float:
    """r_s = 2 G M / c² — event horizon of a non-spinning BH."""
    return 2.0 * G * M_kg / (C ** 2)


def isco_schwarzschild_m(M_kg: float) -> float:
    """ISCO of a Schwarzschild BH = 6 G M / c² = 3 r_s.  MTW Eq 25.16."""
    return 6.0 * G * M_kg / (C ** 2)


def isco_kerr_m(M_kg: float, a_dimensionless: float, prograde: bool = True) -> float:
    """Bardeen-Press-Teukolsky 1972 closed-form ISCO for a Kerr BH.

    `a_dimensionless` ∈ [0, 1] is the dimensionless spin parameter
    a* = J c / (G M²).  Use `prograde=True` for orbits aligned with
    the spin (smaller r_isco) and False for retrograde.
    """
    if not (0.0 <= a_dimensionless <= 1.0):
        raise ValueError("Kerr a* must be in [0, 1]")
    a = a_dimensionless
    Z1 = 1.0 + (1.0 - a ** 2) ** (1.0 / 3.0) * (
        (1.0 + a) ** (1.0 / 3.0) + (1.0 - a) ** (1.0 / 3.0)
    )
    Z2 = math.sqrt(3.0 * a ** 2 + Z1 ** 2)
    if prograde:
        r_isco = 3.0 + Z2 - math.sqrt((3.0 - Z1) * (3.0 + Z1 + 2.0 * Z2))
    else:
        r_isco = 3.0 + Z2 + math.sqrt((3.0 - Z1) * (3.0 + Z1 + 2.0 * Z2))
    # In units of GM/c²; convert to metres.
    return r_isco * G * M_kg / (C ** 2)


def photon_sphere_m(M_kg: float) -> float:
    """Photon sphere of Schwarzschild = 3 G M / c² = 1.5 r_s.  MTW §25.4."""
    return 3.0 * G * M_kg / (C ** 2)


def hawking_temperature_k(M_kg: float) -> float:
    """T_H = ℏ c³ / (8 π G M k_B) — Hawking 1974."""
    if M_kg <= 0.0:
        return 0.0
    return HBAR * C ** 3 / (8.0 * math.pi * G * M_kg * KB)


def roche_limit_fluid_m(
    M_primary_kg: float, R_secondary_m: float, rho_secondary_kg_m3: float,
    rho_primary_kg_m3: float = 0.0,
) -> float:
    """Fluid Roche limit (Wahl 2017 generalisation; reduces to the
    classical 1849 result when ρ_primary = ρ_secondary).

    Returns the orbital separation at which a fluid satellite of the
    given density is torn apart by tidal stress.  ``rho_primary`` is
    optional — ARIA uses M_primary directly when known (preferred); a
    nonzero ``rho_primary`` enables the legacy density-ratio form.
    """
    if rho_primary_kg_m3 > 0.0:
        return R_secondary_m * (
            2.0 * rho_primary_kg_m3 / rho_secondary_kg_m3
        ) ** (1.0 / 3.0)
    if rho_secondary_kg_m3 <= 0.0:
        raise ValueError("rho_secondary must be > 0")
    # d_R = R_s · (2 M_p / m_s)^(1/3),  m_s = (4/3)π R_s³ ρ_s.
    m_s = (4.0 / 3.0) * math.pi * R_secondary_m ** 3 * rho_secondary_kg_m3
    return R_secondary_m * (2.0 * M_primary_kg / m_s) ** (1.0 / 3.0)


def roche_limit_rigid_m(
    M_primary_kg: float, R_secondary_m: float, rho_secondary_kg_m3: float,
) -> float:
    """Rigid (cohesive) Roche limit ≈ 1.26 · fluid result.  Smaller
    cohesive bodies survive closer in.  Wahl 2017 §3."""
    return roche_limit_fluid_m(
        M_primary_kg, R_secondary_m, rho_secondary_kg_m3,
    ) * 1.26


def grav_redshift_full(M_kg: float, r_m: float) -> float:
    """Full Schwarzschild redshift factor 1/√(1 − r_s/r).

    Returns NaN inside the horizon (r ≤ r_s) where the formula is
    invalid; Python returns a Python float `nan` so the caller can
    branch on `math.isnan(z)`.
    """
    rs = schwarzschild_radius_m(M_kg)
    if r_m <= rs:
        return float("nan")
    return 1.0 / math.sqrt(1.0 - rs / r_m)


def kerr_horizon_m(M_kg: float, a_dimensionless: float) -> float:
    """Outer event horizon of a Kerr BH:  r_+ = (G M / c²) · (1 + √(1 − a*²))."""
    if not (0.0 <= a_dimensionless <= 1.0):
        raise ValueError("Kerr a* must be in [0, 1]")
    return (G * M_kg / C ** 2) * (
        1.0 + math.sqrt(1.0 - a_dimensionless ** 2)
    )


def kerr_ergosphere_m(
    M_kg: float, a_dimensionless: float, theta: float = math.pi / 2,
) -> float:
    """Ergosphere outer boundary (Boyer-Lindquist) at polar angle θ.

    r_e = (G M / c²) · (1 + √(1 − a*² cos²θ)).  At θ = π/2 (equator)
    matches the static limit; at θ = 0/π collapses to r_+.
    """
    if not (0.0 <= a_dimensionless <= 1.0):
        raise ValueError("Kerr a* must be in [0, 1]")
    return (G * M_kg / C ** 2) * (
        1.0 + math.sqrt(1.0 - (a_dimensionless * math.cos(theta)) ** 2)
    )
