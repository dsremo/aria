"""Manufacturing & Self-Repair Systems for a Generation Ship.

THE PRINTER PROBLEM:
  You need the printer working to print replacement printer parts.
  If ALL printers fail simultaneously, manufacturing capability is permanently lost.
  This is a single point of failure for the entire mission.

SOLUTION HIERARCHY:
  1. Redundancy: 4+ printers of different types (no common failure mode)
  2. Self-replication: each printer can print parts for the others (RepRap concept)
  3. Non-printable spares: stockpile components that can't be 3D printed
     (electronics, laser diodes, stepper motors, bearings, optics)
  4. Robotic repair: automated maintenance of printers before failure
  5. Material recycling: failed parts → feedstock for new parts

PRINTER TYPES (different materials, different failure modes):
  1. FDM/FFF (Fused Filament): polymers, composites — simplest, most repairable
  2. SLS/SLM (Laser Sintering): metals (steel, titanium, aluminum) — ESA ISS 2024
  3. DLP/SLA (Resin): ceramics, high-detail parts — for seals, valves
  4. EBM (Electron Beam): high-strength metals, refractory alloys — for engine parts
  5. Circuit Printer: PCBs, simple electronics — for sensor/control replacements

NON-PRINTABLE COMPONENTS (the real bottleneck):
  - Laser diodes (for SLM/SLS printers)
  - Stepper motors (precise motion control)
  - Bearings (precision ground steel)
  - Optical elements (lenses, mirrors, fiber optics)
  - Semiconductor chips (CPUs, FPGAs, sensors)
  - Superconductors (for magsail, MRI, etc.)

VON NEUMANN SELF-REPLICATION:
  A printer can print ~70% of another printer's parts (RepRap achieved this).
  The other 30% are the non-printable components above.
  If we stockpile enough non-printable spares, we can rebuild printers indefinitely.

Reference:
  - RepRap Project: first self-replicating 3D printer (2008)
  - NASA ISS Additive Manufacturing Facility (2014-present)
  - ESA metal 3D printing on ISS (2024, stainless steel)
  - Freitas (1980): self-replicating spacecraft, 443-ton seed factory
  - NASA 2026: 3× build volume, adding aluminum + copper printing
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.simulation.mil_hdbk_217f import (
    printer_annual_degradation_rate,
)

logger = structlog.get_logger()


@dataclass
class PrinterState:
    """State of a single 3D printer."""
    name: str
    printer_type: str  # FDM, SLM, DLP, EBM, CIRCUIT
    health: float = 1.0
    # What it can print
    materials: list[str] = field(default_factory=list)
    # Build volume (cm³)
    build_volume_cm3: float = 10000.0
    # Print speed (cm³/hour)
    print_speed_cm3_hr: float = 50.0
    # Power consumption (watts)
    power_w: float = 500.0
    # Can this printer print parts for other printers?
    can_print_printer_parts: bool = True
    # Annual degradation rate (NASA C-MAPSS α=1.538, scaled from turbofan MTBF)
    degradation_rate: float = 0.02  # FDM baseline (Weibull η=47yr → ~2.1%/yr avg)
    # Hours of operation
    total_hours: int = 0
    # Failures repaired
    repairs: int = 0


@dataclass
class NonPrintableSpares:
    """Stockpile of components that CANNOT be 3D printed.

    These are the real bottleneck. When these run out,
    printers can't be repaired, and manufacturing stops.
    """
    laser_diodes: int = 50          # For SLM/SLS printers
    stepper_motors: int = 100       # Precision motion (6 per printer)
    bearings: int = 200             # Linear + rotary (10+ per printer)
    optical_elements: int = 30      # Lenses, mirrors
    semiconductor_chips: int = 100  # Controllers, sensors
    power_supplies: int = 20        # High-current for EBM
    heating_elements: int = 40      # For FDM/SLM
    thermocouples: int = 100        # Temperature sensors
    wiring_harness_m: float = 500.0  # Meters of shielded cable

    def total_components(self) -> int:
        return (self.laser_diodes + self.stepper_motors + self.bearings +
                self.optical_elements + self.semiconductor_chips +
                self.power_supplies + self.heating_elements + self.thermocouples)


@dataclass
class ManufacturingState:
    """Complete manufacturing system state."""
    printers: list[PrinterState] = field(default_factory=list)
    spares: NonPrintableSpares = field(default_factory=NonPrintableSpares)

    # Material feedstock (kg)
    polymer_feedstock_kg: float = 2000.0
    metal_powder_kg: float = 1000.0  # Steel, titanium, aluminum
    resin_liters: float = 500.0
    circuit_substrate_sheets: int = 200

    # Recycling
    recycler_health: float = 1.0
    recycle_efficiency: float = 0.85  # 85% material recovery

    # Production capacity
    daily_capacity_cm3: float = 0.0
    parts_produced_total: int = 0
    printers_rebuilt: int = 0


class ManufacturingSimulator:
    """Simulates the manufacturing/self-repair system.

    The key question: can the ship maintain manufacturing capability
    for 1000 years? The answer depends on:
      1. Printer redundancy (4+ of different types)
      2. Non-printable spare stockpile
      3. Recycling efficiency
      4. Robotic maintenance
    """

    def __init__(self, seed: int | None = None) -> None:
        import random
        self._rng = random.Random(seed)

        # Initialize 4 printer types
        # Degradation rates derived from MIL-HDBK-217F component-level BOM analysis.
        # Each printer's annual degradation = P(>=1 component failure in 8760 hrs)
        # calculated from summing lambda_b * pi_E for all components in the BOM.
        self.state = ManufacturingState(printers=[
            PrinterState(
                name="FDM-1", printer_type="FDM",
                materials=["polymer", "composite", "flexible"],
                build_volume_cm3=20000, print_speed_cm3_hr=100,
                power_w=300,
                degradation_rate=printer_annual_degradation_rate("FDM"),
            ),
            PrinterState(
                name="SLM-1", printer_type="SLM",
                materials=["steel", "titanium", "aluminum", "copper"],
                build_volume_cm3=8000, print_speed_cm3_hr=20,
                power_w=2000,
                degradation_rate=printer_annual_degradation_rate("SLM"),
            ),
            PrinterState(
                name="DLP-1", printer_type="DLP",
                materials=["ceramic", "resin", "dental", "seal"],
                build_volume_cm3=5000, print_speed_cm3_hr=30,
                power_w=400,
                degradation_rate=printer_annual_degradation_rate("DLP"),
            ),
            PrinterState(
                name="CIRCUIT-1", printer_type="CIRCUIT",
                materials=["pcb", "conductor", "resistor"],
                build_volume_cm3=2000, print_speed_cm3_hr=10,
                power_w=200,
                degradation_rate=printer_annual_degradation_rate("CIRCUIT"),
            ),
        ])

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        operational_printers = 0
        total_capacity = 0.0

        for printer in s.printers:
            # ── Degradation ──
            printer.health = max(0, printer.health - printer.degradation_rate)
            printer.total_hours += 8760  # Hours in a year

            # ── Weibull hazard-rate failure ──
            # Source: Weibull (1951), MIL-HDBK-217F reliability prediction
            # h(t) = (beta/eta) * (t/eta)^(beta-1)
            # Printers are mechanical: beta=2.5, eta=25 yr (from biology_social.py WEIBULL_DEFAULTS)
            # At age 1yr: h=0.0036/yr, age 10yr: h=0.045/yr, age 25yr: h=0.1/yr
            _beta, _eta = 2.5, 25.0  # mechanical Weibull params
            _age_years = max(0.1, printer.total_hours / 8760.0)
            _hazard = (_beta / _eta) * (_age_years / _eta) ** (_beta - 1)
            # Scale by health: degraded printers fail faster
            failure_prob = min(0.5, _hazard * (2.0 - printer.health))
            if self._rng.random() < failure_prob:
                printer.health *= 0.5
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Printer {printer.name} ({printer.printer_type}) failure — health {printer.health:.0%}",
                    "subsystem": "manufacturing",
                })

            # ── Repair attempt (if health < 50%) ──
            if printer.health < 0.5 and printer.health > 0:
                repair_success = self._attempt_repair(printer, s)
                if repair_success:
                    printer.health = min(0.8, printer.health + 0.3)
                    printer.repairs += 1
                    events.append({
                        "year": mission_year,
                        "severity": "NOMINAL",
                        "message": f"Printer {printer.name} repaired (health → {printer.health:.0%})",
                        "subsystem": "manufacturing",
                    })

            # ── Capacity calculation ──
            if printer.health > 0.1:
                operational_printers += 1
                total_capacity += printer.print_speed_cm3_hr * 24 * printer.health

        s.daily_capacity_cm3 = total_capacity

        # ── Self-replication check ──
        # If a printer dies completely, try to rebuild it from others
        dead_printers = [p for p in s.printers if p.health <= 0]
        alive_printers = [p for p in s.printers if p.health > 0.3]

        for dead in dead_printers:
            if alive_printers and self._can_rebuild_printer(dead, alive_printers, s):
                dead.health = 0.6  # Rebuilt but not perfect
                s.printers_rebuilt += 1
                events.append({
                    "year": mission_year,
                    "severity": "NOMINAL",
                    "message": f"Printer {dead.name} REBUILT from other printers + spare components "
                               f"(von Neumann self-replication). Total rebuilds: {s.printers_rebuilt}",
                    "subsystem": "manufacturing",
                })

        # ── Material consumption ──
        # Assume 10% of capacity used for ship maintenance
        material_consumed_cm3 = total_capacity * 0.1  # 10% utilization
        material_consumed_kg = material_consumed_cm3 * 0.005  # ~5g/cm³ average density

        # Split between material types
        s.polymer_feedstock_kg = max(0, s.polymer_feedstock_kg - material_consumed_kg * 0.4)
        s.metal_powder_kg = max(0, s.metal_powder_kg - material_consumed_kg * 0.4)
        s.resin_liters = max(0, s.resin_liters - material_consumed_kg * 0.1)

        # ── Recycling ──
        s.recycler_health = max(0.3, s.recycler_health - 0.005)
        recycled_kg = material_consumed_kg * s.recycle_efficiency * s.recycler_health
        s.polymer_feedstock_kg += recycled_kg * 0.4
        s.metal_powder_kg += recycled_kg * 0.4

        # ── Alerts (latched on printer-count transition) ──
        last_reported = getattr(self, "_last_printer_count_report", None)
        if operational_printers == 0 and last_reported != 0:
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": "ALL PRINTERS OFFLINE — manufacturing capability lost. "
                           "Ship cannot produce replacement parts.",
                "subsystem": "manufacturing",
            })
            self._last_printer_count_report = 0
        elif operational_printers == 1 and last_reported != 1:
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Only 1 printer operational ({[p.name for p in s.printers if p.health > 0.1]}). "
                           "Single point of failure for manufacturing.",
                "subsystem": "manufacturing",
            })
            self._last_printer_count_report = 1
        elif operational_printers >= 2:
            self._last_printer_count_report = operational_printers

        if (s.spares.total_components() < 50
                and not getattr(self, "_spares_low_latched", False)):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Non-printable spare components critically low: {s.spares.total_components()} remaining. "
                           "Cannot rebuild printers when they fail.",
                "subsystem": "manufacturing",
            })
            self._spares_low_latched = True
        elif s.spares.total_components() >= 75:
            self._spares_low_latched = False

        return events

    def _attempt_repair(self, printer: PrinterState, state: ManufacturingState) -> bool:
        """Attempt to repair a printer using spares and other printers."""
        sp = state.spares

        # Need: 1 motor, 2 bearings, 1 heating element minimum
        if sp.stepper_motors < 1 or sp.bearings < 2:
            return False

        # SLM needs laser diode
        if printer.printer_type == "SLM" and sp.laser_diodes < 1:
            return False

        # Consume spares
        sp.stepper_motors -= 1
        sp.bearings -= 2
        sp.heating_elements = max(0, sp.heating_elements - 1)

        if printer.printer_type == "SLM":
            sp.laser_diodes -= 1
        if printer.printer_type == "CIRCUIT":
            sp.semiconductor_chips = max(0, sp.semiconductor_chips - 1)

        return True

    def _can_rebuild_printer(
        self, dead: PrinterState, alive: list[PrinterState], state: ManufacturingState
    ) -> bool:
        """Check if a dead printer can be rebuilt from scratch.

        RepRap principle: ~70% of parts can be printed, 30% need non-printable spares.
        """
        sp = state.spares

        # Need substantial non-printable components
        needed_motors = 6
        needed_bearings = 10
        needed_chips = 2

        if sp.stepper_motors < needed_motors:
            return False
        if sp.bearings < needed_bearings:
            return False
        if sp.semiconductor_chips < needed_chips:
            return False

        if dead.printer_type == "SLM" and sp.laser_diodes < 2:
            return False

        # Need at least one metal printer alive (for structural parts)
        has_metal = any(p.printer_type in ("SLM", "EBM") and p.health > 0.3 for p in alive)
        # Need at least one polymer printer (for housing, gears)
        has_polymer = any(p.printer_type == "FDM" and p.health > 0.3 for p in alive)

        if not (has_metal or has_polymer):
            return False

        # Consume spares
        sp.stepper_motors -= needed_motors
        sp.bearings -= needed_bearings
        sp.semiconductor_chips -= needed_chips
        if dead.printer_type == "SLM":
            sp.laser_diodes -= 2

        return True

    def get_manufacturing_report(self) -> dict[str, Any]:
        s = self.state
        return {
            "operational_printers": sum(1 for p in s.printers if p.health > 0.1),
            "total_printers": len(s.printers),
            "printers": [
                {"name": p.name, "type": p.printer_type, "health": p.health,
                 "repairs": p.repairs, "hours": p.total_hours}
                for p in s.printers
            ],
            "daily_capacity_cm3": s.daily_capacity_cm3,
            "printers_rebuilt": s.printers_rebuilt,
            "non_printable_spares": s.spares.total_components(),
            "polymer_feedstock_kg": s.polymer_feedstock_kg,
            "metal_powder_kg": s.metal_powder_kg,
            "recycler_health": s.recycler_health,
        }
