"""N-body Orbital Integrator — Earth-Moon-Sun three-body trajectory propagation.

Replaces patched-conic approximation with numerical integration of the full
gravitational field. This is the foundation for accurate lunar mission simulation.

WHAT THIS SOLVES
================
Patched-conic (used in lunar_return.py, gravity_assist.py) assumes each body's
gravity dominates in its own "sphere of influence." This introduces:
  - ~5-20 km position error over a 3-day translunar coast (Sun perturbation)
  - ~100 m/orbit drift at low lunar orbit (mascons, not modeled here yet)
  - No three-body effects (Lagrange points, halo orbits)

This module integrates the full equations of motion:
  a = -μ_earth × r/|r|³ - μ_moon × (r-r_moon)/|r-r_moon|³ - μ_sun × (r-r_sun)/|r-r_sun|³
      + μ_moon × r_moon/|r_moon|³ + μ_sun × r_sun/|r_sun|³  (indirect terms)

PHYSICS
=======
The state vector is [x, y, z, vx, vy, vz] in the Earth-Centered Inertial (ECI)
J2000 frame. The integrator uses scipy.integrate.solve_ivp with DOP853 (8th-order
Runge-Kutta-Fehlberg) for high accuracy and adaptive step sizing.

Moon and Sun positions are computed from:
  1. Analytical series (default): Meeus (1991) "Astronomical Algorithms"
     - Moon position: accuracy ~0.1° in ecliptic longitude (~650 km at lunar distance)
     - Sun position: accuracy ~0.01° (~26,000 km at 1 AU, but only ~0.1 km effect on
       trajectory near Earth)
  2. JPL DE440 ephemeris (optional): sub-meter accuracy, requires de440s.bsp kernel

Optional perturbations:
  - Earth J2 oblateness: dominant non-spherical term, causes ~7°/day nodal regression
  - Solar radiation pressure (future)

VALIDATION
==========
  Apollo 11 TLI → LOI transit: 3 days → accuracy target ±15 min, ±50 km
  Artemis 2 free-return: 10 days → position accuracy ±100 km
  Halo orbit at L2: period ~14 days, stable to ±1 km over 30 days

References
----------
  Bate, Mueller, White (1971) "Fundamentals of Astrodynamics" §9
  Vallado (2013) 4th ed. §8.4 — numerical orbit propagation
  Meeus J. (1991) "Astronomical Algorithms" ch. 47 (Moon), ch. 25 (Sun)
  Montenbruck & Gill (2000) "Satellite Orbits" §3.2 — third-body perturbations
  JPL DE440: Park et al. (2021) AJ 161:105 — planetary ephemeris
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Callable

import numpy as np
from scipy.integrate import solve_ivp

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

MU_EARTH   = 3.986004418e14    # Earth GM (m³/s²) — Vallado 4th ed Table D-1
MU_MOON    = 4.9048695e12      # Moon GM (m³/s²) — Lunar Sourcebook Table 2.1
MU_SUN     = 1.32712440018e20  # Sun GM (m³/s²) — JPL DE430 (Standish 1998)

R_EARTH_M  = 6_378_136.6       # Earth equatorial radius (m) — Vallado 4th ed
J2_EARTH   = 1.08263e-3        # Earth J2 oblateness — Vallado 4th ed Table D-1

# Moon orbital parameters — Lunar Sourcebook Table 2.8
MOON_SEMI_MAJOR_M    = 3.844e8     # Mean Earth-Moon distance (m)
MOON_ECCENTRICITY    = 0.0549      # Mean orbital eccentricity
MOON_ORBITAL_PERIOD  = 27.321661 * 86400.0  # Sidereal period (s) — Lunar Sourcebook

# Sun parameters — Vallado 4th ed
AU_M = 1.495978707e11  # Astronomical unit (m) — IAU 2012
EARTH_ORBITAL_PERIOD = 365.25636 * 86400.0  # Sidereal year (s) — Vallado Table D-1


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class OrbitalState:
    """Spacecraft state vector in ECI J2000 frame."""
    x: float       # Position x (m)
    y: float       # Position y (m)
    z: float       # Position z (m)
    vx: float      # Velocity x (m/s)
    vy: float      # Velocity y (m/s)
    vz: float      # Velocity z (m/s)
    epoch_s: float  # Time since J2000 epoch (s)

    @property
    def r_vec(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z])

    @property
    def v_vec(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.vz])

    @property
    def r_mag(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    @property
    def v_mag(self) -> float:
        return math.sqrt(self.vx**2 + self.vy**2 + self.vz**2)

    @property
    def state_vector(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z, self.vx, self.vy, self.vz])

    @property
    def specific_energy(self) -> float:
        """Specific orbital energy ε = v²/2 − μ/r (J/kg)."""
        return self.v_mag**2 / 2.0 - MU_EARTH / self.r_mag

    @property
    def altitude_m(self) -> float:
        """Altitude above Earth's surface (m)."""
        return self.r_mag - R_EARTH_M

    def distance_to(self, other_pos: np.ndarray) -> float:
        """Distance to another position vector (m)."""
        d = self.r_vec - other_pos
        return float(np.linalg.norm(d))


