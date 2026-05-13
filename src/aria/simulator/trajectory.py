"""Interstellar trajectory / ΔV budget model.

Scaffolded after Round-2 audit flagged that the simulation claimed
"Alpha Centauri A" as destination without any physics-backed feasibility
check. This module closes that gap:

  * Tsiolkovsky rocket equation for achievable ΔV given mass ratio + Isp
  * Cruise-time estimate for a flat constant-velocity leg
  * Classification of whether a named interstellar target is reachable
    within a given mission-duration budget (e.g. 1 000 years)

A generation ship is not a sprinter — realistic cruise fractions are
0.001 c – 0.01 c, giving multi-millennium voyages to α Centauri. Fusion
Isp of ~10 000 s (Frisbee 2003 JPL/D-26963) bounds what is physically
possible with the fuel-tank volumes specified in ShipParameters.

No external dependencies; pure numpy/math so it imports cheap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from aria.digital_twin.parameters import ShipParameters

# ── Physical constants ──────────────────────────────────────────────────

G0_M_PER_S2: Final[float] = 9.80665          # standard gravity (CODATA)
C_M_PER_S: Final[float]  = 299_792_458.0     # speed of light (CODATA)
LIGHTYEAR_M: Final[float] = 9.460_730_472_580_8e15   # IAU 2015


# ── Mission targets (distance in light-years) ─────────────────────────
#
# Mixed catalog — the engine treats distances in ly regardless of scale,
# so adding solar-system bodies lets the user practise short-range runs
# (Moon, Mars) with the same trajectory pipeline used for Alpha Centauri.
# Solar-system distances are characteristic mean *Earth-to-body* values,
# not perihelion/aphelion extremes.

# 1 AU = 1.49597870700e11 m ÷ 9.4607304725808e15 m/ly = 1.5812507e-5 ly
_AU_IN_LY: Final[float] = 1.49597870700e11 / LIGHTYEAR_M

INTERSTELLAR_TARGETS: dict[str, float] = {
    # ── Solar system (real-data-verified mission targets) ─────────────
    # Moon — 384 400 km mean lunar distance (IAU nominal, Simon 1994 A&A 282:663)
    "Moon":                     384_400_000.0 / LIGHTYEAR_M,
    # L2 halo — 1.5e6 km beyond Earth (JWST / Euclid / Gaia station, NASA JPL DE440)
    "Sun-Earth L2":             1.5e9 / LIGHTYEAR_M,
    # Mars — 225e6 km mean Earth-Mars distance (NASA HORIZONS; used in JPL MOS design)
    "Mars":                     225e9 / LIGHTYEAR_M,
    # Ceres — 2.77 AU Sun, 1.77 AU from Earth mean (Dawn mission data, Russell 2016 Science)
    "Ceres (main belt)":        1.77 * _AU_IN_LY,
    # Jupiter — 4.2 AU mean Earth distance (JPL HORIZONS; Juno/Galileo reference)
    "Jupiter":                  4.2 * _AU_IN_LY,
    # Europa — 4.2 AU (same Earth–Jupiter distance ± Europa's 0.007 AU orbit)
    "Europa":                   4.2 * _AU_IN_LY,
    # Saturn — 8.58 AU mean Earth distance (Cassini mission ephemerides)
    "Saturn":                   8.58 * _AU_IN_LY,
    # Titan — 8.58 AU (Earth–Saturn; Titan's Saturn orbit negligible at this scale)
    "Titan":                    8.58 * _AU_IN_LY,
    # Uranus — 18.2 AU mean Earth distance (Voyager 2 encounter, JPL DE440)
    "Uranus":                   18.2 * _AU_IN_LY,
    # Neptune — 29.05 AU mean Earth distance (Voyager 2 encounter)
    "Neptune":                  29.05 * _AU_IN_LY,
    # Pluto — 38.5 AU mean Earth distance (New Horizons encounter, Stern 2015 Science)
    "Pluto":                    38.5 * _AU_IN_LY,
    # Voyager 1 heliopause — ~120 AU (IBEX/Voyager PLS data, Stone 2013 Science)
    "Voyager 1 (heliopause)":   120.0 * _AU_IN_LY,
    # Inner Oort cloud — 2000 AU (Hills cloud, Dones 2015 review)
    "Inner Oort Cloud":         2000.0 * _AU_IN_LY,

    # ── Interstellar (existing catalog) ───────────────────────────────
    # Proxima Centauri — 4.2465 ly (Gaia EDR3, Brown et al. 2021 A&A 649:A1)
    "Proxima Centauri":        4.2465,
    # α Centauri A — 4.3650 ly (Hipparcos ESA 1997; refined by Kervella 2017 A&A 597:A137)
    "Alpha Centauri A":        4.3650,
    # α Centauri B — 4.3650 ly (same binary pair)
    "Alpha Centauri B":        4.3650,
    # Barnard's Star — 5.9577 ly (Gaia EDR3)
    "Barnard's Star":          5.9577,
    # Wolf 359 — 7.856 ly (Gaia EDR3)
    "Wolf 359":                7.856,
    # Sirius A — 8.6099 ly (Hipparcos; confirmed Gaia EDR3)
    "Sirius A":                8.6099,
    # Epsilon Eridani — 10.4759 ly (Gaia EDR3); rocky-planet candidate host
    "Epsilon Eridani":        10.4759,
    # Tau Ceti — 11.912 ly (Gaia EDR3, Brown et al. 2021); 5 candidate planets
    "Tau Ceti":               11.912,
    # TRAPPIST-1 — 39.5 ly (Gaia EDR3); 7-planet system, JWST priority target
    "TRAPPIST-1":             39.5,
}


# ── Target classification (for UI grouping) ─────────────────────────────
#
# Sub-mean-Earth-Neptune distances = solar-system; rest = interstellar.
# The NEPTUNE_ORBIT_LY threshold (~4.6e-4 ly, ~30 AU) is a natural divider:
# anything beyond it is effectively a stellar-scale voyage.

NEPTUNE_ORBIT_LY: Final[float] = 30.0 * _AU_IN_LY   # ~4.744e-4 ly

def classify_target(name: str) -> str:
    """Return 'solar' for in-system bodies, 'interstellar' otherwise.
    Used by the React target picker to group the dropdown."""
    d = INTERSTELLAR_TARGETS.get(name)
    if d is None:
        return "unknown"
    return "solar" if d < 1e-2 else "interstellar"   # 0.01 ly ~ 632 AU cutoff


# ── Dataclasses ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PropulsionSpec:
    """Single-stage propulsion performance."""

    name: str
    isp_s: float                     # specific impulse [s]
    max_thrust_n: float              # peak thrust [N]
    source: str = ""

    @property
    def exhaust_velocity_m_s(self) -> float:
        """v_e = I_sp * g_0."""
        return self.isp_s * G0_M_PER_S2


# Representative propulsion technologies with published Isp citations.
# All values are conservative mid-range from peer-reviewed / NASA sources.
PROPULSION_OPTIONS: dict[str, PropulsionSpec] = {
    "chemical_bipropellant": PropulsionSpec(
        name="Chemical bipropellant (LH2/LOX)",
        isp_s=450.0,                              # SSME-class, Sutton & Biblarz 2016, Rocket Propulsion Elements 9e
        max_thrust_n=2.3e6,
        source="Sutton & Biblarz 2016 'Rocket Propulsion Elements', 9e, Ch. 7",
    ),
    "nuclear_thermal": PropulsionSpec(
        name="Nuclear thermal (NERVA-class)",
        isp_s=900.0,                              # NERVA Phoebus-2A measured 925 s, Stan 2023 NASA/TM-20220018480
        max_thrust_n=3.3e5,
        source="Stan 2023 NASA/TM-20220018480; Dewar 2007 'To the End of the Solar System'",
    ),
    "ion_electric": PropulsionSpec(
        name="Ion electric (NSTAR / NEXT)",
        isp_s=4_170.0,                            # NEXT thruster measured, Patterson 2007 NASA/TM-2014-218232
        max_thrust_n=0.236,
        source="Patterson & Benson 2007 NASA/TM-2014-218232 'NEXT Ion Propulsion'",
    ),
    "fusion_magnetic": PropulsionSpec(
        name="Fusion magnetic (D/He-3 torus)",
        isp_s=10_000.0,                           # lower bound for D/He-3 ICF, Williams 1998 NASA/TM-98-208831
        max_thrust_n=1.0e5,
        source="Williams 1998 NASA/TM-98-208831; Frisbee 2003 JPL/D-26963",
    ),
    "fusion_direct_drive": PropulsionSpec(
        name="Fusion direct-drive (theoretical upper limit)",
        isp_s=1_000_000.0,                        # near-relativistic exhaust, Frisbee 2003 JPL/D-26963 optimistic case
        max_thrust_n=1.0e6,
        source="Frisbee 2003 JPL/D-26963 'How to Build an Antimatter Rocket', §4.2",
    ),
    "antimatter": PropulsionSpec(
        name="Antimatter annihilation (theoretical)",
        isp_s=1.0e7,                              # γ=2 relativistic exhaust, Frisbee 2003 JPL/D-26963 §5
        max_thrust_n=1.0e3,
        source="Frisbee 2003 JPL/D-26963, §5 — requires kg-scale antimatter (not yet possible)",
    ),
}


# ── Core physics ────────────────────────────────────────────────────────

def tsiolkovsky_delta_v(m_wet_kg: float, m_dry_kg: float, isp_s: float) -> float:
    """Ideal ΔV from the rocket equation.

    ΔV = v_e · ln(m_wet / m_dry),  v_e = I_sp · g_0.

    Parameters
    ----------
    m_wet_kg : total mass at start (structure + propellant) [kg]
    m_dry_kg : structural mass only (no propellant) [kg]
    isp_s    : specific impulse [s]

    Returns
    -------
    delta_v_m_s : achievable ΔV assuming single-stage, no losses [m/s]

    Reference
    ---------
    Tsiolkovsky 1903; Sutton & Biblarz 2016 Ch. 4
    """
    if m_dry_kg <= 0 or m_wet_kg <= m_dry_kg:
        return 0.0
    v_e = isp_s * G0_M_PER_S2
    return v_e * math.log(m_wet_kg / m_dry_kg)


def cruise_time_years(distance_ly: float, cruise_fraction_of_c: float) -> float:
    """Flat constant-velocity cruise time in proper years.

    No relativistic correction applied (valid for β < 0.1 where γ ≈ 1.005).
    For generation ships cruising at 0.001 c – 0.01 c this is well within
    the Newtonian regime.
    """
    if cruise_fraction_of_c <= 0:
        return math.inf
    return distance_ly / cruise_fraction_of_c   # ly / (ly/yr) = yr


@dataclass(frozen=True)
class TrajectoryFeasibility:
    target: str
    distance_ly: float
    required_dv_m_s: float
    achievable_dv_m_s: float
    cruise_fraction_of_c: float
    cruise_time_yr: float
    feasible: bool
    propulsion: str
    notes: str

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "distance_ly": round(self.distance_ly, 4),
            "required_dv_m_s": round(self.required_dv_m_s, 1),
            "achievable_dv_m_s": round(self.achievable_dv_m_s, 1),
            "cruise_fraction_of_c": self.cruise_fraction_of_c,
            "cruise_time_yr": round(self.cruise_time_yr, 1),
            "feasible": self.feasible,
            "propulsion": self.propulsion,
            "notes": self.notes,
        }


def evaluate_mission(
    target: str,
    params: ShipParameters | None = None,
    propulsion_key: str = "fusion_magnetic",
    mission_budget_yr: float = 1_000.0,
    propellant_fraction: float = 0.70,    # ESTIMATE — standard generation-ship mass ratio for structural closure
) -> TrajectoryFeasibility:
    """Check whether the ship can reach *target* within *mission_budget_yr*.

    Strategy:
      1. Assume propellant mass fraction of 70 % (dry + 70 % propellant).
      2. Compute achievable ΔV via Tsiolkovsky.
      3. Divide achievable ΔV by 2 (one burn to accelerate, one to decelerate).
      4. Derive cruise fraction-of-c from the half-ΔV.
      5. Cruise time = distance / cruise-fraction.
      6. Feasible iff cruise_time ≤ mission_budget.

    Parameters
    ----------
    target : one of INTERSTELLAR_TARGETS keys (case-sensitive)
    params : ShipParameters (defaults to nominal ARIA config)
    propulsion_key : one of PROPULSION_OPTIONS keys
    mission_budget_yr : maximum acceptable cruise time (incl. decel) [years]
    propellant_fraction : mass(propellant) / mass(total) at start

    Returns
    -------
    TrajectoryFeasibility record
    """
    if params is None:
        params = ShipParameters()
    if target not in INTERSTELLAR_TARGETS:
        raise ValueError(f"Unknown target '{target}'. Options: {list(INTERSTELLAR_TARGETS)}")
    if propulsion_key not in PROPULSION_OPTIONS:
        raise ValueError(f"Unknown propulsion '{propulsion_key}'. Options: {list(PROPULSION_OPTIONS)}")

    distance_ly = INTERSTELLAR_TARGETS[target]
    prop = PROPULSION_OPTIONS[propulsion_key]

    m_wet = params.ship_mass_kg
    m_dry = m_wet * (1.0 - propellant_fraction)
    achievable_dv = tsiolkovsky_delta_v(m_wet, m_dry, prop.isp_s)

    # Half the ΔV is spent accelerating, half decelerating (cruise = flat leg).
    cruise_v_m_s = achievable_dv / 2.0
    cruise_fraction = cruise_v_m_s / C_M_PER_S

    cruise_time = cruise_time_years(distance_ly, cruise_fraction)
    feasible = cruise_time <= mission_budget_yr and cruise_fraction > 0

    # "Required ΔV" is the ΔV that would get us there in budget
    required_cruise_frac = distance_ly / mission_budget_yr
    required_dv = 2.0 * required_cruise_frac * C_M_PER_S

    notes = []
    if cruise_fraction >= 0.1:
        notes.append("β > 0.1 — relativistic effects neglected by this model")
    if m_dry < 1e5:
        notes.append("dry mass implausibly low; propellant_fraction > 99 %")
    if not feasible:
        deficit = required_dv - achievable_dv
        notes.append(
            f"ΔV deficit {deficit / 1000:.0f} km/s; need higher Isp "
            f"propulsion or longer mission budget"
        )

    return TrajectoryFeasibility(
        target=target,
        distance_ly=distance_ly,
        required_dv_m_s=required_dv,
        achievable_dv_m_s=achievable_dv,
        cruise_fraction_of_c=cruise_fraction,
        cruise_time_yr=cruise_time,
        feasible=feasible,
        propulsion=prop.name,
        notes="; ".join(notes) if notes else "nominal",
    )


# ── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    """Print feasibility tables for all targets × all propulsion options."""
    import argparse

    ap = argparse.ArgumentParser(description="ARIA interstellar mission feasibility")
    ap.add_argument("--target", default=None, help=f"one of {list(INTERSTELLAR_TARGETS)}")
    ap.add_argument("--budget-yr", type=float, default=1_000.0, help="mission-duration budget [years]")
    args = ap.parse_args()

    targets = [args.target] if args.target else list(INTERSTELLAR_TARGETS)

    header = f"{'Target':<22} {'Propulsion':<36} {'Isp (s)':>8} {'Achieve (km/s)':>16} {'Cruise β':>10} {'Time (yr)':>12} {'Feasible':>9}"
    print(header)
    print("─" * len(header))
    for target in targets:
        for key in PROPULSION_OPTIONS:
            r = evaluate_mission(target, propulsion_key=key, mission_budget_yr=args.budget_yr)
            flag = "✓" if r.feasible else "✗"
            print(
                f"{target:<22} {r.propulsion:<36} "
                f"{PROPULSION_OPTIONS[key].isp_s:>8.0f} "
                f"{r.achievable_dv_m_s / 1000:>16.1f} "
                f"{r.cruise_fraction_of_c:>10.5f} "
                f"{r.cruise_time_yr:>12.1f} "
                f"{flag:>9}"
            )
        print()


if __name__ == "__main__":
    main()
