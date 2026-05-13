"""Delta-V Budget — mission trajectory analysis.

Every maneuver costs delta-v. The total delta-v budget determines
whether the ship has enough propellant to complete the mission.

TSIOLKOVSKY ROCKET EQUATION:
  Δv = Isp × g₀ × ln(m₀/m_f)
  Where: Isp = specific impulse (s), g₀ = 9.81 m/s², m₀ = wet mass, m_f = dry mass

MISSION PHASES (Proxima Centauri, 4.24 ly):
  1. Earth departure:    Δv ~10 km/s (escape + injection)
  2. Cruise acceleration: Δv ~30,000 km/s (0.1c = 29,979 km/s)
  3. Mid-course correction: Δv ~100 m/s
  4. Deceleration:        Δv ~30,000 km/s (Forward staged-sail + magsail + fusion)
  5. Orbital insertion:   Δv ~5 km/s (Hohmann transfer to planet)
  6. Station-keeping:     Δv ~50 m/s/yr × mission duration

PROPULSION TYPES (from relativistic_physics.py):
  D-T fusion:     Isp = 100,000 s (exhaust velocity ~1,000 km/s)
  D-He3 fusion:   Isp = 1,000,000 s (10,000 km/s)
  Antimatter:     Isp = 10,000,000 s (100,000 km/s)

References:
  - Tsiolkovsky (1903) rocket equation
  - Forward (1984) staged-sail deceleration
  - Zubrin (1991) magsail braking
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

G0 = 9.80665  # m/s² — ISO 80000-3:2019 standard gravity. Matches physics/departure/tsiolkovsky.py. 9.81 rounds ~0.07 % high and introduced a multi-module Δv drift.
C = 299_792_458  # m/s — CODATA 2018 speed of light


@dataclass
class ManeuverBudget:
    """A single delta-v maneuver."""
    name: str
    phase: str
    delta_v_ms: float
    propellant_kg: float
    source: str


@dataclass
class DeltaVBudget:
    """Complete mission delta-v budget."""
    maneuvers: list[ManeuverBudget] = field(default_factory=list)
    total_delta_v_ms: float = 0.0
    total_propellant_kg: float = 0.0
    mass_ratio: float = 1.0
    propellant_fraction: float = 0.0

    def add(self, name: str, phase: str, delta_v_ms: float,
            propellant_kg: float, source: str) -> None:
        self.maneuvers.append(ManeuverBudget(name, phase, delta_v_ms, propellant_kg, source))
        self.total_delta_v_ms += delta_v_ms
        self.total_propellant_kg += propellant_kg

    def summary(self) -> str:
        lines = ["DELTA-V BUDGET", "=" * 70]
        for m in self.maneuvers:
            lines.append(
                f"  {m.phase:12s}  {m.name:30s}  "
                f"Δv={m.delta_v_ms/1000:>10,.1f} km/s  "
                f"prop={m.propellant_kg:>12,.0f} kg"
            )
        lines.append("-" * 70)
        lines.append(f"  {'TOTAL':12s}  {'':30s}  "
                     f"Δv={self.total_delta_v_ms/1000:>10,.1f} km/s  "
                     f"prop={self.total_propellant_kg:>12,.0f} kg")
        lines.append(f"  Mass ratio: {self.mass_ratio:.2f}")
        lines.append(f"  Propellant fraction: {self.propellant_fraction:.1%}")
        return "\n".join(lines)


def tsiolkovsky(delta_v_ms: float, isp_s: float, dry_mass_kg: float) -> float:
    """Compute propellant mass from Tsiolkovsky equation.

    Returns propellant mass in kg.
    """
    v_exhaust = isp_s * G0
    mass_ratio = math.exp(delta_v_ms / v_exhaust)
    wet_mass = dry_mass_kg * mass_ratio
    return wet_mass - dry_mass_kg


def relativistic_tsiolkovsky(delta_v_ms: float, isp_s: float, dry_mass_kg: float) -> float:
    """Relativistic rocket equation for v > 0.01c.

    m₀/m_f = [(1 + v/c)/(1 - v/c)]^(c / 2v_e)
    """
    v_exhaust = isp_s * G0
    beta = delta_v_ms / C

    if beta < 0.01:
        return tsiolkovsky(delta_v_ms, isp_s, dry_mass_kg)

    # Relativistic mass ratio
    exponent = C / (2 * v_exhaust)
    ratio = ((1 + beta) / (1 - beta)) ** exponent
    wet_mass = dry_mass_kg * ratio
    return wet_mass - dry_mass_kg


def compute_deltav_budget(
    target_distance_ly: float = 4.24,
    cruise_velocity_c: float = 0.1,
    dry_mass_kg: float = 100_000_000,
    isp_s: float = 100_000,  # D-T fusion
    use_magsail_braking: bool = True,
) -> DeltaVBudget:
    """Compute complete mission delta-v budget.

    Args:
        target_distance_ly: Distance to target star
        cruise_velocity_c: Cruise velocity as fraction of c
        dry_mass_kg: Ship dry mass (no propellant)
        isp_s: Specific impulse of main engine
        use_magsail_braking: Whether magsail assists deceleration
    """
    budget = DeltaVBudget()
    cruise_v_ms = cruise_velocity_c * C

    # Phase 1: External laser sail acceleration (Forward 1984)
    # Ship is accelerated to 0.1c by a 7.2 TW laser array at Sol
    # No onboard propellant consumed for acceleration
    budget.add("Laser sail acceleration", "departure", cruise_v_ms, 0,
               "Forward 1984 lightsail: 7.2 TW laser at Sol (no onboard fuel)")

    # Phase 2: No onboard cruise acceleration needed
    # D-T fusion (Isp=100,000s) cannot reach 0.1c — mass ratio = e^30.6 = 10^13
    # The ship is PURELY laser-propelled to cruise velocity

    # Phase 3: Mid-course corrections
    dv_midcourse = 500  # 500 m/s total over mission
    prop_midcourse = tsiolkovsky(dv_midcourse, isp_s, dry_mass_kg)
    budget.add("Mid-course corrections", "cruise", dv_midcourse, prop_midcourse,
               "~10 corrections × 50 m/s each")

    # Phase 4: Deceleration
    if use_magsail_braking:
        # Forward staged-sail + magsail handles most deceleration
        # Ship only needs fusion for final orbital insertion
        dv_decel_fusion = 5_000  # 5 km/s final fusion burn
        prop_decel = tsiolkovsky(dv_decel_fusion, isp_s, dry_mass_kg)
        budget.add("Magsail primary braking", "decel", cruise_v_ms * 0.95, 0,
                   "Forward 1984 staged sail + Zubrin magsail (no propellant)")
        budget.add("Fusion final braking", "decel", dv_decel_fusion, prop_decel,
                   "Fusion burn for orbital capture velocity")
    else:
        # Pure fusion braking: physically impossible with D-T (Isp=100Ks)
        # Mass ratio = e^(30000/981) = 10^13. Requires D-He3 or antimatter.
        v_exhaust = isp_s * G0
        achievable_dv = v_exhaust * math.log(2.0)  # Mass ratio of 2 (50% propellant)
        prop_decel = tsiolkovsky(min(cruise_v_ms, achievable_dv), isp_s, dry_mass_kg)
        budget.add("Fusion deceleration", "decel", min(cruise_v_ms, achievable_dv),
                   prop_decel, "Pure fusion — requires enormous propellant")

    # Phase 5: Orbital insertion
    dv_orbit = 4_354  # From orbital_destination.py capture Δv at Proxima b
    prop_orbit = tsiolkovsky(dv_orbit, isp_s, dry_mass_kg)
    budget.add("Orbital insertion", "arrival", dv_orbit, prop_orbit,
               "Hohmann transfer to Proxima b orbit")

    # Phase 6: Station-keeping
    dv_sk = 50 * 100  # 50 m/s/yr × 100 years of orbiting
    prop_sk = tsiolkovsky(dv_sk, isp_s, dry_mass_kg)
    budget.add("Station-keeping (100 yr)", "orbit", dv_sk, prop_sk,
               "50 m/s/yr for orbit maintenance")

    # Compute overall mass ratio
    budget.mass_ratio = (dry_mass_kg + budget.total_propellant_kg) / dry_mass_kg
    budget.propellant_fraction = budget.total_propellant_kg / (dry_mass_kg + budget.total_propellant_kg)

    return budget
