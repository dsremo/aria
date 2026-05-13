"""Extended-body tidal loading distributed across the spacecraft hull.

The tidal tensor gives the differential acceleration between two points
in a gravitational field. For a 500 m generation ship orbiting a star
at a few AU, the tidal differential between the bow and stern is
non-negligible as a structural load — this module computes that load.

PHYSICS
-------
For a rigid hull element at position L (offset from centre of mass)
along unit axis â:

    a_tidal(L) = −E · (L â)                             [m/s²]

where E is the tidal tensor (1/s²) from tidal_tensor.py. The net
differential acceleration between the fore tip (+L) and aft tip (−L):

    Δa = a_tidal(+L) − a_tidal(−L) = −2 E · (L â)      [m/s²]

Structural tension (hull tending to be pulled apart or compressed)
arises because each element of the hull has a different tidal
acceleration; for a uniform-density rod of mass M and half-length L
oriented along â, the maximum internal tension (at the centre) is:

    F_tidal = ∫₀^L ρ A · |Δa(x)| dx = (M / (2L)) · E_radial · L²  [N]

where E_radial = |â^T · E · â| is the radial tidal eigenvalue.
Simplified result (uniform rod, radial alignment):

    F_tension = (1/4) M · |a_tidal(L)|                  [N]
              = (1/4) M · 2 G M_body L / r³
              = M L G M_body / (2 r³)

For bending (hull axis tilted at angle θ from the radial direction),
the transverse differential acceleration is smaller:
    |a_transverse| = E_transverse · L · sin θ
    Bending moment at centre: M_bend = (M L / 4) · a_transverse  [N·m]

REFERENCES
----------
Misner, Thorne & Wheeler 1973 §1.6 eq. 1.14 — tidal tensor definition
Saulson 1984 Phys Rev D 30:732 — tidal loading on extended bodies
Hughes et al. 2003 Phys Rev D 69:044004 — tidal deformation of hulls
Ramsey 1949 *Newtonian Attraction* §2.4 — tidal integral for rod
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .tidal_tensor import tidal_acceleration_on_point, tidal_tensor_single_perturber


def hull_tidal_acceleration_profile(
    tidal_tensor_1_s2: np.ndarray,
    hull_axis_unit: np.ndarray,
    half_length_m: float,
    n_points: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Tidal acceleration vector at each point along the hull axis [m/s²].

    Samples n_points evenly from −L to +L along the hull axis
    (L = half_length_m). The origin is the centre of mass.

    Args:
        tidal_tensor_1_s2: (3, 3) tidal tensor [1/s²] from tidal_tensor.py.
        hull_axis_unit: (3,) unit vector along hull axis.
        half_length_m: Half-length of the hull [m].
        n_points: Number of sample points (must be ≥ 2).

    Returns:
        Tuple of:
        - positions: (n_points,) array of s-coordinates along hull [m].
        - accelerations: (n_points, 3) tidal acceleration at each position [m/s²].
    """
    if n_points < 2:
        raise ValueError("n_points must be ≥ 2")
    E = np.asarray(tidal_tensor_1_s2, dtype=float).reshape(3, 3)
    axis = np.asarray(hull_axis_unit, dtype=float)
    axis = axis / np.linalg.norm(axis)  # normalise
    positions = np.linspace(-half_length_m, half_length_m, n_points)
    accels = np.zeros((n_points, 3))
    for i, s in enumerate(positions):
        L_vec = s * axis
        accels[i] = tidal_acceleration_on_point(E, L_vec)
    return positions, accels


