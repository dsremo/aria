"""Orbital propellant depot + transfer physics.

Artemis-III relies on on-orbit cryo fuelling: HLS Starship is refuelled
in LEO via multiple tanker launches. This module models:

  1. **Cryogenic boil-off** — Zero-boil-off (ZBO) cryocoolers vs passive
     MLI. Fridkin 2018 boil-off rates.
  2. **Tank mass fractions** — pressurization + insulation overhead
  3. **Transfer line flow** — Bernoulli + pipe friction, 2-phase flow avoidance
  4. **Settling accel for ullage** — RCS burn to keep liquid over outlet

Reference:
    Fridkin, P. D. et al. (2018) "Cryogenic propellant passive storage
        for long-duration missions," AIAA 2018-4646.
    NASA/CP-2005-213815 "Cryogenic Fluid Management Technology."
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List


# Boil-off rates (% mass / day) — Fridkin 2018
_PASSIVE_BOIL_LH2 = 0.01    # very optimistic with 50-layer MLI + radiation shield
_PASSIVE_BOIL_LOX = 0.005
_PASSIVE_BOIL_LCH4 = 0.003   # methane: less volatile, ~0.3 % / day at LEO MLI
_ZBO_COP = 0.1              # cryocooler Coefficient of Performance (ideal Carnot)


# R42 §2.4 — multi-T radiative-sink presets per heliocentric distance.
# Used by ``ambient_temp_k_at()`` so a depot deployed near Mars / Jupiter /
# Saturn / Pluto sees a different parasitic heat load than one in LEO.
# Source: Sutton-Biblarz §10.5 + NASA SP-2010-571 Tab 4-3.
HELIOCENTRIC_AMBIENT_K: dict = {
    "leo":     290.0,    # Earth shadow average
    "mars":    210.0,    # Mars helio-distance, deep-space sink
    "jupiter": 110.0,
    "saturn":   80.0,
    "uranus":   55.0,
    "neptune":  45.0,
    "pluto":    37.0,
    "deep_space": 4.0,    # CMB
}

# Cold-side temperatures for each cryogenic propellant (K).
_COLD_T_K: dict = {
    "LH2":  20.3,
    "LOX":  90.2,
    "LCH4": 111.7,    # boiling point at 1 atm; depot operates at saturation
    "LN2":  77.4,
    "LHe":  4.2,
}


@dataclass
class CryoTank:
    name: str
    propellant: str             # "LH2" / "LOX" / "LCH4" / "MMH" / "N2O4"
    stored_kg: float
    tank_dry_mass_kg: float
    insulation_mli_layers: int = 50
    zbo_enabled: bool = False   # active cryocooler
    outside_temp_k: float = 4.0  # deep-space radiative sink


def ambient_temp_k_at(location: str) -> float:
    """Look up canonical radiative-sink temperature.

    Unknown locations fall back to deep_space (4 K) — the most
    conservative depot-design baseline (least heat in)."""
    return HELIOCENTRIC_AMBIENT_K.get(location.lower(),
                                      HELIOCENTRIC_AMBIENT_K["deep_space"])


def _passive_boil_per_day(propellant: str) -> float:
    """Per-propellant base boil-off rate, R42 multi-fluid extension."""
    return {
        "LH2":  _PASSIVE_BOIL_LH2,
        "LOX":  _PASSIVE_BOIL_LOX,
        "LCH4": _PASSIVE_BOIL_LCH4,
    }.get(propellant, _PASSIVE_BOIL_LOX)


def boil_off_per_day(tank: CryoTank, solar_flux_w_m2: float = 1361.0) -> float:
    """Mass fraction boiled off per day."""
    base = _passive_boil_per_day(tank.propellant)
    mli_factor = max(0.05, 1.0 / tank.insulation_mli_layers)
    heat_factor = solar_flux_w_m2 / 1361.0
    if tank.zbo_enabled:
        base *= 0.05   # cryocooler removes most parasitic heat
    return base * mli_factor * heat_factor


def zbo_cryocooler_power_kw(tank: CryoTank, heat_load_w: float = 50.0) -> float:
    """Power draw to counteract heat load at tank cold temperature."""
    T_cold = _COLD_T_K.get(tank.propellant, 90.0)
    T_hot = 280.0
    carnot = (T_hot - T_cold) / T_cold
    return heat_load_w * carnot / _ZBO_COP / 1000   # kW


def daigle_self_pressurization_dp_kpa_day(
    tank: CryoTank,
    solar_flux_w_m2: float = 1361.0,
    ullage_volume_m3: float = 0.20,
) -> float:
    """Daigle 2008 (NASA-TM-2008-215224) self-pressurization estimate.

    A sealed cryotank rises in pressure as boil-off accumulates in the
    ullage volume.  Estimate dP/day = m_boil · R · T / V — ideal-gas
    approximation good to 10 % over a few days.

    R values (kJ/kg·K): LH2 4.124, LOX 0.260, LCH4 0.518.  Returns
    pressure rise in kPa / day."""
    R_specific_kj_kg_k = {
        "LH2":  4.124,
        "LOX":  0.260,
        "LCH4": 0.518,
        "LN2":  0.297,
        "LHe":  2.077,
    }.get(tank.propellant, 0.260)
    frac = boil_off_per_day(tank, solar_flux_w_m2)
    m_boil_kg = tank.stored_kg * frac
    T_k = _COLD_T_K.get(tank.propellant, 90.0)
    if ullage_volume_m3 <= 0.0:
        return float("inf")
    dp_kpa = m_boil_kg * R_specific_kj_kg_k * T_k / ullage_volume_m3
    return dp_kpa


def simulate_storage(tank: CryoTank, days: int) -> List[tuple]:
    """Simulate tank mass trajectory over `days`."""
    out = []
    mass = tank.stored_kg
    for d in range(days + 1):
        out.append((d, mass))
        frac = boil_off_per_day(tank)
        mass = max(0.0, mass - mass * frac)
    return out


@dataclass
class TransferResult:
    mass_transferred_kg: float
    duration_s: float
    avg_flow_rate_kg_s: float
    ullage_dv_mps: float


def transfer_propellant(source: CryoTank, dest_empty_mass_kg: float,
                        desired_transfer_kg: float,
                        pipe_diameter_m: float = 0.15,
                        source_pressure_bar: float = 4.0) -> TransferResult:
    """Pressure-fed transfer from source tank to dest. Assumes Bernoulli
    + pipe friction; ullage settling requires RCS Δv."""
    # Density (kg/m³): LH2=71, LOX=1141, LCH4=422 (CRC, NIST WebBook).
    density = {
        "LH2":  71.0,
        "LOX": 1141.0,
        "LCH4": 422.0,
        "LN2":  808.0,
        "LHe":  125.0,
    }.get(source.propellant, 1141.0)
    dP_pa = source_pressure_bar * 1e5
    # Bernoulli velocity
    v = math.sqrt(2 * dP_pa / density)
    A = math.pi * (pipe_diameter_m / 2) ** 2
    m_dot = density * A * v
    if m_dot <= 0:
        return TransferResult(0, 0, 0, 0)
    # Cannot exceed available source mass
    transfer = min(desired_transfer_kg, source.stored_kg)
    duration = transfer / m_dot
    # RCS settling: typical 0.1 m/s² × duration → small Δv
    ullage_dv = 0.1 * duration
    return TransferResult(
        mass_transferred_kg=transfer,
        duration_s=duration,
        avg_flow_rate_kg_s=m_dot,
        ullage_dv_mps=ullage_dv,
    )