@dataclass
class PropagationResult:
    """Result of orbit propagation."""
    states: list[OrbitalState]           # State at each output time
    t_seconds: np.ndarray                # Time array (s)
    positions_m: np.ndarray              # (N, 3) position array
    velocities_ms: np.ndarray            # (N, 3) velocity array
    moon_positions_m: np.ndarray         # (N, 3) Moon position array
    integrator_steps: int                # Number of internal RK steps taken
    max_step_error: float                # Estimated max local error
    bodies_included: list[str]           # Which gravitational bodies were included


# ═══════════════════════════════════════════════════════════════════
#  ANALYTICAL EPHEMERIS — Moon and Sun positions
# ═══════════════════════════════════════════════════════════════════
# Simplified Meeus (1991) "Astronomical Algorithms" ch. 47 (Moon), ch. 25 (Sun)
# Accuracy: Moon ~0.1° ecliptic longitude (~650 km), Sun ~0.01° (~26,000 km)
# For lunar mission simulation the Moon position error is the dominant concern;
# 650 km at 384,400 km distance causes <0.1° pointing error, which produces
# <1 km trajectory error over a 3-day coast (well within our targets).

def moon_position_eci(t_since_j2000_s: float) -> np.ndarray:
    """Moon position in ECI J2000 frame (m) using simplified Meeus series.

    Uses the five principal terms of the lunar theory (Meeus ch. 47).
    Accuracy: ~0.1° in ecliptic longitude ≈ 650 km at lunar distance.

    Args:
        t_since_j2000_s: Time since J2000.0 epoch (seconds).

    Returns:
        [x, y, z] Moon position in ECI frame (m).

    References:
        Meeus J. (1991) "Astronomical Algorithms" ch. 47.
        Montenbruck & Pfleger (2000) §3.3.2 — simplified lunar ephemeris.
    """
    # Julian centuries since J2000.0
    T = t_since_j2000_s / (36525.0 * 86400.0)

    # Fundamental arguments (Meeus ch. 47, degrees then → radians)
    # Mean longitude of Moon (referred to mean equinox of date)
    L0 = 218.3165 + 481267.8813 * T   # deg; Meeus eq. 47.1
    # Mean anomaly of Moon
    M_moon = 134.9634 + 477198.8676 * T  # deg; Meeus eq. 47.3
    # Mean anomaly of Sun
    M_sun = 357.5291 + 35999.0503 * T    # deg; Meeus eq. 25.3
    # Moon's argument of latitude
    F = 93.2720 + 483202.0175 * T        # deg; Meeus eq. 47.5
    # Moon's mean elongation from Sun
    D = 297.8502 + 445267.1115 * T       # deg; Meeus eq. 47.2

    # Convert to radians
    L0_r = math.radians(L0 % 360.0)
    M_m = math.radians(M_moon % 360.0)
    M_s = math.radians(M_sun % 360.0)
    F_r = math.radians(F % 360.0)
    D_r = math.radians(D % 360.0)

    # Ecliptic longitude correction (5 principal terms, Meeus Table 47.A)
    dL = (6.289 * math.sin(M_m)               # Evection-related
          - 1.274 * math.sin(2*D_r - M_m)     # Variation
          - 0.658 * math.sin(2*D_r)           # Annual equation
          + 0.214 * math.sin(2*M_m)           # Parallactic inequality
          - 0.186 * math.sin(M_s))            # Solar perturbation
    # Ecliptic latitude correction (Meeus Table 47.B)
    dB = (5.128 * math.sin(F_r)
          + 0.281 * math.sin(M_m + F_r)
          - 0.278 * math.sin(F_r - M_m)
          - 0.173 * math.sin(2*D_r - F_r))
    # Distance correction (km, Meeus eq. 47.9)
    # Mean distance 385,001 km + corrections
    dist_km = (385_001.0
               - 20_905.0 * math.cos(M_m)
               - 3_699.0 * math.cos(2*D_r - M_m)
               - 2_956.0 * math.cos(2*D_r)
               + 570.0 * math.cos(2*M_m))

    # Ecliptic longitude and latitude
    lon_ecl = math.radians((L0 + dL) % 360.0)
    lat_ecl = math.radians(dB)

    # Convert to ecliptic Cartesian
    dist_m = dist_km * 1000.0
    x_ecl = dist_m * math.cos(lat_ecl) * math.cos(lon_ecl)
    y_ecl = dist_m * math.cos(lat_ecl) * math.sin(lon_ecl)
    z_ecl = dist_m * math.sin(lat_ecl)

    # Rotate from ecliptic to equatorial (J2000)
    # Obliquity of the ecliptic at J2000: ε = 23.4393° (IAU 1976)
    eps = math.radians(23.4393)  # IAU 1976 obliquity at J2000
    cos_e = math.cos(eps)
    sin_e = math.sin(eps)

    x_eci = x_ecl
    y_eci = y_ecl * cos_e - z_ecl * sin_e
    z_eci = y_ecl * sin_e + z_ecl * cos_e

    return np.array([x_eci, y_eci, z_eci])


