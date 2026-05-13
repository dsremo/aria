"""
Delta-V (ΔV) calculation for collision avoidance maneuvers.

Uses the full Clohessy-Wiltshire (CW) state transition matrix for relative
motion in circular orbits, not just the secular approximation.

CW equations of relative motion (Hill frame):
  ẍ - 2nẏ - 3n²x = 0    (radial)
  ÿ + 2nẋ = 0            (in-track)
  z̈ + n²z = 0            (cross-track)

Full CW state transition matrix Φ(t):
  x(t) = (4 - 3cos(nt))x₀ + sin(nt)ẋ₀/n + 2(1-cos(nt))ẏ₀/n
  y(t) = 6(sin(nt)-nt)x₀ + y₀ - 2(1-cos(nt))ẋ₀/n + (4sin(nt)-3nt)ẏ₀/n
  z(t) = cos(nt)z₀ + sin(nt)ż₀/n

The secular in-track drift term is: Δy_secular = -3/2 n Δt Δvx (from radial ΔV)
The in-track ΔV contribution is: Δy = (4sin(nt)-3nt)Δvy/n

Both oscillatory AND secular terms are now included for all three directions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from aria.conjunction.core.constants import MU_EARTH_KM


@dataclass
class BurnRecommendation:
    """A recommended collision avoidance burn."""

    direction: str  # "IN_TRACK", "CROSS_TRACK", "RADIAL"
    delta_v_m_s: float  # ΔV magnitude in m/s
    delta_v_km_s: float  # ΔV magnitude in km/s
    lead_time_hours: float  # time before TCA
    expected_separation_km: float  # post-maneuver separation at TCA
    efficiency: float  # km separation per m/s ΔV
    sign: int = 1  # +1 = prograde/outward/north, -1 = retrograde/inward/south
    delta_v_rtn: np.ndarray = field(default_factory=lambda: np.zeros(3))  # [R, T, N] impulse vector


def cw_displacement(
    delta_v_rtn: np.ndarray,
    lead_time_seconds: float,
    semi_major_axis_km: float,
) -> np.ndarray:
    """Compute the displacement at TCA from a ΔV impulse using full CW equations.

    Starting from zero relative position, applies ΔV in RTN and propagates
    the CW equations to find displacement at TCA.

    Args:
        delta_v_rtn: [Δv_R, Δv_T, Δv_N] impulse in km/s (RTN frame)
        lead_time_seconds: Time from burn to TCA (seconds)
        semi_major_axis_km: Orbit semi-major axis (km)

    Returns:
        [Δx, Δy, Δz] displacement at TCA in RTN (km)
    """
    n = math.sqrt(MU_EARTH_KM / semi_major_axis_km**3)
    t = lead_time_seconds
    nt = n * t

    dvr, dvt, dvn = delta_v_rtn[0], delta_v_rtn[1], delta_v_rtn[2]

    sin_nt = math.sin(nt)
    cos_nt = math.cos(nt)

    # CW state transition: position from velocity impulse at t=0
    # x(t) = sin(nt)/n × dvr + 2(1-cos(nt))/n × dvt
    # y(t) = -2(1-cos(nt))/n × dvr + (4sin(nt)-3nt)/n × dvt
    # z(t) = sin(nt)/n × dvn
    dx = sin_nt / n * dvr + 2 * (1 - cos_nt) / n * dvt
    dy = -2 * (1 - cos_nt) / n * dvr + (4 * sin_nt - 3 * nt) / n * dvt
    dz = sin_nt / n * dvn

    return np.array([dx, dy, dz])


def compute_intrack_delta_v(
    desired_separation_km: float,
    lead_time_seconds: float,
    semi_major_axis_km: float,
) -> float:
    """Compute in-track ΔV for desired in-track separation at TCA.

    Full CW: Δy = (4sin(nt) - 3nt)/n × Δv_T
    The dominant secular term is -3nt/n = -3t, giving Δy ≈ -3t × Δv_T
    but the oscillatory 4sin(nt)/n term can be significant at short lead times.

    Returns:
        Required |ΔV| in km/s
    """
    n = math.sqrt(MU_EARTH_KM / semi_major_axis_km**3)
    nt = n * lead_time_seconds

    # Displacement coefficient: dy/dv_T = (4sin(nt) - 3nt) / n
    coeff = (4 * math.sin(nt) - 3 * nt) / n

    if abs(coeff) < 1e-10:
        return float("inf")

    return abs(desired_separation_km / coeff)


def compute_crosstrack_delta_v(
    desired_separation_km: float,
    lead_time_seconds: float,
    semi_major_axis_km: float,
) -> float:
    """Compute cross-track ΔV for desired normal-plane separation.

    Full CW: Δz = sin(nt)/n × Δv_N
    Maximum displacement at nt = π/2 (quarter orbit).

    Returns:
        Required |ΔV| in km/s
    """
    n = math.sqrt(MU_EARTH_KM / semi_major_axis_km**3)
    nt = n * lead_time_seconds

    coeff = math.sin(nt) / n

    if abs(coeff) < 1e-10:
        return float("inf")

    return abs(desired_separation_km / coeff)


def compute_radial_delta_v(
    desired_separation_km: float,
    lead_time_seconds: float,
    semi_major_axis_km: float,
) -> float:
    """Compute radial ΔV for desired in-track separation via radial burn.

    Full CW: Δy_from_radial = -2(1-cos(nt))/n × Δv_R
    A radial burn also creates in-track displacement (coupling).

    Returns:
        Required |ΔV| in km/s
    """
    n = math.sqrt(MU_EARTH_KM / semi_major_axis_km**3)
    nt = n * lead_time_seconds

    # The in-track displacement from a radial impulse
    coeff = -2 * (1 - math.cos(nt)) / n

    if abs(coeff) < 1e-10:
        return float("inf")

    return abs(desired_separation_km / coeff)


def optimal_burn_direction(
    desired_separation_km: float,
    lead_time_seconds: float,
    semi_major_axis_km: float,
) -> BurnRecommendation:
    """Compute the most fuel-efficient burn direction and magnitude.

    Uses full CW equations to compare all three burn directions.

    Args:
        desired_separation_km: Target miss distance at TCA (km)
        lead_time_seconds: Time before TCA (seconds)
        semi_major_axis_km: Semi-major axis (km)

    Returns:
        BurnRecommendation with the minimum-fuel option
    """
    dv_intrack = compute_intrack_delta_v(
        desired_separation_km, lead_time_seconds, semi_major_axis_km
    )
    dv_crosstrack = compute_crosstrack_delta_v(
        desired_separation_km, lead_time_seconds, semi_major_axis_km
    )
    dv_radial = compute_radial_delta_v(
        desired_separation_km, lead_time_seconds, semi_major_axis_km
    )

    options = [
        ("IN_TRACK", dv_intrack),
        ("CROSS_TRACK", dv_crosstrack),
        ("RADIAL", dv_radial),
    ]

    best_dir, best_dv = min(options, key=lambda x: x[1])

    if best_dv == float("inf") or best_dv <= 0:
        efficiency = 0.0
    else:
        efficiency = desired_separation_km / (best_dv * 1000)

    # Determine sign (prograde vs retrograde) from CW coefficient
    n = math.sqrt(MU_EARTH_KM / semi_major_axis_km**3)
    nt = n * lead_time_seconds
    dv_rtn = np.zeros(3)

    if best_dir == "IN_TRACK":
        coeff = (4 * math.sin(nt) - 3 * nt) / n
        sign = -1 if coeff < 0 else 1  # negative coeff → negative ΔV for positive separation
        dv_rtn[1] = sign * best_dv  # T component
    elif best_dir == "CROSS_TRACK":
        coeff = math.sin(nt) / n
        sign = 1 if coeff > 0 else -1
        dv_rtn[2] = sign * best_dv  # N component
    else:  # RADIAL
        coeff = -2 * (1 - math.cos(nt)) / n
        sign = -1 if coeff < 0 else 1
        dv_rtn[0] = sign * best_dv  # R component

    return BurnRecommendation(
        direction=best_dir,
        delta_v_m_s=best_dv * 1000 if best_dv != float("inf") else float("inf"),
        delta_v_km_s=best_dv,
        lead_time_hours=lead_time_seconds / 3600.0,
        expected_separation_km=desired_separation_km,
        efficiency=efficiency,
        sign=sign,
        delta_v_rtn=dv_rtn,
    )
