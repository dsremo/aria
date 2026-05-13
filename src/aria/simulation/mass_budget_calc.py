"""Spacecraft mass budget calculator.

Provides mass estimation tools for preliminary spacecraft design:
- Dry mass buildup by subsystem (Wertz & Larson heuristics)
- Wet mass sizing via Tsiolkovsky
- Growth margin tracking (PDR, CDR, flight)
- Mass distribution pie chart data

Standard spacecraft mass fractions by subsystem (SMAD Table 14-18):
- Structure: 15-25% of dry mass
- Propulsion: 3-5% (dry) + propellant (wet)
- Power: 20-30% (solar array + battery)
- Thermal: 2-5%
- ADCS: 5-10%
- TT&C (comms): 3-6%
- C&DH (avionics): 3-5%
- Payload: 15-25%
- Cabling: 3-8%
- Harness/margin: 10-30%

References:
    Wertz & Larson (1999) SMAD Table 14-18
    Brown (2002) "Elements of Spacecraft Design" Ch. 2
    ESA/ESTEC mass-budget guidelines for design phases
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MassItem:
    """A single mass line item."""
    name: str
    mass_kg: float
    subsystem: str
    growth_factor: float = 1.0    # 1.00 CDR, 1.10 PDR, 1.25 conceptual
    citation: str = ""


@dataclass
class MassBudget:
    """Complete spacecraft mass budget with growth tracking."""
    items: List[MassItem] = field(default_factory=list)
    propellant_kg: float = 0.0      # tracked separately
    design_phase: str = "PDR"        # "Conceptual", "PDR", "CDR", "Flight"

    def add(self, item: MassItem) -> None:
        self.items.append(item)

    def add_quick(
        self, name: str, mass_kg: float, subsystem: str,
        growth_factor: float = 1.1, citation: str = "",
    ) -> None:
        """Shortcut for adding an item."""
        self.items.append(MassItem(name, mass_kg, subsystem, growth_factor, citation))

    def dry_mass_current_kg(self) -> float:
        """Dry mass without growth margin applied."""
        return sum(i.mass_kg for i in self.items)

    def dry_mass_with_growth_kg(self) -> float:
        """Dry mass with per-item growth factors applied."""
        return sum(i.mass_kg * i.growth_factor for i in self.items)

    def wet_mass_kg(self) -> float:
        """Total mass including propellant."""
        return self.dry_mass_with_growth_kg() + self.propellant_kg

    def by_subsystem(self) -> Dict[str, float]:
        """Mass breakdown by subsystem (current, without growth)."""
        breakdown: Dict[str, float] = {}
        for i in self.items:
            breakdown[i.subsystem] = breakdown.get(i.subsystem, 0.0) + i.mass_kg
        return breakdown

    def by_subsystem_pct(self) -> Dict[str, float]:
        """Percentage breakdown."""
        total = self.dry_mass_current_kg()
        if total <= 0:
            return {}
        return {k: v / total * 100 for k, v in self.by_subsystem().items()}

    def check_against_smad_ranges(self) -> Dict[str, str]:
        """Check if subsystem fractions match SMAD typical ranges.

        Returns dict of {subsystem: status} where status is
        "ok", "low", or "high".
        Reference: Wertz & Larson 1999 Table 14-18.
        """
        smad_ranges = {
            # subsystem: (low_pct, high_pct)
            "structure": (15, 25),
            "propulsion": (3, 8),
            "power": (20, 30),
            "thermal": (2, 5),
            "adcs": (5, 10),
            "comms": (3, 6),
            "avionics": (3, 5),
            "payload": (15, 25),
        }
        actual = self.by_subsystem_pct()
        check: Dict[str, str] = {}
        for sub, (lo, hi) in smad_ranges.items():
            # Case-insensitive match
            val = sum(v for k, v in actual.items() if k.lower() == sub)
            if val < lo:
                check[sub] = f"low ({val:.1f}% vs {lo}-{hi}%)"
            elif val > hi:
                check[sub] = f"high ({val:.1f}% vs {lo}-{hi}%)"
            else:
                check[sub] = f"ok ({val:.1f}%)"
        return check

    def summary(self) -> Dict[str, float]:
        """Full mass budget summary."""
        return {
            "dry_mass_kg": self.dry_mass_current_kg(),
            "dry_mass_with_growth_kg": self.dry_mass_with_growth_kg(),
            "propellant_kg": self.propellant_kg,
            "wet_mass_kg": self.wet_mass_kg(),
            "item_count": len(self.items),
            "subsystem_count": len(self.by_subsystem()),
            "design_phase": self.design_phase,
        }


# ══════════════════════════════════════════════════════════════════
#  Growth factors by design phase (SMAD Table 14-21)
# ══════════════════════════════════════════════════════════════════

GROWTH_FACTORS_BY_PHASE = {
    "conceptual": 1.25,   # 25% margin in early design
    "prelim": 1.15,       # SRR/PDR
    "pdr": 1.10,          # post-PDR, items getting defined
    "cdr": 1.05,          # post-CDR, detailed designs
    "flight": 1.00,       # actual hardware mass
}


def estimate_heuristic_budget(
    payload_mass_kg: float,
    mission_type: str = "leo_science",
) -> MassBudget:
    """Build a heuristic mass budget given a payload mass.

    Uses typical subsystem fractions for different mission types.
    Initial estimate for conceptual design phase (Phase A).

    Args:
        payload_mass_kg: science/mission payload mass
        mission_type: "leo_science", "gto_comm", "interplanetary"

    Returns:
        MassBudget pre-populated with typical subsystem items
    """
    # Different mission types have different subsystem fractions
    if mission_type == "leo_science":
        fractions = {
            "structure": 0.20,
            "power": 0.25,
            "thermal": 0.04,
            "adcs": 0.08,
            "comms": 0.04,
            "avionics": 0.04,
            "propulsion": 0.05,
            "payload": 0.20,
            "harness": 0.10,
        }
    elif mission_type == "gto_comm":
        fractions = {
            "structure": 0.22,
            "power": 0.28,
            "thermal": 0.03,
            "adcs": 0.06,
            "comms": 0.06,
            "avionics": 0.04,
            "propulsion": 0.12,    # more for GEO insertion + keeping
            "payload": 0.15,
            "harness": 0.04,
        }
    else:  # interplanetary
        fractions = {
            "structure": 0.15,
            "power": 0.30,         # larger solar panels at Mars/beyond
            "thermal": 0.05,
            "adcs": 0.08,
            "comms": 0.05,         # bigger dish
            "avionics": 0.04,
            "propulsion": 0.10,
            "payload": 0.18,
            "harness": 0.05,
        }

    # Back-calculate total dry mass from payload fraction
    payload_frac = fractions["payload"]
    if payload_frac <= 0:
        payload_frac = 0.2
    total_dry = payload_mass_kg / payload_frac

    # Build the budget
    budget = MassBudget(design_phase="Conceptual")
    budget.add_quick("Primary payload", payload_mass_kg, "payload",
                     growth_factor=1.15)
    for sub, frac in fractions.items():
        if sub == "payload":
            continue
        budget.add_quick(
            f"{sub} (heuristic)",
            total_dry * frac,
            sub,
            growth_factor=1.25,
            citation="SMAD 14-18 typical fraction",
        )

    return budget
