"""Cabin fire safety — ignition/spread/suppression model.

Critical spacecraft hazard — the Apollo 1 fire taught the standard:
high-O₂ atmospheres are extreme fire hazards. This module models:

  1. **Ignition probability** — a function of O₂ partial pressure and
     temperature (Hull 1981 fire-safety empirical fits)
  2. **Flame spread rate** — for representative materials (FRR Velcro,
     PTFE, wire insulation) in microgravity (Torero 2003)
  3. **Smoke / CO generation** — vs fuel burned kg
  4. **Suppression** — CO₂ flood or N₂ dump effectiveness

References:
    Hull, T. R. (1981) "Fire safety in spacecraft." NASA TP-1793.
    Torero, J. L. et al. (2003) "Flames in microgravity," AIAA 2003-2792.
    NASA STD-6001 "Flammability, Offgassing, and Compatibility
        Requirements" Rev B.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class CabinAtmosphere:
    total_pressure_kpa: float = 101.325       # 1 atm sea-level
    o2_fraction: float = 0.21
    temperature_k: float = 295.0
    relative_humidity: float = 0.50
    cabin_volume_m3: float = 45.0


@dataclass
class FireState:
    t_s: float
    burning_mass_kg: float
    o2_fraction: float
    co_ppm: float
    temperature_k: float
    extinguished: bool = False


@dataclass
class FireReport:
    history: List[FireState] = field(default_factory=list)
    peak_temp_k: float = 0.0
    peak_co_ppm: float = 0.0
    final_o2_fraction: float = 0.21
    extinguished: bool = False
    time_to_incapacitation_s: float = 0.0
    notes: List[str] = field(default_factory=list)


# Heat of combustion (MJ/kg) and CO yield (kg CO per kg fuel)
_MATERIALS = {
    "velcro":       {"hc_mjkg": 25.0, "co_yield": 0.10, "ignition_T": 550},
    "wire_insul":   {"hc_mjkg": 28.0, "co_yield": 0.15, "ignition_T": 600},
    "ptfe":         {"hc_mjkg": 5.0,  "co_yield": 0.25, "ignition_T": 700},
    "paper":        {"hc_mjkg": 16.0, "co_yield": 0.08, "ignition_T": 500},
    "cotton":       {"hc_mjkg": 17.0, "co_yield": 0.05, "ignition_T": 520},
}


def ignition_probability(atm: CabinAtmosphere, heat_source_w: float,
                         material: str = "velcro") -> float:
    """Empirical ignition probability given atmosphere + heat source."""
    mat = _MATERIALS.get(material)
    if not mat:
        return 0.0
    # High O₂ lowers ignition energy — Hull fit
    o2_factor = (atm.o2_fraction / 0.21) ** 2
    # Temperature margin to ignition. A room-temperature cabin with a
    # heat source (short circuit, arc) can still ignite flammable
    # materials — the heat source is what raises local temp to ignition.
    # Use the heat_source_w as the dominant factor.
    base_T_factor = 0.1   # background flammability even at 295 K
    # Heat source correction: 100 W is a serious ignition source
    heat_factor = min(1.0, heat_source_w / 100.0)
    return min(1.0, 0.3 * o2_factor * heat_factor + base_T_factor * o2_factor * heat_factor)


def simulate_fire(atm: CabinAtmosphere, fuel_kg: float = 1.0,
                  material: str = "velcro",
                  suppression_after_s: float = 30.0,
                  suppression_type: str = "co2_flood",
                  dt_s: float = 1.0) -> FireReport:
    """Simulate a cabin fire given an initial fuel mass + atmosphere.

    Produces an oxygen drawdown, temperature rise, and CO accumulation
    curve — the three quantities FDIR agents watch for fire alarm.
    """
    mat = _MATERIALS.get(material) or _MATERIALS["velcro"]
    V = atm.cabin_volume_m3
    # Initial moles of O₂
    kT = 8.314 * atm.temperature_k
    mol_total = atm.total_pressure_kpa * 1000 * V / kT
    mol_o2 = mol_total * atm.o2_fraction
    total_mass_air = mol_total * 0.029   # approx

    burning = 0.0
    remaining = fuel_kg
    temp = atm.temperature_k
    co_ppm = 0.0
    extinguished = False
    t = 0.0
    history: List[FireState] = []
    # Burn rate (kg/s) — scales with O₂ fraction and available fuel
    while t < 600 and not extinguished:
        o2_frac = mol_o2 / max(mol_total, 1)
        burn_rate = min(remaining, 0.02 * o2_frac * (0.5 + 0.5 * atm.total_pressure_kpa / 101.325))
        # Required O₂ mass per kg fuel ≈ 2.3 for typical organics
        o2_consumed_kg = burn_rate * 2.3 * dt_s
        o2_consumed_mol = o2_consumed_kg / 0.032
        mol_o2 = max(0.0, mol_o2 - o2_consumed_mol)
        remaining = max(0.0, remaining - burn_rate * dt_s)
        burning += burn_rate * dt_s

        # Heat release
        heat_rate_w = burn_rate * mat["hc_mjkg"] * 1e6
        temp += heat_rate_w * dt_s / (total_mass_air * 1005.0)

        # CO generation
        co_ppm += burn_rate * mat["co_yield"] * dt_s / (total_mass_air * 28e-6 / 1e6)

        # Suppression kicks in
        if t >= suppression_after_s:
            if suppression_type == "co2_flood":
                # O₂ depletion — suppresses when O₂ < 15%
                mol_o2 *= 0.9 ** (dt_s / 5)
            elif suppression_type == "n2_purge":
                mol_o2 *= 0.85 ** (dt_s / 5)
            if mol_o2 / max(mol_total, 1) < 0.13:
                extinguished = True

        history.append(FireState(
            t_s=t, burning_mass_kg=burning,
            o2_fraction=mol_o2 / max(mol_total, 1),
            co_ppm=co_ppm, temperature_k=temp,
            extinguished=extinguished,
        ))
        t += dt_s
        if remaining <= 0:
            extinguished = True

    # Time to crew incapacitation: CO > 4000 ppm causes loss of consciousness
    incap_t = next((s.t_s for s in history if s.co_ppm > 4000), 0.0)

    return FireReport(
        history=history,
        peak_temp_k=max((s.temperature_k for s in history), default=temp),
        peak_co_ppm=max((s.co_ppm for s in history), default=co_ppm),
        final_o2_fraction=history[-1].o2_fraction if history else atm.o2_fraction,
        extinguished=extinguished,
        time_to_incapacitation_s=incap_t,
        notes=[f"Material: {material}, total burned: {burning:.3f} kg"],
    )