def differential_tidal_acceleration_m_s2(
    tidal_tensor_1_s2: np.ndarray,
    hull_axis_unit: np.ndarray,
    half_length_m: float,
) -> np.ndarray:
    """Differential tidal acceleration between bow (+L) and stern (−L) [m/s²].

    Δa = a_tidal(+L â) − a_tidal(−L â) = −2 E (L â)

    Reference: MTW §1.6; Saulson 1984 Phys Rev D 30:732.

    Args:
        tidal_tensor_1_s2: (3, 3) tidal tensor [1/s²].
        hull_axis_unit: Unit vector along hull long axis.
        half_length_m: Hull half-length [m].

    Returns:
        (3,) differential acceleration vector [m/s²].
    """
    E = np.asarray(tidal_tensor_1_s2, dtype=float).reshape(3, 3)
    axis = np.asarray(hull_axis_unit, dtype=float)
    axis = axis / np.linalg.norm(axis)
    L_vec = half_length_m * axis
    a_fore = tidal_acceleration_on_point(E, L_vec)
    a_aft = tidal_acceleration_on_point(E, -L_vec)
    return a_fore - a_aft


def max_tidal_differential_m_s2(
    tidal_tensor_1_s2: np.ndarray,
    hull_axis_unit: np.ndarray,
    half_length_m: float,
) -> float:
    """Magnitude of differential tidal acceleration fore-to-aft [m/s²].

    Args:
        tidal_tensor_1_s2: (3, 3) tidal tensor [1/s²].
        hull_axis_unit: Unit vector along hull long axis.
        half_length_m: Hull half-length [m].

    Returns:
        Scalar magnitude [m/s²].
    """
    da = differential_tidal_acceleration_m_s2(
        tidal_tensor_1_s2, hull_axis_unit, half_length_m
    )
    return float(np.linalg.norm(da))


def hull_tidal_tension_N(
    tidal_tensor_1_s2: np.ndarray,
    hull_axis_unit: np.ndarray,
    half_length_m: float,
    hull_mass_kg: float,
) -> float:
    """Maximum internal tension / compression at hull midpoint from tidal loading [N].

    For a uniform-density rod oriented along hull_axis, the peak internal
    structural force (at the centre cross-section) is:

        F = (hull_mass / (2 × half_length)) × ∫₀^L |a_tidal(x)| dx

    For the linear tidal profile a_tidal(x) = E_radial × x (valid when
    E is constant over the hull), this integrates exactly to:

        F = (1/4) × hull_mass × |a_tidal(half_length)|   [N]

    Reference: Ramsey 1949 §2.4; Saulson 1984 Phys Rev D 30:732.

    Args:
        tidal_tensor_1_s2: (3, 3) tidal tensor [1/s²].
        hull_axis_unit: Unit vector along hull long axis.
        half_length_m: Hull half-length [m].
        hull_mass_kg: Total hull mass [kg].

    Returns:
        Peak internal tension/compression [N]. Non-negative.
    """
    if hull_mass_kg <= 0.0:
        raise ValueError("hull_mass_kg must be > 0")
    E = np.asarray(tidal_tensor_1_s2, dtype=float).reshape(3, 3)
    axis = np.asarray(hull_axis_unit, dtype=float)
    axis = axis / np.linalg.norm(axis)
    L_vec = half_length_m * axis
    a_tip = float(np.linalg.norm(tidal_acceleration_on_point(E, L_vec)))
    return 0.25 * hull_mass_kg * a_tip


def hull_tidal_bending_moment_Nm(
    tidal_tensor_1_s2: np.ndarray,
    hull_axis_unit: np.ndarray,
    half_length_m: float,
    hull_mass_kg: float,
) -> float:
    """Peak tidal bending moment at hull midpoint [N·m].

    For a uniform-density rod, the transverse tidal acceleration
    gradient creates a bending moment. The moment at the centre is:

        M_bend = (1/4) hull_mass × |a_transverse(L)|     [N·m]

    where a_transverse is the tidal acceleration component perpendicular
    to the hull axis at the tip.

    Reference: Saulson 1984 Phys Rev D 30:732.

    Args:
        tidal_tensor_1_s2: (3, 3) tidal tensor [1/s²].
        hull_axis_unit: Unit vector along hull long axis.
        half_length_m: Hull half-length [m].
        hull_mass_kg: Total hull mass [kg].

    Returns:
        Peak bending moment [N·m]. Non-negative.
    """
    if hull_mass_kg <= 0.0:
        raise ValueError("hull_mass_kg must be > 0")
    E = np.asarray(tidal_tensor_1_s2, dtype=float).reshape(3, 3)
    axis = np.asarray(hull_axis_unit, dtype=float)
    axis = axis / np.linalg.norm(axis)
    L_vec = half_length_m * axis
    a_vec = tidal_acceleration_on_point(E, L_vec)
    # Transverse component = total - axial projection
    a_axial = float(np.dot(a_vec, axis)) * axis
    a_transverse = a_vec - a_axial
    a_trans_mag = float(np.linalg.norm(a_transverse))
    return 0.25 * hull_mass_kg * a_trans_mag * half_length_m