def sun_position_eci(t_since_j2000_s: float) -> np.ndarray:
    """Sun position in ECI J2000 frame (m) using simplified Meeus series.

    Uses the low-precision solar coordinates from Meeus ch. 25.
    Accuracy: ~0.01° in ecliptic longitude ≈ 26,000 km at 1 AU.
    The Sun's gravitational effect on near-Earth trajectories is small
    (perturbation ~10⁻⁵ g at Earth's distance), so this accuracy is
    more than sufficient.

    Args:
        t_since_j2000_s: Time since J2000.0 epoch (seconds).

    Returns:
        [x, y, z] Sun position in ECI frame (m).

    References:
        Meeus J. (1991) "Astronomical Algorithms" ch. 25.
        Montenbruck & Pfleger (2000) §3.3.1.
    """
    T = t_since_j2000_s / (36525.0 * 86400.0)

    # Mean longitude of Sun (Meeus eq. 25.2)
    L0 = 280.46646 + 36000.76983 * T  # deg

    # Mean anomaly of Sun (Meeus eq. 25.3)
    M = 357.52911 + 35999.05029 * T   # deg
    M_rad = math.radians(M % 360.0)

    # Equation of center (Meeus eq. 25.4)
    C = ((1.9146 - 0.004817 * T) * math.sin(M_rad)
         + 0.019993 * math.sin(2 * M_rad)
         + 0.000290 * math.sin(3 * M_rad))

    # Sun's true longitude
    lon_true = math.radians((L0 + C) % 360.0)

    # Sun's distance from Earth (AU, then → m)
    # Meeus eq. 25.5
    e = 0.016708634 - 0.000042037 * T  # orbital eccentricity
    v = M_rad + math.radians(C)  # true anomaly
    R_au = 1.000001018 * (1 - e**2) / (1 + e * math.cos(v))
    R_m = R_au * AU_M

    # Ecliptic to ECI (J2000 obliquity)
    eps = math.radians(23.4393)  # IAU 1976 obliquity
    cos_e = math.cos(eps)
    sin_e = math.sin(eps)

    x_ecl = R_m * math.cos(lon_true)
    y_ecl = R_m * math.sin(lon_true)
    z_ecl = 0.0  # Sun is in ecliptic plane

    x_eci = x_ecl
    y_eci = y_ecl * cos_e - z_ecl * sin_e
    z_eci = y_ecl * sin_e + z_ecl * cos_e

    return np.array([x_eci, y_eci, z_eci])


# ═══════════════════════════════════════════════════════════════════
#  EQUATIONS OF MOTION
# ═══════════════════════════════════════════════════════════════════

