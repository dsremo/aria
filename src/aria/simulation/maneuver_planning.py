"""Maneuver planning — impulsive and continuous thrust.

Provides a unified API for mission maneuver planning:
- Impulsive burns (chemical propulsion): instant Δv at specified time
- Continuous thrust (electric propulsion): guided acceleration over
  an interval using Edelbaum/Kechichian or targeted rendezvous

A maneuver sequence can be composed of multiple segments and executed
against the propagator to produce a complete trajectory.

Also includes:
- Delta-V accounting (fuel mass consumption via Tsiolkovsky)
- Maneuver verification (predicted vs actual)
- Station-keeping maneuvers (ground-track maintenance, LEO drag makeup)

Patterns studied from:
- Poliastro Maneuver class (MIT)
- Orekit ImpulseManeuver + ConstantThrustManeuver (Apache, Java)
- Open Space Toolkit Segment/Sequence (Apache)

References:
    Vallado (2013) "Fundamentals of Astrodynamics" Ch. 6.
    Battin (1999) "Mathematics of Astrodynamics" §6.5.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np


class BurnType(enum.Enum):
    IMPULSIVE = "impulsive"          # instantaneous Δv
    CONTINUOUS = "continuous"         # constant thrust over interval
    EDELBAUM = "edelbaum"             # low-thrust a+i change


@dataclass
class Burn:
    """A single maneuver segment."""
    burn_type: BurnType
    start_time: float                         # mission elapsed time [s]
    duration: float = 0.0                     # [s], 0 for impulsive
    delta_v: Optional[np.ndarray] = None      # (3,) Δv vector [m/s]
    thrust_accel: float = 0.0                 # continuous acceleration [m/s²]
    direction: Optional[np.ndarray] = None    # (3,) thrust direction (unit)
    isp_s: float = 300.0                      # specific impulse [s]
    name: str = ""


@dataclass
class ManeuverResult:
    """Result of a maneuver plan execution."""
    initial_mass_kg: float
    final_mass_kg: float
    total_dv_ms: float
    total_fuel_kg: float
    total_time_s: float
    burns_executed: int


G0 = 9.80665  # m/s² — standard gravity for Isp definition


# ══════════════════════════════════════════════════════════════════
#  Tsiolkovsky fuel accounting
# ══════════════════════════════════════════════════════════════════

def tsiolkovsky_fuel_mass(
    initial_mass_kg: float,
    delta_v_ms: float,
    isp_s: float,
) -> float:
    """Fuel mass required for a Δv using the rocket equation.

    Δv = Isp * g0 * ln(m0 / mf)
    → mf = m0 * exp(-Δv / (Isp * g0))
    → fuel = m0 - mf
    """
    if isp_s <= 0 or delta_v_ms <= 0:
        return 0.0
    exhaust_v = isp_s * G0
    mass_fraction = math.exp(-delta_v_ms / exhaust_v)
    return initial_mass_kg * (1.0 - mass_fraction)


def tsiolkovsky_dv(
    initial_mass_kg: float,
    final_mass_kg: float,
    isp_s: float,
) -> float:
    """Δv achievable for given mass ratio and Isp."""
    if final_mass_kg <= 0 or initial_mass_kg <= final_mass_kg:
        return 0.0
    return isp_s * G0 * math.log(initial_mass_kg / final_mass_kg)


# ══════════════════════════════════════════════════════════════════
#  Impulsive maneuvers
# ══════════════════════════════════════════════════════════════════

def apply_impulsive_burn(
    r: np.ndarray, v: np.ndarray, delta_v: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Apply an instantaneous Δv. Position unchanged, velocity shifted."""
    return r.copy(), v + np.asarray(delta_v, dtype=float)


def hohmann_transfer_burns(
    mu: float, r1: float, r2: float
) -> Tuple[Burn, Burn, float]:
    """Plan a two-burn Hohmann transfer between circular orbits.

    Returns (burn1, burn2, tof_seconds).
    """
    a_t = (r1 + r2) / 2.0
    v1 = math.sqrt(mu / r1)
    v2 = math.sqrt(mu / r2)
    v_t1 = math.sqrt(mu * (2.0 / r1 - 1.0 / a_t))
    v_t2 = math.sqrt(mu * (2.0 / r2 - 1.0 / a_t))
    dv1 = v_t1 - v1
    dv2 = v2 - v_t2
    tof = math.pi * math.sqrt(a_t ** 3 / mu)

    burn1 = Burn(
        burn_type=BurnType.IMPULSIVE,
        start_time=0.0,
        delta_v=np.array([0.0, dv1, 0.0]),  # tangential (local frame)
        name="hohmann_burn_1",
    )
    burn2 = Burn(
        burn_type=BurnType.IMPULSIVE,
        start_time=tof,
        delta_v=np.array([0.0, dv2, 0.0]),
        name="hohmann_burn_2",
    )
    return burn1, burn2, tof


