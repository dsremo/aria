"""EVA suit consumables — critical-path life-support model for moonwalkers.

Apollo/Artemis EVA suits are closed-loop life-support bubbles for 6-8 h.
Four consumables control mission duration:

  1. Primary Life Support System (PLSS) O₂ — metabolic + leak
  2. Lithium-hydroxide CO₂ scrubber canister (or amine swing-bed in xEMU)
  3. PLSS battery — fans, pumps, comms, avionics, heaters
  4. Cooling water — sublimator (Apollo) or LCG loop rejection

Exceeding any budget forces abort-to-vehicle. This module gives ARIA the
ability to say "we have 4.2 h of margin at current rate" rather than
checking "EVA_DURATION" as a config checkbox.

Metabolic rates are from NASA STD-3001, with work-intensity scaling from
Connolly (2006) J. Spacecraft. CO₂ and O₂ rates are per-crew-member.

References:
    NASA-STD-3001 Vol 2 Rev B (2019) §6 Human Physiology
    Connolly, J. F. (2006) "Crew Metabolic Rates for Lunar EVA"
    NASA TM-109065 (1994) — Apollo EMU thermal control
    Thomas & McMann (2006) "US Spacesuits" — xEMU background
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


# ══════════════════════════════════════════════════════════════════
#  Metabolic rate by work intensity (Connolly 2006, NASA-STD-3001)
#  Units: W (metabolic heat production = O₂ × 20.1 kJ/L ÷ τ)
# ══════════════════════════════════════════════════════════════════

_METABOLIC_RATE_W = {
    "rest":            100.0,   # resting / standing
    "light":           200.0,   # walking level
    "moderate":        350.0,   # Apollo J-mission sampling rate
    "heavy":           500.0,   # rock-hammering, deep drilling
    "extreme":         700.0,   # hard-surface traverse with heavy tools
}


# ══════════════════════════════════════════════════════════════════
#  Consumption rates — per-crewmember, per-hour
# ══════════════════════════════════════════════════════════════════

# O₂: metabolic + leak. Apollo PLSS leak ≈ 0.05 kg/h nominal.
_O2_PER_WATT_KG_H = 1.0e-4   # ≈ 0.1 g O₂ per W hr  (20.1 kJ/L × 1.43 g/L)
_O2_LEAK_KG_H = 0.05

# CO₂: 1.0 kg produced per kg O₂ consumed (RQ ≈ 0.85 by moles, ≈ 1 by mass)
_CO2_MASS_RATIO = 1.00

# Battery: avg draw for fans + pumps + comms + instruments. Apollo A7L
# PLSS averaged ~80 W (Thomas & McMann 2006 §Apollo); xEMU ≈ 140 W.
# The `per_crew_w` scaling is a minor correction for heater duty cycle in
# cold environments; the pilot is stationary so it's modest.
_BATT_BASE_W = 80.0
_BATT_PER_CREW_W = 25.0

# Cooling water: sublimator uses ~0.2 kg H₂O per kWh of heat rejected
_SUBLIMATOR_KG_PER_KWH = 0.200


@dataclass
class SuitConfig:
    """One EVA suit's starting consumables + hardware caps."""
    name: str = "xEMU"
    o2_kg: float = 1.30                # PLSS high-pressure O₂ bottle
    battery_wh: float = 850.0          # Li-ion pack (xEMU spec)
    co2_scrubber_capacity_kg: float = 0.90   # LiOH + amine, scrubbed CO₂
    cooling_water_kg: float = 3.60     # sublimator feed
    leak_rate_kg_h: float = _O2_LEAK_KG_H
    max_duration_h: float = 8.0        # hard envelope (suit structural)
    abort_margin_h: float = 0.5        # safety cushion before abort


@dataclass
class EVAState:
    """Consumables snapshot at a given mission time."""
    t_h: float
    o2_kg: float
    co2_scrubbed_kg: float             # cumulative CO₂ absorbed
    battery_wh: float
    cooling_water_kg: float
    metabolic_rate_w: float
    activity: str


@dataclass
class EVAReport:
    """Full EVA summary + abort recommendation."""
    config: SuitConfig
    states: List[EVAState] = field(default_factory=list)
    total_duration_h: float = 0.0
    abort_recommended: bool = False
    abort_reason: str = ""
    binding_consumable: Optional[str] = None   # which runs out first
    time_remaining_h: Optional[float] = None   # at final rate


# ══════════════════════════════════════════════════════════════════
#  Core simulator
# ══════════════════════════════════════════════════════════════════