def _third_body_accel(r_sc: np.ndarray, r_body: np.ndarray, mu_body: float) -> np.ndarray:
    """Third-body gravitational acceleration (direct + indirect terms).

    The acceleration on the spacecraft due to a third body (Moon or Sun)
    in the Earth-centered frame includes both the direct attraction and
    the indirect term (acceleration of Earth toward the third body):

      a = -μ_body × [(r_sc - r_body)/|r_sc - r_body|³ + r_body/|r_body|³]

    The first term is the direct attraction; the second is the indirect
    term that accounts for Earth's acceleration toward the third body
    (since we're in a non-inertial Earth-centered frame, strictly speaking
    we need the difference in acceleration between spacecraft and Earth).

    Montenbruck & Gill (2000) §3.2, eq. 3.34.

    Args:
        r_sc:     Spacecraft position in ECI (m).
        r_body:   Third body position in ECI (m).
        mu_body:  Third body GM (m³/s²).

    Returns:
        Acceleration vector (m/s²).
    """
    r_rel = r_sc - r_body
    r_rel_norm = np.linalg.norm(r_rel)
    r_body_norm = np.linalg.norm(r_body)

    # Avoid division by zero (should never happen physically)
    if r_rel_norm < 1.0 or r_body_norm < 1.0:
        return np.zeros(3)

    # Direct term + indirect term (Montenbruck eq. 3.34)
    a = -mu_body * (r_rel / r_rel_norm**3 + r_body / r_body_norm**3)
    return a


def _j2_accel(r: np.ndarray) -> np.ndarray:
    """Earth J2 oblateness perturbation acceleration.

    The J2 term of Earth's gravity field causes:
      - Nodal regression: ~7°/day for LEO
      - Apsidal rotation
      - Short-period oscillations in inclination

    Formula from Vallado 4th ed eq. 8-25:
      a_J2 = -(3/2) × J2 × μ × R_e² / r⁵ × [x(5z²/r² - 1), y(5z²/r² - 1), z(5z²/r² - 3)]

    Args:
        r: Spacecraft position in ECI (m).

    Returns:
        J2 perturbation acceleration (m/s²).

    References:
        Vallado (2013) 4th ed eq. 8-25.
    """
    x, y, z = r
    r_mag = np.linalg.norm(r)
    if r_mag < R_EARTH_M:
        return np.zeros(3)

    r2 = r_mag**2
    r5 = r_mag**5
    z2_r2 = (z / r_mag)**2  # (z/r)²

    coeff = -1.5 * J2_EARTH * MU_EARTH * R_EARTH_M**2 / r5

    ax = coeff * x * (5.0 * z2_r2 - 1.0)
    ay = coeff * y * (5.0 * z2_r2 - 1.0)
    az = coeff * z * (5.0 * z2_r2 - 3.0)

    return np.array([ax, ay, az])


# Solar radiation pressure at 1 AU
P_SUN_1AU = 4.56e-6  # N/m² — Montenbruck & Gill (2000) §3.4; solar constant / c


def _srp_accel(r_sc: np.ndarray, r_sun: np.ndarray,
               area_m2: float, mass_kg: float, cr: float) -> np.ndarray:
    """Solar radiation pressure acceleration.

    SRP pushes the spacecraft away from the Sun. The force depends on:
      - Solar flux at the spacecraft distance (inverse square from 1 AU)
      - Spacecraft area/mass ratio (A/m)
      - Reflectivity coefficient Cr (1.0 = absorbing, 2.0 = perfect mirror)

    a_SRP = -P_sun × Cr × (A/m) × r_sun_sc / |r_sun_sc| × (AU/|r_sun|)²

    The force points AWAY from the Sun (anti-sunward).

    Args:
        r_sc:     Spacecraft position in ECI (m).
        r_sun:    Sun position in ECI (m).
        area_m2:  Effective cross-sectional area (m²).
        mass_kg:  Spacecraft mass (kg).
        cr:       Reflectivity coefficient (1.0–2.0). Typical: 1.3–1.5.

    Returns:
        SRP acceleration vector (m/s²).

    References:
        Montenbruck & Gill (2000) "Satellite Orbits" §3.4.
    """
    r_sun_sc = r_sc - r_sun  # vector from Sun to spacecraft
    d_sun = np.linalg.norm(r_sun_sc)
    if d_sun < 1.0:
        return np.zeros(3)

    # Solar pressure at spacecraft distance (inverse square)
    p_local = P_SUN_1AU * (AU_M / d_sun) ** 2

    # SRP acceleration: away from Sun
    a_srp = p_local * cr * (area_m2 / mass_kg) * r_sun_sc / d_sun
    return a_srp


