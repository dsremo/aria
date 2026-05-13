"""Assembly Interface Definitions — How every part of ARIA connects.

Defines the mechanical joints between major ship subsystems: which parts
mate, the fastener type and count, seal requirements, and torque specs.
This is the build-instruction layer that bridges the part manifest
(:mod:`aria.digital_twin.part_manifest`) with the hardware catalogue
(:mod:`aria.digital_twin.components_db`).

Every interface spec references real aerospace fastener standards so that
the digital twin can compute total fastener counts and mass budgets.

Santos (Mechanical PDR) — SAMPLE vs EXHAUSTIVE interfaces
---------------------------------------------------------
The 33 interface entries in this module are NOT an exhaustive enumeration
of every mechanical joint on the ship. For repeated structural joints they
represent a SAMPLE of the joint TYPE, not one entry per occurrence:

  * Hull-to-ring-frame interfaces: only 4 of 71 ring frames are listed
    individually (hull_to_ring_frame_01..04). The remaining 67 ring-frame
    joints are identical in fastener type, count, torque, and seal — they
    share the same InterfaceSpec template and should be multiplied out
    when computing ship-wide totals.
  * Radiator panel deployment hinges: 8 of 100 radiator panels have
    explicit entries; the other 92 follow the same template.
  * Similarly, habitat spoke bolted flanges, ECLSS piping flanges, and
    standardized rack-mount joints are represented by a single entry per
    joint TYPE.

When computing total fastener / seal / torque-tool counts for procurement
or the mass budget, callers MUST scale each sampled interface by the true
part_manifest quantity (e.g. multiply hull_to_ring_frame by 71,
radiator_panel_to_deploy_hinge by 100, etc.). The sampled entries exist so
that design intent (joint TYPE) is auditable without bloating this file to
several thousand entries.

References
----------
NASA-STD-5020A   Requirements for Threaded Fastening Systems in Spaceflight
                 Hardware (2018).
ECSS-E-HB-32-23A Threaded fasteners handbook (ESA, 2010).
VDI 2230         Systematic calculation of highly stressed bolted joints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.digital_twin.components_db import COMPONENT_DATABASE, Component


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InterfaceSpec:
    """Specification for a single mechanical joint in the ship.

    Parameters
    ----------
    joint_name : str
        Unique identifier for this interface.
    part_a : str
        Name of the first mating part (from part_manifest or subsystem).
    part_b : str
        Name of the second mating part.
    connection_type : str
        One of: bolted, welded, sealed, press_fit, riveted, bonded, clamped.
    fastener_type : str | None
        Part number from components_db (e.g. "ISO-4014-M20x100-8.8").
    fastener_count : int
        Number of fasteners at this joint.
    seal_type : str | None
        Part number of the seal/gasket, if applicable.
    seal_count : int
        Number of seals at this joint.
    torque_spec_nm : float | None
        Assembly torque per fastener [Nm], if bolted.
    notes : str
        Design rationale or reference.
    """

    joint_name: str
    part_a: str
    part_b: str
    connection_type: str
    fastener_type: Optional[str] = None
    fastener_count: int = 0
    seal_type: Optional[str] = None
    seal_count: int = 0
    torque_spec_nm: Optional[float] = None
    notes: str = ""


# ---------------------------------------------------------------------------
# Ship interface definitions — 35 major joints
# ---------------------------------------------------------------------------

SHIP_INTERFACES: List[InterfaceSpec] = [
    # ── Structure ────────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="hull_fwd_to_main_bulkhead",
        part_a="Forward hull cylinder",
        part_b="Main pressure bulkhead",
        connection_type="bolted",
        fastener_type="ISO-4014-M24x120-8.8",
        fastener_count=120,  # circumferential bolt circle on ~5 m dia hull (NASA-STD-5020A pattern)
        seal_type="AS568-395-FKM",
        seal_count=2,  # dual O-ring seal (redundant, NASA-STD-5020A §4.3)
        torque_spec_nm=710.0,  # VDI 2230, M24-8.8
        notes="Primary structural joint; dual seal per NASA-STD-5020A",
    ),
    InterfaceSpec(
        joint_name="hull_aft_to_main_bulkhead",
        part_a="Aft hull cylinder",
        part_b="Main pressure bulkhead",
        connection_type="bolted",
        fastener_type="ISO-4014-M24x120-8.8",
        fastener_count=120,
        seal_type="AS568-395-FKM",
        seal_count=2,
        torque_spec_nm=710.0,
        notes="Aft structural joint, mirror of forward",
    ),
    InterfaceSpec(
        joint_name="hull_to_ring_frame_01",
        part_a="Hull cylinder",
        part_b="Ring frame #1",
        connection_type="riveted",
        fastener_type="NAS1398-4.8",
        fastener_count=480,  # two rows × ~240 rivets per ring (Airbus A350 heritage)
        notes="Internal ring frames riveted to hull skin; NAS1398 flush rivets",
    ),
    InterfaceSpec(
        joint_name="hull_to_ring_frame_02",
        part_a="Hull cylinder",
        part_b="Ring frame #2",
        connection_type="riveted",
        fastener_type="NAS1398-4.8",
        fastener_count=480,
        notes="Internal ring frames riveted to hull skin",
    ),
    InterfaceSpec(
        joint_name="hull_to_ring_frame_03",
        part_a="Hull cylinder",
        part_b="Ring frame #3",
        connection_type="riveted",
        fastener_type="NAS1398-4.8",
        fastener_count=480,
        notes="Internal ring frames riveted to hull skin",
    ),
    InterfaceSpec(
        joint_name="hull_to_ring_frame_04",
        part_a="Hull cylinder",
        part_b="Ring frame #4",
        connection_type="riveted",
        fastener_type="NAS1398-4.8",
        fastener_count=480,
        notes="Internal ring frames riveted to hull skin",
    ),
    InterfaceSpec(
        joint_name="hull_to_longitudinal_stringers",
        part_a="Hull cylinder",
        part_b="Longitudinal stringers (x24)",
        connection_type="riveted",
        fastener_type="NAS1398-6.4",
        fastener_count=2400,  # 24 stringers × ~100 rivets each (stiffened-shell design)
        notes="Stringers riveted to skin panels for buckling stability (NASA-SP-8007)",
    ),

    # ── Hatches & Doors ──────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="main_hatch_to_hull",
        part_a="Main EVA hatch",
        part_b="Hull hatch frame",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-A4-80",
        fastener_count=48,  # ISS hatch heritage — ~48 bolts on 1 m hatch (SSP 41004)
        seal_type="CBM-SEAL-1000",
        seal_count=1,
        torque_spec_nm=155.0,  # A4-80 M16
        notes="Inflatable seal per ISS CBM heritage (SSP 41004)",
    ),
    InterfaceSpec(
        joint_name="internal_hatch_01",
        part_a="Compartment hatch",
        part_b="Bulkhead hatch frame",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-A4-80",
        fastener_count=36,
        seal_type="CBM-SEAL-800",
        seal_count=1,
        torque_spec_nm=155.0,
        notes="Internal pressure-rated hatch, 800 mm diameter",
    ),
    InterfaceSpec(
        joint_name="internal_hatch_02",
        part_a="Compartment hatch",
        part_b="Bulkhead hatch frame",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-A4-80",
        fastener_count=36,
        seal_type="CBM-SEAL-800",
        seal_count=1,
        torque_spec_nm=155.0,
        notes="Internal pressure-rated hatch (redundant path)",
    ),

    # ── Reactor & Power ──────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="reactor_vessel_to_hull_mount",
        part_a="Reactor pressure vessel",
        part_b="Reactor mounting frame",
        connection_type="bolted",
        fastener_type="ASTM-A193-B8M-M20x200",
        fastener_count=48,  # heavy reactor flange (ASME BPVC VIII Div.1)
        seal_type="ASME-B16.20-8in-600-718",
        seal_count=2,
        torque_spec_nm=350.0,
        notes="High-temp reactor flange; B8M studs for 538 °C service (ASME BPVC)",
    ),
    InterfaceSpec(
        joint_name="reactor_primary_loop_flange",
        part_a="Reactor outlet nozzle",
        part_b="Primary coolant pipe",
        connection_type="bolted",
        fastener_type="ASTM-A193-B7-M24x250",
        fastener_count=24,
        seal_type="ASME-B16.20-4in-300-718",
        seal_count=1,
        torque_spec_nm=750.0,
        notes="Primary loop high-pressure flange (ASME B16.5 Class 300)",
    ),
    InterfaceSpec(
        joint_name="reactor_mounting_frame_to_hull",
        part_a="Reactor mounting frame",
        part_b="Aft hull truss nodes",
        connection_type="bolted",
        fastener_type="ISO-4014-M30x150-8.8",
        fastener_count=32,
        torque_spec_nm=1400.0,
        notes="Transfer reactor loads to hull structure; M30 for high preload",
    ),
    InterfaceSpec(
        joint_name="heat_exchanger_to_frame",
        part_a="Primary heat exchanger",
        part_b="HX support frame",
        connection_type="bolted",
        fastener_type="ISO-4014-M20x100-A4-80",
        fastener_count=16,
        seal_type="ASME-B16.20-4in-300-718",
        seal_count=2,  # inlet + outlet flanges
        torque_spec_nm=305.0,
        notes="Bolted HX with spiral-wound gaskets on both flanges",
    ),

    # ── Propulsion ───────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="engine_thrust_frame_to_hull",
        part_a="Engine thrust structure",
        part_b="Aft hull cone",
        connection_type="bolted",
        fastener_type="ISO-4014-M30x150-8.8",
        fastener_count=64,  # high bolt count for thrust loads
        torque_spec_nm=1400.0,
        notes="Primary thrust load path; 64 × M30 for distributed loading",
    ),
    InterfaceSpec(
        joint_name="propellant_tank_to_frame",
        part_a="Propellant tank (x4)",
        part_b="Tank support skirt",
        connection_type="bolted",
        fastener_type="ISO-4014-M20x100-8.8",
        fastener_count=96,  # 4 tanks × 24 bolts each
        torque_spec_nm=410.0,
        notes="Tank skirt attachment; 24 bolts per tank circumference",
    ),
    InterfaceSpec(
        joint_name="propellant_feed_line_flange",
        part_a="Propellant tank outlet",
        part_b="Feed line pipe",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-A4-80",
        fastener_count=32,  # 4 tanks × 8 flange bolts
        seal_type="ASME-B16.20-2in-150-718",
        seal_count=4,
        torque_spec_nm=155.0,
        notes="Cryogenic propellant flanges with spiral-wound gaskets",
    ),

    # ── ECLSS (Life Support) ─────────────────────────────────────────────
    InterfaceSpec(
        joint_name="eclss_air_duct_to_bulkhead",
        part_a="ECLSS air distribution duct",
        part_b="Bulkhead penetration flange",
        connection_type="bolted",
        fastener_type="ISO-4014-M10x60-A4-80",
        fastener_count=40,  # 5 penetrations × 8 bolts each
        seal_type="AS568-150-EPDM",
        seal_count=5,
        torque_spec_nm=36.0,
        notes="Air ducts through bulkheads; EPDM seals for water-vapor compatibility",
    ),
    InterfaceSpec(
        joint_name="water_tank_to_frame",
        part_a="Potable water tank",
        part_b="ECLSS equipment rack",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-8.8",
        fastener_count=16,
        torque_spec_nm=210.0,
        notes="Water tank mounting; vibration-isolated with flexible hose connections",
    ),
    InterfaceSpec(
        joint_name="eclss_pipe_to_flange_general",
        part_a="ECLSS coolant/water piping",
        part_b="Equipment flanges (various)",
        connection_type="bolted",
        fastener_type="ISO-4014-M10x60-8.8",
        fastener_count=160,  # ~20 flanged connections × 8 bolts
        seal_type="AS568-150-FKM",
        seal_count=20,
        torque_spec_nm=49.0,
        notes="General ECLSS pipe-to-equipment connections with Viton O-rings",
    ),

    # ── Habitat Ring ─────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="habitat_ring_bearing_mount",
        part_a="Habitat ring rotor",
        part_b="Central hub (stator)",
        connection_type="bolted",
        fastener_type="ISO-4014-M24x120-A4-80",
        fastener_count=80,  # large-diameter bearing mounting ring
        torque_spec_nm=530.0,
        notes="Magnetic bearing stator bolted to central hub; critical alignment",
    ),
    InterfaceSpec(
        joint_name="habitat_ring_segment_splice",
        part_a="Ring segment A",
        part_b="Ring segment B",
        connection_type="bolted",
        fastener_type="ISO-4014-M20x100-8.8",
        fastener_count=192,  # 4 splice joints × 48 bolts each (torus segments)
        seal_type="AS568-395-FKM",
        seal_count=4,
        torque_spec_nm=410.0,
        notes="Pressurized torus segments spliced with dual O-ring seals",
    ),
    InterfaceSpec(
        joint_name="habitat_spoke_to_hub",
        part_a="Habitat spoke (x4)",
        part_b="Central hub node",
        connection_type="bolted",
        fastener_type="ISO-4014-M30x150-8.8",
        fastener_count=2400,  # 4 spokes × 600 M30 bolts each
        torque_spec_nm=1100.0,
        # Load: 59,000t torus × ω²R = 81 MN per spoke
        # M30-8.8 proof load = 314 kN. 600 bolts = 188 MN capacity. SF=2.3
        notes="Spokes transfer centripetal loads — sized for 81 MN/spoke (SF=2.3)",
    ),

    # ── Radiators ────────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="radiator_panel_to_deploy_hinge",
        part_a="Radiator panel (x8)",
        part_b="Deployment hinge assembly",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-8.8",
        fastener_count=64,  # 8 panels × 8 hinge bolts
        torque_spec_nm=210.0,
        notes="Radiator panels on deployable hinges; linear actuator driven",
    ),
    InterfaceSpec(
        joint_name="radiator_coolant_qd",
        part_a="Radiator coolant header",
        part_b="Main coolant loop",
        connection_type="sealed",
        fastener_type=None,
        fastener_count=0,
        seal_type="AS568-150-VMQ",
        seal_count=16,  # 8 panels × inlet + outlet
        notes="Quick-disconnect with silicone O-rings for radiator modularity",
    ),

    # ── Shield ───────────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="shield_panel_to_hull",
        part_a="Radiation shield panel (x32)",
        part_b="Hull outer surface studs",
        connection_type="bolted",
        fastener_type="ISO-4014-M10x60-8.8",
        fastener_count=512,  # 32 panels × 16 bolts each
        torque_spec_nm=49.0,
        notes="Shield panels bolted to hull standoffs; replaceable during maintenance",
    ),

    # ── Computing / Avionics ─────────────────────────────────────────────
    InterfaceSpec(
        joint_name="avionics_rack_to_hull",
        part_a="Avionics equipment rack (x4)",
        part_b="Hull interior rail",
        connection_type="bolted",
        fastener_type="ISO-4014-M10x60-8.8",
        fastener_count=64,  # 4 racks × 16 bolts
        torque_spec_nm=49.0,
        notes="Standard 19-inch rack mounting to hull rails (ECSS-E-ST-34C)",
    ),

    # ── Piping General ───────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="pipe_to_bulkhead_penetration",
        part_a="Coolant/water piping",
        part_b="Bulkhead penetration fitting",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-8.8",
        fastener_count=80,  # ~10 penetrations × 8 bolts
        seal_type="AS568-150-FKM",
        seal_count=10,
        torque_spec_nm=210.0,
        notes="All pressure-boundary bulkhead crossings; double O-ring",
    ),
    InterfaceSpec(
        joint_name="pipe_support_clamp",
        part_a="Piping (various)",
        part_b="Pipe support bracket",
        connection_type="clamped",
        fastener_type="ISO-4014-M10x60-8.8",
        fastener_count=200,  # distributed pipe supports throughout ship
        torque_spec_nm=49.0,
        notes="U-bolt pipe clamps every 1.5 m per ASME B31.3",
    ),

    # ── Docking ──────────────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="docking_ring_to_hull",
        part_a="Docking ring mechanism",
        part_b="Forward hull end ring",
        connection_type="bolted",
        fastener_type="ISO-4014-M24x120-A4-80",
        fastener_count=60,
        seal_type="CBM-SEAL-1000",
        seal_count=1,
        torque_spec_nm=530.0,
        notes="IDSS-compatible docking interface (NASA docking system heritage)",
    ),

    # ── Manufacturing / Workshop ─────────────────────────────────────────
    InterfaceSpec(
        joint_name="workshop_equipment_to_deck",
        part_a="Manufacturing equipment (CNC, 3D printer, etc.)",
        part_b="Workshop deck plate",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-8.8",
        fastener_count=48,  # ~6 machines × 8 bolts each
        torque_spec_nm=210.0,
        notes="Anti-vibration mounts with through-bolts to deck structure",
    ),

    # ── Electrical Harness ───────────────────────────────────────────────
    InterfaceSpec(
        joint_name="cable_tray_to_hull",
        part_a="Cable tray (x12 runs)",
        part_b="Hull interior brackets",
        connection_type="bolted",
        fastener_type="ISO-4014-M10x60-8.8",
        fastener_count=240,  # 12 runs × 20 brackets each
        torque_spec_nm=49.0,
        notes="Cable routing trays per ECSS-E-ST-34C wiring standards",
    ),

    # ── Thermal Control ──────────────────────────────────────────────────
    InterfaceSpec(
        joint_name="pump_to_coolant_manifold",
        part_a="Coolant pump (x4)",
        part_b="Coolant manifold flange",
        connection_type="bolted",
        fastener_type="ISO-4014-M16x80-A4-80",
        fastener_count=32,  # 4 pumps × 8 flange bolts
        seal_type="AS568-150-FKM",
        seal_count=8,  # inlet + outlet per pump
        torque_spec_nm=155.0,
        notes="Main coolant pumps with Viton face seals",
    ),
]


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def get_fastener_count() -> Dict[str, int]:
    """Total fastener count by fastener part number across all interfaces.

    Returns
    -------
    dict
        Mapping of fastener part_number -> total count.
    """
    counts: Dict[str, int] = {}
    for iface in SHIP_INTERFACES:
        if iface.fastener_type is not None and iface.fastener_count > 0:
            counts[iface.fastener_type] = (
                counts.get(iface.fastener_type, 0) + iface.fastener_count
            )
    return counts


def get_total_fastener_mass_kg() -> float:
    """Total mass of all fasteners across all ship interfaces [kg].

    Looks up each fastener's unit mass from the components database and
    multiplies by the count at each interface.

    Returns
    -------
    float
        Total fastener mass in kilograms.

    Raises
    ------
    KeyError
        If a fastener_type references a part_number not in COMPONENT_DATABASE.
    """
    total_g = 0.0
    for iface in SHIP_INTERFACES:
        if iface.fastener_type is not None and iface.fastener_count > 0:
            component = COMPONENT_DATABASE[iface.fastener_type]
            total_g += component.mass_g * iface.fastener_count
    return total_g / 1000.0


def get_bolt_installation_crew_hours() -> Dict[str, float]:
    """Estimated crew-hours to install all fasteners (Santos R6 PDR).

    Installation rates (NASA-STD-5020A Appendix B, ECSS-E-HB-32-23A Table 4):
      - Small bolts (M6-M12): ~5 min per bolt (includes torque, inspection)
      - Medium bolts (M16-M20): ~10 min
      - Large bolts (M24-M30): ~15 min
      - Rivets (NAS1398): ~2 min per rivet
      - Qualified inspection adds ~30% overhead

    Returns dict with: total_hours, installation_hours, inspection_hours,
    crew_shifts (at 8 hr × 20 crew = 160 crew-hr/shift).
    """
    install_minutes = 0.0
    for iface in SHIP_INTERFACES:
        if iface.fastener_type is None or iface.fastener_count == 0:
            continue
        ftype = iface.fastener_type
        if "M6" in ftype or "M8" in ftype or "M10" in ftype or "M12" in ftype:
            rate = 5.0   # min per bolt
        elif "M16" in ftype or "M20" in ftype:
            rate = 10.0
        elif "M24" in ftype or "M30" in ftype or "M36" in ftype:
            rate = 15.0
        elif "NAS1398" in ftype or "rivet" in ftype.lower():
            rate = 2.0
        else:
            rate = 10.0  # Default medium
        install_minutes += iface.fastener_count * rate

    install_hours = install_minutes / 60.0
    inspection_hours = install_hours * 0.30
    total_hours = install_hours + inspection_hours
    crew_shift_hours = 20 * 8  # 20 crew × 8 hr shift

    return {
        "total_hours": total_hours,
        "installation_hours": install_hours,
        "inspection_hours": inspection_hours,
        "crew_shifts": total_hours / crew_shift_hours,
        "calendar_days_20_crew": total_hours / crew_shift_hours,
    }


def get_seal_count() -> Dict[str, int]:
    """Total seal/gasket count by seal part number across all interfaces.

    Returns
    -------
    dict
        Mapping of seal part_number -> total count.
    """
    counts: Dict[str, int] = {}
    for iface in SHIP_INTERFACES:
        if iface.seal_type is not None and iface.seal_count > 0:
            counts[iface.seal_type] = (
                counts.get(iface.seal_type, 0) + iface.seal_count
            )
    return counts


def get_total_seal_mass_kg() -> float:
    """Total mass of all seals and gaskets [kg]."""
    total_g = 0.0
    for iface in SHIP_INTERFACES:
        if iface.seal_type is not None and iface.seal_count > 0:
            component = COMPONENT_DATABASE[iface.seal_type]
            total_g += component.mass_g * iface.seal_count
    return total_g / 1000.0


def get_interface_by_name(joint_name: str) -> InterfaceSpec:
    """Look up an interface by its joint name.

    Raises
    ------
    KeyError
        If the joint name is not found.
    """
    for iface in SHIP_INTERFACES:
        if iface.joint_name == joint_name:
            return iface
    raise KeyError(f"Interface not found: {joint_name}")


def get_interfaces_for_part(part_name: str) -> List[InterfaceSpec]:
    """Return all interfaces where a given part appears (as part_a or part_b)."""
    return [
        iface for iface in SHIP_INTERFACES
        if part_name in iface.part_a or part_name in iface.part_b
    ]
