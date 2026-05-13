"""Atmospheric density models for orbit decay and aerodynamic forces.

Provides density models at altitudes from surface to 1000+ km:

- **COESA76**: U.S. Standard Atmosphere 1976 (0-1000 km, piecewise layers)
- **Exponential**: Simple scale-height model (faster, less accurate)
- **Jacchia77-like**: Temperature-scaled density for high atmosphere
  (500-2000 km where solar activity dominates)

For precise orbit propagation, use NRLMSISE-00 which includes species
breakdown (N₂, O, O₂, Ar, He, H) — but it's a large data tables model.
The models here are analytical approximations sufficient for:
- LEO drag budgeting
- Decay-lifetime estimation
- Aerodynamic heating calculations
- Re-entry trajectory prediction

References:
    U.S. Standard Atmosphere 1976, NASA TM-X-74335
    Jacchia, L.G. (1977). SAO Special Report 375
    Vallado (2013) §8.6, Tables 8-4 through 8-7
    Hedin, A.E. (1987). "MSIS-86 Thermospheric Model"
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ══════════════════════════════════════════════════════════════════
#  U.S. Standard Atmosphere 1976 (piecewise)
# ══════════════════════════════════════════════════════════════════

# (altitude_km, density_kg_m3, scale_height_m) for altitudes 0-1000 km
# From Vallado 2013 Table 8-4.
_COESA76_LAYERS: list[tuple[float, float, float]] = [
    (0,    1.225,        8440.0),
    (25,   3.899e-2,     6349.0),
    (30,   1.774e-2,     6682.0),
    (40,   3.972e-3,     7554.0),
    (50,   1.057e-3,     8382.0),
    (60,   3.206e-4,     7714.0),
    (70,   8.770e-5,     6549.0),
    (80,   1.905e-5,     5799.0),
    (90,   3.396e-6,     5382.0),
    (100,  5.297e-7,     5877.0),
    (110,  9.661e-8,     7263.0),
    (120,  2.438e-8,     9473.0),
    (130,  8.484e-9,     12636.0),
    (140,  3.845e-9,     16149.0),
    (150,  2.070e-9,     22523.0),
    (180,  5.464e-10,    29740.0),
    (200,  2.789e-10,    37105.0),
    (250,  7.248e-11,    45546.0),
    (300,  2.418e-11,    53628.0),
    (350,  9.518e-12,    53298.0),
    (400,  3.725e-12,    58515.0),
    (450,  1.585e-12,    60828.0),
    (500,  6.967e-13,    63822.0),
    (600,  1.454e-13,    71835.0),
    (700,  3.614e-14,    88667.0),
    (800,  1.170e-14,   124640.0),
    (900,  5.245e-15,   181050.0),
    (1000, 3.019e-15,   268000.0),
]


def coesa76_density(altitude_m: float) -> float:
    """US Standard Atmosphere 1976 density at altitude.

    Uses piecewise exponential interpolation between tabulated values.
    Valid 0 to 1000 km. Returns 0 for altitudes above 1000 km.

    Args:
        altitude_m: altitude above mean sea level [m]

    Returns:
        density [kg/m³]

    Reference: NASA TM-X-74335, Vallado 2013 Table 8-4.
    """
    alt_km = altitude_m / 1000.0

    if alt_km < 0:
        return _COESA76_LAYERS[0][1]
    if alt_km >= 1000:
        return 0.0

    # Find the layer
    for i in range(len(_COESA76_LAYERS) - 1):
        h0, rho0, H = _COESA76_LAYERS[i]
        h1 = _COESA76_LAYERS[i + 1][0]
        if h0 <= alt_km < h1:
            # Exponential interpolation within the layer
            return rho0 * math.exp(-(altitude_m - h0 * 1000.0) / H)

    return _COESA76_LAYERS[-1][1]


def exponential_density(
    altitude_m: float,
    rho0: float = 1.225,
    h0_m: float = 0.0,
    scale_height_m: float = 7500.0,
) -> float:
    """Simple exponential density model.

    rho(h) = rho0 * exp(-(h - h0) / H)

    Fast approximation — accurate to ~20% in the 0-200 km range if
    tuned for the altitude of interest. For better accuracy use
    coesa76_density() which has altitude-dependent scale heights.
    """
    return rho0 * math.exp(-(altitude_m - h0_m) / scale_height_m)


# ══════════════════════════════════════════════════════════════════
#  Thermospheric density with solar activity scaling (Jacchia-like)
# ══════════════════════════════════════════════════════════════════

def jacchia_like_density(
    altitude_m: float,
    f107: float = 150.0,
    f107_81day_avg: float = 150.0,
    ap: float = 4.0,
) -> float:
    """Thermospheric density scaled by solar activity.

    For altitudes 200-1000 km, density varies by up to 10× between
    solar minimum (F10.7 ~70) and solar maximum (F10.7 ~250).

    Args:
        altitude_m: altitude [m]
        f107: 10.7 cm solar flux [sfu] (70-300)
        f107_81day_avg: 81-day running average F10.7
        ap: geomagnetic activity index (0-400)

    Returns:
        density [kg/m³]

    Reference: Jacchia 1977 SAO Special Report 375.
    Simplified model — for flight use NRLMSISE-00 or JB2008.
    """
    # Base density from COESA76 (solar-moderate baseline, F10.7 ~150)
    base_density = coesa76_density(altitude_m)

    # Solar activity scaling (empirical, Vallado 2013 §8.6.2):
    # For altitudes above 200 km, density scales roughly as:
    # rho = rho_base * (f107 / 150)^k * exp(alpha * ap)
    # where k depends on altitude (~1-2 in thermosphere, 0 below 100km)
    alt_km = altitude_m / 1000.0
    if alt_km < 100:
        return base_density
    if alt_km > 1000:
        return 0.0

    # Scaling exponent grows with altitude
    k = min(2.0, 0.005 * (alt_km - 100))

    # Solar flux scaling
    f_scale = (max(f107, 70.0) / 150.0) ** k

    # Geomagnetic activity bump (small)
    ap_scale = math.exp(0.01 * max(ap - 4.0, 0.0))

    # 81-day average affects thermospheric temperature
    t_scale = 1.0 + 0.002 * (f107_81day_avg - 150.0)

    return base_density * f_scale * ap_scale * max(t_scale, 0.5)


# ══════════════════════════════════════════════════════════════════
#  Orbit decay estimation
# ══════════════════════════════════════════════════════════════════

@dataclass
class DecayEstimate:
    """Estimated orbital decay lifetime."""
    altitude_initial_km: float
    lifetime_days: float
    lifetime_years: float
    altitude_km_per_day_loss: float
    periapsis_altitude_at_decay_km: float = 80.0  # re-entry altitude


def estimate_decay_lifetime(
    altitude_km: float,
    area_over_mass_m2_kg: float = 0.01,
    C_D: float = 2.2,
    f107: float = 150.0,
    R_earth_m: float = 6378137.0,
    mu_earth: float = 3.986e14,
) -> DecayEstimate:
    """Estimate orbital decay lifetime for a circular LEO orbit.

    Uses the drag equation and empirical scaling. For eccentric orbits
    or precision estimates, use a full numerical integration with
    NRLMSISE-00.

    Args:
        altitude_km: circular orbit altitude [km]
        area_over_mass_m2_kg: A/m ratio (0.01 for typical cubesat-like,
            0.03 for ISS-like)
        C_D: drag coefficient (~2.2 for tumbling, 2.0 for streamlined)
        f107: solar flux

    Returns:
        DecayEstimate with lifetime days/years and decay rate

    Reference: Vallado 2013 §8.6.3 Eq. (8-41).
    """
    r = R_earth_m + altitude_km * 1000.0
    v = math.sqrt(mu_earth / r)
    rho = jacchia_like_density(altitude_km * 1000.0, f107=f107)

    # Drag deceleration: a = 0.5 * rho * v² * C_D * A/m
    a_drag = 0.5 * rho * v ** 2 * C_D * area_over_mass_m2_kg

    if a_drag <= 0:
        return DecayEstimate(
            altitude_initial_km=altitude_km,
            lifetime_days=float("inf"),
            lifetime_years=float("inf"),
            altitude_km_per_day_loss=0.0,
        )

    # Altitude loss rate: dh/dt = -2 * a_drag * r / v  (orbit-averaged)
    # In one orbital period, the spacecraft loses 2π * a_drag * r / v² of
    # semi-major axis. Per day:
    dh_dt_m_s = -2.0 * a_drag * r / v  # m/s altitude loss
    dh_per_day_km = abs(dh_dt_m_s) * 86400.0 / 1000.0

    # Rough lifetime: time to drop to ~80 km re-entry altitude
    altitude_to_lose_km = altitude_km - 80.0
    # Decay rate accelerates as altitude drops (density grows exp)
    # Empirical: effective lifetime ≈ 2× naive estimate
    lifetime_days = altitude_to_lose_km / max(dh_per_day_km, 1e-30) * 2.0

    return DecayEstimate(
        altitude_initial_km=altitude_km,
        lifetime_days=lifetime_days,
        lifetime_years=lifetime_days / 365.25,
        altitude_km_per_day_loss=dh_per_day_km,
    )


# ══════════════════════════════════════════════════════════════════
#  Aerodynamic heating
# ══════════════════════════════════════════════════════════════════

def stagnation_heat_flux_chapman(
    velocity_ms: float,
    density_kg_m3: float,
    nose_radius_m: float = 0.3,
) -> float:
    """Stagnation-point heat flux using Chapman's approximation.

    q = k * sqrt(rho / R_nose) * v³

    where k = 1.7415e-4 in SI units (for air, Chapman 1958).

    Used for re-entry trajectory analysis and TPS sizing.

    Args:
        velocity_ms: vehicle velocity [m/s]
        density_kg_m3: atmospheric density [kg/m³]
        nose_radius_m: effective nose radius [m]

    Returns:
        Heat flux [W/m²]

    Reference: Chapman 1958 NACA TN 4276, Allen & Eggers 1958.
    """
    if nose_radius_m <= 0 or density_kg_m3 <= 0:
        return 0.0
    k = 1.7415e-4  # Chapman constant for air
    return k * math.sqrt(density_kg_m3 / nose_radius_m) * velocity_ms ** 3
