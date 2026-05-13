"""Perturbation acceleration models for orbit propagation.

Provides modular perturbation accelerations that can be composed with
the main gravitational acceleration in numerical propagators:
- J2 oblateness
- J3 higher-order oblateness
- J4, J5, J6 higher-order oblateness (long-period nodal/apsidal oscillations)
- Atmospheric drag with Earth rotation correction
- Solar radiation pressure with eclipse shadow toggle
- Third-body gravitational perturbation

Each function returns a (3,) acceleration vector that is added to the
main gravity acceleration in the equations of motion.

Algorithms studied from:
- poliastro core/perturbations.py (MIT) — all models
- poliastro core/events.py line_of_sight (MIT) — shadow function

References:
    Vallado, D.A. (2013). "Fundamentals of Astrodynamics" 4th ed. Ch. 8.
    Curtis, H. (2014). "Orbital Mechanics for Engineering Students" §12.
    Montenbruck & Gill (2000). "Satellite Orbits" §3.
"""

from __future__ import annotations

import math

import numpy as np


def j2_perturbation(
    r: np.ndarray, mu: float, J2: float, R_body: float
) -> np.ndarray:
    """J2 (oblateness) perturbation acceleration.

    The dominant perturbation for LEO/MEO orbits.
    Causes: nodal regression, apsidal precession.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        J2: J2 coefficient (e.g., 1.08263e-3 for Earth, GEM-T1)
        R_body: equatorial radius of the body [m]

    Returns:
        (3,) acceleration [m/s²]

    Reference: Vallado (2013) Eq. (8-26).
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-10:
        return np.zeros(3)

    r5 = r_mag ** 5
    z2_r2 = (r[2] / r_mag) ** 2
    coeff = -1.5 * mu * J2 * R_body ** 2 / r5

    ax = coeff * r[0] * (1.0 - 5.0 * z2_r2)
    ay = coeff * r[1] * (1.0 - 5.0 * z2_r2)
    az = coeff * r[2] * (3.0 - 5.0 * z2_r2)

    return np.array([ax, ay, az])


def j3_perturbation(
    r: np.ndarray, mu: float, J3: float, R_body: float
) -> np.ndarray:
    """J3 perturbation acceleration (pear-shaped term).

    Much smaller than J2 but causes long-period eccentricity oscillations.
    Odd harmonic: zero on equatorial plane, maximum effect at mid-latitudes.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        J3: J3 coefficient (e.g., -2.5327e-6 for Earth, EGM96)
        R_body: equatorial radius [m]

    Returns:
        (3,) acceleration [m/s²]

    Derivation: a_J3 = ∇[(μ/r)*J3*(R/r)^3*P3(z/r)] using
        ∂[P3(s)/r^4]/∂x_i = x_i/r^6*[-s*P3'(s)-4*P3(s)] for i∈{x,y}
        ∂[P3(s)/r^4]/∂z = [P3'(1-s^2)-4s*P3] / r^5
    where s=z/r, P3(s)=(5s^3-3s)/2.
    Reference: Vallado (2013) §8.7; Montenbruck & Gill (2000) §3.2.
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-10:
        return np.zeros(3)

    r6 = r_mag ** 6   # r^(n+3) for n=3: CRITICAL FIX (was r^7)
    z_r = r[2] / r_mag
    z2_r2 = z_r ** 2

    # f3(s) = (5s/2)*(3-7s²):  -s*P3'(s) - 4*P3(s) = (5s/2)*(3-7s²)
    coeff = mu * J3 * R_body ** 3 / r6
    fxy = (5.0 / 2.0) * z_r * (3.0 - 7.0 * z2_r2)

    # g3(s) = (-35s^4+30s^2-3)/2:  P3'(1-s²)-4s*P3(s) = (-35s^4+30s^2-3)/2
    # Note az = coeff * r_mag * g3  (factor of r from ∂r/∂z term)
    gz = (-35.0 * z2_r2 ** 2 + 30.0 * z2_r2 - 3.0) / 2.0

    return np.array([
        coeff * r[0] * fxy,
        coeff * r[1] * fxy,
        coeff * r_mag * gz,
    ])


def j4_perturbation(
    r: np.ndarray, mu: float, J4: float, R_body: float
) -> np.ndarray:
    """J4 perturbation acceleration.

    Fourth zonal harmonic — causes long-period oscillations in inclination,
    eccentricity, and node. Magnitude ~1/8 of J3, but accumulates over long
    cruise arcs (> 1 year). Essential for generation-ship trajectory accuracy.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        J4: J4 coefficient (e.g., -1.6199e-6 for Earth, EGM96)
        R_body: equatorial radius [m]

    Returns:
        (3,) acceleration [m/s²]

    Derivation: a_J4 = -∇[μJ4(R/r)^4 P4(z/r)/r] using
        ∂[P4(s)/r^5]/∂x = -(x/r^7)[s·P4'(s)+5·P4(s)]
        ∂[P4(s)/r^5]/∂z = -(5/8)(z/r)(15-70s²+63s⁴)/r^6
    where P4(s) = (35s⁴-30s²+3)/8.
    Reference: Vallado (2013) §8.7; Montenbruck & Gill (2000) §3.2.
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-10:
        return np.zeros(3)

    r7 = r_mag ** 7   # r^(n+3) for n=4: FIX — was r^9 (r^(2n+1))
    z2_r2 = (r[2] / r_mag) ** 2

    # (5·P4 + s·P4') = (5/8)(3-42s²+63s⁴);  J4 sign carries via EGM96 value
    coeff = (5.0 / 8.0) * mu * J4 * R_body ** 4 / r7

    factor_xy = 3.0 - 42.0 * z2_r2 + 63.0 * z2_r2 ** 2
    factor_z  = 15.0 - 70.0 * z2_r2 + 63.0 * z2_r2 ** 2

    return np.array([
        coeff * r[0] * factor_xy,
        coeff * r[1] * factor_xy,
        coeff * r[2] * factor_z,
    ])


def j5_perturbation(
    r: np.ndarray, mu: float, J5: float, R_body: float
) -> np.ndarray:
    """J5 perturbation acceleration.

    Fifth zonal harmonic. Odd harmonics (J3, J5) contribute to north-south
    asymmetry. Relevant for high-precision lunar orbit and planetary approach.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        J5: J5 coefficient (e.g., -2.277e-7 for Earth, EGM96)
        R_body: equatorial radius [m]

    Returns:
        (3,) acceleration [m/s²]

    Derivation: a_J5 = -∇[μJ5(R/r)^5 P5(z/r)/r] using
        ∂[P5(s)/r^6]/∂x = -(x/r^8)[s·P5'(s)+6·P5(s)]
                         = -(x/r^8)·(21s/8)·(5-30s²+33s⁴)  [negative of code fxy]
        ∂[P5(s)/r^6]/∂z = [-6s·P5+(1-s²)·P5']/r^7
                         = (-693s⁶+945s⁴-315s²+15)/(8r^7)
    where P5(s)=(63s⁵-70s³+15s)/8; odd harmonic so no extra sign flip.
    Reference: Vallado (2013) §8.7; Montenbruck & Gill (2000) §3.2.
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-10:
        return np.zeros(3)

    r8 = r_mag ** 8   # r^(n+3) for n=5: FIX — was r^11 (r^(2n+1))
    z_r = r[2] / r_mag
    z2_r2 = z_r ** 2

    coeff = mu * J5 * R_body ** 5 / r8

    # (6·P5 + s·P5') = (21s/8)(5-30s²+33s⁴)  → fxy has z_r factor (odd harmonic)
    fxy = (21.0 / 8.0) * z_r * (5.0 - 30.0 * z2_r2 + 33.0 * z2_r2 ** 2)

    # [-6s·P5+(1-s²)·P5'] = (-693s⁶+945s⁴-315s²+15)/8
    gz = (-693.0 * z2_r2 ** 3 + 945.0 * z2_r2 ** 2 - 315.0 * z2_r2 + 15.0) / 8.0

    return np.array([
        coeff * r[0] * fxy,
        coeff * r[1] * fxy,
        coeff * r_mag * gz,
    ])


def j6_perturbation(
    r: np.ndarray, mu: float, J6: float, R_body: float
) -> np.ndarray:
    """J6 perturbation acceleration.

    Sixth zonal harmonic. Secondary nodal/apsidal period contribution.
    Negligible for LEO (<1 year) but accumulates in 20-50 year cruise.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        J6: J6 coefficient (e.g., 5.406e-7 for Earth, EGM96)
        R_body: equatorial radius [m]

    Returns:
        (3,) acceleration [m/s²]

    Derivation: a_J6 = -∇[μJ6(R/r)^6 P6(z/r)/r] using
        ∂[P6(s)/r^7]/∂x = -(x/r^9)[s·P6'(s)+7·P6(s)]
                         = -(x/r^9)·(7/16)·(429s⁶-495s⁴+135s²-5)
        ∂[P6(s)/r^7]/∂z = [-7s·P6+(1-s²)·P6']/r^8
                         = (7s/16r^8)·(-429s⁶+693s⁴-315s²+35)
    where P6(s)=(231s⁶-315s⁴+105s²-5)/16; even harmonic → negative coeff.
    Reference: Vallado (2013) §8.7; Montenbruck & Gill (2000) §3.2.
    """
    r_mag = np.linalg.norm(r)
    if r_mag < 1e-10:
        return np.zeros(3)

    r9 = r_mag ** 9   # r^(n+3) for n=6: FIX — was r^13 (r^(2n+1))
    z2_r2 = (r[2] / r_mag) ** 2

    # -(7·P6 + s·P6') = -(7/16)(429s⁶-495s⁴+135s²-5)
    coeff = -(7.0 / 16.0) * mu * J6 * R_body ** 6 / r9

    factor_xy = 429.0 * z2_r2 ** 3 - 495.0 * z2_r2 ** 2 + 135.0 * z2_r2 - 5.0

    # [-7s·P6+(1-s²)·P6'] = (7/16)s·(-429s⁶+693s⁴-315s²+35) → factor_z/s absorbed into r[2]
    factor_z  = 429.0 * z2_r2 ** 3 - 693.0 * z2_r2 ** 2 + 315.0 * z2_r2 - 35.0

    return np.array([
        coeff * r[0] * factor_xy,
        coeff * r[1] * factor_xy,
        coeff * r[2] * factor_z,
    ])


# EGM96 zonal harmonic coefficients for Earth (unitless)
# Reference: Lemoine et al. (1998) "The Development of the Joint NASA GSFC and
# the National Imagery and Mapping Agency (NIMA) Geopotential Model EGM96"
# NASA/TP-1998-206861, Table 2.
EARTH_J2 = 1.08263e-3   # EGM96
EARTH_J3 = -2.5327e-6   # EGM96
EARTH_J4 = -1.6199e-6   # EGM96
EARTH_J5 = -2.277e-7    # EGM96
EARTH_J6 = 5.406e-7     # EGM96
EARTH_R  = 6378136.3    # m, EGM96 equatorial radius
EARTH_MU = 3.986004418e14  # m³/s², EGM96


def zonal_harmonics(
    r: np.ndarray,
    mu: float = EARTH_MU,
    R_body: float = EARTH_R,
    J2: float = EARTH_J2,
    J3: float = EARTH_J3,
    J4: float = EARTH_J4,
    J5: float = EARTH_J5,
    J6: float = EARTH_J6,
    order: int = 6,
) -> np.ndarray:
    """Combined zonal harmonic perturbation up to J6.

    Args:
        r: (3,) position vector [m]
        mu: gravitational parameter [m³/s²]
        R_body: equatorial radius [m]
        J2..J6: zonal harmonic coefficients
        order: highest order to include (2-6)

    Returns:
        (3,) total zonal perturbation acceleration [m/s²]
    """
    acc = np.zeros(3)
    if order >= 2:
        acc += j2_perturbation(r, mu, J2, R_body)
    if order >= 3:
        acc += j3_perturbation(r, mu, J3, R_body)
    if order >= 4:
        acc += j4_perturbation(r, mu, J4, R_body)
    if order >= 5:
        acc += j5_perturbation(r, mu, J5, R_body)
    if order >= 6:
        acc += j6_perturbation(r, mu, J6, R_body)
    return acc


# ── Earth rotation correction for atmospheric drag ────────────────────────────
_OMEGA_EARTH = 7.2921150e-5  # rad/s, IAU 1976


def atmospheric_drag_exponential(
    r: np.ndarray,
    v: np.ndarray,
    C_D: float,
    A_over_m: float,
    rho0: float = 3.614e-13,
    h0: float = 700e3,
    H_scale: float = 88667.0,
    R_body: float = 6378137.0,
) -> np.ndarray:
    """Atmospheric drag acceleration using exponential density model.

    Args:
        r: (3,) position [m]
        v: (3,) velocity [m/s]
        C_D: drag coefficient (~2.2 for typical spacecraft)
        A_over_m: area-to-mass ratio [m²/kg]
        rho0: reference density [kg/m³] at h0 (default: 700km, CIRA-72)
        h0: reference altitude [m]
        H_scale: scale height [m]
        R_body: body equatorial radius [m]

    Returns:
        (3,) drag acceleration [m/s²] (always opposing velocity)

    Reference: Vallado (2013) Eq. (8-36).
    """
    r_mag = np.linalg.norm(r)
    h = r_mag - R_body  # altitude above surface

    if h < 0:
        h = 0.0

    # Exponential density model
    rho = rho0 * math.exp(-(h - h0) / H_scale)

    # Relative velocity w.r.t. rotating atmosphere (Earth rotation correction)
    # Atmosphere co-rotates with Earth at ω_E = 7.292e-5 rad/s.
    # v_atmosphere = ω × r; drag acts on v - v_atm.
    # Correction is ~0.5 km/s at equator — 5-10% error if ignored.
    # Ref: Vallado (2013) Eq. (8-36); Montenbruck & Gill (2000) §3.4.
    omega_cross_r = np.array([
        -_OMEGA_EARTH * r[1],
         _OMEGA_EARTH * r[0],
         0.0,
    ])
    v_rel = v - omega_cross_r
    v_rel_mag = np.linalg.norm(v_rel)

    if v_rel_mag < 1e-10:
        return np.zeros(3)

    # Drag acceleration: a = -0.5 * rho * v² * C_D * A/m * v_hat
    return -0.5 * rho * v_rel_mag * C_D * A_over_m * v_rel


def solar_radiation_pressure(
    r_sat: np.ndarray,
    r_sun: np.ndarray,
    C_R: float,
    A_over_m: float,
    R_body: float = 6378137.0,
    P_sun: float = 4.56e-6,
    AU: float = 1.496e11,
) -> np.ndarray:
    """Solar radiation pressure with eclipse shadow toggle.

    SRP accelerates the spacecraft in the anti-sunward direction.
    The acceleration is zeroed when the spacecraft is in the body's
    shadow (eclipse).

    Args:
        r_sat: (3,) satellite position relative to central body [m]
        r_sun: (3,) Sun position relative to central body [m]
        C_R: radiation pressure coefficient (1.0 = perfect absorber, 2.0 = perfect reflector)
        A_over_m: area-to-mass ratio [m²/kg]
        R_body: equatorial radius of the eclipsing body [m]
        P_sun: solar flux at 1 AU [N/m²] (IAU 2015: 4.56e-6)
        AU: 1 AU in metres

    Returns:
        (3,) SRP acceleration [m/s²]

    Reference: Curtis (2014) §12.9, Vallado (2013) §8.6.4.
    """
    # Check eclipse (line of sight to Sun)
    from aria.physics.gravity.nbody import line_of_sight
    if not line_of_sight(r_sat, r_sun, R_body):
        return np.zeros(3)  # in shadow

    # Sun direction from satellite
    r_sun_to_sat = r_sat - r_sun
    dist_sun = np.linalg.norm(r_sun_to_sat)
    if dist_sun < 1e-10:
        return np.zeros(3)

    # Pressure scales as 1/r² from the Sun
    P = P_sun * (AU / dist_sun) ** 2

    # SRP acceleration (anti-sunward)
    sun_dir = r_sun_to_sat / dist_sun
    return -P * C_R * A_over_m * sun_dir


def third_body_perturbation(
    r_sat: np.ndarray,
    r_third: np.ndarray,
    mu_third: float,
) -> np.ndarray:
    """Third-body gravitational perturbation.

    The acceleration on the satellite due to a third body (e.g., Moon, Sun)
    in addition to the central body. Uses the standard formulation with
    the indirect term.

    Args:
        r_sat: (3,) satellite position relative to central body [m]
        r_third: (3,) third body position relative to central body [m]
        mu_third: gravitational parameter of third body [m³/s²]

    Returns:
        (3,) perturbation acceleration [m/s²]

    Reference: Battin (1999) §8.3, Vallado (2013) Eq. (8-33).
    """
    r_sat_to_third = r_third - r_sat
    r_st_mag = np.linalg.norm(r_sat_to_third)
    r_third_mag = np.linalg.norm(r_third)

    if r_st_mag < 1e-10 or r_third_mag < 1e-10:
        return np.zeros(3)

    # Direct term + indirect term
    return mu_third * (
        r_sat_to_third / r_st_mag ** 3
        - r_third / r_third_mag ** 3
    )