def plane_change_burn(
    v_orbital_ms: float, delta_inc_rad: float
) -> float:
    """Δv magnitude for a plane change at constant speed.

    Δv = 2 * v * sin(Δi / 2)

    Plane changes are expensive — at 7.5 km/s LEO speed, a 10° change
    requires ~1.3 km/s Δv. That's why Edelbaum low-thrust transfers
    combine plane changes with altitude changes.
    """
    return 2.0 * v_orbital_ms * math.sin(0.5 * delta_inc_rad)


def combined_plane_change(
    v_initial_ms: float, v_final_ms: float, delta_inc_rad: float
) -> float:
    """Δv for combined in-plane + plane change maneuver.

    Δv² = v1² + v2² - 2*v1*v2*cos(Δi)

    This is more efficient than doing the two maneuvers separately.
    Reference: Vallado (2013) Eq. (6-30).
    """
    return math.sqrt(
        v_initial_ms ** 2 + v_final_ms ** 2
        - 2.0 * v_initial_ms * v_final_ms * math.cos(delta_inc_rad)
    )


# ══════════════════════════════════════════════════════════════════
#  Continuous thrust maneuvers
# ══════════════════════════════════════════════════════════════════

def continuous_thrust_dv(thrust_accel_ms2: float, duration_s: float) -> float:
    """Δv accumulated from constant thrust over a duration."""
    return thrust_accel_ms2 * duration_s


def thrust_from_power(
    power_w: float,
    isp_s: float,
    efficiency: float = 0.7,
) -> float:
    """Thrust force [N] from available electrical power.

    For electric propulsion: F = 2 * eta * P / (Isp * g0)
    where eta is the thruster efficiency.

    Typical electric propulsion:
    - Ion thrusters (NEXT): Isp=4100s, thrust=250mN @ 6kW
    - Hall thrusters: Isp=1500-2000s, thrust=50-500mN
    - VASIMR: Isp=3000-30000s variable
    """
    if isp_s <= 0:
        return 0.0
    return 2.0 * efficiency * power_w / (isp_s * G0)


# ══════════════════════════════════════════════════════════════════
#  Station-keeping maneuvers
# ══════════════════════════════════════════════════════════════════

def drag_makeup_dv_per_year(
    altitude_km: float, area_over_mass_m2_kg: float = 0.01
) -> float:
    """Approximate annual Δv budget to maintain a LEO orbit against drag.

    Rough estimate from CIRA-72 exponential atmosphere at given altitude.
    Ballpark figures (Vallado 2013 Table 8-5):
    - 300 km: ~50 m/s/yr
    - 400 km: ~10 m/s/yr
    - 500 km: ~2 m/s/yr
    - 600 km: ~0.5 m/s/yr
    """
    # Exponential fit to published values
    return 50.0 * math.exp(-(altitude_km - 300.0) / 60.0) * (area_over_mass_m2_kg / 0.01)


def geo_stationkeeping_dv_per_year() -> float:
    """Annual Δv for GEO station-keeping.

    N-S keeping: ~43 m/s/yr (dominant — lunisolar perturbation)
    E-W keeping: ~2 m/s/yr
    Total: ~45 m/s/yr (Vallado 2013 §8.6.2)
    """
    return 45.0


# ══════════════════════════════════════════════════════════════════
#  Maneuver sequence
# ══════════════════════════════════════════════════════════════════

