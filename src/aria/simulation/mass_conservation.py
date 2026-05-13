"""Element-Balance Mass Conservation Ledger.

CRITICAL: A closed-loop life support system MUST track every atom.
At 98% recycling efficiency, 2% loss per cycle means total atmospheric
loss in ~50 cycles without makeup gas. Over 1000 years, even 99.9%
efficiency leads to cumulative depletion.

TRACKED ELEMENTS (kg):
  O2: Crew respiration consumes, ECLSS electrolyzes water to replenish
  CO2: Crew exhales, Sabatier converts to CH4 + H2O, plants absorb
  H2O: Recycled via UPA/BPA (97-98% ISS), condensate from breathing
  N2: Inert buffer gas, slowly leaks through seals
  CH4: Sabatier byproduct, vented or cracked
  H2: Electrolysis product, used in Sabatier or fuel cells
  Trace: NH3, CO, VOCs from offgassing — removed by TCCS

MASS BALANCE EQUATIONS (per day, per person):
  O2 consumed: 0.84 kg/day (NASA BVAD)
  CO2 produced: 1.00 kg/day (NASA BVAD)
  H2O consumed: 2.50 kg/day drinking + 0.76 kg food moisture (NASA BVAD)
  H2O produced: 1.80 kg/day metabolic + 2.53 kg/day exhaled vapor (NASA BVAD)
  Food consumed: 1.83 kg/day dry (NASA BVAD)

  Sabatier: CO2 + 4H2 → CH4 + 2H2O (0.818 kg H2O per kg CO2)
  Electrolysis: 2H2O → 2H2 + O2 (0.889 kg O2 per kg H2O)

HULL LEAK RATE:
  ISS: ~0.227 kg/day air loss (ICES-2020-223, Matty 2010)
  Scaled to generation ship: ~2 kg/day (larger hull, more seals)

References:
  - NASA BVAD: "Baseline Values and Assumptions Document" NASA/TP-2015-218570
  - ICES-2020-223: Matty (2020) ISS Air Loss Assessment
  - ICES-2023-097: ISS Water Recovery System Performance
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# NASA BVAD per-person per-day values (kg)
BVAD_O2_CONSUMED = 0.84
BVAD_CO2_PRODUCED = 1.00
BVAD_H2O_DRINKING = 2.50
BVAD_H2O_FOOD_MOISTURE = 0.76
BVAD_H2O_METABOLIC = 1.80
BVAD_H2O_EXHALED = 2.53
BVAD_FOOD_DRY = 1.83

# Sabatier stoichiometry
SABATIER_H2O_PER_KG_CO2 = 0.818  # kg H2O produced per kg CO2 consumed
SABATIER_CH4_PER_KG_CO2 = 0.364  # kg CH4 produced per kg CO2

# Electrolysis stoichiometry
ELECTROLYSIS_O2_PER_KG_H2O = 0.889  # kg O2 per kg H2O consumed
ELECTROLYSIS_H2_PER_KG_H2O = 0.111  # kg H2 per kg H2O consumed

# Hull leak rate (scaled from ISS)
HULL_LEAK_KG_DAY = 2.0  # Mixed air loss (78% N2, 21% O2, 1% other)


@dataclass
class MassLedger:
    """Element-by-element mass tracking for the closed-loop system."""
    # Atmospheric reserves (kg)
    # O2/N2 totals include hull atmosphere + high-pressure tankage
    # Hull atmo: ~90t O2 (hull_vol × 1.225 kg/m³ × 0.21)
    # Tankage: 210t O2 in 6 spherical tanks at 200 bar (utility_systems.py)
    o2_kg: float = 300_000.0       # 90t atmo + 210t tankage = 300t total
    co2_kg: float = 500.0          # Small buffer, continuously removed
    n2_kg: float = 900_000.0       # ~350t atmo + 550t tankage (buffer gas reserve)
    h2o_kg: float = 500_000.0      # ~500 tonnes water reserve
    h2_kg: float = 1_000.0         # Small H2 buffer for Sabatier
    ch4_kg: float = 0.0            # Sabatier byproduct (vented)
    food_kg: float = 2_000_000.0   # Initial food + hydroponics buffer

    # Cumulative losses (kg) — tracks where mass went
    total_leaked_kg: float = 0.0
    total_vented_ch4_kg: float = 0.0
    total_unrecovered_kg: float = 0.0

    # Recycling efficiencies
    water_recovery_pct: float = 97.5  # ISS: 97-98% (ICES-2023-097)
    o2_recovery_pct: float = 99.0     # Electrolysis + Sabatier chain
    co2_scrubbing_pct: float = 99.5   # CDRA + Sabatier combined

    # Hull integrity
    hull_leak_kg_day: float = HULL_LEAK_KG_DAY
    makeup_gas_reserve_kg: float = 50_000.0  # Stored N2/O2 for leak compensation

    # Balance check
    total_mass_initial_kg: float = 0.0
    total_mass_current_kg: float = 0.0
    mass_closure_pct: float = 100.0


class MassConservationSimulator:
    """Tracks element-by-element mass balance for the generation ship.

    Every kg of O2, CO2, H2O, N2 is accounted for. The mass ledger
    detects silent leaks before they become fatal.
    """

    def __init__(self, crew_size: int = 1000, seed: int | None = None) -> None:
        import random
        self._rng = random.Random(seed)
        self._crew = crew_size
        self.state = MassLedger()
        # Record initial mass for closure check
        self.state.total_mass_initial_kg = self._total_mass()

    def _total_mass(self) -> float:
        s = self.state
        return (s.o2_kg + s.co2_kg + s.n2_kg + s.h2o_kg +
                s.h2_kg + s.ch4_kg + s.food_kg + s.makeup_gas_reserve_kg)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Simulate one year of mass cycling."""
        events: list[dict[str, Any]] = []
        s = self.state
        days = 365.25

        # ── Per-day mass flows, scaled to year ──
        crew = self._crew

        # Consumption
        o2_consumed = BVAD_O2_CONSUMED * crew * days
        co2_produced = BVAD_CO2_PRODUCED * crew * days
        h2o_consumed = (BVAD_H2O_DRINKING + BVAD_H2O_FOOD_MOISTURE) * crew * days
        h2o_produced = (BVAD_H2O_METABOLIC + BVAD_H2O_EXHALED) * crew * days
        food_consumed = BVAD_FOOD_DRY * crew * days

        # ── ECLSS Processing ──
        # Sabatier: CO2 → CH4 + H2O
        co2_scrubbed = co2_produced * s.co2_scrubbing_pct / 100
        sabatier_h2o = co2_scrubbed * SABATIER_H2O_PER_KG_CO2
        sabatier_ch4 = co2_scrubbed * SABATIER_CH4_PER_KG_CO2

        # Electrolysis: H2O → O2 + H2
        h2o_for_electrolysis = o2_consumed / ELECTROLYSIS_O2_PER_KG_H2O
        electrolysis_o2 = h2o_for_electrolysis * ELECTROLYSIS_O2_PER_KG_H2O
        electrolysis_h2 = h2o_for_electrolysis * ELECTROLYSIS_H2_PER_KG_H2O

        # ── Correct ECLSS water cycle (no double-counting) ──
        # Total water throughput = drinking + food moisture (crew input)
        # All output (urine, sweat, exhaled vapor) is collected and recycled
        # Net loss = throughput × (1 - recovery_rate) + electrolysis consumption
        h2o_throughput = h2o_consumed  # Total crew water intake
        h2o_loss_from_recycling = h2o_throughput * (1.0 - s.water_recovery_pct / 100)
        h2o_gained_sabatier = sabatier_h2o  # Sabatier produces new water from CO2

        # O2 balance: electrolysis produces O2, crew consumes it
        # Net should be ~0 if electrolysis keeps up
        o2_net = electrolysis_o2 - o2_consumed
        s.o2_kg = max(0.0, s.o2_kg + o2_net)
        if o2_net < 0:
            s.total_unrecovered_kg += abs(o2_net)

        # CO2 balance: crew produces, Sabatier removes
        co2_net = co2_produced - co2_scrubbed
        s.co2_kg += co2_net

        # H2O balance: gained from Sabatier, lost from imperfect recycling + electrolysis
        h2o_net = h2o_gained_sabatier - h2o_loss_from_recycling - h2o_for_electrolysis
        s.h2o_kg += h2o_net

        # H2 balance: electrolysis produces, Sabatier consumes
        h2_consumed_sabatier = co2_scrubbed * 4 * 2.016 / 44.01  # Stoichiometric
        # Sabatier can't consume more H2 than available
        h2_consumed_sabatier = min(h2_consumed_sabatier, max(0, s.h2_kg + electrolysis_h2))
        s.h2_kg = max(0.0, s.h2_kg + electrolysis_h2 - h2_consumed_sabatier)

        # CH4 vented
        s.ch4_kg += sabatier_ch4
        if s.ch4_kg > 100:
            vented = s.ch4_kg - 50
            s.total_vented_ch4_kg += vented
            s.ch4_kg = 50

        # Food consumption (replenished by hydroponics + synthesis)
        s.food_kg = max(0.0, s.food_kg - food_consumed)
        # Hydroponics + starch synthesis replenish ~95% of food consumed
        food_grown = food_consumed * 0.95
        s.food_kg += food_grown

        # ── Hull leakage ──
        annual_leak = s.hull_leak_kg_day * days
        # Leak composition: 78% N2, 21% O2, 1% CO2
        n2_leaked = annual_leak * 0.78
        o2_leaked = annual_leak * 0.21
        co2_leaked = annual_leak * 0.01

        s.n2_kg -= n2_leaked
        s.o2_kg -= o2_leaked
        s.co2_kg -= co2_leaked
        s.total_leaked_kg += annual_leak

        # Compensate from makeup gas
        if s.makeup_gas_reserve_kg > annual_leak:
            s.makeup_gas_reserve_kg -= annual_leak
            s.n2_kg += n2_leaked
            s.o2_kg += o2_leaked
        else:
            # Makeup gas depleted
            if s.makeup_gas_reserve_kg > 0:
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": f"Makeup gas reserves depleted. "
                               f"Hull leaking {annual_leak:.0f} kg/yr uncompensated.",
                    "subsystem": "eclss",
                })
                s.makeup_gas_reserve_kg = 0

        # ── Mass closure check ──
        s.total_mass_current_kg = self._total_mass()
        if s.total_mass_initial_kg > 0:
            s.mass_closure_pct = (s.total_mass_current_kg / s.total_mass_initial_kg) * 100

        # ── Alerts (latched with hysteresis) ──
        def _latch(name: str, cond: bool, clear: bool, event: dict) -> None:
            key = f"_mass_{name}_latched"
            if cond and not getattr(self, key, False):
                events.append(event)
                setattr(self, key, True)
            elif clear:
                setattr(self, key, False)

        _latch("o2_low", s.o2_kg < 50_000, s.o2_kg >= 75_000, {
            "year": mission_year, "severity": "WARNING",
            "message": f"O2 reserves at {s.o2_kg:.0f} kg ({s.o2_kg / 300_000 * 100:.0f}%)",
            "subsystem": "eclss",
        })
        _latch("starvation", s.food_kg < food_consumed * 7, s.food_kg >= food_consumed * 14, {
            "year": mission_year, "severity": "CRITICAL",
            "message": f"STARVATION: food reserves {s.food_kg:.0f} kg "
                       f"(< 1 week supply for {self._crew} crew)",
            "subsystem": "eclss",
        })
        _latch("o2_depleted", s.o2_kg <= 0, s.o2_kg > 100, {
            "year": mission_year, "severity": "CRITICAL",
            "message": "O2 reserves DEPLETED — crew asphyxiation imminent",
            "subsystem": "eclss",
        })
        _latch("n2_low", s.n2_kg < 100_000, s.n2_kg >= 150_000, {
            "year": mission_year, "severity": "WARNING",
            "message": f"N2 buffer gas at {s.n2_kg:.0f} kg ({s.n2_kg / 900_000 * 100:.0f}%)",
            "subsystem": "eclss",
        })
        _latch("h2o_low", s.h2o_kg < 100_000, s.h2o_kg >= 150_000, {
            "year": mission_year, "severity": "WARNING",
            "message": f"Water reserves at {s.h2o_kg:.0f} kg ({s.h2o_kg / 500_000 * 100:.0f}%)",
            "subsystem": "eclss",
        })
        _latch("closure_low", s.mass_closure_pct < 95, s.mass_closure_pct >= 96, {
            "year": mission_year, "severity": "CRITICAL",
            "message": f"Mass closure {s.mass_closure_pct:.1f}% — "
                       f"lost {s.total_mass_initial_kg - s.total_mass_current_kg:.0f} kg total",
            "subsystem": "eclss",
        })

        return events

    def get_report(self) -> dict[str, Any]:
        s = self.state
        return {
            "o2_kg": round(s.o2_kg),
            "co2_kg": round(s.co2_kg),
            "n2_kg": round(s.n2_kg),
            "h2o_kg": round(s.h2o_kg),
            "h2_kg": round(s.h2_kg, 1),
            "food_kg": round(s.food_kg),
            "mass_closure_pct": round(s.mass_closure_pct, 2),
            "total_leaked_kg": round(s.total_leaked_kg),
            "makeup_gas_remaining_kg": round(s.makeup_gas_reserve_kg),
            "vented_ch4_kg": round(s.total_vented_ch4_kg),
        }