def simulate_eva(cfg: SuitConfig,
                 activity_plan: List[tuple[float, str]],
                 dt_h: float = 0.1) -> EVAReport:
    """Integrate suit consumables over the EVA plan.

    Args:
        cfg: suit config with starting consumables.
        activity_plan: list of (duration_h, activity_key). Activity keys must
            appear in _METABOLIC_RATE_W.
        dt_h: integration step (hours). 0.1 = 6-minute resolution.

    Returns EVAReport with full state timeline, the binding consumable,
    and the recommended abort time.
    """
    o2 = cfg.o2_kg
    batt = cfg.battery_wh
    co2 = 0.0
    water = cfg.cooling_water_kg
    states: List[EVAState] = []

    t = 0.0
    binding = None
    for duration_h, activity in activity_plan:
        rate_w = _METABOLIC_RATE_W.get(activity, _METABOLIC_RATE_W["moderate"])
        # Per-hour consumption at this activity
        o2_rate = rate_w * _O2_PER_WATT_KG_H + cfg.leak_rate_kg_h
        co2_rate = rate_w * _O2_PER_WATT_KG_H * _CO2_MASS_RATIO
        # Battery: base + crew-proportional; one crew per suit
        batt_rate_w = _BATT_BASE_W + _BATT_PER_CREW_W
        # Cooling: reject all metabolic heat + base electronics (assume
        # 100 W of electronics also dumps to the sublimator)
        heat_rate_w = rate_w + 100.0
        water_rate = (heat_rate_w / 1000.0) * _SUBLIMATOR_KG_PER_KWH

        steps = max(1, int(round(duration_h / dt_h)))
        for _ in range(steps):
            if o2 <= 0 or batt <= 0 or water <= 0 or co2 >= cfg.co2_scrubber_capacity_kg:
                break
            o2 -= o2_rate * dt_h
            co2 += co2_rate * dt_h
            batt -= batt_rate_w * dt_h
            water -= water_rate * dt_h
            t += dt_h
            states.append(EVAState(
                t_h=t, o2_kg=max(o2, 0), co2_scrubbed_kg=min(co2, cfg.co2_scrubber_capacity_kg),
                battery_wh=max(batt, 0), cooling_water_kg=max(water, 0),
                metabolic_rate_w=rate_w, activity=activity,
            ))

    # Time-remaining at final rate (for the "abort in X minutes" readout)
    if states:
        last = states[-1]
        rate_w = last.metabolic_rate_w
        o2_rate = rate_w * _O2_PER_WATT_KG_H + cfg.leak_rate_kg_h
        co2_rate = rate_w * _O2_PER_WATT_KG_H * _CO2_MASS_RATIO
        batt_rate_w = _BATT_BASE_W + _BATT_PER_CREW_W
        water_rate = (rate_w + 100.0) / 1000.0 * _SUBLIMATOR_KG_PER_KWH
        trems = {
            "o2":     last.o2_kg / max(o2_rate, 1e-6),
            "co2":    (cfg.co2_scrubber_capacity_kg - last.co2_scrubbed_kg)
                      / max(co2_rate, 1e-6),
            "battery": last.battery_wh / max(batt_rate_w, 1e-6),
            "cooling": last.cooling_water_kg / max(water_rate, 1e-6),
        }
        binding = min(trems, key=trems.get)
        t_rem = trems[binding]
    else:
        t_rem = 0.0
        binding = "unknown"

    # Abort decision: < 0.5 h of binding consumable = abort
    abort = t_rem < cfg.abort_margin_h
    abort_reason = ""
    if abort:
        abort_reason = f"{binding} margin {t_rem:.2f} h < abort_margin {cfg.abort_margin_h} h"
    if t > cfg.max_duration_h:
        abort = True
        abort_reason += f"; exceeded suit max duration {cfg.max_duration_h} h"

    return EVAReport(
        config=cfg,
        states=states,
        total_duration_h=t,
        abort_recommended=abort,
        abort_reason=abort_reason,
        binding_consumable=binding,
        time_remaining_h=t_rem,
    )


# ══════════════════════════════════════════════════════════════════
#  Apollo-class + xEMU EVA profiles
# ══════════════════════════════════════════════════════════════════

def apollo_11_eva_1() -> EVAReport:
    """Apollo 11 first-and-only EVA — 2h 31m (duration confirmed)."""
    cfg = SuitConfig(
        name="Apollo 11 A7L",
        o2_kg=0.60,                  # ~1.3 lb (PLSS 1020 psi bottle, Thomas & McMann)
        battery_wh=280.0,             # Apollo PLSS-6 rechargeable Ag-Zn battery
        co2_scrubber_capacity_kg=0.454,  # 1 lb LiOH cartridge
        cooling_water_kg=2.27,        # 5 lb H₂O sublimator feed (design-life 4 h)
        leak_rate_kg_h=0.05,
        max_duration_h=6.0,
    )
    plan = [
        (0.17, "light"),       # pad + ladder descent, 10 min
        (0.50, "moderate"),    # flag + plaque + sample collection
        (1.00, "moderate"),    # experiments deployment
        (0.60, "light"),       # photography + ladder ascent
    ]
    return simulate_eva(cfg, plan)


def artemis_3_eva_sv() -> EVAReport:
    """Projected Artemis-III Shackleton traverse EVA (6-hour sortie)."""
    cfg = SuitConfig(
        name="xEMU",
        o2_kg=1.30,
        battery_wh=850.0,
        co2_scrubber_capacity_kg=0.90,
        cooling_water_kg=3.60,
    )
    plan = [
        (0.5, "light"),
        (2.0, "moderate"),
        (1.5, "heavy"),
        (1.5, "moderate"),
        (0.5, "light"),
    ]
    return simulate_eva(cfg, plan)
