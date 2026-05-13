"""
Maneuver detection from TLE time-series.

Detects unannounced satellite maneuvers by comparing consecutive TLEs
for the same NORAD ID. A maneuver causes sudden discontinuities in:
  - Mean motion (n) — orbital altitude change
  - RAAN (Ω) — plane change
  - Eccentricity — orbit shape change

Detection thresholds are calibrated to distinguish maneuvers from
normal TLE fitting noise and J2/drag perturbations.

Typical TLE fitting noise (1σ):
  Δn ~ 0.001 rev/day for LEO
  ΔΩ ~ 0.01° per update for LEO
  Δe ~ 0.0001 per update

Maneuver thresholds (> 5σ of fitting noise):
  |Δn| > 0.01 rev/day  → altitude-changing maneuver
  |ΔΩ| > 0.1°          → plane change (rare, expensive)
  |Δe| > 0.001          → eccentricity change
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from aria.conjunction.core.types import SpaceObject


@dataclass
class ManeuverFlag:
    """A detected maneuver event."""

    norad_id: str
    name: str
    detected_at: datetime
    delta_mean_motion: float  # rev/day
    delta_raan_deg: float
    delta_eccentricity: float
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    reason: str


# Thresholds for maneuver detection (conservative — minimize false negatives)
# Based on Oltrogge & Alfano 2013 Adv Astronaut Sci 150 § "Maneuver detection survey"
DELTA_N_THRESHOLD = 0.005       # ESTIMATE — 0.005 rev/day ≈ 370 m altitude change (Oltrogge 2013 §3)
DELTA_RAAN_THRESHOLD_DEG = 0.05  # ESTIMATE — 0.05 deg RAAN change after J2 drift removal (Oltrogge 2013)
DELTA_ECC_THRESHOLD = 0.0005    # ESTIMATE — eccentricity change threshold (Oltrogge 2013 §3)


def detect_maneuver(
    tle_old: SpaceObject,
    tle_new: SpaceObject,
    dt_hours: float | None = None,
) -> ManeuverFlag | None:
    """Compare two consecutive TLEs for the same object and detect maneuvers.

    Args:
        tle_old: Previous TLE
        tle_new: Updated TLE (must be same NORAD ID)
        dt_hours: Time between TLEs in hours (computed from epochs if None)

    Returns:
        ManeuverFlag if maneuver detected, None otherwise
    """
    if tle_old.norad_id != tle_new.norad_id:
        return None

    e_old = tle_old.elements
    e_new = tle_new.elements
    if e_old is None or e_new is None:
        return None

    # Time between TLEs
    if dt_hours is None:
        dt = (e_new.epoch - e_old.epoch).total_seconds() / 3600.0
    else:
        dt = dt_hours

    if dt <= 0:
        return None

    # Mean motion change (rev/day)
    n_old_rpd = e_old.mean_motion_rad_per_s * 86400.0 / (2 * math.pi)
    n_new_rpd = e_new.mean_motion_rad_per_s * 86400.0 / (2 * math.pi)
    delta_n = abs(n_new_rpd - n_old_rpd)

    # RAAN change after removing expected J2 drift
    from aria.conjunction.screening.orbital_plane import _j2_secular_rates
    raan_rate, argp_rate = _j2_secular_rates(
        e_old.semi_major_axis, e_old.eccentricity, e_old.inclination
    )
    expected_raan_drift = raan_rate * dt * 3600.0  # rad
    actual_raan_change = e_new.raan - e_old.raan
    residual_raan = abs(actual_raan_change - expected_raan_drift)
    delta_raan_deg = math.degrees(residual_raan)

    # Eccentricity change
    delta_ecc = abs(e_new.eccentricity - e_old.eccentricity)

    # Check thresholds
    reasons = []
    if delta_n > DELTA_N_THRESHOLD:
        reasons.append(f"Δn={delta_n:.4f} rev/day (>{DELTA_N_THRESHOLD})")
    if delta_raan_deg > DELTA_RAAN_THRESHOLD_DEG:
        reasons.append(f"ΔΩ={delta_raan_deg:.3f}° (>{DELTA_RAAN_THRESHOLD_DEG}°)")
    if delta_ecc > DELTA_ECC_THRESHOLD:
        reasons.append(f"Δe={delta_ecc:.5f} (>{DELTA_ECC_THRESHOLD})")

    if not reasons:
        return None

    confidence = "HIGH" if len(reasons) >= 2 else ("HIGH" if delta_n > 0.05 else "MEDIUM")

    return ManeuverFlag(
        norad_id=tle_new.norad_id,
        name=tle_new.name,
        detected_at=e_new.epoch,
        delta_mean_motion=delta_n,
        delta_raan_deg=delta_raan_deg,
        delta_eccentricity=delta_ecc,
        confidence=confidence,
        reason="; ".join(reasons),
    )