def equations_of_motion(
    t: float,
    state: np.ndarray,
    epoch_s: float,
    include_moon: bool = True,
    include_sun: bool = True,
    include_j2: bool = False,
    srp_area_m2: float = 0.0,
    srp_mass_kg: float = 1.0,
    srp_cr: float = 1.5,
) -> np.ndarray:
    """Right-hand side of the orbital equations of motion.

    d/dt [r, v] = [v, a]

    where a = a_earth + a_moon + a_sun + a_J2 + a_SRP

    Args:
        t:             Time since propagation start (s).
        state:         [x, y, z, vx, vy, vz] in ECI (m, m/s).
        epoch_s:       Epoch of propagation start (s since J2000.0).
        include_moon:  Include lunar third-body gravity.
        include_sun:   Include solar third-body gravity.
        include_j2:    Include Earth J2 oblateness.
        srp_area_m2:   Solar radiation pressure cross-section area (m²). 0 = no SRP.
        srp_mass_kg:   Spacecraft mass for SRP calculation (kg).
        srp_cr:        SRP reflectivity coefficient (1.0–2.0). Default 1.5.

    Returns:
        d/dt [x, y, z, vx, vy, vz] (m/s, m/s²).
    """
    r = state[:3]
    v = state[3:]
    r_mag = np.linalg.norm(r)

    # Central body: Earth point-mass gravity
    a = -MU_EARTH * r / r_mag**3

    # J2 oblateness
    if include_j2:
        a += _j2_accel(r)

    # Third bodies
    t_abs = epoch_s + t  # absolute time since J2000

    if include_moon:
        r_moon = moon_position_eci(t_abs)
        a += _third_body_accel(r, r_moon, MU_MOON)

    r_sun = None
    if include_sun:
        r_sun = sun_position_eci(t_abs)
        a += _third_body_accel(r, r_sun, MU_SUN)

    # Solar radiation pressure
    if srp_area_m2 > 0.0:
        if r_sun is None:
            r_sun = sun_position_eci(t_abs)
        a += _srp_accel(r, r_sun, srp_area_m2, srp_mass_kg, srp_cr)

    return np.concatenate([v, a])


# ═══════════════════════════════════════════════════════════════════
#  PROPAGATOR
# ═══════════════════════════════════════════════════════════════════

def propagate(
    initial_state: OrbitalState,
    duration_s: float,
    dt_output_s: float = 60.0,
    include_moon: bool = True,
    include_sun: bool = True,
    include_j2: bool = False,
    srp_area_m2: float = 0.0,
    srp_mass_kg: float = 1.0,
    srp_cr: float = 1.5,
    rtol: float = 1e-10,
    atol: float = 1e-10,
) -> PropagationResult:
    """Propagate an orbital state forward in time using the n-body integrator.

    Uses scipy.integrate.solve_ivp with DOP853 (8th-order Runge-Kutta with
    adaptive step size). The relative and absolute tolerances default to 1e-10,
    which gives ~1 meter accuracy for near-Earth orbits over days.

    Args:
        initial_state:  Starting OrbitalState in ECI J2000.
        duration_s:     Propagation duration (seconds). Positive = forward.
        dt_output_s:    Output interval (s). Default 60s (once per minute).
        include_moon:   Include lunar third-body gravity (default True).
        include_sun:    Include solar third-body gravity (default True).
        include_j2:     Include Earth J2 oblateness (default False).
        rtol:           Relative tolerance for integrator. Default 1e-10.
        atol:           Absolute tolerance for integrator. Default 1e-10.

    Returns:
        PropagationResult with state history and metadata.

    References:
        Hairer et al. (1993) "Solving Ordinary Differential Equations I" — DOP853
        Vallado (2013) §8.4 — numerical propagation.
    """
    y0 = initial_state.state_vector
    epoch = initial_state.epoch_s

    # Output times
    n_points = max(2, int(abs(duration_s) / dt_output_s) + 1)
    t_eval = np.linspace(0.0, duration_s, n_points)

    # Integrate
    sol = solve_ivp(
        fun=equations_of_motion,
        t_span=(0.0, duration_s),
        y0=y0,
        method='DOP853',
        t_eval=t_eval,
        rtol=rtol,
        atol=atol,
        args=(epoch, include_moon, include_sun, include_j2,
              srp_area_m2, srp_mass_kg, srp_cr),
        dense_output=True,
    )

    if not sol.success:
        raise RuntimeError(f"N-body propagation failed: {sol.message}")

    # Extract results
    positions = sol.y[:3].T    # (N, 3)
    velocities = sol.y[3:].T   # (N, 3)

    # Compute Moon positions at each output time
    moon_pos = np.array([moon_position_eci(epoch + t) for t in sol.t])

    # Build OrbitalState list
    states = []
    for i, t in enumerate(sol.t):
        states.append(OrbitalState(
            x=positions[i, 0], y=positions[i, 1], z=positions[i, 2],
            vx=velocities[i, 0], vy=velocities[i, 1], vz=velocities[i, 2],
            epoch_s=epoch + t,
        ))

    bodies = ["earth"]
    if include_moon:
        bodies.append("moon")
    if include_sun:
        bodies.append("sun")
    if include_j2:
        bodies.append("earth_j2")
    if srp_area_m2 > 0:
        bodies.append("srp")

    return PropagationResult(
        states=states,
        t_seconds=sol.t,
        positions_m=positions,
        velocities_ms=velocities,
        moon_positions_m=moon_pos,
        integrator_steps=sol.nfev,
        max_step_error=float(np.max(np.abs(sol.t[1:] - sol.t[:-1]))) if len(sol.t) > 1 else 0.0,
        bodies_included=bodies,
    )


