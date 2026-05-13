"""Orbital element conversions and Kepler equation solvers.

Provides conversions between:
- Classical Orbital Elements (COE): a, e, i, Omega, omega, nu
- Modified Equinoctial Elements (MEE): p, f, g, h, k, L (singularity-free)
- State vectors (r, v)

And Kepler equation solvers:
- Mean anomaly → Eccentric anomaly (elliptic, Newton-Raphson)
- Mean anomaly → Hyperbolic anomaly (hyperbolic)
- Eccentric anomaly → True anomaly
- True anomaly → Eccentric anomaly

MEE are essential for low-thrust trajectory optimization and numerical
propagation near circular/equatorial orbits where classical elements
have singularities.

References:
    Walker, M.J.H. et al. (1985). "A set of modified equinoctial orbit
    elements." Celestial Mechanics, 36(4), 409-419.

    Battin (1999) "An Introduction to the Mathematics and Methods of
    Astrodynamics" AIAA, Ch. 4.

    Algorithm approaches studied from poliastro core/elements.py (MIT)
    and Rebound tools.c Kepler solvers (GPL, clean-room reimplemented).
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════
#  Kepler equation solvers
# ══════════════════════════════════════════════════════════════════

def mean_to_eccentric(M: float, e: float, tol: float = 1e-14, maxiter: int = 50) -> float:
    """Solve Kepler's equation M = E - e*sin(E) for elliptic orbits.

    Uses Newton-Raphson iteration with Markley (1995) initial guess.

    Args:
        M: Mean anomaly [rad]
        e: Eccentricity (0 ≤ e < 1)
        tol: Convergence tolerance
        maxiter: Maximum iterations

    Returns:
        E: Eccentric anomaly [rad]
    """
    # Markley initial guess (Markley 1995 Cel Mech 63 101)
    M = M % (2.0 * math.pi)
    if M > math.pi:
        M -= 2.0 * math.pi

    # Starting value
    E = M + 0.85 * e * (1.0 if M >= 0 else -1.0)

    for _ in range(maxiter):
        f = E - e * math.sin(E) - M
        fp = 1.0 - e * math.cos(E)
        dE = -f / fp
        E += dE
        if abs(dE) < tol:
            break

    return E


def mean_to_hyperbolic(M: float, e: float, tol: float = 1e-14, maxiter: int = 50) -> float:
    """Solve hyperbolic Kepler equation M = e*sinh(H) - H.

    Args:
        M: Mean anomaly [rad]
        e: Eccentricity (e > 1)

    Returns:
        H: Hyperbolic anomaly [rad]
    """
    # Initial guess
    if abs(M) < 0.01:
        H = M
    else:
        H = math.log(2.0 * abs(M) / e + 1.8) * (1.0 if M >= 0 else -1.0)

    for _ in range(maxiter):
        f = e * math.sinh(H) - H - M
        fp = e * math.cosh(H) - 1.0
        dH = -f / fp
        H += dH
        if abs(dH) < tol:
            break

    return H


def eccentric_to_true(E: float, e: float) -> float:
    """Convert eccentric anomaly to true anomaly (elliptic).

    Uses the half-angle formula for numerical stability.
    """
    return 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(E / 2.0),
        math.sqrt(1.0 - e) * math.cos(E / 2.0),
    )


def true_to_eccentric(nu: float, e: float) -> float:
    """Convert true anomaly to eccentric anomaly (elliptic)."""
    return 2.0 * math.atan2(
        math.sqrt(1.0 - e) * math.sin(nu / 2.0),
        math.sqrt(1.0 + e) * math.cos(nu / 2.0),
    )


def mean_to_true(M: float, e: float) -> float:
    """Convert mean anomaly to true anomaly.

    Handles elliptic (e < 1) and hyperbolic (e > 1) cases.
    """
    if e < 1.0:
        E = mean_to_eccentric(M, e)
        return eccentric_to_true(E, e)
    elif e > 1.0:
        H = mean_to_hyperbolic(M, e)
        return 2.0 * math.atan(math.sqrt((e + 1.0) / (e - 1.0)) * math.tanh(H / 2.0))
    else:
        # Parabolic: Barker's equation
        W = 3.0 * M
        Y = (W + math.sqrt(W * W + 1.0)) ** (1.0 / 3.0)
        return 2.0 * math.atan(Y - 1.0 / Y)


# ══════════════════════════════════════════════════════════════════
#  State vector ↔ Classical Orbital Elements
# ══════════════════════════════════════════════════════════════════

def rv_to_coe(
    r: np.ndarray, v: np.ndarray, mu: float
) -> Tuple[float, float, float, float, float, float]:
    """State vectors to classical orbital elements.

    Returns (a, e, i, Omega, omega, nu) where:
        a: semi-major axis [same units as r]
        e: eccentricity
        i: inclination [rad]
        Omega: RAAN [rad]
        omega: argument of periapsis [rad]
        nu: true anomaly [rad]
    """
    r_vec = np.asarray(r, dtype=float)
    v_vec = np.asarray(v, dtype=float)

    r_mag = np.linalg.norm(r_vec)
    v_mag = np.linalg.norm(v_vec)

    # Specific angular momentum
    h = np.cross(r_vec, v_vec)
    h_mag = np.linalg.norm(h)

    # Node vector
    k_hat = np.array([0.0, 0.0, 1.0])
    n = np.cross(k_hat, h)
    n_mag = np.linalg.norm(n)

    # Eccentricity vector
    e_vec = ((v_mag ** 2 - mu / r_mag) * r_vec - np.dot(r_vec, v_vec) * v_vec) / mu
    e = np.linalg.norm(e_vec)

    # Semi-major axis (from vis-viva)
    energy = 0.5 * v_mag ** 2 - mu / r_mag
    if abs(e - 1.0) > 1e-10:
        a = -mu / (2.0 * energy)
    else:
        a = float('inf')  # parabolic

    # Inclination
    i = math.acos(np.clip(h[2] / h_mag, -1.0, 1.0))

    # RAAN
    if n_mag > 1e-15:
        Omega = math.acos(np.clip(n[0] / n_mag, -1.0, 1.0))
        if n[1] < 0:
            Omega = 2.0 * math.pi - Omega
    else:
        Omega = 0.0  # equatorial orbit

    # Argument of periapsis
    if n_mag > 1e-15 and e > 1e-15:
        omega = math.acos(np.clip(np.dot(n, e_vec) / (n_mag * e), -1.0, 1.0))
        if e_vec[2] < 0:
            omega = 2.0 * math.pi - omega
    else:
        omega = 0.0

    # True anomaly
    if e > 1e-15:
        nu = math.acos(np.clip(np.dot(e_vec, r_vec) / (e * r_mag), -1.0, 1.0))
        if np.dot(r_vec, v_vec) < 0:
            nu = 2.0 * math.pi - nu
    else:
        nu = 0.0

    return a, e, i, Omega, omega, nu


def coe_to_rv(
    a: float, e: float, i: float,
    Omega: float, omega: float, nu: float,
    mu: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Classical orbital elements to state vectors.

    Returns (r, v) as (3,) arrays.
    """
    # Semi-latus rectum
    p = a * (1.0 - e ** 2) if e < 1.0 else a * (e ** 2 - 1.0)

    # Position and velocity in perifocal frame
    r_pqw = p / (1.0 + e * math.cos(nu))
    r_pf = np.array([r_pqw * math.cos(nu), r_pqw * math.sin(nu), 0.0])
    v_pf = np.array([
        -math.sqrt(mu / p) * math.sin(nu),
        math.sqrt(mu / p) * (e + math.cos(nu)),
        0.0,
    ])

    # Rotation matrix from perifocal to inertial
    R = _rotation_pqw_to_ijk(Omega, omega, i)

    return R @ r_pf, R @ v_pf


