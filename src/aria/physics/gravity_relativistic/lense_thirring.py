"""Lense-Thirring frame dragging from a rotating central mass
(§4.6 of docs/pods/A2_tidal_tensor.md).

In the linearised Kerr metric of a body with mass `M` and angular
momentum vector `J`, a test gyroscope at displacement `r` from the
body center precesses at angular rate

    Ω_LT = (G / (c² r³)) · ( 3 (J · r̂) r̂ − J )         [rad/s]

(Ciufolini & Wheeler *Gravitation and Inertia* §6.2, ISBN
978-0691033235). This has two useful limits:

  - Over the poles (`r ∥ J`): `|Ω_LT| = 2 G J / (c² r³)` — maximum
    magnitude, parallel to J.
  - In the equatorial plane (`r ⊥ J`): `|Ω_LT| = G J / (c² r³)` —
    half the polar value, anti-parallel to J.

Gravity Probe B (Everitt 2011 PRL 106 221101 DOI 10.1103/PhysRevLett.106.221101)
measured 37.2 ± 7.2 mas/yr at the poles of Earth at 642 km altitude,
in agreement with the linearised Kerr prediction.
"""

from __future__ import annotations

import numpy as np

# Exact speed of light (SI 2019).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8

# Earth total angular momentum — IERS Conventions 2010 (Petit & Luzum,
# IERS Technical Note 36, 2010). Dominated by the crust and mantle
# solid-body rotation.
J_EARTH_KG_M2_S: float = 5.86e33  # kg m² s⁻¹ (IERS 2010)

# Sun total angular momentum — helioseismic measurement
# (Komm 2008 Solar Phys 254 285 DOI 10.1007/s11207-008-9292-7).
J_SUN_KG_M2_S: float = 1.92e41  # kg m² s⁻¹ (Komm 2008)

# Jupiter angular momentum — Juno moment-of-inertia determination
# (Helled 2011 ApJ 726 15 DOI 10.1088/0004-637X/726/1/15).
J_JUPITER_KG_M2_S: float = 6.9e42  # kg m² s⁻¹ (Helled 2011)


def lense_thirring_precession(
    position_from_body_m: np.ndarray,
    angular_momentum_kg_m2_s: np.ndarray,
) -> np.ndarray:
    """General Lense-Thirring precession vector `Ω_LT` (rad/s).

    Ω_LT = (G / (c² r³)) · (3 (J · r̂) r̂ − J)

    Args:
        position_from_body_m: (3,) position vector of the gyroscope
            relative to the body center (m).
        angular_momentum_kg_m2_s: (3,) body angular-momentum vector
            (kg·m²/s).

    Returns:
        (3,) precession angular-velocity vector in rad/s.

    Unit audit: `G / (c² r³)` = (m³ kg⁻¹ s⁻²)/(m² s⁻²) / m³ =
    (kg⁻¹) / m² = ... multiplied by J [kg m² s⁻¹] gives s⁻¹ ✓.
    """
    # CODATA 2018 G.
    G = 6.67430e-11

    r_vec = np.asarray(position_from_body_m, dtype=float).reshape(3)
    J = np.asarray(angular_momentum_kg_m2_s, dtype=float).reshape(3)
    r = float(np.linalg.norm(r_vec))
    if r == 0.0:
        raise ValueError("gyroscope position coincides with body center")
    r_hat = r_vec / r
    prefac = G / (SPEED_OF_LIGHT_M_S**2 * r**3)
    return prefac * (3.0 * float(np.dot(J, r_hat)) * r_hat - J)


def lense_thirring_polar_rate(
    angular_momentum_kg_m2_s: float, orbit_radius_m: float
) -> float:
    """Instantaneous magnitude of Ω_LT for a gyroscope **stationary**
    above the pole of a rotating body (J ∥ r̂).

    At the pole, r̂ is parallel to J, so
        3 (J · r̂) r̂ − J = 3 J − J = 2 J
    giving
        |Ω_LT| = 2 G J / (c² r³)                         [rad/s]

    Note: this is **not** the rate that Gravity Probe B measured.
    GPB's gyroscope was on a polar *circular orbit*, not stationary
    over the pole, so its gyroscope spin axis averaged over all
    latitudes. The orbit-averaged Schiff frame-dragging precession
    for that geometry is ``lense_thirring_schiff_polar_orbit``
    (see below), which is 1/4 of the instantaneous polar rate.

    Args:
        angular_momentum_kg_m2_s: |J| of the rotating body (scalar).
        orbit_radius_m: distance from body center (m).

    Returns:
        Instantaneous polar-stationary precession rate in rad/s.
    """
    if angular_momentum_kg_m2_s <= 0.0:
        raise ValueError("angular_momentum_kg_m2_s must be positive")
    if orbit_radius_m <= 0.0:
        raise ValueError("orbit_radius_m must be positive")
    G = 6.67430e-11  # CODATA 2018
    return 2.0 * G * angular_momentum_kg_m2_s / (
        SPEED_OF_LIGHT_M_S**2 * orbit_radius_m**3
    )


def lense_thirring_schiff_polar_orbit(
    angular_momentum_kg_m2_s: float, semi_major_axis_m: float
) -> float:
    """Orbit-averaged Schiff frame-dragging drift for a gyroscope on a
    **polar circular orbit** of radius ``a`` (the Gravity Probe B
    geometry).

    <|Ω_LT|>_orbit = G J / (2 c² a³)                    [rad/s]

    Derivation: Schiff 1960 PRL 4 215 DOI 10.1103/PhysRevLett.4.215
    gives the general frame-dragging term `Ω_LT = (G/c²r³)(3(J·r̂)r̂ − J)`;
    for a gyroscope on a polar circular orbit (J perpendicular to the
    orbit plane), averaging over the orbit produces the factor 1/4
    relative to the instantaneous polar-stationary value. This is the
    formula whose prediction Gravity Probe B confirmed to ~20 %
    (Everitt 2011 PRL 106 221101 DOI 10.1103/PhysRevLett.106.221101,
    `37.2 ± 7.2 mas/yr` at 642 km altitude).

    Args:
        angular_momentum_kg_m2_s: |J| of the central body (kg·m²/s).
        semi_major_axis_m: orbit semi-major axis (m). For a circular
            orbit this is just the orbit radius.

    Returns:
        Orbit-averaged precession rate in rad/s.
    """
    if angular_momentum_kg_m2_s <= 0.0:
        raise ValueError("angular_momentum_kg_m2_s must be positive")
    if semi_major_axis_m <= 0.0:
        raise ValueError("semi_major_axis_m must be positive")
    G = 6.67430e-11  # CODATA 2018
    return (
        G
        * angular_momentum_kg_m2_s
        / (2.0 * SPEED_OF_LIGHT_M_S**2 * semi_major_axis_m**3)
    )
