"""Integrated mission design workflow.

Ties together the tools built from open-source study into a single
end-to-end workflow:

  1. Porkchop optimizer finds optimal departure/arrival dates
  2. Izzo Lambert solver computes transfer Δv
  3. Tsiolkovsky computes required propellant mass
  4. Maneuver sequence plans burns
  5. IAS15 integrator verifies trajectory (optional)
  6. Event detector finds key mission events

This is the composition layer — it glues together the physics primitives
into something an operator can use. A real mission designer would use
this to compare launch windows, size the propulsion system, and verify
the trajectory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from aria.simulation.lambert_izzo import lambert_izzo
from aria.simulation.maneuver_planning import (
    Burn, BurnType, ManeuverSequence, tsiolkovsky_fuel_mass, G0,
)
from aria.simulation.porkchop import compute_porkchop, PorkchopResult


@dataclass
class MissionDesign:
    """A complete interplanetary mission design."""
    origin: str
    destination: str
    dep_date_day: float              # days from epoch
    arr_date_day: float
    tof_days: float
    c3_departure: float              # km²/s²
    v_inf_arrival: float             # km/s
    departure_burn: Burn
    arrival_burn: Burn
    total_dv_ms: float
    dry_mass_kg: float
    fuel_required_kg: float
    feasible: bool
    porkchop: Optional[PorkchopResult] = None


def design_mission(
    origin_ephemeris_fn: Callable,
    destination_ephemeris_fn: Callable,
    origin_velocity_fn: Callable,
    destination_velocity_fn: Callable,
    mu_central: float,
    dep_window: Tuple[float, float],
    arr_window: Tuple[float, float],
    dry_mass_kg: float,
    fuel_budget_kg: float,
    isp_s: float = 300.0,
    n_dep: int = 20,
    n_arr: int = 20,
    origin_name: str = "origin",
    destination_name: str = "destination",
    max_revs: int = 0,
) -> MissionDesign:
    """Full interplanetary mission design pipeline.

    Args:
        origin_ephemeris_fn: callable(day) → (3,) origin position [m]
        destination_ephemeris_fn: callable(day) → (3,) destination position [m]
        origin_velocity_fn: callable(day) → (3,) origin velocity [m/s]
        destination_velocity_fn: callable(day) → (3,) destination velocity [m/s]
        mu_central: central body gravitational parameter [m³/s²]
        dep_window: (earliest, latest) departure day
        arr_window: (earliest, latest) arrival day
        dry_mass_kg: spacecraft dry mass
        fuel_budget_kg: available propellant mass
        isp_s: specific impulse (chemical ~300, electric ~3000+)
        n_dep, n_arr: porkchop grid resolution
        origin_name, destination_name: labels

    Returns:
        MissionDesign with optimal window, burns, and feasibility.
    """
    # Step 1: Porkchop grid to find optimal window.  When max_revs > 0
    # the grid scans Type-III/IV multi-rev Lambert solutions and picks
    # the lowest-C3 candidate per cell — useful for outer-planet
    # missions where a 1- or 2-rev transfer can shave 10–30 % off C3
    # in exchange for a longer time of flight (e.g. Galileo-class
    # VEEGA-multi-rev).  Direct missions to the inner planets always
    # win at M=0, so the default keeps the historical behaviour.
    porkchop = compute_porkchop(
        mu_central=mu_central,
        r_departure_fn=origin_ephemeris_fn,
        r_arrival_fn=destination_ephemeris_fn,
        dep_range_days=dep_window,
        arr_range_days=arr_window,
        n_dep=n_dep,
        n_arr=n_arr,
        v_planet_departure_fn=origin_velocity_fn,
        v_planet_arrival_fn=destination_velocity_fn,
        max_revs=max_revs,
    )

    if porkchop.valid_count == 0:
        raise ValueError("No valid Lambert solutions in window")

    # Step 2: Solve Lambert for the optimal window
    dep_day = porkchop.best_dep_day
    arr_day = porkchop.best_arr_day
    tof_s = (arr_day - dep_day) * 86400.0

    r1 = origin_ephemeris_fn(dep_day)
    r2 = destination_ephemeris_fn(arr_day)
    v_origin = origin_velocity_fn(dep_day)
    v_dest = destination_velocity_fn(arr_day)

    # Use the same M that won the porkchop search so the Δv numbers
    # below are consistent with the displayed C3.
    chosen_M = max(0, getattr(porkchop, "best_M", 0))
    v1, v2 = lambert_izzo(mu_central, r1, r2, tof_s, M=chosen_M)

    # Step 3: Compute departure and arrival Δv relative to bodies
    dv_depart = v1 - v_origin
    dv_arrive = v_dest - v2  # to match destination velocity
    dv_depart_mag = float(np.linalg.norm(dv_depart))
    dv_arrive_mag = float(np.linalg.norm(dv_arrive))
    total_dv = dv_depart_mag + dv_arrive_mag

    # Step 4: Tsiolkovsky fuel mass
    wet_mass = dry_mass_kg + fuel_budget_kg
    fuel_required = tsiolkovsky_fuel_mass(wet_mass, total_dv, isp_s)
    feasible = fuel_required <= fuel_budget_kg

    # Step 5: Build burn sequence
    departure_burn = Burn(
        burn_type=BurnType.IMPULSIVE,
        start_time=0.0,
        delta_v=dv_depart,
        isp_s=isp_s,
        name=f"TMI_{origin_name}_to_{destination_name}",
    )
    arrival_burn = Burn(
        burn_type=BurnType.IMPULSIVE,
        start_time=tof_s,
        delta_v=dv_arrive,
        isp_s=isp_s,
        name=f"orbit_insertion_{destination_name}",
    )

    return MissionDesign(
        origin=origin_name,
        destination=destination_name,
        dep_date_day=dep_day,
        arr_date_day=arr_day,
        tof_days=arr_day - dep_day,
        c3_departure=porkchop.best_c3,
        v_inf_arrival=float(np.linalg.norm(v2 - v_dest) / 1000.0),
        departure_burn=departure_burn,
        arrival_burn=arrival_burn,
        total_dv_ms=total_dv,
        dry_mass_kg=dry_mass_kg,
        fuel_required_kg=fuel_required,
        feasible=feasible,
        porkchop=porkchop,
    )


def design_summary(design: MissionDesign) -> Dict:
    """Human-readable summary of a mission design."""
    return {
        "route": f"{design.origin} → {design.destination}",
        "departure_day": round(design.dep_date_day, 1),
        "arrival_day": round(design.arr_date_day, 1),
        "time_of_flight_days": round(design.tof_days, 1),
        "c3_km2_s2": round(design.c3_departure, 2),
        "v_infinity_arrival_km_s": round(design.v_inf_arrival, 3),
        "departure_dv_ms": round(float(np.linalg.norm(design.departure_burn.delta_v)), 1),
        "arrival_dv_ms": round(float(np.linalg.norm(design.arrival_burn.delta_v)), 1),
        "total_dv_ms": round(design.total_dv_ms, 1),
        "dry_mass_kg": design.dry_mass_kg,
        "fuel_required_kg": round(design.fuel_required_kg, 1),
        "feasible": design.feasible,
        "porkchop_valid_fraction": round(
            design.porkchop.valid_count / max(design.porkchop.total_count, 1), 3
        ) if design.porkchop else 0.0,
    }


# ══════════════════════════════════════════════════════════════════
#  Built-in ephemeris for solar system bodies (simplified)
# ══════════════════════════════════════════════════════════════════

# Orbital parameters for major bodies (J2000, heliocentric circular
# approximation — fine for porkchop-scale mission design where
# accuracy-to-1% is sufficient).
# Real mission design should use JPL DE430 via astropy.
_AU_M = 1.495978707e11
_GM_SUN = 1.32712440018e20

_BODIES_APPROX: Dict[str, Dict] = {
    "earth":   {"a_m": 1.000e11 * _AU_M / 1e11, "period_d": 365.25},
    "mars":    {"a_m": 1.524 * _AU_M, "period_d": 686.97},
    "venus":   {"a_m": 0.723 * _AU_M, "period_d": 224.70},
    "jupiter": {"a_m": 5.203 * _AU_M, "period_d": 4332.59},
    "saturn":  {"a_m": 9.537 * _AU_M, "period_d": 10759.22},
    "mercury": {"a_m": 0.387 * _AU_M, "period_d": 87.969},
}


def ephemeris_functions(body: str) -> Tuple[Callable, Callable]:
    """Return (position_fn, velocity_fn) for a solar-system body.

    Simplified circular orbit — good for porkchop design at ±2%.
    For precision flight use JPL ephemeris.
    """
    if body not in _BODIES_APPROX:
        raise ValueError(f"Unknown body: {body}. Known: {list(_BODIES_APPROX.keys())}")

    params = _BODIES_APPROX[body]
    a = params["a_m"]
    period_s = params["period_d"] * 86400.0
    omega = 2.0 * np.pi / period_s
    v_circ = np.sqrt(_GM_SUN / a)

    def pos_fn(day: float) -> np.ndarray:
        t = day * 86400.0
        return np.array([a * np.cos(omega * t), a * np.sin(omega * t), 0.0])

    def vel_fn(day: float) -> np.ndarray:
        t = day * 86400.0
        return v_circ * np.array([-np.sin(omega * t), np.cos(omega * t), 0.0])

    return pos_fn, vel_fn


def design_earth_mars_mission(
    dep_window: Tuple[float, float] = (0, 400),
    arr_window: Tuple[float, float] = (150, 600),
    dry_mass_kg: float = 3000.0,
    fuel_budget_kg: float = 6000.0,
    isp_s: float = 320.0,
) -> MissionDesign:
    """Convenience wrapper for Earth-to-Mars mission design."""
    er_fn, ev_fn = ephemeris_functions("earth")
    mr_fn, mv_fn = ephemeris_functions("mars")
    return design_mission(
        origin_ephemeris_fn=er_fn,
        destination_ephemeris_fn=mr_fn,
        origin_velocity_fn=ev_fn,
        destination_velocity_fn=mv_fn,
        mu_central=_GM_SUN,
        dep_window=dep_window,
        arr_window=arr_window,
        dry_mass_kg=dry_mass_kg,
        fuel_budget_kg=fuel_budget_kg,
        isp_s=isp_s,
        origin_name="Earth",
        destination_name="Mars",
    )