# ══════════════════════════════════════════════════════════════════
#  Modified Equinoctial Elements (MEE)
# ══════════════════════════════════════════════════════════════════

def coe_to_mee(
    a: float, e: float, i: float,
    Omega: float, omega: float, nu: float,
) -> Tuple[float, float, float, float, float, float]:
    """Classical to Modified Equinoctial Elements.

    Returns (p, f, g, h, k, L) where:
        p: semi-latus rectum
        f: e * cos(omega + Omega)
        g: e * sin(omega + Omega)
        h: tan(i/2) * cos(Omega)
        k: tan(i/2) * sin(Omega)
        L: Omega + omega + nu (true longitude)

    MEE are singularity-free for circular and equatorial orbits.
    Reference: Walker et al. (1985) Cel Mech 36 409.
    """
    p = a * (1.0 - e ** 2)
    f = e * math.cos(omega + Omega)
    g = e * math.sin(omega + Omega)
    h = math.tan(i / 2.0) * math.cos(Omega)
    k = math.tan(i / 2.0) * math.sin(Omega)
    L = Omega + omega + nu

    return p, f, g, h, k, L


def mee_to_coe(
    p: float, f: float, g: float,
    h: float, k: float, L: float,
) -> Tuple[float, float, float, float, float, float]:
    """Modified Equinoctial to Classical Orbital Elements.

    Returns (a, e, i, Omega, omega, nu).
    """
    e = math.sqrt(f ** 2 + g ** 2)
    i = 2.0 * math.atan(math.sqrt(h ** 2 + k ** 2))
    Omega = math.atan2(k, h)
    omega_plus_Omega = math.atan2(g, f)
    omega = omega_plus_Omega - Omega
    nu = L - omega_plus_Omega
    a = p / (1.0 - e ** 2) if abs(1.0 - e ** 2) > 1e-15 else float('inf')

    return a, e, i, Omega, omega, nu


