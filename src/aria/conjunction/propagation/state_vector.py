"""
State vector utilities — conversions between Cartesian and Keplerian elements.
"""

from __future__ import annotations

import math

import numpy as np

from aria.conjunction.core.constants import MU_EARTH_KM
from aria.conjunction.core.types import OrbitalElements, StateVector


def state_to_elements(state: StateVector, mu: float = MU_EARTH_KM) -> OrbitalElements:
    """Convert Cartesian state vector to classical Keplerian orbital elements.

    Args:
        state: Position and velocity in an inertial frame
        mu: Gravitational parameter (km³/s²)

    Returns:
        OrbitalElements
    """
    r = state.position
    v = state.velocity
    r_mag = np.linalg.norm(r)
    v_mag = np.linalg.norm(v)

    # Angular momentum
    h = np.cross(r, v)
    h_mag = np.linalg.norm(h)

    # Node vector (points toward ascending node)
    k_hat = np.array([0.0, 0.0, 1.0])
    n = np.cross(k_hat, h)
    n_mag = np.linalg.norm(n)

    # Eccentricity vector
    e_vec = ((v_mag**2 - mu / r_mag) * r - np.dot(r, v) * v) / mu
    ecc = np.linalg.norm(e_vec)

    # Specific mechanical energy → semi-major axis
    energy = v_mag**2 / 2.0 - mu / r_mag
    if abs(energy) < 1e-14:
        sma = float("inf")  # parabolic
    else:
        sma = -mu / (2.0 * energy)

    # Inclination
    inc = math.acos(np.clip(h[2] / h_mag, -1.0, 1.0))

    # RAAN (Right Ascension of Ascending Node)
    if n_mag > 1e-10:
        raan = math.acos(np.clip(n[0] / n_mag, -1.0, 1.0))
        if n[1] < 0:
            raan = 2 * math.pi - raan
    else:
        raan = 0.0  # equatorial orbit

    # Argument of perigee
    if n_mag > 1e-10 and ecc > 1e-10:
        argp = math.acos(np.clip(np.dot(n, e_vec) / (n_mag * ecc), -1.0, 1.0))
        if e_vec[2] < 0:
            argp = 2 * math.pi - argp
    else:
        argp = 0.0

    # True anomaly
    if ecc > 1e-10:
        nu = math.acos(np.clip(np.dot(e_vec, r) / (ecc * r_mag), -1.0, 1.0))
        if np.dot(r, v) < 0:
            nu = 2 * math.pi - nu
    else:
        nu = 0.0

    return OrbitalElements(
        semi_major_axis=sma,
        eccentricity=ecc,
        inclination=inc,
        raan=raan,
        arg_perigee=argp,
        true_anomaly=nu,
        epoch=state.epoch,
    )


def elements_to_state(elements: OrbitalElements, mu: float = MU_EARTH_KM) -> StateVector:
    """Convert classical Keplerian elements to Cartesian state vector.

    Outputs in the same inertial frame as the elements' reference frame.
    """
    a = elements.semi_major_axis
    e = elements.eccentricity
    i = elements.inclination
    raan = elements.raan
    argp = elements.arg_perigee
    nu = elements.true_anomaly

    # Semi-latus rectum
    p = a * (1 - e**2)

    # Position and velocity in perifocal frame (PQW)
    r_mag = p / (1 + e * math.cos(nu))

    r_pqw = np.array([
        r_mag * math.cos(nu),
        r_mag * math.sin(nu),
        0.0,
    ])

    v_pqw = np.array([
        -math.sqrt(mu / p) * math.sin(nu),
        math.sqrt(mu / p) * (e + math.cos(nu)),
        0.0,
    ])

    # Rotation matrix: PQW → ECI
    cos_raan = math.cos(raan)
    sin_raan = math.sin(raan)
    cos_argp = math.cos(argp)
    sin_argp = math.sin(argp)
    cos_i = math.cos(i)
    sin_i = math.sin(i)

    R = np.array([
        [
            cos_raan * cos_argp - sin_raan * sin_argp * cos_i,
            -cos_raan * sin_argp - sin_raan * cos_argp * cos_i,
            sin_raan * sin_i,
        ],
        [
            sin_raan * cos_argp + cos_raan * sin_argp * cos_i,
            -sin_raan * sin_argp + cos_raan * cos_argp * cos_i,
            -cos_raan * sin_i,
        ],
        [
            sin_argp * sin_i,
            cos_argp * sin_i,
            cos_i,
        ],
    ])

    return StateVector(
        position=R @ r_pqw,
        velocity=R @ v_pqw,
        epoch=elements.epoch,
    )
