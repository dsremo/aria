"""Re-entry corridor analysis for returning spacecraft.

Computes the range of entry flight path angles (γ) that result in safe
re-entry. Entries too steep → excessive deceleration (crew G-limits
exceeded, vehicle structural failure). Entries too shallow → skip-out
(bounce back into space) or excessive heating.

Corridor boundaries:
- Upper (shallow): skip-out boundary. If γ > γ_skip, vehicle leaves
  atmosphere without slowing enough.
- Lower (steep): deceleration limit. If γ < γ_max, peak G's exceed
  crew tolerance (5-8 G sustained, 12 G peak for trained astronauts).

Also computes:
- Peak dynamic pressure (for structural loads)
- Peak heat flux (for TPS sizing)
- Total heat load (integrated heating)
- Range (downrange distance from entry interface)

References:
    Allen & Eggers (1958) NACA Report 1381
    Chapman (1959) NASA TR R-11 (lifting entry)
    Vallado (2013) "Fundamentals of Astrodynamics" §11
    Apollo re-entry corridor: γ between -5.5° and -6.5° (nominal -6.0°)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from aria.physics.gravity.atmosphere import coesa76_density, stagnation_heat_flux_chapman


# ══════════════════════════════════════════════════════════════════
#  Ballistic re-entry trajectory (Allen-Eggers 1958)
# ══════════════════════════════════════════════════════════════════

@dataclass
class ReentryProfile:
    """Trajectory profile of a ballistic re-entry."""
    altitudes_km: np.ndarray
    velocities_mps: np.ndarray
    decelerations_g: np.ndarray
    heat_fluxes_wm2: np.ndarray
    dynamic_pressures_pa: np.ndarray
    times_s: np.ndarray

    peak_g: float
    peak_q_pa: float            # peak dynamic pressure
    peak_heat_flux_wm2: float   # peak stagnation heating
    total_heat_load_jm2: float  # integrated heat load
    entry_angle_deg: float
    entry_velocity_mps: float
    landing_velocity_mps: float


def simulate_ballistic_reentry(
    entry_altitude_km: float = 120.0,
    entry_velocity_mps: float = 7800.0,
    entry_angle_deg: float = -6.0,
    ballistic_coefficient: float = 500.0,  # beta = m / (C_D * A) [kg/m²]
    nose_radius_m: float = 0.3,
    dt_s: float = 0.5,
    max_time_s: float = 600.0,
) -> ReentryProfile:
    """Simulate a 1-DOF ballistic re-entry from given entry conditions.

    Uses simplified Allen-Eggers equations with US Standard Atmosphere.
    No lift, no 3-DOF (simplification for corridor analysis).

    Args:
        entry_altitude_km: altitude of entry interface [km]
        entry_velocity_mps: velocity at entry interface [m/s]
        entry_angle_deg: flight path angle at entry [deg] (negative = descent)
        ballistic_coefficient: beta = m / (C_D * A) [kg/m²]
        nose_radius_m: stagnation nose radius for heating calc
        dt_s: integration timestep
        max_time_s: maximum simulation time

    Returns:
        ReentryProfile with full trajectory

    Reference: Allen & Eggers 1958 NACA Report 1381.
    """
    h = entry_altitude_km * 1000.0  # altitude [m]
    v = entry_velocity_mps
    gamma = math.radians(entry_angle_deg)
    t = 0.0

    alts: List[float] = []
    vels: List[float] = []
    decels_g: List[float] = []
    heat_fluxes: List[float] = []
    dyn_press: List[float] = []
    times: List[float] = []

    total_heat_jm2 = 0.0

    while h > 0 and t < max_time_s:
        rho = coesa76_density(h)
        # Dynamic pressure
        q = 0.5 * rho * v * v

        # Deceleration from drag
        # a_drag = q / beta
        a_drag = q / ballistic_coefficient

        # Gravity component along velocity
        g_local = 9.81 * (6378137.0 / (6378137.0 + h)) ** 2
        a_gravity_along = g_local * math.sin(-gamma)  # positive decel for γ<0

        # Total deceleration magnitude (drag - gravity-along)
        a_total = a_drag - a_gravity_along
        decel_g = abs(a_total / 9.81)

        # Heat flux
        q_heat = stagnation_heat_flux_chapman(v, rho, nose_radius_m)

        # Record
        alts.append(h / 1000.0)
        vels.append(v)
        decels_g.append(decel_g)
        heat_fluxes.append(q_heat)
        dyn_press.append(q)
        times.append(t)

        # Integrate (Euler — fine for corridor trends)
        dv = -a_total * dt_s
        v_new = max(0.0, v + dv)

        # Flight path angle evolves: dγ/dt = (v/r - g/v) cos(γ) (L=0 ballistic)
        # For simplicity, use near-constant γ with small gravity turn
        dgamma = -g_local * math.cos(gamma) / max(v, 10.0) * dt_s
        gamma_new = gamma + dgamma

        # Altitude: dh/dt = v * sin(γ)
        dh = v * math.sin(gamma) * dt_s
        h_new = max(0.0, h + dh)

        # Integrate heat load
        total_heat_jm2 += q_heat * dt_s

        h = h_new
        v = v_new
        gamma = gamma_new
        t += dt_s

    return ReentryProfile(
        altitudes_km=np.array(alts),
        velocities_mps=np.array(vels),
        decelerations_g=np.array(decels_g),
        heat_fluxes_wm2=np.array(heat_fluxes),
        dynamic_pressures_pa=np.array(dyn_press),
        times_s=np.array(times),
        peak_g=float(max(decels_g)) if decels_g else 0.0,
        peak_q_pa=float(max(dyn_press)) if dyn_press else 0.0,
        peak_heat_flux_wm2=float(max(heat_fluxes)) if heat_fluxes else 0.0,
        total_heat_load_jm2=total_heat_jm2,
        entry_angle_deg=entry_angle_deg,
        entry_velocity_mps=entry_velocity_mps,
        landing_velocity_mps=v,
    )


# ══════════════════════════════════════════════════════════════════
#  Corridor boundaries
# ══════════════════════════════════════════════════════════════════

@dataclass
class ReentryCorridor:
    """Safe re-entry corridor for a vehicle."""
    shallow_bound_deg: float           # skip-out / undershoot boundary
    steep_bound_deg: float             # peak-G boundary
    nominal_entry_deg: float
    max_allowable_g: float
    max_allowable_heat_flux_mw_m2: float


def compute_reentry_corridor(
    entry_velocity_mps: float = 7800.0,
    entry_altitude_km: float = 120.0,
    ballistic_coefficient: float = 500.0,
    max_g: float = 8.0,
    max_heat_flux_mw_m2: float = 10.0,
    nose_radius_m: float = 0.3,
    angle_search_range_deg: Tuple[float, float] = (-12.0, -1.0),
    n_samples: int = 20,
) -> ReentryCorridor:
    """Find safe entry angle corridor by bisection through entry angles.

    Returns the range of entry angles for which:
        peak G < max_g AND peak heat flux < max_heat_flux_mw_m2

    Args:
        entry_velocity_mps: interface velocity
        entry_altitude_km: interface altitude
        ballistic_coefficient: m/(C_D*A)
        max_g: max tolerable deceleration (crew ~8g sustained)
        max_heat_flux_mw_m2: TPS limit
        nose_radius_m: for heat flux calc
        angle_search_range_deg: range of angles to search
        n_samples: number of angles to sample

    Returns:
        ReentryCorridor with shallow/steep bounds
    """
    angles = np.linspace(angle_search_range_deg[0], angle_search_range_deg[1], n_samples)
    viable_angles: List[float] = []

    for angle in angles:
        profile = simulate_ballistic_reentry(
            entry_altitude_km=entry_altitude_km,
            entry_velocity_mps=entry_velocity_mps,
            entry_angle_deg=float(angle),
            ballistic_coefficient=ballistic_coefficient,
            nose_radius_m=nose_radius_m,
            dt_s=1.0,
            max_time_s=800.0,
        )
        peak_q_mw = profile.peak_heat_flux_wm2 / 1e6
        # Skip-out detection: if final altitude is above 80 km and velocity
        # still above 5 km/s, we skipped out
        if len(profile.altitudes_km) > 0:
            final_alt = profile.altitudes_km[-1]
            final_vel = profile.velocities_mps[-1]
            skipped_out = final_alt > 50.0 and final_vel > 5000.0
        else:
            skipped_out = False

        if (profile.peak_g < max_g
                and peak_q_mw < max_heat_flux_mw_m2
                and not skipped_out):
            viable_angles.append(float(angle))

    if not viable_angles:
        # No viable corridor — return a zero-width one
        return ReentryCorridor(
            shallow_bound_deg=0.0,
            steep_bound_deg=0.0,
            nominal_entry_deg=0.0,
            max_allowable_g=max_g,
            max_allowable_heat_flux_mw_m2=max_heat_flux_mw_m2,
        )

    shallow = max(viable_angles)  # closest to 0 = most shallow
    steep = min(viable_angles)    # most negative = steepest
    nominal = 0.5 * (shallow + steep)

    return ReentryCorridor(
        shallow_bound_deg=shallow,
        steep_bound_deg=steep,
        nominal_entry_deg=nominal,
        max_allowable_g=max_g,
        max_allowable_heat_flux_mw_m2=max_heat_flux_mw_m2,
    )


# ══════════════════════════════════════════════════════════════════
#  Pre-canned vehicle profiles
# ══════════════════════════════════════════════════════════════════

def apollo_corridor() -> ReentryCorridor:
    """Apollo CM re-entry corridor at lunar return velocity.

    Published (NASA SP-350): γ = -6.5° ± 0.5°, 11 km/s entry.
    """
    return compute_reentry_corridor(
        entry_velocity_mps=11000.0,
        entry_altitude_km=122.0,     # Apollo entry interface
        ballistic_coefficient=360.0,  # Apollo CM ~5500kg, C_D*A ~15 m²
        max_g=12.0,                   # Apollo crew tolerance
        max_heat_flux_mw_m2=15.0,
        nose_radius_m=4.0,            # CM blunt body
    )


def soyuz_corridor() -> ReentryCorridor:
    """Soyuz re-entry corridor from LEO."""
    return compute_reentry_corridor(
        entry_velocity_mps=7800.0,
        entry_altitude_km=100.0,
        ballistic_coefficient=320.0,
        max_g=9.0,
        max_heat_flux_mw_m2=8.0,
        nose_radius_m=2.2,
    )