def mee_to_rv(
    p: float, f: float, g: float,
    h: float, k: float, L: float,
    mu: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Modified Equinoctial Elements directly to state vectors.

    More efficient than mee→coe→rv for numerical propagation.
    Reference: Walker et al. (1985) Eqs. (3)-(6).
    """
    cos_L = math.cos(L)
    sin_L = math.sin(L)

    alpha2 = h ** 2 - k ** 2
    s2 = 1.0 + h ** 2 + k ** 2
    w = 1.0 + f * cos_L + g * sin_L
    r = p / w

    r_vec = (r / s2) * np.array([
        cos_L + alpha2 * cos_L + 2.0 * h * k * sin_L,
        sin_L - alpha2 * sin_L + 2.0 * h * k * cos_L,
        2.0 * (h * sin_L - k * cos_L),
    ])

    sqrt_mu_p = math.sqrt(mu / p)
    v_vec = (-1.0 / s2) * sqrt_mu_p * np.array([
        sin_L + alpha2 * sin_L - 2.0 * h * k * cos_L + g - 2.0 * f * h * k / s2,
        -cos_L + alpha2 * cos_L + 2.0 * h * k * sin_L - f + 2.0 * g * h * k / s2,
        -2.0 * (h * cos_L + k * sin_L + f * h + g * k),
    ])

    return r_vec, v_vec


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════

def _rotation_pqw_to_ijk(Omega: float, omega: float, i: float) -> np.ndarray:
    """3x3 rotation matrix from perifocal (PQW) to inertial (IJK) frame."""
    cO, sO = math.cos(Omega), math.sin(Omega)
    cw, sw = math.cos(omega), math.sin(omega)
    ci, si = math.cos(i), math.sin(i)

    return np.array([
        [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci, sO * si],
        [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
        [sw * si, cw * si, ci],
    ])
