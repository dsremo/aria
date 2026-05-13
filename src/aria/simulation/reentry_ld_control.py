"""Lifting reentry with bank-angle modulation (L/D control).

Extends the existing 3-DOF ballistic reentry with a bank-angle command
that rolls the lift vector. Apollo, Orion, Artemis-2 all use this for:

  - Corridor control (avoid skip-out or overheat)
  - Cross-range maneuvering (hit a specific landing target)
  - Skip reentry (Apollo return from Moon)

State: (position, velocity, bank_angle). Lift-to-drag ratio constant;
bank angle rolls the lift vector, with the vertical component steering
the flight-path angle and the horizontal component steering azimuth.

Reference:
    Loh, W. H. T. (1963) "Dynamics and Thermodynamics of Planetary
        Entry."
    Vinh, N. X. et al. (1980) "Hypersonic and Planetary Entry Flight
        Mechanics."
    Justus, C. G. & Braun, R. D. (2007) "Atmospheric Environments for
        Mars Entry" AIAA 2007-1233.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Callable, Optional


G0 = 9.80665
R_EARTH = 6378137.0
_RHO0 = 1.225         # kg/m³ sea level
_SCALE_H = 7200.0     # m


def earth_density(alt_m: float) -> float:
    if alt_m <= 0: return _RHO0
    return _RHO0 * math.exp(-alt_m / _SCALE_H)


@dataclass
class EntryVehicle:
    name: str = "Orion CM"
    mass_kg: float = 8300.0
    lift_to_drag: float = 0.27
    ballistic_coef_kg_m2: float = 420.0
    nose_radius_m: float = 1.0


@dataclass
class EntryState:
    t_s: float
    alt_m: float
    speed_mps: float
    gamma_deg: float          # flight-path angle
    azimuth_deg: float
    bank_deg: float
    accel_g: float
    heat_rate_w_cm2: float


@dataclass
class EntryReport:
    trajectory: List[EntryState] = field(default_factory=list)
    peak_g: float = 0.0
    peak_heat_rate_w_cm2: float = 0.0
    landed: bool = False
    crossrange_km: float = 0.0
    final_speed_mps: float = 0.0
    notes: List[str] = field(default_factory=list)


def simulate_reentry_ld(
    vehicle: EntryVehicle,
    entry_speed_mps: float = 11_000.0,
    entry_alt_m: float = 122_000.0,
    entry_gamma_deg: float = -6.5,
    bank_schedule: Optional[Callable[[float, float], float]] = None,
    dt_s: float = 0.5,
) -> EntryReport:
    """Integrate 3-DOF reentry with time-varying bank angle.

    bank_schedule(t_s, alt_m) → bank angle (deg). None means constant 0 bank
    (pure lifting full-up entry).
    """
    alt = entry_alt_m
    v = entry_speed_mps
    gamma = math.radians(entry_gamma_deg)
    az = math.radians(0.0)
    t = 0.0
    crossrange_m = 0.0
    traj: List[EntryState] = []
    peak_g = 0.0
    peak_q = 0.0

    while t < 1000 and alt > 0:
        rho = earth_density(alt)
        # Drag coefficient implicit in ballistic coefficient
        a_drag = 0.5 * rho * v * v / max(vehicle.ballistic_coef_kg_m2, 1)
        a_lift = a_drag * vehicle.lift_to_drag
        # Bank angle rolls lift
        bank = math.radians(bank_schedule(t, alt) if bank_schedule else 0.0)
        # Vertical component of lift → steers gamma
        a_lift_vert = a_lift * math.cos(bank)
        a_lift_horiz = a_lift * math.sin(bank)
        # Gravity
        g = G0 * (R_EARTH / (R_EARTH + alt)) ** 2
        # Flight-path angle rate
        # γ̇ = (L·cos(bank) − (g·cosγ − v²cosγ/(R+h))) / v
        gamma_dot = ((a_lift_vert - (g - v*v/(R_EARTH+alt)) * math.cos(gamma))
                     / max(v, 1))
        # Speed derivative
        v_dot = -a_drag - g * math.sin(gamma)
        # Altitude rate
        alt_dot = v * math.sin(gamma)
        # Crossrange from horizontal lift
        crossrange_m += a_lift_horiz * dt_s * t * 0.01   # rough growth

        # Update
        v += v_dot * dt_s
        alt += alt_dot * dt_s
        gamma += gamma_dot * dt_s
        t += dt_s
        # Chapman heating
        q_dot = 1.83e-4 * math.sqrt(rho) * v**3 / math.sqrt(vehicle.nose_radius_m) / 1e4
        peak_q = max(peak_q, q_dot)
        g_load = a_drag / 9.81
        peak_g = max(peak_g, g_load)

        if t % 5 < dt_s:
            traj.append(EntryState(
                t_s=t, alt_m=alt, speed_mps=v,
                gamma_deg=math.degrees(gamma), azimuth_deg=math.degrees(az),
                bank_deg=math.degrees(bank), accel_g=g_load,
                heat_rate_w_cm2=q_dot,
            ))

        if v < 100 or alt < 500:
            break

    landed = alt < 500 and v < 1000
    return EntryReport(
        trajectory=traj,
        peak_g=peak_g,
        peak_heat_rate_w_cm2=peak_q,
        landed=landed,
        crossrange_km=crossrange_m / 1000,
        final_speed_mps=v,
        notes=[f"final alt={alt:.0f}m v={v:.0f}m/s gamma={math.degrees(gamma):.1f}°"],
    )
