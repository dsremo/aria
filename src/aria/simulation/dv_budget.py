"""Delta-V Budget Tool — mission-level propellant planning for any destination.

Every space mission is fundamentally a ΔV budget: how much velocity change do
you need, and how much fuel does that require? This module computes the full
ΔV breakdown for missions from Earth orbit to any planet, Moon, or deep space.

WHAT THIS COMPUTES
==================
For a given mission (e.g., Earth → Mars orbit → surface → return):
  1. Launch to parking orbit: ΔV₁ (not modeled — launch vehicle dependent)
  2. Departure burn (TLI/TMI): ΔV₂ from vis-viva
  3. Arrival burn (LOI/MOI): ΔV₃ from vis-viva
  4. Landing: ΔV₄ (gravity + drag losses)
  5. Ascent: ΔV₅ (same as landing, roughly)
  6. Return departure: ΔV₆
  7. Earth entry: ΔV₇ (aerobraking or propulsive)
  Total: ΣΔV = ΔV₂ + ΔV₃ + ... + ΔV₇

Then Tsiolkovsky gives the mass ratio:
  m_initial / m_final = exp(ΣΔV / (Isp × g₀))

SOLAR SYSTEM ΔV MAP
===================
Published Hohmann transfer ΔV values (Wertz "Space Mission Engineering" Table 6-4;
Vallado 4th ed Table 6-3):

  Destination    | Departure ΔV | Arrival ΔV | Total (one-way)
  Moon (LOI)     |   3,130      |    900     |   4,030 m/s
  Mars (MOI)     |   3,600      |    900     |   4,500 m/s
  Venus (VOI)    |   3,500      |   3,300    |   6,800 m/s
  Jupiter (JOI)  |   6,300      |    600     |   6,900 m/s (gravity assist: ~1,000)
  Saturn (SOI)   |   7,300      |    500     |   7,800 m/s (with Jupiter GA: ~3,000)

References
----------
  Wertz J.R. et al. "Space Mission Engineering: The New SMAD" Table 6-4
  Vallado D.A. (2013) 4th ed §6.3 — Hohmann transfer ΔV
  Curtis H.D. (2014) "Orbital Mechanics for Engineering Students" §8
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

G0 = 9.80665               # Standard gravity (m/s²) — NIST CODATA 2018
MU_SUN = 1.32712440018e20  # Sun GM (m³/s²) — JPL DE430
AU_M = 1.495978707e11      # Astronomical unit (m) — IAU 2012

# Planetary data: (name, orbit_radius_AU, mu_m3s2, radius_m, atmo_flag)
# Sources: Vallado 4th ed Table D-3; JPL Solar System Dynamics
PLANETS = {
    "mercury":  {"a_au": 0.387, "mu": 2.2032e13,  "r_m": 2.4397e6,  "atmo": False},
    "venus":    {"a_au": 0.723, "mu": 3.2486e14,  "r_m": 6.0518e6,  "atmo": True},
    "earth":    {"a_au": 1.000, "mu": 3.986e14,   "r_m": 6.3781e6,  "atmo": True},
    "mars":     {"a_au": 1.524, "mu": 4.2828e13,  "r_m": 3.3962e6,  "atmo": True},
    "jupiter":  {"a_au": 5.203, "mu": 1.2669e17,  "r_m": 7.1492e7,  "atmo": True},
    "saturn":   {"a_au": 9.537, "mu": 3.7931e16,  "r_m": 6.0268e7,  "atmo": True},
    "uranus":   {"a_au": 19.19, "mu": 5.7940e15,  "r_m": 2.5559e7,  "atmo": True},
    "neptune":  {"a_au": 30.07, "mu": 6.8351e15,  "r_m": 2.4764e7,  "atmo": True},
    "moon":     {"a_au": None,  "mu": 4.9049e12,  "r_m": 1.7374e6,  "atmo": False},
}

# Standard parking orbit for ΔV calculations
DEFAULT_PARKING_ALT_KM = 185.0  # LEO parking orbit — NASA standard


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DVPhase:
    """A single phase in a ΔV budget."""
    name: str
    dv_ms: float
    description: str


@dataclass
class DVBudget:
    """Complete mission ΔV budget with propellant mass."""
    mission_name: str
    destination: str
    phases: list[DVPhase]
    total_dv_ms: float
    # Propellant (computed from Tsiolkovsky if Isp provided)
    isp_s: Optional[float] = None
    payload_kg: Optional[float] = None
    initial_mass_kg: Optional[float] = None
    propellant_kg: Optional[float] = None
    mass_ratio: Optional[float] = None


# ═══════════════════════════════════════════════════════════════════
#  HOHMANN TRANSFER ΔV
# ═══════════════════════════════════════════════════════════════════

def hohmann_dv(
    r1_au: float,
    r2_au: float,
) -> tuple[float, float]:
    """Compute Hohmann transfer ΔV between two circular heliocentric orbits.

    Returns (ΔV_departure, ΔV_arrival) in m/s. Both are positive.
    The departure ΔV is from the planet's orbit to the transfer ellipse.
    The arrival ΔV is from the transfer ellipse to the target orbit.

    These are heliocentric ΔVs — the actual spacecraft ΔV from a parking
    orbit is different (see planet_departure_dv and planet_arrival_dv).

    Args:
        r1_au: Departure orbit radius (AU).
        r2_au: Arrival orbit radius (AU).

    Returns:
        (dv_depart_ms, dv_arrive_ms) — heliocentric ΔVs in m/s.

    References:
        Bate et al. (1971) §6.2 — Hohmann transfer.
        Vallado (2013) §6.3 eq. 6-5 through 6-8.
    """
    r1 = r1_au * AU_M
    r2 = r2_au * AU_M

    # Circular orbital speeds
    v1 = math.sqrt(MU_SUN / r1)
    v2 = math.sqrt(MU_SUN / r2)

    # Transfer orbit semi-major axis
    a_t = (r1 + r2) / 2.0

    # Transfer orbit speeds at departure and arrival (vis-viva)
    v_t1 = math.sqrt(MU_SUN * (2.0 / r1 - 1.0 / a_t))
    v_t2 = math.sqrt(MU_SUN * (2.0 / r2 - 1.0 / a_t))

    dv_depart = abs(v_t1 - v1)
    dv_arrive = abs(v2 - v_t2)

    return dv_depart, dv_arrive


def hohmann_transfer_time(r1_au: float, r2_au: float) -> float:
    """Hohmann transfer time (seconds) between two circular orbits.

    T_transfer = π × sqrt(a_t³ / μ_sun)

    Args:
        r1_au, r2_au: Departure and arrival orbit radii (AU).

    Returns:
        Transfer time (seconds). Divide by 86400 for days.
    """
    r1 = r1_au * AU_M
    r2 = r2_au * AU_M
    a_t = (r1 + r2) / 2.0
    return math.pi * math.sqrt(a_t**3 / MU_SUN)


def planet_departure_dv(
    planet: str,
    v_inf_ms: float,
    parking_alt_km: float = 200.0,
) -> float:
    """ΔV from circular parking orbit to departure hyperbola with given v∞.

    Uses the Oberth effect: burning at low altitude is more efficient.
    ΔV = v_peri_hyperbola − v_circular
    where v_peri_hyperbola = sqrt(v_esc² + v∞²) and v_esc = sqrt(2μ/r).

    Args:
        planet:         Planet name (key in PLANETS dict).
        v_inf_ms:       Hyperbolic excess speed at planet's SOI (m/s).
        parking_alt_km: Parking orbit altitude above planet surface (km).

    Returns:
        Departure ΔV (m/s).

    References:
        Vallado (2013) §6.4 — planetary departure.
    """
    p = PLANETS[planet.lower()]
    r = p["r_m"] + parking_alt_km * 1000.0
    v_circ = math.sqrt(p["mu"] / r)
    v_esc = math.sqrt(2.0 * p["mu"] / r)
    v_peri = math.sqrt(v_esc**2 + v_inf_ms**2)
    return v_peri - v_circ


def planet_arrival_dv(
    planet: str,
    v_inf_ms: float,
    target_alt_km: float = 200.0,
) -> float:
    """ΔV from arrival hyperbola to circular orbit at target planet.

    Same physics as departure but in reverse — braking burn at periapsis.

    Args:
        planet:        Planet name.
        v_inf_ms:      Approach v∞ at planet's SOI (m/s).
        target_alt_km: Target circular orbit altitude (km).

    Returns:
        Arrival (orbit insertion) ΔV (m/s).
    """
    return planet_departure_dv(planet, v_inf_ms, target_alt_km)


# ═══════════════════════════════════════════════════════════════════
#  MISSION ΔV BUDGETS
# ═══════════════════════════════════════════════════════════════════

def moon_mission_budget(round_trip: bool = True) -> DVBudget:
    """ΔV budget for Earth → Moon orbit → (return).

    Apollo-class mission: LEO → TLI → LOI → (TEI → Entry).

    References:
        NASA SP-350 — Apollo ΔV budget.
        Vallado (2013) Table 6-3.
    """
    phases = [
        DVPhase("TLI", 3_130.0, "Trans-Lunar Injection from 185 km — Vallado Table 6-3"),
        DVPhase("LOI", 900.0, "Lunar Orbit Insertion at 110 km — Vallado Table 6-3"),
    ]
    if round_trip:
        phases.extend([
            DVPhase("TEI", 900.0, "Trans-Earth Injection from 110 km — NASA SP-350"),
            DVPhase("Entry", 0.0, "Atmospheric entry (aerocapture, no propulsive ΔV)"),
        ])
    total = sum(p.dv_ms for p in phases)
    return DVBudget("Earth-Moon", "moon", phases, total)


def mars_mission_budget(round_trip: bool = True) -> DVBudget:
    """ΔV budget for Earth → Mars orbit → (return).

    Conjunction-class (minimum energy) mission.

    References:
        Wertz "SMAD" Table 6-4; Vallado Table 6-3.
    """
    # Hohmann heliocentric ΔVs
    dv_dep_helio, dv_arr_helio = hohmann_dv(1.0, 1.524)

    # Actual spacecraft ΔVs (from parking orbits, using Oberth effect)
    dv_tmi = planet_departure_dv("earth", dv_dep_helio, 185.0)
    dv_moi = planet_arrival_dv("mars", dv_arr_helio, 250.0)

    phases = [
        DVPhase("TMI", dv_tmi, f"Trans-Mars Injection (v∞={dv_dep_helio:.0f} m/s)"),
        DVPhase("MOI", dv_moi, f"Mars Orbit Insertion at 250 km (v∞={dv_arr_helio:.0f} m/s)"),
    ]
    if round_trip:
        # Return: Mars departure + Earth arrival (aerobraking)
        dv_tei_mars = planet_departure_dv("mars", dv_arr_helio, 250.0)
        phases.extend([
            DVPhase("TEI-Mars", dv_tei_mars, "Trans-Earth Injection from Mars orbit"),
            DVPhase("Earth Entry", 0.0, "Earth aerobraking (no propulsive ΔV)"),
        ])
    total = sum(p.dv_ms for p in phases)
    return DVBudget("Earth-Mars", "mars", phases, total)


def jupiter_mission_budget() -> DVBudget:
    """ΔV budget for Earth → Jupiter orbit (one-way, no gravity assist).

    Direct Hohmann transfer. With Jupiter gravity assist, the ΔV can be
    reduced by ~3,000 m/s (see gravity_assist.py).

    References:
        Wertz "SMAD" Table 6-4.
    """
    dv_dep, dv_arr = hohmann_dv(1.0, 5.203)
    dv_tji = planet_departure_dv("earth", dv_dep, 185.0)
    dv_joi = planet_arrival_dv("jupiter", dv_arr, 1000.0)

    phases = [
        DVPhase("TJI", dv_tji, f"Trans-Jupiter Injection (v∞={dv_dep:.0f} m/s)"),
        DVPhase("JOI", dv_joi, f"Jupiter Orbit Insertion at 1000 km (v∞={dv_arr:.0f} m/s)"),
    ]
    total = sum(p.dv_ms for p in phases)
    return DVBudget("Earth-Jupiter", "jupiter", phases, total)


def custom_mission_budget(
    destination: str,
    target_orbit_alt_km: float = 200.0,
    round_trip: bool = False,
) -> DVBudget:
    """ΔV budget for Earth → any planet orbit.

    Args:
        destination:        Planet name (mercury, venus, mars, jupiter, etc.)
        target_orbit_alt_km: Orbit altitude at destination (km).
        round_trip:         Include return leg.

    Returns:
        DVBudget with departure and arrival ΔVs.
    """
    dest = destination.lower()
    if dest not in PLANETS or dest == "earth":
        raise ValueError(f"Invalid destination: {destination}")

    if dest == "moon":
        return moon_mission_budget(round_trip)

    p = PLANETS[dest]
    if p["a_au"] is None:
        raise ValueError(f"No heliocentric orbit for {destination}")

    dv_dep_helio, dv_arr_helio = hohmann_dv(1.0, p["a_au"])
    dv_depart = planet_departure_dv("earth", dv_dep_helio, DEFAULT_PARKING_ALT_KM)
    dv_arrive = planet_arrival_dv(dest, dv_arr_helio, target_orbit_alt_km)

    phases = [
        DVPhase("Departure", dv_depart, f"Earth departure (v∞={dv_dep_helio:.0f} m/s)"),
        DVPhase("Arrival", dv_arrive, f"{dest.title()} orbit insertion at {target_orbit_alt_km:.0f} km"),
    ]
    if round_trip:
        dv_return_dep = planet_departure_dv(dest, dv_arr_helio, target_orbit_alt_km)
        phases.extend([
            DVPhase("Return departure", dv_return_dep, f"{dest.title()} departure"),
            DVPhase("Earth entry", 0.0, "Aerobraking at Earth"),
        ])

    total = sum(p.dv_ms for p in phases)
    return DVBudget(f"Earth-{dest.title()}", dest, phases, total)


# ═══════════════════════════════════════════════════════════════════
#  PROPELLANT CALCULATOR
# ═══════════════════════════════════════════════════════════════════

def compute_propellant(
    budget: DVBudget,
    payload_kg: float,
    isp_s: float,
) -> DVBudget:
    """Add propellant mass calculation to a ΔV budget.

    Uses Tsiolkovsky rocket equation:
      m_initial / m_payload = exp(ΔV / (Isp × g₀))

    Note: this gives the IDEAL propellant mass. Real missions add 5–10%
    margin for residuals, boiloff (cryogenic), and off-nominal events.

    Args:
        budget:     DVBudget with phases and total ΔV.
        payload_kg: Dry mass delivered to destination (kg).
        isp_s:      Engine specific impulse (s).

    Returns:
        Same DVBudget with propellant fields filled in.
    """
    v_e = isp_s * G0
    mass_ratio = math.exp(budget.total_dv_ms / v_e)
    initial_mass = payload_kg * mass_ratio
    propellant = initial_mass - payload_kg

    budget.isp_s = isp_s
    budget.payload_kg = payload_kg
    budget.initial_mass_kg = initial_mass
    budget.propellant_kg = propellant
    budget.mass_ratio = mass_ratio
    return budget


# ═══════════════════════════════════════════════════════════════════
#  SOLAR SYSTEM ΔV MAP
# ═══════════════════════════════════════════════════════════════════

def solar_system_dv_map() -> list[dict]:
    """ΔV map for Hohmann transfers from Earth to all planets.

    Returns:
        List of {destination, dv_departure_ms, dv_arrival_ms, total_ms,
                 transfer_time_days, hohmann_dv_helio_ms}.
    """
    results = []
    for name, p in PLANETS.items():
        if name == "earth" or p["a_au"] is None:
            continue
        dv_dep_h, dv_arr_h = hohmann_dv(1.0, p["a_au"])
        dv_dep = planet_departure_dv("earth", dv_dep_h, DEFAULT_PARKING_ALT_KM)
        dv_arr = planet_arrival_dv(name, dv_arr_h, 200.0)
        t_days = hohmann_transfer_time(1.0, p["a_au"]) / 86400.0

        results.append({
            "destination": name,
            "dv_departure_ms": dv_dep,
            "dv_arrival_ms": dv_arr,
            "total_one_way_ms": dv_dep + dv_arr,
            "transfer_time_days": t_days,
            "v_inf_departure_ms": dv_dep_h,
            "v_inf_arrival_ms": dv_arr_h,
        })

    return sorted(results, key=lambda x: x["total_one_way_ms"])


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── Solar System ΔV Map (Hohmann from 185 km LEO) ────────────")
    dvmap = solar_system_dv_map()
    print(f"  {'Destination':<12s}  {'Depart':>8s}  {'Arrive':>8s}  {'Total':>8s}  {'Time':>10s}")
    print(f"  {'':─<12s}  {'':─>8s}  {'':─>8s}  {'':─>8s}  {'':─>10s}")
    for d in dvmap:
        t_str = f"{d['transfer_time_days']:.0f} days"
        if d['transfer_time_days'] > 365:
            t_str = f"{d['transfer_time_days']/365:.1f} yr"
        print(f"  {d['destination']:<12s}  {d['dv_departure_ms']:>7.0f}  "
              f"{d['dv_arrival_ms']:>7.0f}  {d['total_one_way_ms']:>7.0f}  {t_str:>10s}")

    print("\n── Moon Mission Budget (round-trip) ─────────────────────────")
    moon = moon_mission_budget(round_trip=True)
    for p in moon.phases:
        print(f"  {p.name:<15s} {p.dv_ms:>7.0f} m/s  {p.description}")
    print(f"  {'TOTAL':<15s} {moon.total_dv_ms:>7.0f} m/s")
    moon = compute_propellant(moon, payload_kg=30_000.0, isp_s=450.0)
    print(f"  Payload: {moon.payload_kg:.0f} kg, Isp: {moon.isp_s:.0f} s")
    print(f"  Initial mass: {moon.initial_mass_kg:.0f} kg, Propellant: {moon.propellant_kg:.0f} kg")
    print(f"  Mass ratio: {moon.mass_ratio:.2f}×")

    print("\n── Mars Mission Budget (round-trip) ─────────────────────────")
    mars = mars_mission_budget(round_trip=True)
    for p in mars.phases:
        print(f"  {p.name:<15s} {p.dv_ms:>7.0f} m/s  {p.description}")
    print(f"  {'TOTAL':<15s} {mars.total_dv_ms:>7.0f} m/s")
    mars_chem = compute_propellant(mars, 50_000.0, 450.0)
    mars_ntp = compute_propellant(mars_mission_budget(True), 50_000.0, 900.0)
    print(f"  Chemical (Isp=450s): {mars_chem.propellant_kg:.0f} kg propellant "
          f"(ratio {mars_chem.mass_ratio:.1f}×)")
    print(f"  NTP (Isp=900s):      {mars_ntp.propellant_kg:.0f} kg propellant "
          f"(ratio {mars_ntp.mass_ratio:.1f}×)")
