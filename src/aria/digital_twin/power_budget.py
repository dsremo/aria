"""Ship Power Budget — tracks every watt generated and consumed.

The digital twin needs to verify that the 66 MWe reactor actually covers
all power consumers. This module does a bottom-up power accounting.

POWER GENERATION:
  Fusion reactor: 200 MW thermal × 33% Brayton = 66 MWe
  RTG backup: 10 kWe (Kilopower KRUSTY-derived)
  Solar (near stars only): 0 during interstellar cruise

POWER CONSUMPTION (bottom-up from simulation modules):
  ECLSS:
    - CDRA CO2 removal: 1.5 kW (ISS CDRA specs)
    - Sabatier reactor: 0.5 kW
    - Electrolysis (OGS): 3.0 kW per unit × 10 units = 30 kW
    - Water recovery (WRS): 2.0 kW
    - TCCS (trace contaminant): 0.5 kW
    - HVAC fans: 800 kW (1 W/m³ × 790,000 m³ habitat, ASHRAE 2019)
    - Subtotal ECLSS: ~1,650 kW for 1000 crew

  Lighting:
    - Grow lights: 8,000 kW (40 m²/person × 1000 crew × 200 W/m², NASA BVAD)
    - General lighting: 100 kW
    - Subtotal: 8,100 kW

  Propulsion:
    - Magsail cryocooler: 50 kW (from advanced_systems.py)
    - Attitude control: 20 kW
    - Subtotal: 70 kW

  Computing:
    - Ship AI (ARIA): 100 kW
    - Sensors + networking: 50 kW
    - Subtotal: 150 kW

  Manufacturing:
    - 3D printers: 3 kW avg (from manufacturing.py: 4 printers)
    - Recycling systems: 50 kW
    - Subtotal: 53 kW

  Thermal:
    - Coolant pumps: 200 kW (from thermal_management.py)
    - Cryocooler (reactor magnets): 5,000 kW (Wei R6: 8T REBCO realistic sizing)
    - Subtotal: 5,200 kW

  Habitat:
    - Cooking/kitchen: 100 kW
    - Water heating: 200 kW
    - Laundry: 50 kW
    - Exercise equipment: 20 kW
    - Recreation: 30 kW
    - Medical bay: 50 kW
    - Subtotal: 450 kW

  Communications:
    - Laser comm (deep space): 100 kW (from advanced_systems.py)
    - Internal network: 10 kW
    - Subtotal: 110 kW

  TOTAL CONSUMPTION: ~15,278 kW = 15.3 MW (post Hassan/Laurent/Wei PDR fixes)
  AVAILABLE: 66 MW
  MARGIN: 50.7 MW (77% margin — reactor sized for propulsion + safety)

  NOTE: Most of the 200 MW thermal goes to propulsion (direct thermal),
  not electrical. The 66 MWe is for ship systems only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class PowerConsumer:
    """A single power consumer."""
    name: str
    subsystem: str
    power_kw: float
    source: str  # Citation or reference to simulation module


@dataclass
class PowerBudget:
    """Complete electrical power budget."""
    consumers: list[PowerConsumer] = field(default_factory=list)
    total_consumption_kw: float = 0.0
    total_generation_kw: float = 66_000.0  # 66 MWe default
    margin_kw: float = 0.0
    margin_pct: float = 0.0

    def add(self, name: str, subsystem: str, power_kw: float, source: str) -> None:
        self.consumers.append(PowerConsumer(name, subsystem, power_kw, source))
        self.total_consumption_kw += power_kw
        self.margin_kw = self.total_generation_kw - self.total_consumption_kw
        self.margin_pct = self.margin_kw / max(self.total_generation_kw, 1) * 100

    def summary(self) -> str:
        lines = ["POWER BUDGET SUMMARY", "=" * 60]
        by_sub: dict[str, float] = {}
        for c in self.consumers:
            by_sub[c.subsystem] = by_sub.get(c.subsystem, 0) + c.power_kw

        for sub, power in sorted(by_sub.items(), key=lambda x: -x[1]):
            pct = power / max(self.total_consumption_kw, 1) * 100
            lines.append(f"  {sub:25s}  {power:>8,.0f} kW  ({pct:5.1f}%)")

        lines.append("-" * 60)
        lines.append(f"  {'TOTAL CONSUMPTION':25s}  {self.total_consumption_kw:>8,.0f} kW")
        lines.append(f"  {'GENERATION':25s}  {self.total_generation_kw:>8,.0f} kW")
        lines.append(f"  {'MARGIN':25s}  {self.margin_kw:>8,.0f} kW ({self.margin_pct:.0f}%)")
        return "\n".join(lines)


def compute_power_budget(crew_size: int = 1000) -> PowerBudget:
    """Compute bottom-up power budget scaled to crew size."""
    budget = PowerBudget()
    scale = crew_size / 1000.0  # Scale from 1000-crew baseline

    # ECLSS
    budget.add("CO2 removal (CDRA)", "eclss", 15 * scale, "ISS CDRA × crew scaling")
    budget.add("Sabatier reactor", "eclss", 5 * scale, "ISS Sabatier × crew")
    budget.add("O2 generation (electrolysis)", "eclss", 300 * scale, "10 OGS units × 30 kW")
    budget.add("Water recovery (WRS)", "eclss", 20 * scale, "ISS WRS × crew")
    budget.add("Trace contaminant (TCCS)", "eclss", 5 * scale, "ISS TCCS × crew")
    # HVAC: 1 W/m³ × 790,000 m³ pressurized habitat volume ≈ 800 kW
    # (ASHRAE Handbook—HVAC Applications 2019, Ch. 19 specific fan power;
    #  NASA BVAD 2015 cabin ventilation budget)
    budget.add("HVAC fans + ductwork", "eclss", 800 * scale, "1 W/m³ × 790,000 m³ habitat (ASHRAE Handbook 2019; NASA BVAD)")

    # Lighting
    # Grow lights sized to agriculture_area_m2: 1000 crew × 40 m²/person × 200 W/m²
    # PPFD ≈ 400 µmol/m²/s red+blue LED (Massa et al., HortScience 41, 2006;
    # Wheeler, Adv. Space Res. 31, 2003; NASA BVAD crop power density).
    budget.add("Grow lights (hydroponics)", "lighting", 8000, "1000 crew × 40 m²/person × 200 W/m² (NASA BVAD; Massa 2006; Wheeler 2003)")
    budget.add("General habitat lighting", "lighting", 100 * scale, "10 W/m² × floor area")

    # Propulsion
    budget.add("Magsail cryocooler", "propulsion", 50, "advanced_systems.py MgB₂ cooling")
    budget.add("Attitude control (CMGs)", "propulsion", 20, "4 × 5 kW CMG clusters")

    # Computing
    budget.add("Ship AI (ARIA core)", "computing", 100, "GPU cluster for cognitive engine")
    budget.add("Sensors + networking", "computing", 50 * scale, "Distributed sensor mesh")

    # Manufacturing
    budget.add("3D printers (4 types)", "manufacturing", 3, "manufacturing.py: avg 0.75 kW each")
    budget.add("Recycling systems", "manufacturing", 50 * scale, "Metal/polymer recycling")

    # Thermal
    # NOTE (Nakamura, Fluids PDR): 200 kW coolant-pump budget may be
    # undersized for 200 MW_th primary NaK loop. A ~3% pumping penalty
    # (Todreas & Kazimi, Nuclear Systems Vol. 2, 2012) would imply ~6 MW
    # of pump shaft power at full reactor output. Current value reflects
    # cruise-mode (low flow) operation; revisit when reactor ops profile
    # is finalized.
    budget.add("Coolant pumps (NaK loop)", "thermal", 200, "thermal_management.py (cruise-mode; see Nakamura note)")
    # 8 T REBCO coil at 20 K with ~17 W/m heat leak × 1000 m coil
    # length = 17 kW total cold-end heat load. For a Stirling
    # cryocooler at 20 K the inverse coefficient of performance
    # (W_input / W_lifted) is ~300 (Eckels et al. 2016
    # *Cryogenics* 75 6 Fig 3), giving ~5 MW input. This is
    # within a factor of 15 of the Carnot floor
    # T_cold / (T_hot - T_cold) = 20 / 280 ≈ 0.071 →
    # 17e3 / 0.071 ≈ 240 kW absolute minimum, with the ~20×
    # degradation from Carnot to real-device performance being
    # typical for Stirling cycles.
    budget.add("Reactor magnet cryocooler", "thermal", 5000, "8T REBCO @20K, ~50 kW heat leak, COP~300 (Eckels 2016 Cryogenics 75:6) — Wei R6")

    # Habitat
    budget.add("Kitchen/cooking", "habitat", 100 * scale, "1000 crew × 3 meals/day")
    budget.add("Water heating", "habitat", 200 * scale, "Showers + laundry")
    budget.add("Laundry", "habitat", 50 * scale, "Industrial laundry")
    budget.add("Exercise equipment", "habitat", 20 * scale, "Treadmills, ergometers")
    budget.add("Recreation + entertainment", "habitat", 30 * scale, "Media, VR, workshops")
    budget.add("Medical bay", "habitat", 50, "Surgical suite + diagnostics")

    # Communications
    budget.add("Laser comm (deep space)", "communications", 100, "advanced_systems.py")
    budget.add("Internal network", "communications", 10 * scale, "Ship-wide WiFi/fiber")

    return budget
