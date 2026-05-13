"""
Space weather effects on atmospheric drag and orbital prediction accuracy.

During geomagnetic storms (Kp > 5), atmospheric density at LEO altitudes
can increase by 10-100x, causing:
  - Rapid orbital decay (10x normal)
  - In-track position errors of kilometers within hours
  - TLE-derived B* becoming stale almost immediately

This module provides:
  1. Drag uncertainty scaling based on altitude and solar/geomagnetic activity
  2. Additional in-track covariance inflation during active periods
  3. Kp/F10.7 activity level classification

Sources:
  - NOAA SWPC: Space weather indices
  - Jacchia-Roberts atmospheric model empirical fits
  - MSISE-90 density variation studies (Doornbos et al., 2008)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np


class ActivityLevel(Enum):
    """Space weather activity classification."""
    QUIET = "QUIET"        # Kp 0-2, F10.7 < 100
    MODERATE = "MODERATE"  # Kp 3-4, F10.7 100-150
    ACTIVE = "ACTIVE"      # Kp 5-6, F10.7 150-200
    STORM = "STORM"        # Kp 7+, F10.7 > 200


@dataclass
class SpaceWeatherState:
    """Current space weather conditions."""

    kp_index: float = 2.0      # ESTIMATE — Kp=2 quiet conditions (Menvielle & Berthelier 1991 Rev Geophys 29 415)
    f107_index: float = 120.0  # ESTIMATE — F10.7=120 SFU moderate solar activity (Tapping 2013 Space Weather 11 394)
    f107_avg: float = 120.0    # ESTIMATE — 81-day centered F10.7 average (Tapping 2013)
    ap_index: float = 7.0      # ESTIMATE — Ap=7 quiet activity (Menvielle & Berthelier 1991)

    @property
    def activity_level(self) -> ActivityLevel:
        if self.kp_index >= 7 or self.f107_index > 200:
            return ActivityLevel.STORM
        elif self.kp_index >= 5 or self.f107_index > 150:
            return ActivityLevel.ACTIVE
        elif self.kp_index >= 3 or self.f107_index > 100:
            return ActivityLevel.MODERATE
        return ActivityLevel.QUIET


def drag_uncertainty_factor(
    altitude_km: float,
    weather: SpaceWeatherState | None = None,
) -> float:
    """Compute multiplicative factor for in-track uncertainty due to drag.

    Returns a factor by which the in-track σ should be multiplied to
    account for atmospheric density uncertainty at the given altitude
    and space weather conditions.

    The factor accounts for:
      1. Altitude-dependent drag sensitivity (exponential atmosphere)
      2. Geomagnetic activity enhancement
      3. Solar cycle phase (F10.7)

    Args:
        altitude_km: Orbital altitude (km)
        weather: Current space weather state (defaults to moderate)

    Returns:
        Multiplicative factor ≥ 1.0 for in-track σ
    """
    if weather is None:
        weather = SpaceWeatherState()

    # Base factor: altitude-dependent drag sensitivity
    # Below 400 km: drag dominates, uncertainty is high
    # 400-800 km: moderate drag
    # Above 800 km: drag negligible, SRP dominates
    if altitude_km < 200:
        alt_factor = 5.0   # ESTIMATE — very high drag at <200 km (NRLMSISE-00: ρ ~ 10⁻⁸ kg/m³ at 200 km)
    elif altitude_km < 400:
        alt_factor = 1.0 + 4.0 * math.exp(-(altitude_km - 200) / 100)  # ESTIMATE — exponential fit to NRLMSISE-00
    elif altitude_km < 800:
        alt_factor = 1.0 + 1.5 * math.exp(-(altitude_km - 400) / 200)  # ESTIMATE — moderate drag regime
    else:
        alt_factor = 1.0  # above ~800 km, drag is minor (Vallado & Finkleman 2014 Acta Astronaut 95 141)

    # Geomagnetic enhancement factor
    # During storms, density can increase 10-100x at 400 km (Emmert 2015 Adv Space Res 55 2320)
    kp_factor = {
        ActivityLevel.QUIET: 1.0,   # Kp<3 baseline
        ActivityLevel.MODERATE: 1.5,  # ESTIMATE — Kp 3-5: ~1.5× density increase (Emmert 2015)
        ActivityLevel.ACTIVE: 3.0,    # ESTIMATE — Kp 5-7: ~3× (Emmert 2015)
        ActivityLevel.STORM: 10.0,    # ESTIMATE — Kp≥7: up to 10× (Emmert 2015 Fig.4)
    }[weather.activity_level]

    # Solar cycle enhancement
    # At solar maximum (F10.7 ~ 200), density at 400km is ~5x higher than
    # at solar minimum (F10.7 ~ 70), making drag predictions harder
    # (Emmert 2015 Adv Space Res 55 2320; Marcos 1993 AAS 93-408)
    solar_factor = 1.0 + 0.5 * max(0, (weather.f107_index - 100)) / 100  # ESTIMATE — Marcos 1993 fit

    return alt_factor * kp_factor * solar_factor


def inflate_covariance_for_drag(
    covariance_rtn: np.ndarray,
    altitude_km: float,
    weather: SpaceWeatherState | None = None,
) -> np.ndarray:
    """Inflate the in-track component of an RTN covariance for drag uncertainty.

    Only the T (in-track / transverse) component is inflated, as drag
    uncertainty primarily manifests as along-track timing error.

    Args:
        covariance_rtn: 3x3 covariance in RTN frame (km²)
        altitude_km: Orbital altitude (km)
        weather: Current space weather conditions

    Returns:
        Inflated 3x3 covariance in RTN frame (km²)
    """
    factor = drag_uncertainty_factor(altitude_km, weather)

    C = np.array(covariance_rtn, dtype=np.float64)
    # Inflate T component: σ_T → σ_T × factor, so σ_T² → σ_T² × factor²
    C[1, 1] *= factor**2
    # Also inflate cross-terms involving T
    C[0, 1] *= factor
    C[1, 0] *= factor
    C[1, 2] *= factor
    C[2, 1] *= factor

    return C