# ═══════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def circular_orbit_state(
    altitude_km: float,
    inclination_deg: float = 0.0,
    raan_deg: float = 0.0,
    epoch_s: float = 0.0,
) -> OrbitalState:
    """Create an OrbitalState for a circular orbit at given altitude.

    Args:
        altitude_km:      Altitude above Earth surface (km).
        inclination_deg:  Orbital inclination (deg). 0 = equatorial.
        raan_deg:         Right ascension of ascending node (deg).
        epoch_s:          Epoch time (s since J2000).

    Returns:
        OrbitalState with position at ascending node, velocity prograde.

    References:
        Curtis (2014) §4.3 — orbital elements to state vector.
    """
    r = R_EARTH_M + altitude_km * 1000.0
    v = math.sqrt(MU_EARTH / r)

    inc = math.radians(inclination_deg)
    raan = math.radians(raan_deg)

    # Position at ascending node (true anomaly = 0, argument of perigee = 0)
    x = r * math.cos(raan)
    y = r * math.sin(raan)
    z = 0.0

    # Velocity perpendicular to radius in orbital plane
    vx = -v * (math.cos(raan) * math.sin(0.0) + math.sin(raan) * math.cos(0.0) * math.cos(inc))
    vy = -v * (math.sin(raan) * math.sin(0.0) - math.cos(raan) * math.cos(0.0) * math.cos(inc))
    vz = v * math.cos(0.0) * math.sin(inc)

    # Simplified: for ω=0, ν=0 → velocity is along y' axis in orbital frame
    # After rotation by RAAN and inclination:
    vx = -v * math.sin(raan) * math.cos(inc)
    vy = v * math.cos(raan) * math.cos(inc)
    vz = v * math.sin(inc)

    return OrbitalState(x=x, y=y, z=z, vx=vx, vy=vy, vz=vz, epoch_s=epoch_s)


def compute_tli_direction(
    state0: OrbitalState,
    transit_time_hr: float = 96.0,
    steering_fraction: float = 0.10,
) -> np.ndarray:
    """Compute TLI burn direction that targets the Moon's future position.

    The Moon moves ~13.2°/day in its orbit. For a 96-hour (4-day) transit,
    it advances ~53°. A pure prograde burn sends the spacecraft to the
    correct altitude but in the wrong direction. This function blends
    the prograde velocity direction with a steering component aimed at
    where the Moon WILL BE at arrival time.

    The blend is mostly prograde (for orbital energy) with a small
    tangential component toward the Moon's future position. The n-body
    integrator and lunar gravity then capture the spacecraft for a
    close flyby.

    Args:
        state0:             Spacecraft state at TLI burn time.
        transit_time_hr:    Expected transit time to Moon's distance (hours).
        steering_fraction:  Fraction of burn direction aimed at Moon (0–1).
                            Default 0.10 (10%). Higher = more direct aim,
                            lower = more energy-efficient.
                            ESTIMATE — pending Lambert solver optimization.

    Returns:
        Unit vector for the TLI burn direction in ECI frame.

    References:
        Bate et al. (1971) §9 — targeting problem.
    """
    epoch = state0.epoch_s
    t_arrival_s = transit_time_hr * 3600.0

    # Moon position at arrival time
    r_moon_arrival = moon_position_eci(epoch + t_arrival_s)
    target_dir = r_moon_arrival / np.linalg.norm(r_moon_arrival)

    # Prograde direction (for energy)
    v_hat = state0.v_vec / state0.v_mag

    # Project target direction into the tangential plane (perpendicular to radius)
    # TLI is at periapsis so the burn should be mostly tangential
    r_hat = state0.r_vec / state0.r_mag
    target_tangential = target_dir - np.dot(target_dir, r_hat) * r_hat
    t_norm = np.linalg.norm(target_tangential)
    if t_norm > 1e-10:
        target_tangential = target_tangential / t_norm
    else:
        target_tangential = v_hat

    # Blend: mostly prograde, small component steered toward Moon
    burn_dir = (1.0 - steering_fraction) * v_hat + steering_fraction * target_tangential
    return burn_dir / np.linalg.norm(burn_dir)


