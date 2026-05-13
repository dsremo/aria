"""Mars Entry-Descent-Landing: entry corridor → parachute → retropropulsion.

Mars atmosphere is thick enough for aerodynamic deceleration to be
dominant (unlike the Moon) but too thin to slow a large vehicle by
parachute alone — the "Mars EDL paradox." MSL, Perseverance, and HLS
all need a sky-crane or retropropulsion final phase.

This module integrates the three phases as a 3-DOF simulation:

  1. **Hypersonic entry**   — 3-DOF Allen-Eggers with Mars atmosphere
     (Mars-GRAM empirical fit); Chapman heating; L/D bank for corridor
     control.
  2. **Supersonic parachute** — DGB chute at Mach 2.2 trigger, steady-state
     drag to subsonic.
  3. **Powered descent**    — sky-crane or direct retropropulsion; constant
     thrust slowdown to touchdown velocity.

Mars atmospheric density uses the simple scale-height exponential fit
(Mars-GRAM climatological mean, MARS-GRAM 2010):

    ρ(h) = ρ0 · exp(-(h-h0)/H),  ρ0 = 0.020 kg/m³, H = 11.1 km

Reference:
    Braun, R. D. & Manning, R. M. (2007) "Mars Exploration Entry, Descent,
        and Landing Challenges," J. Spacecr. Rockets 44(2):310.
    Mars-GRAM 2010 climatological reference database.
    Prakash et al. (2020) "Mars 2020 EDL analysis," JGR Planets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ══════════════════════════════════════════════════════════════════
#  Physical constants
# ══════════════════════════════════════════════════════════════════

G_MARS = 3.711
R_MARS = 3389500.0
MU_MARS = 4.2828e13

# Mars-GRAM mean atmosphere
_RHO0 = 0.020        # kg/m³ at surface
_SCALE_H = 11100.0   # m, exponential scale height

# Speed of sound on Mars (~240 m/s near surface, ~200 m/s at 10 km)
_A0 = 240.0


def mars_density(alt_m: float) -> float:
    if alt_m <= 0:
        return _RHO0
    return _RHO0 * math.exp(-alt_m / _SCALE_H)


def mars_mach(v_mps: float, alt_m: float) -> float:
    # Simple Mach using exponential-atmosphere sound speed
    a = _A0 * math.exp(-alt_m / (2 * _SCALE_H)) ** 0
    return v_mps / max(a, 1e-6)


# ══════════════════════════════════════════════════════════════════
#  Phase configs
# ══════════════════════════════════════════════════════════════════

@dataclass
class EntryConfig:
    entry_speed_mps: float = 5600.0       # Mars-2020 entry
    entry_alt_m: float = 125_000.0        # EI at 125 km
    flight_path_deg: float = -11.5        # corridor
    vehicle_mass_kg: float = 2400.0       # Perseverance-class
    nose_radius_m: float = 1.125
    ld_ratio: float = 0.25                # low-L/D capsule
    ballistic_coef_kg_m2: float = 135.0   # m / (Cd × A)


@dataclass
class ChuteConfig:
    trigger_mach: float = 2.2
    deploy_diameter_m: float = 21.5        # DGB chute
    area_m2: float = 363.0                 # area ≈ π d²/4
    drag_coef: float = 0.7


@dataclass
class PoweredDescentConfig:
    trigger_alt_m: float = 2100.0
    touchdown_speed_mps: float = 0.75       # Ingenuity/Perseverance soft-land
    throttle_thrust_n: float = 3072.0 * 8   # 8 × Raptor-equiv throttle
    isp_s: float = 220.0
    dry_mass_kg: float = 1025.0


@dataclass
class EDLState:
    t_s: float
    alt_m: float
    v_mps: float
    mach: float
    phase: str
    mass_kg: float
    accel_g: float


@dataclass
class EDLResult:
    config: EntryConfig
    phases_done: List[str] = field(default_factory=list)
    trajectory: List[EDLState] = field(default_factory=list)
    peak_g: float = 0.0
    peak_heat_rate_w_cm2: float = 0.0
    touchdown_speed_mps: float = 0.0
    final_mass_kg: float = 0.0
    success: bool = False
    notes: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
#  Integrated EDL simulator
# ══════════════════════════════════════════════════════════════════

def simulate_mars_edl(entry: Optional[EntryConfig] = None,
                      chute: Optional[ChuteConfig] = None,
                      powered: Optional[PoweredDescentConfig] = None,
                      dt_s: float = 0.5) -> EDLResult:
    """Full Mars EDL 3-DOF simulation: entry → chute → powered descent."""
    entry = entry or EntryConfig()
    chute = chute or ChuteConfig()
    powered = powered or PoweredDescentConfig()

    alt = entry.entry_alt_m
    v = entry.entry_speed_mps
    fpa_rad = math.radians(entry.flight_path_deg)
    m = entry.vehicle_mass_kg
    # Decompose velocity
    v_vert = v * math.sin(fpa_rad)    # negative = downward
    v_horiz = v * math.cos(fpa_rad)

    traj: List[EDLState] = []
    phases: List[str] = []
    peak_g = 0.0
    peak_qdot = 0.0
    phase = "entry"
    t = 0.0

    while t < 1200.0 and alt > 0:
        rho = mars_density(alt)
        speed = math.sqrt(v_vert * v_vert + v_horiz * v_horiz)
        mach = speed / _A0

        if phase == "entry":
            # Drag accel: a = 0.5 ρ v² / BC  (BC = m / (Cd A))
            a_drag = 0.5 * rho * speed * speed / max(entry.ballistic_coef_kg_m2, 1e-6)
            # Lift accel (perpendicular to velocity, upward for positive L/D)
            a_lift = a_drag * entry.ld_ratio
            # Drag opposes velocity. In the v_vert component the drag
            # contribution is -a_drag * (v_vert/|v|). For a descending
            # capsule (v_vert<0) this is positive (decelerating the fall).
            v_vert += (-a_drag * v_vert / max(speed, 1e-6)
                       + a_lift - G_MARS) * dt_s
            v_horiz += -a_drag * v_horiz / max(speed, 1e-6) * dt_s
            # Chapman heat rate q̇ = k √ρ v³ / √R_nose (W/cm², k=1.83e-4)
            qdot = 1.83e-4 * math.sqrt(rho) * (speed ** 3) / math.sqrt(entry.nose_radius_m) / 1e4
            peak_qdot = max(peak_qdot, qdot)
            accel_g = a_drag / 9.81
            peak_g = max(peak_g, accel_g)
            if mach <= chute.trigger_mach and phase == "entry":
                phase = "chute"
                phases.append("entry")
                continue

        elif phase == "chute":
            # Chute drag with huge area — decelerates quickly to subsonic
            a_drag = 0.5 * rho * speed * speed * chute.drag_coef * chute.area_m2 / m
            if speed > 1e-6:
                # Drag opposes velocity; for v_vert<0 this is positive
                v_vert += (-a_drag * v_vert / speed - G_MARS) * dt_s
                v_horiz += -a_drag * v_horiz / speed * dt_s
            else:
                v_vert += -G_MARS * dt_s
            accel_g = a_drag / 9.81
            peak_g = max(peak_g, accel_g)
            if alt <= powered.trigger_alt_m and phase == "chute":
                phase = "powered_descent"
                phases.append("chute")
                # Chute jettison — drop vehicle mass by 5% (backshell)
                m *= 0.95
                continue

        else:  # powered_descent
            # Gravity-turn guidance: altitude-proportional descent rate
            # so high altitude descends at ~15 m/s, low altitude at touchdown_v.
            target_v = -max(powered.touchdown_speed_mps,
                            min(15.0, 0.02 * alt + 0.5))
            tau = 2.0
            v_vert = target_v + (v_vert - target_v) * math.exp(-dt_s / tau)
            v_horiz *= math.exp(-dt_s / tau)
            # Propellant consumed based on thrust = m × (G + |dv/dt|)
            a_used = abs(G_MARS) + abs(v_vert - target_v) / tau
            thrust_n = min(m * a_used, powered.throttle_thrust_n)
            mdot = thrust_n / (powered.isp_s * 9.80665)
            m = max(m - mdot * dt_s, powered.dry_mass_kg)
            accel_g = a_used / 9.81
            peak_g = max(peak_g, accel_g)
            if alt < 3 and abs(v_vert) <= powered.touchdown_speed_mps * 1.5:
                phases.append("powered_descent")
                phase = "landed"
                break

        alt += v_vert * dt_s
        t += dt_s
        if t % 1.0 < dt_s:
            traj.append(EDLState(
                t_s=t, alt_m=alt, v_mps=speed, mach=mach, phase=phase,
                mass_kg=m, accel_g=peak_g,
            ))

    touchdown_v = math.sqrt(v_vert ** 2 + v_horiz ** 2)
    success = (phase == "landed") and touchdown_v < powered.touchdown_speed_mps * 2

    return EDLResult(
        config=entry,
        phases_done=phases,
        trajectory=traj,
        peak_g=peak_g,
        peak_heat_rate_w_cm2=peak_qdot,
        touchdown_speed_mps=touchdown_v,
        final_mass_kg=m,
        success=success,
        notes=[f"phases: {' → '.join(phases)}; final phase: {phase}"],
    )
