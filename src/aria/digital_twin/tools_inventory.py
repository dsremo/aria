"""Crew Tools & Equipment Inventory — everything needed to maintain the ship.

A generation ship must carry tools for every possible repair, from
tightening a bolt to replacing a reactor component. The crew cannot
order parts from Earth — everything must be on board or manufacturable.

CATEGORIES:
  1. Hand tools (wrenches, pliers, screwdrivers, hammers)
  2. Power tools (drills, grinders, impact wrenches)
  3. Measurement instruments (calipers, micrometers, gauges)
  4. Welding equipment (TIG, orbital, friction stir)
  5. Diagnostic equipment (oscilloscopes, multimeters, thermal cameras)
  6. Heavy equipment (cranes, hoists, forklifts)
  7. Safety equipment (suits, harnesses, fire extinguishers)
  8. Medical equipment (surgical tools, diagnostic imaging)
  9. Scientific instruments (spectrometers, microscopes, telescopes)
  10. Manufacturing consumables (welding rod, cutting fluid, abrasives)

Reference: NASA ISS Tool Crib Inventory (JSC-28918), ESA Columbus Tool Kit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolItem:
    """A single tool or equipment item."""
    name: str
    category: str
    subcategory: str
    quantity: int
    mass_kg: float           # Per unit
    power_watts: float = 0   # 0 = manual/unpowered
    replaceable: bool = True  # Can be 3D printed?
    source: str = ""         # Standard or manufacturer


# ── Complete tool inventory ──────────────────────────────────────────────

TOOL_INVENTORY: list[ToolItem] = [
    # ── 1. HAND TOOLS ──
    ToolItem("Combination wrench set (8-32mm)", "hand_tools", "wrenches", 20, 3.5,
             source="ISO 1711, Snap-on Industrial"),
    ToolItem("Socket set (1/4, 3/8, 1/2 drive)", "hand_tools", "wrenches", 20, 5.0,
             source="ISO 2725, Snap-on"),
    ToolItem("Torque wrench (10-350 Nm)", "hand_tools", "wrenches", 10, 2.5,
             source="ISO 6789, CDI Torque Products"),
    ToolItem("Allen key set (2-19mm)", "hand_tools", "wrenches", 30, 0.8,
             source="ISO 2936"),
    ToolItem("Pliers set (needle, slip-joint, locking)", "hand_tools", "pliers", 20, 0.4,
             source="ISO 5746, Knipex"),
    ToolItem("Wire strippers/crimpers", "hand_tools", "pliers", 15, 0.3,
             source="MIL-DTL-22520 crimping"),
    ToolItem("Screwdriver set (Phillips, flat, Torx)", "hand_tools", "screwdrivers", 20, 0.3,
             source="ISO 8764, Wera Kraftform"),
    ToolItem("Ball-peen hammer (500g, 1kg)", "hand_tools", "hammers", 10, 1.0,
             source="ISO 15601"),
    ToolItem("Dead-blow mallet", "hand_tools", "hammers", 5, 1.5),
    ToolItem("Pry bar set (300-900mm)", "hand_tools", "leverage", 5, 2.0),
    ToolItem("Hacksaw with spare blades", "hand_tools", "cutting", 10, 0.8),
    ToolItem("Files (flat, round, half-round)", "hand_tools", "finishing", 20, 0.3),
    ToolItem("Tap and die set (M3-M30)", "hand_tools", "threading", 5, 8.0,
             source="ISO 529"),
    ToolItem("Pipe cutter (6-150mm)", "hand_tools", "cutting", 5, 1.5),
    ToolItem("Tube bender (6-25mm)", "hand_tools", "forming", 3, 3.0),
    ToolItem("Rivet gun (manual)", "hand_tools", "fastening", 5, 1.0,
             source="Cherry Aerospace"),

    # ── 2. POWER TOOLS ──
    ToolItem("Cordless drill/driver (18V)", "power_tools", "drilling", 15, 2.0, 500,
             source="Milwaukee M18"),
    ToolItem("Impact wrench (1/2 drive, 18V)", "power_tools", "fastening", 10, 3.5, 800,
             source="Milwaukee M18 FUEL"),
    ToolItem("Angle grinder (125mm)", "power_tools", "grinding", 5, 2.5, 1000),
    ToolItem("Orbital sander", "power_tools", "finishing", 5, 1.8, 300),
    ToolItem("Reciprocating saw", "power_tools", "cutting", 5, 3.0, 1200),
    ToolItem("Band saw (portable)", "power_tools", "cutting", 2, 15.0, 1500),
    ToolItem("Drill press (bench)", "power_tools", "drilling", 2, 45.0, 750),
    ToolItem("Lathe (bench, 200mm swing)", "power_tools", "machining", 2, 80.0, 1500,
             replaceable=False, source="Precision Matthews PM-1228"),
    ToolItem("Milling machine (bench)", "power_tools", "machining", 1, 150.0, 2000,
             replaceable=False, source="Precision Matthews PM-25MV"),

    # ── 3. MEASUREMENT ──
    ToolItem("Digital caliper (150mm)", "measurement", "dimensional", 20, 0.2,
             source="Mitutoyo 500-196-30"),
    ToolItem("Micrometer set (0-150mm)", "measurement", "dimensional", 5, 0.5,
             source="Mitutoyo Series 103"),
    ToolItem("Dial indicator (0.01mm)", "measurement", "dimensional", 10, 0.3),
    ToolItem("Pressure gauge (0-1 MPa)", "measurement", "pressure", 20, 0.5,
             source="Ashcroft Type 1009"),
    ToolItem("Pressure gauge (0-20 MPa)", "measurement", "pressure", 10, 0.8),
    ToolItem("Multimeter (Fluke 87V)", "measurement", "electrical", 20, 0.6,
             source="Fluke 87V Industrial"),
    ToolItem("Oscilloscope (4ch, 200MHz)", "measurement", "electrical", 5, 4.0, 50,
             source="Keysight DSOX1204G"),
    ToolItem("Thermal camera (FLIR)", "measurement", "thermal", 5, 0.8,
             source="FLIR E6-XT"),
    ToolItem("Ultrasonic thickness gauge", "measurement", "NDT", 5, 0.5,
             source="Olympus 38DL PLUS"),
    ToolItem("Radiation survey meter", "measurement", "radiation", 10, 1.0,
             source="Ludlum Model 9-3"),
    ToolItem("Gas detector (O2, CO, H2S, LEL)", "measurement", "gas", 15, 0.5,
             source="RAE MultiRAE"),
    ToolItem("Level (digital, 600mm)", "measurement", "alignment", 5, 0.8),

    # ── 4. WELDING ──
    ToolItem("TIG welder (AC/DC, 300A)", "welding", "arc", 3, 35.0, 8000,
             replaceable=False, source="Miller Dynasty 300"),
    ToolItem("Orbital weld head (25-150mm)", "welding", "orbital", 2, 15.0, 3000,
             replaceable=False, source="Arc Machines M207"),
    # Williams (Manufacturing PDR): FSW is the only qualified process for
    # Ti-6Al-4V / Al-Li hull repair on a multi-century mission. A single tool
    # is a single-point failure for all structural weld ops — carry two
    # independent tools for redundancy (NASA-STD-5017A single-fault tolerance
    # rationale; Mishra & Ma, Mater. Sci. Eng. R 50, 2005 — FSW equipment
    # duty-cycle and spindle-bearing wear data).
    ToolItem("Friction stir weld tool (primary)", "welding", "FSW", 1, 500.0, 15000,
             replaceable=False, source="For Ti-6Al-4V hull repair; NASA MSFC FSW flight heritage"),
    ToolItem("Friction stir weld tool (redundant)", "welding", "FSW", 1, 500.0, 15000,
             replaceable=False, source="Williams PDR — single-fault tolerance for hull repair (NASA-STD-5017A)"),
    ToolItem("Welding rod (Ti ERTi-5)", "consumables", "welding", 500, 0.1,
             source="AWS A5.16, ASTM B348"),
    ToolItem("Welding rod (SS ER316L)", "consumables", "welding", 500, 0.1,
             source="AWS A5.9"),
    ToolItem("Welding gas (Ar, 50L cylinder)", "consumables", "welding", 20, 80.0,
             source="Shielding gas, 99.999% purity"),

    # ── 5. DIAGNOSTIC ──
    ToolItem("Borescope (articulating, 6mm)", "diagnostics", "inspection", 5, 1.0,
             source="Olympus IPLEX NX"),
    ToolItem("Eddy current flaw detector", "diagnostics", "NDT", 2, 5.0, 30,
             replaceable=False, source="Olympus NORTEC 600"),
    ToolItem("Vibration analyzer", "diagnostics", "condition_monitoring", 3, 2.0, 10,
             source="SKF CMXA 80"),
    ToolItem("Leak detector (He mass spec)", "diagnostics", "leak", 2, 15.0, 200,
             replaceable=False, source="Pfeiffer ASM 340"),

    # ── 6. HEAVY EQUIPMENT ──
    ToolItem("Chain hoist (2t)", "heavy_equipment", "lifting", 5, 25.0),
    ToolItem("Chain hoist (10t)", "heavy_equipment", "lifting", 2, 80.0),
    ToolItem("Come-along (2t)", "heavy_equipment", "pulling", 5, 8.0),
    ToolItem("Hydraulic jack (20t)", "heavy_equipment", "lifting", 3, 15.0),
    ToolItem("Electric forklift (1t)", "heavy_equipment", "transport", 2, 1500.0, 5000,
             replaceable=False),
    ToolItem("Overhead crane (5t, 10m span)", "heavy_equipment", "lifting", 4, 2000.0, 10000,
             replaceable=False, source="Demag overhead crane"),

    # ── 7. SAFETY ──
    ToolItem("EVA suit", "safety", "suits", 20, 55.0,
             replaceable=False, source="NASA xEMU heritage"),
    ToolItem("IVA emergency suit", "safety", "suits", 100, 8.0),
    ToolItem("Fall arrest harness", "safety", "harnesses", 50, 2.0,
             source="EN 361"),
    ToolItem("Fire extinguisher (CO2, 5kg)", "safety", "fire", 100, 12.0,
             source="ISS PFE heritage"),
    ToolItem("Portable O2 supply (1hr)", "safety", "breathing", 50, 5.0),
    ToolItem("Radiation dosimeter (personal)", "safety", "radiation", 1200, 0.05,
             source="Landauer InLight"),
    ToolItem("First aid kit (trauma)", "safety", "medical", 30, 5.0),

    # ── 8. MEDICAL ──
    ToolItem("Surgical instrument set", "medical", "surgical", 5, 8.0,
             replaceable=False, source="Aesculap Basic Surgery Set"),
    ToolItem("Ultrasound (portable)", "medical", "imaging", 3, 3.0, 50,
             replaceable=False, source="Philips Lumify"),
    ToolItem("X-ray (portable)", "medical", "imaging", 1, 25.0, 2000,
             replaceable=False, source="MinXray HF100+"),
    ToolItem("Defibrillator (AED)", "medical", "cardiac", 10, 2.5,
             source="Philips HeartStart"),
    ToolItem("Ventilator", "medical", "respiratory", 5, 10.0, 200,
             replaceable=False),
    ToolItem("Dental instruments set", "medical", "dental", 3, 3.0,
             replaceable=False),

    # ── 9. SCIENTIFIC ──
    ToolItem("Optical microscope (1000x)", "scientific", "microscopy", 5, 5.0, 20),
    ToolItem("Spectrometer (UV-Vis-NIR)", "scientific", "spectroscopy", 2, 8.0, 50,
             replaceable=False, source="Ocean Insight FLAME-S"),
    ToolItem("Telescope (200mm Cassegrain)", "scientific", "astronomy", 2, 15.0,
             source="Celestron C8"),
    ToolItem("PCR machine (DNA analysis)", "scientific", "biology", 2, 8.0, 200,
             replaceable=False, source="Bio-Rad CFX96"),

    # ── 10. CONSUMABLES ──
    ToolItem("Cutting discs (125mm)", "consumables", "abrasives", 500, 0.1),
    ToolItem("Drill bits (HSS, 1-25mm set)", "consumables", "cutting", 50, 0.5),
    ToolItem("Drill bits (carbide, Ti-6Al-4V)", "consumables", "cutting", 20, 0.3,
             source="Kennametal for titanium"),
    ToolItem("Sandpaper (60-2000 grit)", "consumables", "finishing", 1000, 0.01),
    ToolItem("Thread sealant (PTFE tape)", "consumables", "sealing", 200, 0.05),
    ToolItem("Lubricant (Braycote 601EF)", "consumables", "lubrication", 100, 0.5,
             source="Castrol Braycote, space-rated vacuum grease"),
    ToolItem("Adhesive (epoxy, 2-part)", "consumables", "bonding", 200, 0.3,
             source="3M Scotch-Weld EC-2216"),
    ToolItem("Cable ties (assorted)", "consumables", "fastening", 10000, 0.005),
    ToolItem("Heat shrink tubing", "consumables", "electrical", 500, 0.01),
    ToolItem("Solder (Sn63/Pb37)", "consumables", "electrical", 50, 0.5,
             source="Kester 44 flux-cored"),
]


def get_inventory() -> list[ToolItem]:
    """Return complete tool inventory."""
    return list(TOOL_INVENTORY)


def get_total_mass_kg() -> float:
    """Total mass of all tools and equipment."""
    return sum(t.mass_kg * t.quantity for t in TOOL_INVENTORY)


def get_by_category() -> dict[str, list[ToolItem]]:
    """Group tools by category."""
    cats: dict[str, list[ToolItem]] = {}
    for t in TOOL_INVENTORY:
        cats.setdefault(t.category, []).append(t)
    return cats


def get_non_replaceable() -> list[ToolItem]:
    """Items that CANNOT be 3D printed — must be preserved for mission lifetime."""
    return [t for t in TOOL_INVENTORY if not t.replaceable]


def get_power_consumers() -> list[ToolItem]:
    """Items that consume electrical power."""
    return [t for t in TOOL_INVENTORY if t.power_watts > 0]


def get_summary() -> dict[str, Any]:
    """Summary statistics."""
    by_cat = get_by_category()
    return {
        "total_items": sum(t.quantity for t in TOOL_INVENTORY),
        "unique_types": len(TOOL_INVENTORY),
        "total_mass_kg": get_total_mass_kg(),
        "categories": {cat: len(items) for cat, items in by_cat.items()},
        "non_replaceable_count": len(get_non_replaceable()),
        "max_power_consumer_w": max(t.power_watts for t in TOOL_INVENTORY),
    }