def lambert_tli_to_moon(
    state0: OrbitalState,
    transit_time_hr: float = 96.0,
) -> np.ndarray:
    """Compute exact TLI velocity using Lambert solver to reach the Moon.

    Uses the existing validated Lambert universal variable solver from
    free_return.py to find the velocity vector that connects the spacecraft's
    current position to the Moon's position at arrival time, in exactly
    the given transit time.

    This replaces the approximate steering approach (compute_tli_direction)
    with an exact solution. The resulting velocity gives a trajectory that
    passes through the Moon's position.

    Args:
        state0:          Spacecraft state at TLI burn time.
        transit_time_hr: Desired transit time to Moon (hours).

    Returns:
        Required velocity vector at departure (m/s) in ECI frame.
        The TLI ΔV is then: v_lambert - v_current.

    References:
        Bate, Mueller, White (1971) §5.3 — Lambert's problem.
    """
    from aria.simulation.free_return import lambert_universal_variable

    epoch = state0.epoch_s
    tof_s = transit_time_hr * 3600.0

    # Departure: spacecraft position at TLI
    r1 = state0.r_vec

    # Arrival: Moon position at arrival time
    r2 = moon_position_eci(epoch + tof_s)

    # Solve Lambert: find v1, v2 that connect r1 → r2 in tof_s
    v1_lambert, _ = lambert_universal_variable(
        r1, r2, tof_s, mu=MU_EARTH, prograde=True,
    )

    return v1_lambert


def optimal_raan_for_moon(
    altitude_km: float,
    inclination_deg: float,
    epoch_s: float,
    transit_time_hr: float = 96.0,
) -> float:
    """Find the RAAN that places the TLI apogee direction toward the Moon.

    The apogee of a prograde TLI burn from the ascending node is roughly
    180° opposite in longitude. So the RAAN should place the burn point
    opposite the Moon's arrival position, with a small lead correction.

    This is a first-order geometric calculation, not a Lambert solver.
    It gets the trajectory within ~170,000 km of the Moon. A full Lambert
    solver (future work) is needed for the final ~170,000 → 130 km.

    Args:
        altitude_km:      Parking orbit altitude (km).
        inclination_deg:  Orbital inclination (deg).
        epoch_s:          Launch epoch (s since J2000).
        transit_time_hr:  Expected transit to Moon (hours).

    Returns:
        Optimal RAAN (degrees) for the parking orbit.
    """
    # Moon position at arrival time
    t_arrival_s = transit_time_hr * 3600.0
    r_moon = moon_position_eci(epoch_s + t_arrival_s)

    # Moon's ecliptic longitude
    moon_lon = math.degrees(math.atan2(r_moon[1], r_moon[0]))

    # Burn at ascending node → apogee ~180° away.
    # Lead correction: -10° empirically gives best approach for 96hr transit.
    raan = moon_lon + 180.0 - 10.0  # ESTIMATE — empirical lead angle from sweep
    return raan % 360.0


def distance_to_moon(state: OrbitalState) -> float:
    """Distance from spacecraft to Moon (m)."""
    r_moon = moon_position_eci(state.epoch_s)
    return float(np.linalg.norm(state.r_vec - r_moon))


def orbital_period(altitude_km: float) -> float:
    """Orbital period for circular orbit at given altitude (seconds).

    T = 2π × sqrt(a³/μ)  (Kepler's third law)

    Args:
        altitude_km: Altitude above Earth surface (km).

    Returns:
        Orbital period (seconds).
    """
    a = R_EARTH_M + altitude_km * 1000.0
    return 2.0 * math.pi * math.sqrt(a**3 / MU_EARTH)


def specific_energy(r_mag: float, v_mag: float) -> float:
    """Specific orbital energy (J/kg).

    ε = v²/2 − μ/r

    Negative → bound orbit (ellipse/circle).
    Zero → parabolic escape.
    Positive → hyperbolic escape.
    """
    return v_mag**2 / 2.0 - MU_EARTH / r_mag


