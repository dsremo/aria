"""Bill of Materials with redundancy levels.

Answers the operational-engineering question: "what redundant systems do
we actually have? where are the single points of failure?"

Each entry says:
  * how many physical units exist
  * how many are needed for nominal operation (M-out-of-N)
  * what the failure mode is when too many fail
  * what subsystem it belongs to + which part_id (cross-link to inspector)

This is the single source of truth for redundancy counts that the
dependency graph + part_inspector then build on. Cited against existing
spacecraft conventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class BomItem:
    """One BOM line item — N units installed, M needed to operate."""

    item_id: str            # short stable identifier
    name: str               # human-readable
    subsystem: str          # one of: structure / power / thermal / propulsion / shielding / habitat / eclss / comms / navigation / avionics
    n_installed: int        # how many physical units exist
    n_required:  int        # M-out-of-N — minimum needed for nominal ops
    mass_kg_each: float
    mtbf_hours: Optional[float] = None        # mean time between failures per unit
    related_part_ids: List[str] = field(default_factory=list)
    failure_mode_if_below_min: str = ""
    notes: str = ""
    citation: str = ""

    @property
    def redundancy_level(self) -> int:
        """How many units can fail before mission-critical loss."""
        return self.n_installed - self.n_required

    @property
    def is_single_point_of_failure(self) -> bool:
        return self.n_installed == 1 and self.n_required == 1

    @property
    def total_mass_kg(self) -> float:
        return self.mass_kg_each * self.n_installed


# ── BOM declared as data — one source of truth ─────────────────────

_BOM_DATA: List[dict] = [
    # ── Power ─────────────────────────────────────────────────────
    {"item_id": "reactor", "name": "Fusion Reactor (D/He-3)",
     "subsystem": "power", "n_installed": 1, "n_required": 1,
     "mass_kg_each": 2.3e6, "mtbf_hours": 6.1e5,
     "related_part_ids": ["reactor_engine"],
     "failure_mode_if_below_min": "Total ship power loss → mission abort",
     "notes": "Single reactor — APU provides emergency-only bootstrap",
     "citation": "Frisbee 2003 JPL/D-26963; Abdou 2015"},

    {"item_id": "apu_bootstrap", "name": "Auxiliary Power Unit",
     "subsystem": "power", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 1.5e4, "mtbf_hours": 4e4,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot cold-start reactor without external power",
     "notes": "50 kW each, redundant — only used during startup or reactor SCRAM",
     "citation": "NASA-STD-8719.24 §3.2"},

    {"item_id": "hvdc_bus", "name": "20.4 kV HVDC Distribution Bus",
     "subsystem": "power", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 8e3, "mtbf_hours": 1.5e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Power distribution failure — load shedding cascade",
     "notes": "Dual-bus architecture, automatic crossover on bus failure",
     "citation": "Hofer 2014 'HVDC for Spacecraft'"},

    # ── Thermal ───────────────────────────────────────────────────
    {"item_id": "radiator_wing", "name": "Heat Rejection Wing (250×125 m)",
     "subsystem": "thermal", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 6.95e5, "mtbf_hours": 2.6e5,
     "related_part_ids": ["radiator_array_0", "radiator_array_1"],
     "failure_mode_if_below_min": "Cannot reject 134 MW — reactor thermal limit triggers SCRAM",
     "notes": "Loss of one wing halves capacity — degraded ops, eventual SCRAM if both lost",
     "citation": "thermal_management.py — ε·σ·A·T⁴ at 500 K"},

    {"item_id": "thermal_pump", "name": "K Heat-Pipe Pump",
     "subsystem": "thermal", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 250.0, "mtbf_hours": 8.7e4,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Thermal-loop failure — coolant loss → reactor SCRAM in ~30 min",
     "notes": "Quad-redundant centrifugal pump; loss of 2 still works at reduced flow",
     "citation": "Dunn & Reay 1994 Heat Pipes"},

    # ── Propulsion ────────────────────────────────────────────────
    {"item_id": "magnetic_nozzle", "name": "Magnetic Nozzle",
     "subsystem": "propulsion", "n_installed": 1, "n_required": 1,
     "mass_kg_each": 1.2e5, "mtbf_hours": 3.5e5,
     "related_part_ids": ["magnetic_nozzle"],
     "failure_mode_if_below_min": "Loss of main thrust — cannot perform delta-V manoeuvres",
     "notes": "Single nozzle (cost / mass tradeoff); RCS engine bells provide attitude only, not main thrust",
     "citation": "Frisbee 2003 §4.2"},

    {"item_id": "rcs_engine_bell", "name": "RCS Arc-Jet Bell",
     "subsystem": "propulsion", "n_installed": 4, "n_required": 3,
     "mass_kg_each": 3600.0, "mtbf_hours": 1.0e5,
     "related_part_ids": ["engine_bell_0", "engine_bell_1", "engine_bell_2", "engine_bell_3"],
     "failure_mode_if_below_min": "Cannot achieve full attitude control — mission degraded but recoverable",
     "notes": "4-way symmetric — 3 of 4 still gives full attitude control",
     "citation": "Patterson 2007 NASA/TM-2014-218232"},

    {"item_id": "fuel_tank", "name": "Cryo Fuel Tank (D/He-3)",
     "subsystem": "propulsion", "n_installed": 3, "n_required": 2,
     "mass_kg_each": 5.0e6, "mtbf_hours": 4.4e5,
     "related_part_ids": ["fuel_tank_0", "fuel_tank_1", "fuel_tank_2"],
     "failure_mode_if_below_min": "Insufficient propellant for return ΔV; mission becomes one-way",
     "notes": "Tank C is reserve; A+B carry primary load",
     "citation": "Frisbee 2003 §3.4"},

    # ── Shielding ─────────────────────────────────────────────────
    {"item_id": "shield_layer_full_stack", "name": "7-Layer Shield Stack",
     "subsystem": "shielding", "n_installed": 7, "n_required": 5,
     "mass_kg_each": 1.43e6, "mtbf_hours": 4.4e5,
     "related_part_ids": [f"shield_layer_{i}" for i in range(7)],
     "failure_mode_if_below_min": "Crew dose exceeds NASA 500 mSv/yr limit",
     "notes": "Ablation ice (L4) is dominant — layers 0-3 are active and can be repaired in flight",
     "citation": "Cucinotta 2014 NASA/TP-2013-217375"},

    # ── Habitat ───────────────────────────────────────────────────
    {"item_id": "habitat_spoke", "name": "Habitat Ring Spoke (hollow tube)",
     "subsystem": "structure", "n_installed": 6, "n_required": 4,
     "mass_kg_each": 2.0e5, "mtbf_hours": 1.3e6,  # 200t each: hollow CNT tube r=2m t=20mm L=500m ρ=1600
     "related_part_ids": [f"spoke_{i}" for i in range(6)],
     "failure_mode_if_below_min": "Ring stops rotating safely — must spin down for repair",
     "notes": "6 hollow-tube spokes at 60° spacing — mass_budget.py π(r²-(r-t)²)×L×ρ_CNT",
     "citation": "O'Neill 1977; hollow tube correction (commit 7dafeea fixed solid→hollow)"},

    {"item_id": "ring_bearing", "name": "Habitat Ring Bearing System",
     "subsystem": "structure", "n_installed": 1, "n_required": 1,
     "mass_kg_each": 5.0e4, "mtbf_hours": 8.7e5,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Ring rotation lost — habitat reverts to micro-gravity",
     "notes": "Single bearing assembly with magnetic-primary + roller-backup (see bearing_dynamics.py)",
     "citation": "Schweitzer & Maslen 2009 'Magnetic Bearings'"},

    {"item_id": "hab_module", "name": "Crew Quarter Pod",
     "subsystem": "habitat", "n_installed": 24, "n_required": 18,
     "mass_kg_each": 8.96e4, "mtbf_hours": 4.4e5,
     "related_part_ids": [f"hab_module_{i}" for i in range(24)],
     "failure_mode_if_below_min": "Crew over-densified beyond 56 occupants/module — psych + ECLSS strain",
     "notes": "24 pods × 42 crew = 1008 capacity; 6 reserve for redundancy + isolation",
     "citation": "NASA-TP-2015-218570 BVAD §5"},

    # ── ECLSS ─────────────────────────────────────────────────────
    {"item_id": "eclss_water_recovery_chain", "name": "Water Recovery Chain",
     "subsystem": "eclss", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 8e3, "mtbf_hours": 5e4,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot recycle urine + condensate → drinking water shortage",
     "notes": "Quad-redundant Sabatier + UV + filter chain (ISS heritage); 2 of 4 sustains crew",
     "citation": "NASA TM-2018-220117 'ISS Water Recovery'"},

    {"item_id": "eclss_co2_scrubber", "name": "CO2 Scrubber (zeolite + LiOH backup)",
     "subsystem": "eclss", "n_installed": 3, "n_required": 2,
     "mass_kg_each": 1.5e3, "mtbf_hours": 3.5e4,
     "related_part_ids": [],
     "failure_mode_if_below_min": "CO2 builds up to 1 % v/v in <72 hr — crew impairment",
     "notes": "Triple-redundant; LiOH cartridge as 7-day emergency reserve",
     "citation": "NASA-TM-2004-212592 §3"},

    {"item_id": "eclss_o2_generator", "name": "O2 Generator (electrolysis)",
     "subsystem": "eclss", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 1.0e3, "mtbf_hours": 3e4,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot generate 840 kg O2/day — must vent N2 reserves",
     "notes": "Quad-redundant water-electrolysis; 2 of 4 covers full 1000-crew demand",
     "citation": "NASA TP-2015-218570 BVAD §5.4"},

    # ── Comms / Avionics / Nav ────────────────────────────────────
    {"item_id": "comm_ka_dish", "name": "Ka-Band High-Gain Dish",
     "subsystem": "comms", "n_installed": 4, "n_required": 1,
     "mass_kg_each": 2200.0, "mtbf_hours": 5.3e5,
     "related_part_ids": [f"comm_antenna_{i}" for i in range(4)],
     "failure_mode_if_below_min": "Loss of high-bandwidth Earth uplink (S-band fallback only)",
     "notes": "4 dishes — 1 sufficient; quad redundancy for pointing-loss + MMOD strikes",
     "citation": "NASA DSN 810-005"},

    {"item_id": "flight_computer_tmr", "name": "Flight Computer (TMR triplet)",
     "subsystem": "avionics", "n_installed": 3, "n_required": 2,
     "mass_kg_each": 50.0, "mtbf_hours": 4e5,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Triple-redundant voting fails → manual flight by crew",
     "notes": "Three rad-hard SoCs in lockstep; 2 of 3 outvotes a failed unit",
     "citation": "Plauger 2015 'TMR FPGA in Space'"},

    {"item_id": "star_tracker", "name": "Star Tracker",
     "subsystem": "navigation", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 25.0, "mtbf_hours": 8e5,
     "related_part_ids": ["bow_sensor_ring"],
     "failure_mode_if_below_min": "Position uncertainty grows; IMU drift unbounded",
     "notes": "4 trackers at 90° offsets — any 2 give 3-axis attitude solution",
     "citation": "ESA Star Tracker SED 2018"},

    {"item_id": "imu", "name": "Inertial Measurement Unit",
     "subsystem": "navigation", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 12.0, "mtbf_hours": 6e5,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Lose attitude rate during star-tracker outage",
     "notes": "4 quad-redundant FOG (fiber optic gyros) + accelerometer triads",
     "citation": "Honeywell µHRG 2020 datasheet"},

    # ── Crew ──────────────────────────────────────────────────────
    {"item_id": "medical_bay", "name": "Medical Bay",
     "subsystem": "habitat", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 5e4, "mtbf_hours": 1e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot treat trauma / surgery; loses crew in major incidents",
     "notes": "Two medbays — ring 90° + ring 270° for failover during fire/decompression in one half",
     "citation": "NASA HRP 2022 medical-systems baseline"},

    {"item_id": "crew_cryosleep", "name": "Crew Cryo-Sleep Capsule",
     "subsystem": "habitat", "n_installed": 1100, "n_required": 1000,
     "mass_kg_each": 800.0, "mtbf_hours": 2e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot cycle full crew off-shift; raises waking population strain",
     "notes": "10 % spare capacity for failovers + emergency hibernation",
     "citation": "ESTIMATE — generation-ship cryo design heuristic"},

    # ── Structure (previously under-counted — BOM totalled 40.5 Mt of a
    # 100 Mt ship-mass target. The pressure hull, habitat-ring shell,
    # cargo bay, labs, docking ports, fabricator, and lifepods were all
    # implicit in the geometry but absent from the parts list. Added
    # below to close the budget; masses derived from shell geometry +
    # conservative density assumptions.)
    {"item_id": "pressure_hull_cylinder", "name": "Pressure Hull (main cylinder)",
     "subsystem": "structure", "n_installed": 1, "n_required": 1,
     "mass_kg_each": 2.0e7, "mtbf_hours": 1.3e6,
     "related_part_ids": ["hull_main"],
     "failure_mode_if_below_min": "Hull breach — catastrophic decompression",
     "notes": "711.9 m × 12.6 m Ti-6Al-4V, 80 mm wall. Mass = 2π·R·L·t·ρ.",
     "citation": "MMPDS-17; surface 56 364 m² × 0.08 m × 4430 kg/m³"},

    {"item_id": "habitat_ring_shell", "name": "Habitat Ring Torus Shell",
     "subsystem": "habitat", "n_installed": 1, "n_required": 1,
     "mass_kg_each": 1.26e7, "mtbf_hours": 1.3e6,  # 12.6 Mt: 4π²×500×20 × 0.02m × 1600 kg/m³
     "related_part_ids": ["habitat_ring"],
     "failure_mode_if_below_min": "Ring structural failure — loss of 0.56 g habitat",
     "notes": "R=500 m, r=20 m torus, 20 mm CNT composite wall (mass_budget.py formula).",
     "citation": "O'Neill 1977 §4.3; CNT composite Demczyk 2002; matches mass_budget.py"},

    {"item_id": "cargo_hold", "name": "Cargo Hold + Provisions",
     "subsystem": "habitat", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 1.5e6, "mtbf_hours": 2e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Insufficient food/spare-parts reserves; mission margin reduced",
     "notes": "4 × 1500 t — food, water, spares, tooling, medical stores",
     "citation": "NASA-TP-2015-218570 BVAD §4.3 per-crew supply budget"},

    {"item_id": "science_lab", "name": "Scientific Laboratory",
     "subsystem": "habitat", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 1.0e6, "mtbf_hours": 1.5e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Limited on-board research during cruise + arrival survey",
     "notes": "Biology + materials + astronomy workbenches",
     "citation": "ISS USOS lab module heritage (~ 14 t plus racks)"},

    {"item_id": "docking_port", "name": "Docking Port",
     "subsystem": "structure", "n_installed": 4, "n_required": 2,
     "mass_kg_each": 1.25e5, "mtbf_hours": 2e6,
     "related_part_ids": ["docking_port_45", "docking_port_135",
                          "docking_port_225", "docking_port_315"],
     "failure_mode_if_below_min": "Cannot receive supply / crew-transfer shuttles",
     "notes": "125 t each, 4 around hull (dorsal × 2 + ventral × 2)",
     "citation": "IDSS (International Docking System Standard) mass envelope"},

    {"item_id": "fabricator_3d", "name": "3D Printer / Fabricator",
     "subsystem": "eclss", "n_installed": 2, "n_required": 1,
     "mass_kg_each": 2.5e5, "mtbf_hours": 3e5,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Cannot produce repair patches — backlog grows",
     "notes": "Metal + polymer FDM/SLM, 500 kg/hr throughput. See repair_queue.",
     "citation": "NASA TM-2018-219859"},

    {"item_id": "lifepod", "name": "Emergency Lifepod",
     "subsystem": "habitat", "n_installed": 40, "n_required": 20,
     "mass_kg_each": 2.5e4, "mtbf_hours": 3e6,
     "related_part_ids": [],
     "failure_mode_if_below_min": "Insufficient evacuation capacity — 25 crew per pod",
     "notes": "40 pods × 25 t — seats 1 000 with 100 % redundancy",
     "citation": "Apollo LEM + Soyuz descent-module scaling"},
]


# Build immutable BomItem instances at import time
BOM: Dict[str, BomItem] = {
    d["item_id"]: BomItem(**d) for d in _BOM_DATA
}


# ── Public API ─────────────────────────────────────────────────────

def list_items() -> List[BomItem]:
    return list(BOM.values())


def get_item(item_id: str) -> Optional[BomItem]:
    return BOM.get(item_id)


def items_by_subsystem(subsystem: str) -> List[BomItem]:
    return [it for it in BOM.values() if it.subsystem == subsystem]


def single_points_of_failure() -> List[BomItem]:
    return [it for it in BOM.values() if it.is_single_point_of_failure]


def total_mass_kg() -> float:
    return sum(it.total_mass_kg for it in BOM.values())


def to_dict() -> dict:
    """JSON-serialisable summary for the HTTP API."""
    items = [
        {
            "item_id":             it.item_id,
            "name":                it.name,
            "subsystem":           it.subsystem,
            "n_installed":         it.n_installed,
            "n_required":          it.n_required,
            "redundancy_level":    it.redundancy_level,
            "is_spof":             it.is_single_point_of_failure,
            "mass_kg_each":        it.mass_kg_each,
            "total_mass_kg":       it.total_mass_kg,
            "mtbf_hours":          it.mtbf_hours,
            "related_part_ids":    it.related_part_ids,
            "failure_mode":        it.failure_mode_if_below_min,
            "notes":               it.notes,
            "citation":            it.citation,
        }
        for it in BOM.values()
    ]
    return {
        "items": items,
        "summary": {
            "total_items":   len(items),
            "total_mass_kg": round(total_mass_kg(), 1),
            "spof_count":    len(single_points_of_failure()),
            "spof_items":    [it.item_id for it in single_points_of_failure()],
        },
    }
