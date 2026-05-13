"""Linear-elastic fracture mechanics: K_I and critical crack length
(§4.6 of F2 scope).

Irwin's stress-intensity factor for a tensile crack of length `a` in
an infinite plate under remote uniform stress `σ` (Irwin 1957 J Appl
Mech 24 361; Anderson 2017 *Fracture Mechanics: Fundamentals and
Applications* 4th ed Ch. 2, ISBN 978-1498728133):

    K_I = σ √(π a) · Y(a/W, geometry)                    [Pa·m^½]

where Y is a dimensionless geometry factor that depends on the
crack and specimen shape. Two important closed-form cases:

  - **Center crack of length 2a in an infinite plate** (Anderson
    2017 Table 2.4): Y = 1 (the canonical "infinite plate" result).
        K_I = σ √(π a)

  - **Single-edge crack of length a in a semi-infinite plate**
    (Anderson 2017 Table 2.4 row 2): Y = 1.12 (the free-surface
    correction for an edge crack).
        K_I = 1.12 σ √(π a)

Brittle fracture occurs when `K_I` reaches the material's plane-
strain fracture toughness `K_Ic`. Solving for the critical crack
length at given stress:

    a_crit = (1 / π) · (K_Ic / (Y σ))²                   [m]

For Ti-6Al-4V (K_Ic = 55 MPa·m^½, MMPDS-17 Table 5.3.1) under a
hoop stress of 400 MPa with Y = 1.12:

    a_crit = (1/π) · (55 / (1.12 · 400))² = (1/π) · 0.01506
           ≈ 0.0048 m ≈ 4.8 mm

i.e. any crack longer than ~5 mm is unstable. This is the canonical
F2 §9 worked example.
"""

from __future__ import annotations

import math


def stress_intensity_center_crack(
    stress_pa: float, crack_half_length_m: float
) -> float:
    """K_I for a center crack of half-length `a` in an infinite plate.

    K_I = σ √(π a)                                        [Pa·m^½]

    Args:
        stress_pa: remote tensile stress (Pa).
        crack_half_length_m: half-length of the through-crack (m).

    Returns:
        K_I in Pa·m^½. Returns 0 for zero stress or zero crack length.
    """
    if stress_pa < 0.0:
        raise ValueError("stress_pa must be non-negative")
    if crack_half_length_m < 0.0:
        raise ValueError("crack_half_length_m must be non-negative")
    return stress_pa * math.sqrt(math.pi * crack_half_length_m)


def stress_intensity_edge_crack(
    stress_pa: float, crack_length_m: float, geometry_factor: float = 1.12
) -> float:
    """K_I for a single-edge crack of length `a`.

    K_I = Y σ √(π a)                                      [Pa·m^½]

    The default `Y = 1.12` is the canonical free-surface correction
    for a short edge crack in a semi-infinite plate (Anderson 2017
    Table 2.4 row 2). For other geometries (compact-tension specimens,
    surface flaws in cylinders, etc.) the caller should pass the
    appropriate Y from a handbook (Tada-Paris-Irwin 2000).

    Args:
        stress_pa: remote tensile stress (Pa).
        crack_length_m: edge-crack length (m).
        geometry_factor: dimensionless Y. Default 1.12.

    Returns:
        K_I in Pa·m^½.
    """
    if geometry_factor <= 0.0:
        raise ValueError("geometry_factor must be positive")
    # stress_intensity_center_crack expects HALF-length; for an edge crack
    # of full length a, the equivalent center-crack half-length is a/2.
    return geometry_factor * stress_intensity_center_crack(stress_pa, crack_length_m / 2.0)


def critical_crack_length(
    fracture_toughness_pa_sqrt_m: float,
    applied_stress_pa: float,
    geometry_factor: float = 1.12,
) -> float:
    """Critical crack length at which K_I reaches K_Ic.

    a_crit = (1/π) · (K_Ic / (Y σ))²                     [m]

    Args:
        fracture_toughness_pa_sqrt_m: K_Ic (Pa·m^½).
        applied_stress_pa: σ (Pa). Must be positive.
        geometry_factor: Y. Default 1.12.

    Returns:
        a_crit in m.
    """
    if fracture_toughness_pa_sqrt_m <= 0.0:
        raise ValueError("fracture_toughness_pa_sqrt_m must be positive")
    if applied_stress_pa <= 0.0:
        raise ValueError("applied_stress_pa must be positive")
    if geometry_factor <= 0.0:
        raise ValueError("geometry_factor must be positive")
    return (1.0 / math.pi) * (
        fracture_toughness_pa_sqrt_m / (geometry_factor * applied_stress_pa)
    ) ** 2