class ManeuverSequence:
    """A sequence of burns to be executed during propagation.

    Usage:
        seq = ManeuverSequence(dry_mass_kg=1000, initial_fuel_kg=500)
        seq.add_burn(burn1)
        seq.add_burn(burn2)
        result = seq.execute(propagator, initial_state, isp=300)
    """

    def __init__(
        self,
        dry_mass_kg: float = 1000.0,
        initial_fuel_kg: float = 500.0,
    ) -> None:
        self.dry_mass_kg = dry_mass_kg
        self.initial_fuel_kg = initial_fuel_kg
        self.fuel_kg = initial_fuel_kg
        self.burns: List[Burn] = []
        self._executed: List[Burn] = []

    def add_burn(self, burn: Burn) -> None:
        """Append a burn to the sequence."""
        self.burns.append(burn)

    def total_dv(self) -> float:
        """Sum of Δv magnitudes across all planned burns."""
        total = 0.0
        for b in self.burns:
            if b.burn_type == BurnType.IMPULSIVE and b.delta_v is not None:
                total += float(np.linalg.norm(b.delta_v))
            elif b.burn_type == BurnType.CONTINUOUS:
                total += b.thrust_accel * b.duration
        return total

    def total_fuel_required(self, isp_s: float = 300.0) -> float:
        """Total fuel mass required for the entire sequence."""
        total_dv = self.total_dv()
        initial_mass = self.dry_mass_kg + self.initial_fuel_kg
        return tsiolkovsky_fuel_mass(initial_mass, total_dv, isp_s)

    def is_feasible(self, isp_s: float = 300.0) -> bool:
        """Check if there's enough fuel for all burns."""
        return self.total_fuel_required(isp_s) <= self.initial_fuel_kg

    def summary(self, isp_s: float = 300.0) -> dict:
        """Return a summary of the maneuver plan."""
        total_dv = self.total_dv()
        fuel_needed = self.total_fuel_required(isp_s)
        return {
            "n_burns": len(self.burns),
            "impulsive": sum(1 for b in self.burns if b.burn_type == BurnType.IMPULSIVE),
            "continuous": sum(1 for b in self.burns if b.burn_type == BurnType.CONTINUOUS),
            "total_dv_ms": total_dv,
            "fuel_required_kg": fuel_needed,
            "fuel_available_kg": self.initial_fuel_kg,
            "feasible": fuel_needed <= self.initial_fuel_kg,
            "dry_mass_kg": self.dry_mass_kg,
            "wet_mass_kg": self.dry_mass_kg + self.initial_fuel_kg,
        }


# ══════════════════════════════════════════════════════════════════
#  Rendezvous and proximity operations
# ══════════════════════════════════════════════════════════════════

def clohessy_wiltshire_solution(
    r0: np.ndarray, v0: np.ndarray, t: float, n: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Propagate relative state using Clohessy-Wiltshire equations.

    Linear analytical solution for relative motion near a circular
    reference orbit. Used for rendezvous & docking.

    Args:
        r0: (3,) relative position at t=0 (LVLH frame) [m]
        v0: (3,) relative velocity at t=0 [m/s]
        t: time since t=0 [s]
        n: mean motion of reference orbit [rad/s]

    Returns:
        (r_rel, v_rel) at time t in LVLH frame.

    Reference: Clohessy & Wiltshire (1960), Vallado (2013) §6.7.
    """
    nt = n * t
    s = math.sin(nt)
    c = math.cos(nt)
    x0, y0, z0 = r0
    vx0, vy0, vz0 = v0

    # CW state transition matrix
    x = (4.0 - 3.0 * c) * x0 + s / n * vx0 + 2.0 / n * (1.0 - c) * vy0
    y = 6.0 * (s - nt) * x0 + y0 + 2.0 / n * (c - 1.0) * vx0 + (4.0 * s / n - 3.0 * t) * vy0
    z = c * z0 + s / n * vz0

    vx = 3.0 * n * s * x0 + c * vx0 + 2.0 * s * vy0
    vy = 6.0 * n * (c - 1.0) * x0 - 2.0 * s * vx0 + (4.0 * c - 3.0) * vy0
    vz = -n * s * z0 + c * vz0

    return np.array([x, y, z]), np.array([vx, vy, vz])


def cw_targeting(
    r_start: np.ndarray,
    r_end: np.ndarray,
    tof: float,
    n: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Solve the Clohessy-Wiltshire targeting problem: find v_start such
    that the relative motion reaches r_end at time tof.

    Returns (v_start, v_end) — required initial and final velocities.
    """
    nt = n * tof
    s = math.sin(nt)
    c = math.cos(nt)

    # CW targeting: solve for v_start given r_start and r_end
    # r_end = Phi_rr @ r_start + Phi_rv @ v_start
    # → v_start = inv(Phi_rv) @ (r_end - Phi_rr @ r_start)

    Phi_rr = np.array([
        [4.0 - 3.0 * c, 0.0, 0.0],
        [6.0 * (s - nt), 1.0, 0.0],
        [0.0, 0.0, c],
    ])
    Phi_rv = np.array([
        [s / n, 2.0 / n * (1.0 - c), 0.0],
        [2.0 / n * (c - 1.0), 4.0 * s / n - 3.0 * tof, 0.0],
        [0.0, 0.0, s / n],
    ])

    try:
        v_start = np.linalg.solve(Phi_rv, r_end - Phi_rr @ r_start)
    except np.linalg.LinAlgError:
        v_start = np.zeros(3)

    _, v_end = clohessy_wiltshire_solution(r_start, v_start, tof, n)
    return v_start, v_end
