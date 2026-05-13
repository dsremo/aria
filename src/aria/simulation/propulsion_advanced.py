"""Advanced Propulsion — NTP, Ion/Electric, and Fusion drives.

Chemical rockets max out at Isp ≈ 450 s (LOX/LH2). To reach Mars in months
instead of years, or the outer planets at all, we need higher-Isp engines.

PROPULSION TECHNOLOGIES
========================

1. Nuclear Thermal Propulsion (NTP) — Isp ≈ 850-1000 s
   Reactor heats hydrogen propellant to 2500-3000 K, expands through nozzle.
   NERVA (1960s): demonstrated 825 s Isp, 334 kN thrust.
   DRACO (NASA/DARPA 2025+): flight demo targeting 900 s Isp.
   Advantage: 2× Isp of chemical → halves propellant for same ΔV.
   Mars transit: ~4 months instead of ~9 months (higher energy trajectory).

2. Ion / Hall Thruster — Isp ≈ 1,500-10,000 s
   Electric field accelerates ionized propellant (xenon, krypton).
   NEXT-C (NASA): 6,900 s Isp, 0.24 N thrust (Dawn, DART missions).
   SPT-140 (Hall): 1,770 s Isp, 0.29 N thrust (Starlink, Psyche).
   Advantage: 10-20× chemical Isp → dramatic propellant savings.
   Disadvantage: very low thrust → spiral trajectories, months to escape Earth.

3. Fusion Propulsion — Isp ≈ 10,000-1,000,000 s
   D-He3 or p-B11 fusion → exhaust velocity 1,000-100,000 km/s.
   Project Icarus / ICAN-II: conceptual, Isp ≈ 300,000 s.
   Advantage: sufficient for interstellar precursor missions (0.01-0.1c).
   Status: no flight demonstration; earliest practical: 2060+.

PHYSICS
=======
All propulsion follows the same Tsiolkovsky equation:
  ΔV = Isp × g₀ × ln(m_initial / m_final)

The difference is in exhaust velocity (v_e = Isp × g₀) and thrust:
  - Chemical: v_e ≈ 4.4 km/s, thrust ≈ 10⁶ N (impulsive burns)
  - NTP: v_e ≈ 8.8 km/s, thrust ≈ 10⁵ N (near-impulsive)
  - Ion: v_e ≈ 30-90 km/s, thrust ≈ 0.1-1 N (continuous low-thrust)
  - Fusion: v_e ≈ 10,000 km/s, thrust ≈ 10³ N (continuous medium-thrust)

For low-thrust systems, the trajectory is not a Hohmann ellipse but a
spiral. The effective ΔV for a spiral escape from LEO is ~41% higher
than the impulsive Hohmann ΔV (the "gravity loss" penalty).

References
----------
  Borowski S.K. (2012) NASA/TM-2012-217772 — NTP for Mars missions
  NASA DRACO program (2025) — Nuclear thermal flight demonstration
  Patterson M.J. (2007) AIAA-2007-5199 — NEXT ion engine
  Cassibry J.T. et al. (2015) J. Spacecraft 52:1 — fusion propulsion
  Stuhlinger E. (1964) "Ion Propulsion for Space Flight" — low-thrust theory
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

G0 = 9.80665  # Standard gravity (m/s²) — NIST CODATA 2018

# ═══════════════════════════════════════════════════════════════════
#  ENGINE DATABASE
# ═══════════════════════════════════════════════════════════════════
# Each engine: (name, type, Isp_s, thrust_N, mass_kg, power_kw, propellant, source)

ENGINES = {
    # Chemical (reference)
    "rl10b2": {
        "name": "RL10B-2", "type": "chemical_lox_lh2",
        "isp_s": 462.0, "thrust_n": 110_000.0, "mass_kg": 277.0,
        "power_kw": 0.0, "propellant": "LOX/LH2",
        "source": "ULA RL10B-2 spec sheet; Artemis ICPS engine",
    },
    "raptor2": {
        "name": "Raptor 2", "type": "chemical_lox_ch4",
        "isp_s": 350.0, "thrust_n": 2_300_000.0, "mass_kg": 1_600.0,
        "power_kw": 0.0, "propellant": "LOX/CH4",
        "source": "SpaceX Raptor 2 (2022); Starship main engine",
    },
    # Nuclear Thermal
    "nerva": {
        "name": "NERVA XE-Prime", "type": "ntp",
        "isp_s": 825.0, "thrust_n": 334_000.0, "mass_kg": 10_100.0,
        "power_kw": 0.0, "propellant": "LH2",
        "source": "Borowski (2012) NASA/TM-2012-217772; NERVA test series 1969",
    },
    "draco": {
        "name": "DRACO NTP", "type": "ntp",
        "isp_s": 900.0, "thrust_n": 25_000.0, "mass_kg": 3_500.0,
        "power_kw": 0.0, "propellant": "LH2",
        "source": "NASA/DARPA DRACO program (2025); target Isp from program goals",
    },
    # Ion / Electric
    "next_c": {
        "name": "NEXT-C", "type": "ion_gridded",
        "isp_s": 6_900.0, "thrust_n": 0.24, "mass_kg": 12.7,
        "power_kw": 6.9, "propellant": "Xenon",
        "source": "Patterson (2007) AIAA-2007-5199; DART mission engine",
    },
    "spt140": {
        "name": "SPT-140", "type": "hall_thruster",
        "isp_s": 1_770.0, "thrust_n": 0.29, "mass_kg": 8.5,
        "power_kw": 4.5, "propellant": "Xenon",
        "source": "Fakel SPT-140 spec; Psyche mission thruster",
    },
    "vasimr": {
        "name": "VASIMR VX-200", "type": "plasma",
        "isp_s": 5_000.0, "thrust_n": 6.0, "mass_kg": 620.0,
        "power_kw": 200.0, "propellant": "Argon",
        "source": "Chang Díaz (2015) Ad Astra Rocket; VX-200SS ground test",
    },
    # Fusion (conceptual)
    "icf_dthe3": {
        "name": "ICF D-He3", "type": "fusion_icf",
        "isp_s": 300_000.0, "thrust_n": 1_000.0, "mass_kg": 200_000.0,
        "power_kw": 1_000_000.0, "propellant": "D-He3",
        "source": "Cassibry (2015) J. Spacecraft 52:1; Project Icarus baseline",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PropulsionResult:
    """Result of a propulsion calculation."""
    engine_name: str
    engine_type: str
    isp_s: float
    exhaust_velocity_ms: float
    dv_ms: float
    payload_kg: float
    propellant_kg: float
    initial_mass_kg: float
    mass_ratio: float
    burn_time_s: Optional[float] = None
    thrust_n: Optional[float] = None


@dataclass
class LowThrustTransfer:
    """Low-thrust (ion/electric) spiral transfer result."""
    engine_name: str
    dv_impulsive_ms: float         # Equivalent Hohmann ΔV
    dv_spiral_ms: float            # Actual ΔV including gravity losses
    gravity_loss_factor: float     # Spiral ΔV / impulsive ΔV
    thrust_n: float
    spacecraft_mass_kg: float
    acceleration_ms2: float
    burn_time_days: float
    propellant_kg: float
    power_required_kw: float


@dataclass
class MissionComparison:
    """Side-by-side comparison of engines for the same mission."""
    mission_name: str
    dv_ms: float
    payload_kg: float
    results: list[PropulsionResult]


# ═══════════════════════════════════════════════════════════════════
#  CORE CALCULATIONS
# ═══════════════════════════════════════════════════════════════════

def tsiolkovsky(
    dv_ms: float,
    payload_kg: float,
    isp_s: float,
) -> PropulsionResult:
    """Compute propellant mass from the ideal rocket equation.

    ΔV = Isp × g₀ × ln(m_i / m_f)
    m_i / m_f = exp(ΔV / (Isp × g₀))
    propellant = m_i − m_f = m_f × (exp(ΔV/v_e) − 1)

    Args:
        dv_ms:      Required velocity change (m/s).
        payload_kg: Dry mass (everything except propellant) (kg).
        isp_s:      Specific impulse (s).

    Returns:
        PropulsionResult with mass breakdown.

    References:
        Tsiolkovsky K.E. (1903) — ideal rocket equation.
    """
    v_e = isp_s * G0
    mass_ratio = math.exp(dv_ms / v_e)
    initial_mass = payload_kg * mass_ratio
    propellant = initial_mass - payload_kg

    return PropulsionResult(
        engine_name="generic",
        engine_type="generic",
        isp_s=isp_s,
        exhaust_velocity_ms=v_e,
        dv_ms=dv_ms,
        payload_kg=payload_kg,
        propellant_kg=propellant,
        initial_mass_kg=initial_mass,
        mass_ratio=mass_ratio,
    )


def engine_burn(
    engine_key: str,
    dv_ms: float,
    payload_kg: float,
) -> PropulsionResult:
    """Compute propellant and burn time for a specific engine.

    Args:
        engine_key: Key in ENGINES dict.
        dv_ms:      Required ΔV (m/s).
        payload_kg: Dry mass (kg).

    Returns:
        PropulsionResult with engine-specific parameters.
    """
    if engine_key not in ENGINES:
        raise ValueError(f"Unknown engine: {engine_key}. Use: {list(ENGINES.keys())}")

    eng = ENGINES[engine_key]
    result = tsiolkovsky(dv_ms, payload_kg, eng["isp_s"])
    result.engine_name = eng["name"]
    result.engine_type = eng["type"]
    result.thrust_n = eng["thrust_n"]

    # Burn time: t = m_prop × v_e / F
    if eng["thrust_n"] > 0:
        result.burn_time_s = result.propellant_kg * result.exhaust_velocity_ms / eng["thrust_n"]

    return result


def low_thrust_transfer(
    engine_key: str,
    dv_impulsive_ms: float,
    spacecraft_mass_kg: float,
    gravity_loss_factor: float = 1.41,
) -> LowThrustTransfer:
    """Compute a low-thrust spiral transfer (ion/electric propulsion).

    Low-thrust engines can't do impulsive burns. The spiral trajectory
    requires ~41% more ΔV than the Hohmann equivalent (Edelbaum 1961):
      ΔV_spiral ≈ 1.41 × ΔV_Hohmann  (for LEO escape)

    For interplanetary transfers the factor varies (1.0-1.5 depending
    on the specific trajectory and thrust-to-weight ratio).

    Args:
        engine_key:          Engine key in ENGINES dict.
        dv_impulsive_ms:     Equivalent impulsive (Hohmann) ΔV (m/s).
        spacecraft_mass_kg:  Total spacecraft mass at start (kg).
        gravity_loss_factor: Spiral ΔV / impulsive ΔV. Default 1.41
                             (Edelbaum 1961 for LEO escape).

    Returns:
        LowThrustTransfer with burn time and power requirements.

    References:
        Edelbaum T.N. (1961) ARS Journal 31:4 — low-thrust orbit transfer.
        Stuhlinger E. (1964) "Ion Propulsion for Space Flight".
    """
    eng = ENGINES[engine_key]
    dv_spiral = dv_impulsive_ms * gravity_loss_factor

    result = tsiolkovsky(dv_spiral, spacecraft_mass_kg, eng["isp_s"])
    accel = eng["thrust_n"] / spacecraft_mass_kg
    burn_time_s = result.propellant_kg * result.exhaust_velocity_ms / eng["thrust_n"]

    return LowThrustTransfer(
        engine_name=eng["name"],
        dv_impulsive_ms=dv_impulsive_ms,
        dv_spiral_ms=dv_spiral,
        gravity_loss_factor=gravity_loss_factor,
        thrust_n=eng["thrust_n"],
        spacecraft_mass_kg=spacecraft_mass_kg,
        acceleration_ms2=accel,
        burn_time_days=burn_time_s / 86400.0,
        propellant_kg=result.propellant_kg,
        power_required_kw=eng["power_kw"],
    )


# ═══════════════════════════════════════════════════════════════════
#  MISSION COMPARISONS
# ═══════════════════════════════════════════════════════════════════

def compare_engines_for_mission(
    mission_name: str,
    dv_ms: float,
    payload_kg: float,
    engine_keys: Optional[list[str]] = None,
) -> MissionComparison:
    """Compare multiple engines for the same mission ΔV.

    Args:
        mission_name: Descriptive name.
        dv_ms:        Total mission ΔV (m/s).
        payload_kg:   Dry payload mass (kg).
        engine_keys:  Engine keys to compare. Default: all engines.

    Returns:
        MissionComparison with results for each engine.
    """
    if engine_keys is None:
        engine_keys = list(ENGINES.keys())

    results = []
    for key in engine_keys:
        r = engine_burn(key, dv_ms, payload_kg)
        results.append(r)

    return MissionComparison(mission_name, dv_ms, payload_kg, results)


def mars_propulsion_comparison(payload_kg: float = 50_000.0) -> MissionComparison:
    """Compare propulsion options for a Mars round-trip mission.

    Total ΔV ≈ 7,800 m/s (conjunction-class Hohmann round-trip).

    References:
        Borowski (2012) NASA/TM-2012-217772 — NTP Mars mission architecture.
    """
    return compare_engines_for_mission(
        "Mars Round-Trip",
        dv_ms=7_800.0,
        payload_kg=payload_kg,
        engine_keys=["rl10b2", "raptor2", "nerva", "draco", "vasimr", "icf_dthe3"],
    )


def interstellar_precursor_comparison(
    payload_kg: float = 1_000.0,
    target_speed_kms: float = 100.0,
) -> MissionComparison:
    """Compare propulsion options for an interstellar precursor mission.

    Target: 100 km/s (0.033% c) — reaches 100 AU in ~5 years.
    This is the "fast solar system exit" regime.

    References:
        McNutt et al. (2019) "Interstellar Probe" — 200 AU science mission.
    """
    dv = target_speed_kms * 1000.0  # km/s → m/s
    return compare_engines_for_mission(
        f"Interstellar Precursor ({target_speed_kms:.0f} km/s)",
        dv_ms=dv,
        payload_kg=payload_kg,
        engine_keys=["nerva", "draco", "next_c", "vasimr", "icf_dthe3"],
    )


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── Engine Database ──────────────────────────────────────────")
    print(f"  {'Engine':<18s}  {'Type':<18s}  {'Isp (s)':>8s}  {'Thrust':>12s}  {'Propellant'}")
    for key, eng in ENGINES.items():
        thrust_str = f"{eng['thrust_n']:.0f} N" if eng["thrust_n"] > 1 else f"{eng['thrust_n']*1000:.0f} mN"
        print(f"  {eng['name']:<18s}  {eng['type']:<18s}  {eng['isp_s']:>8.0f}  "
              f"{thrust_str:>12s}  {eng['propellant']}")

    print("\n── Mars Round-Trip (50,000 kg payload, 7800 m/s ΔV) ────────")
    comp = mars_propulsion_comparison()
    print(f"  {'Engine':<18s}  {'Isp':>6s}  {'Propellant':>12s}  {'Total Mass':>12s}  {'Ratio':>6s}")
    for r in comp.results:
        print(f"  {r.engine_name:<18s}  {r.isp_s:>5.0f}s  {r.propellant_kg:>11.0f}kg  "
              f"{r.initial_mass_kg:>11.0f}kg  {r.mass_ratio:>5.1f}×")

    print("\n── Interstellar Precursor (1,000 kg, 100 km/s) ─────────────")
    icomp = interstellar_precursor_comparison()
    print(f"  {'Engine':<18s}  {'Isp':>8s}  {'Propellant':>14s}  {'Ratio':>8s}  {'Feasible'}")
    for r in icomp.results:
        feasible = "YES" if r.mass_ratio < 100 else "NO (too much fuel)"
        print(f"  {r.engine_name:<18s}  {r.isp_s:>7.0f}s  {r.propellant_kg:>13.0f}kg  "
              f"{r.mass_ratio:>7.1f}×  {feasible}")