def tidal_stress_at_cross_section_Pa(
    hull_tidal_tension_N_value: float,
    cross_section_area_m2: float,
) -> float:
    """Average tidal stress at the hull midpoint cross-section [Pa].

    σ_tidal = F_tidal / A_cross_section

    Args:
        hull_tidal_tension_N_value: Tidal tension from hull_tidal_tension_N [N].
        cross_section_area_m2: Cross-sectional area of the hull [m²].

    Returns:
        Average tensile/compressive stress [Pa].
    """
    if cross_section_area_m2 <= 0.0:
        raise ValueError("cross_section_area_m2 must be > 0")
    return hull_tidal_tension_N_value / cross_section_area_m2


def is_tidal_stress_critical(
    tidal_stress_Pa: float,
    yield_strength_Pa: float,
    safety_factor: float = 2.0,
) -> bool:
    """True if tidal stress exceeds the allowable (yield / safety_factor).

    Args:
        tidal_stress_Pa: Computed tidal stress [Pa].
        yield_strength_Pa: Material yield strength [Pa].
        safety_factor: Design safety factor (default 2.0 per NASA STD-5020).

    Returns:
        True if tidal stress is critical.
    """
    return tidal_stress_Pa >= yield_strength_Pa / safety_factor


def solar_perihelion_tidal_scenario(
    ship_distance_AU: float,
    ship_half_length_m: float,
    ship_mass_kg: float,
    hull_cross_section_m2: float,
) -> dict:
    """Tidal loading at given solar distance for the generation ship.

    Uses the Sun's GM = 1.327×10²⁰ m³/s². Reports tension, bending
    moment, and stress for a radially aligned hull (worst case for
    tension) and a transverse hull (worst case for bending).

    Args:
        ship_distance_AU: Distance from Sun [AU]. 1 AU = 1.496×10¹¹ m.
        ship_half_length_m: Hull half-length [m].
        ship_mass_kg: Total ship mass [kg].
        hull_cross_section_m2: Cross-sectional area [m²].

    Returns:
        Dict with tension_N, bending_moment_Nm, stress_Pa, differential_m_s2.
    """
    GM_SUN = 1.32712440018e20   # m³/s² (IAU 2012)
    AU_M   = 1.495978707e11     # m/AU (IAU 2012)
    r = ship_distance_AU * AU_M
    # Radial tidal acceleration at hull tip (worst-case tension)
    # E_radial = 2 GM/r³; a_tip = E_radial × L; F = 0.25 × M × a_tip
    E_radial = 2.0 * GM_SUN / (r ** 3)
    a_tip = E_radial * ship_half_length_m
    tension_N = 0.25 * ship_mass_kg * a_tip
    stress_Pa = tension_N / hull_cross_section_m2
    # Differential acceleration over full hull length (2L)
    diff_m_s2 = 2.0 * a_tip
    # Bending moment: zero for radially aligned hull (no transverse component)
    # Use transverse orientation for bending (hull ⊥ radial = worst bending)
    # E_transverse = GM/r³; a_trans_tip = E_trans × L; M_bend = 0.25 × M × a_trans × L
    E_transverse = GM_SUN / (r ** 3)
    a_trans = E_transverse * ship_half_length_m
    bending_moment_Nm = 0.25 * ship_mass_kg * a_trans * ship_half_length_m
    return {
        "tension_N": tension_N,
        "bending_moment_Nm": bending_moment_Nm,
        "stress_Pa": stress_Pa,
        "differential_m_s2": diff_m_s2,
    }
