"""Hertzian elastic contact (§4.1 of F4 scope).

Two elastic spheres pressed together with force `F` produce a
quasi-static circular contact area. Johnson 1985 *Contact Mechanics*
§3 (ISBN 978-0521347969) derives the closed-form relations between
force, indentation, contact radius, and maximum pressure:

    F  = (4/3) E* √R · δ^(3/2)                            [N]
    a  = √(R δ)                                           contact radius [m]
    p_0 = (3 F) / (2 π a²)                                peak pressure [Pa]
       = (1/π) (6 F E*² / R²)^(1/3)                       (eliminating a, δ)

Reduced modulus:
    1/E* = (1 − ν_1²)/E_1 + (1 − ν_2²)/E_2                [1/Pa]

Reduced radius:
    1/R  = 1/R_1 + 1/R_2                                  [1/m]

These relations are the canonical starting point for any low-velocity
(quasi-static) impact calculation. They are valid when (i) both
bodies remain elastic (`p_0 < 1.6 σ_y` is the yield onset), (ii) the
contact zone is small compared to both radii, and (iii) friction is
negligible. For true HVI these conditions are all violated and the
hydrodynamic regime (Hugoniot + EOS) takes over — see `hugoniot.py`.

A quick engineering sanity check: a 1 mm steel ball pressed with
1 N against a steel flat gives `δ ≈ 0.5 μm`, `a ≈ 25 μm`,
`p_0 ≈ 800 MPa`. Crossing the `1.6 σ_y` yield threshold happens
at about `F ≈ 3 N` for the same geometry.
"""

from __future__ import annotations

import math


def reduced_elastic_modulus(
    e_1_pa: float, nu_1: float, e_2_pa: float, nu_2: float
) -> float:
    """Reduced modulus `E*` such that `1/E* = (1−ν₁²)/E₁ + (1−ν₂²)/E₂`.

    Args:
        e_1_pa, e_2_pa: Young's moduli of the two bodies (Pa).
        nu_1, nu_2: Poisson's ratios of the two bodies.

    Returns:
        E* in Pa.
    """
    if e_1_pa <= 0.0 or e_2_pa <= 0.0:
        raise ValueError("Young's moduli must be positive")
    if not (-1.0 < nu_1 < 0.5) or not (-1.0 < nu_2 < 0.5):
        raise ValueError("Poisson's ratios must lie in (-1, 0.5)")
    inv = (1.0 - nu_1 * nu_1) / e_1_pa + (1.0 - nu_2 * nu_2) / e_2_pa
    return 1.0 / inv


def hertzian_contact_force(
    reduced_modulus_pa: float,
    reduced_radius_m: float,
    indentation_m: float,
) -> float:
    """Quasi-static Hertzian contact force.

    F = (4/3) E* √R · δ^(3/2)                             [N]

    Args:
        reduced_modulus_pa: `E*` (Pa).
        reduced_radius_m: `R` (m).
        indentation_m: `δ` (m), must be non-negative.

    Returns:
        Contact force in N.
    """
    if reduced_modulus_pa <= 0.0:
        raise ValueError("reduced_modulus_pa must be positive")
    if reduced_radius_m <= 0.0:
        raise ValueError("reduced_radius_m must be positive")
    if indentation_m < 0.0:
        raise ValueError("indentation_m must be non-negative")
    return (4.0 / 3.0) * reduced_modulus_pa * math.sqrt(reduced_radius_m) * (
        indentation_m ** 1.5
    )


def hertzian_contact_radius(
    reduced_radius_m: float, indentation_m: float
) -> float:
    """Contact-patch radius `a = √(R δ)` [m].

    Only valid in the elastic regime; large δ violates the
    small-contact assumption.
    """
    if reduced_radius_m <= 0.0:
        raise ValueError("reduced_radius_m must be positive")
    if indentation_m < 0.0:
        raise ValueError("indentation_m must be non-negative")
    return math.sqrt(reduced_radius_m * indentation_m)


def hertzian_max_pressure(
    contact_force_n: float,
    reduced_modulus_pa: float,
    reduced_radius_m: float,
) -> float:
    """Maximum (central) pressure under the Hertzian contact patch.

    p_0 = (1/π) · (6 F E*² / R²)^(1/3)                    [Pa]

    Derived by eliminating `a` and `δ` from the F/δ and p_0/a
    relations in Johnson 1985 §3.
    """
    if contact_force_n < 0.0:
        raise ValueError("contact_force_n must be non-negative")
    if reduced_modulus_pa <= 0.0:
        raise ValueError("reduced_modulus_pa must be positive")
    if reduced_radius_m <= 0.0:
        raise ValueError("reduced_radius_m must be positive")
    if contact_force_n == 0.0:
        return 0.0
    return (1.0 / math.pi) * (
        6.0 * contact_force_n * reduced_modulus_pa * reduced_modulus_pa
        / (reduced_radius_m * reduced_radius_m)
    ) ** (1.0 / 3.0)