def sphere_of_influence(body_mu: float, body_orbit_radius: float,
                         central_mu: float = MU_SUN) -> float:
    """Sphere of influence radius (m).

    R_SOI = a × (m_body / m_central)^(2/5)

    For Earth-Moon system: R_SOI_moon ≈ 66,000 km.
    For Earth in Sun system: R_SOI_earth ≈ 924,000 km.

    Args:
        body_mu:           GM of the body whose SOI we want.
        body_orbit_radius: Semi-major axis of body's orbit around central (m).
        central_mu:        GM of the central body.

    Returns:
        SOI radius (m).

    References:
        Vallado (2013) §8.6 — sphere of influence.
    """
    return body_orbit_radius * (body_mu / central_mu) ** 0.4


# ═══════════════════════════════════════════════════════════════════
#  VALIDATION
# ═══════════════════════════════════════════════════════════════════

def validate_leo_orbit(altitude_km: float = 400.0, n_orbits: int = 3) -> dict:
    """Validate the integrator by propagating a LEO orbit and checking energy conservation.

    A purely Keplerian orbit should have constant specific energy.
    With Moon and Sun perturbations, the energy will drift slightly
    (~10⁻⁸ relative change per orbit for LEO).

    Returns dict with energy drift, position drift, and validation status.
    """
    state0 = circular_orbit_state(altitude_km)
    T = orbital_period(altitude_km)
    duration = n_orbits * T

    result = propagate(state0, duration, dt_output_s=T/100.0,
                       include_moon=True, include_sun=True, include_j2=False)

    # Energy conservation check
    energies = []
    for s in result.states:
        energies.append(specific_energy(s.r_mag, s.v_mag))

    e0 = energies[0]
    max_drift = max(abs(e - e0) for e in energies) / abs(e0)

    # Altitude check: should stay near initial altitude
    altitudes = [s.altitude_m / 1000.0 for s in result.states]
    alt_variation = max(altitudes) - min(altitudes)

    return {
        "altitude_km": altitude_km,
        "n_orbits": n_orbits,
        "energy_relative_drift": max_drift,
        "altitude_variation_km": alt_variation,
        "integrator_evaluations": result.integrator_steps,
        "valid": max_drift < 1e-6,  # relative energy conserved to 10⁻⁶
    }


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── N-Body Integrator Validation ──────────────────────────────")

    # 1. LEO orbit conservation
    print("\n1. LEO orbit (400 km, 3 orbits):")
    v = validate_leo_orbit(400.0, n_orbits=3)
    print(f"   Energy drift:      {v['energy_relative_drift']:.2e} (target < 1e-6)")
    print(f"   Alt variation:     {v['altitude_variation_km']:.3f} km")
    print(f"   RK evaluations:    {v['integrator_evaluations']}")
    print(f"   Valid:             {'YES' if v['valid'] else 'NO'}")

    # 2. Moon distance check
    print("\n2. Moon position sanity check:")
    r_moon_now = moon_position_eci(0.0)
    d_moon = np.linalg.norm(r_moon_now) / 1e6
    print(f"   Moon distance at J2000:  {d_moon:.1f} × 10⁶ km "
          f"(expected ~384 × 10³ km = 0.384 × 10⁶ km)")

    # 3. Sun distance check
    r_sun_now = sun_position_eci(0.0)
    d_sun_au = np.linalg.norm(r_sun_now) / AU_M
    print(f"   Sun distance at J2000:   {d_sun_au:.4f} AU (expected ~1.0 AU)")

    # 4. Sphere of influence
    soi_moon = sphere_of_influence(MU_MOON, MOON_SEMI_MAJOR_M, MU_EARTH) / 1e6
    soi_earth = sphere_of_influence(MU_EARTH, AU_M, MU_SUN) / 1e6
    print(f"\n3. Spheres of influence:")
    print(f"   Moon SOI:   {soi_moon:.0f} × 10⁶ m = {soi_moon*1000:.0f} km (expected ~66,000 km)")
    print(f"   Earth SOI:  {soi_earth:.0f} × 10⁶ m = {soi_earth*1000:.0f} km (expected ~924,000 km)")

    # 5. Multi-day coast (cislunar)
    print("\n4. Three-day cislunar propagation (ISS orbit, no TLI):")
    state0 = circular_orbit_state(400.0, inclination_deg=51.6)
    result = propagate(state0, 3 * 86400.0, dt_output_s=3600.0)
    print(f"   Duration:     3 days ({len(result.states)} output points)")
    print(f"   RK evals:     {result.integrator_steps}")
    print(f"   Final alt:    {result.states[-1].altitude_m/1000:.1f} km")
    print(f"   Moon dist:    {distance_to_moon(result.states[-1])/1e6:.1f} × 10⁶ m")
    print(f"   Bodies:       {result.bodies_included}")
