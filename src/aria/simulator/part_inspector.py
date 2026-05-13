"""Universal part-inspection API — snapshot any ship part's operational state.

Produces a :class:`PartSnapshot` for any ship part_id (the same strings
used as glTF mesh names). Snapshots combine three layers:

  1. **Static**  — dimensions, material, mass, position (parametric)
  2. **Design**  — role, subsystem, citation
  3. **Dynamic** — current health / temperature / power-draw / fault,
                   derived from the mission phase + startup state

This is the layer the UI talks to. A React panel can render "Reactor"
with all its numbers, then hop up to "Dependencies: power_distribution,
magnetic_nozzle" without the frontend needing to know anything about the
physics models beneath.

References
----------
Failure-rate data uses MIL-HDBK-217F / PRISM where available; otherwise
ESTIMATE-tagged conservative numbers.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from aria.digital_twin.dependency_graph import get_dependency_graph
from aria.digital_twin.parameters import ShipParameters
from aria.simulator.mission_phases import get_phase_controller
from aria.simulator.startup_sequence import StepStatus, get_startup_controller


# ── Data shape ──────────────────────────────────────────────────────

@dataclass
class PartSnapshot:
    """Complete operational state of a single ship part."""

    # Identity
    part_id: str
    name: str
    subsystem: str
    description: str

    # Geometry
    position_xyz_m: tuple[float, float, float]
    dimensions_m: Dict[str, float]
    mass_kg: float
    material: str

    # Operational state
    health_pct: float
    operational: bool
    temperature_k: Optional[float] = None
    power_draw_w: Optional[float] = None
    duty_cycle_pct: Optional[float] = None

    # Lifecycle
    mtbf_hours: Optional[float] = None
    mission_time_hours: float = 0.0
    failure_mode: Optional[str] = None

    # Interactions
    depends_on: List[str] = field(default_factory=list)
    feeds: List[str] = field(default_factory=list)

    # Citations
    sources: List[str] = field(default_factory=list)


# ── Part registry — static metadata for every part in the ship ───────

def _hull_stiffener_meta(i: int) -> dict:
    """Common metadata for hull_stiffener_0..4."""
    return {
        "name": f"Hull Ring Frame {i}",
        "subsystem": "structure",
        "description": "NASA-SP-8007 ring-frame stiffener welded circumferentially to the hull",
        "material": "Ti-6Al-4V",
        "dimensions_m": {"ring_radius": 16.4, "tube_radius": 1.51},
        "mass_kg": 4.8e4,       # ESTIMATE - 12 % wider than hull, 1.5 m tube × 2πR × ρ_Ti
        "mtbf_hours": 8.7e5,    # ~100 yr MTBF, MIL-HDBK-217F F1 aircraft structural
        "sources": ["NASA-SP-8007 (buckling)", "MIL-HDBK-217F"],
    }


def _fuel_tank_meta(i: int, label: str) -> dict:
    return {
        "name": f"Cryo Fuel Tank {label}",
        "subsystem": "propulsion",
        "description": "Cryogenic D/He-3 storage, multi-layer insulation, zero-boiloff cryocooler",
        "material": "Al-2219-T87",
        "dimensions_m": {"radius": 31.5, "length": 71.2},
        "mass_kg": 5.0e6,       # rough 0.5 % structural mass fraction of ship, Frisbee 2003
        "mtbf_hours": 4.4e5,    # cryocooler-limited, NASA TM-2015-218570
        "sources": ["Frisbee 2003 JPL/D-26963", "NASA-TM-2015-218570"],
    }


def _radiator_wing_meta(i: int) -> dict:
    return {
        "name": f"Heat-Rejection Wing {['+Y', '-Y'][i]}",
        "subsystem": "thermal",
        "description": "Potassium heat-pipe deployable radiator panel; rejects waste heat via σAT⁴",
        "material": "Al-6061-T6",
        "dimensions_m": {"width": 200.0, "height": 125.0, "thickness": 0.010},
        "mass_kg": 6.95e5,       # 200 × 125 × 0.010 × 2780 kg/m³
        "mtbf_hours": 2.6e5,    # MMOD-limited, NASA-STD-7009 shield design
        "sources": ["thermal_management.py", "Dunn & Reay 1994 Heat Pipes"],
    }


def _spoke_meta(i: int) -> dict:
    angle_deg = int(round(360.0 * i / 6))
    return {
        "name": f"Habitat Spoke {angle_deg}°",
        "subsystem": "structure",
        "description": "Radial truss transferring centrifugal load from ring rim to hull axis",
        "material": "Ti-6Al-4V",
        "dimensions_m": {"radius": 8.0, "length": 487.4},
        "mass_kg": 1.4e6,        # 2π × 8 × 487 × 7 mm × 4430 kg/m³
        "mtbf_hours": 1.3e6,     # structural, ~150 yr
        "sources": ["O'Neill 1977 High Frontier", "habitat_ring.py"],
    }


def _hab_module_meta(i: int) -> dict:
    angle_deg = round(360.0 * i / 24)
    return {
        "name": f"Crew Module {i + 1} ({angle_deg}°)",
        "subsystem": "habitat",
        "description": "Pressurised crew quarters pod on habitat ring outer rim. ~42 crew per module.",
        "material": "Al-Li-2195",
        "dimensions_m": {"axial": 14.0, "radial": 8.0, "tangential": 16.0},
        "mass_kg": 8.96e4,       # 14 × 16 × 8 × 50 kg/m³ aerospace avg
        "mtbf_hours": 4.4e5,     # ~50 yr pressurised shell life
        "sources": ["NASA-TP-2015-218570 BVAD §5"],
    }


def _shield_layer_meta(i: int) -> dict:
    layers = {
        0: ("Detection LIDAR",       0.10,  "sensor_array",      "Outermost warning layer — detects incoming micrometeoroids at 10 km range"),
        1: ("Active Plasma Deflector", 0.50, "plasma_deflector",  "Charged-particle steering via MW-class plasma"),
        2: ("Magnetic Deflector",    0.30,  "superconducting_coil","YBCO/Nb₃Sn dipole; bends high-Z GCR around ship"),
        3: ("Electrostatic Grid",    0.001, "tungsten_mesh",     "Sub-MeV electron trap; charged grid"),
        4: ("Ablation Ice Layer",    5.45,  "water_ice",         "Primary mass shield; 5.45 m water ice absorbs GCR"),
        5: ("Whipple Bumper",        0.209, "SiC_Kevlar_Al7075", "Fragments inbound debris on impact"),
        6: ("Structural Hull Layer", 0.006, "Ti-6Al-4V_HealTech","Innermost, self-healing polymer-coated Ti"),
    }
    layer_name, thickness, material, desc = layers[i]
    return {
        "name": f"Shield L{i} · {layer_name}",
        "subsystem": "shielding",
        "description": desc,
        "material": material,
        "dimensions_m": {"thickness": thickness, "area_m2": 2000.0},
        "mass_kg": thickness * 2000.0 * {"water_ice": 917.0}.get(material, 4430.0),
        "mtbf_hours": 1.75e6 if i == 4 else 3.5e5,     # ice ablates slowly; others shorter
        "sources": ["shield_system.py", "Cucinotta 2014 NASA/TP-2013-217375"],
    }


def _comm_antenna_meta(i: int) -> dict:
    return {
        "name": f"Ka-Band Comm Array {i + 1}",
        "subsystem": "comms",
        "description": "High-gain Ka-band dish for Deep Space Network uplink",
        "material": "Al-6061-T6",
        "dimensions_m": {"dish_radius": 5.0, "mast_length": 10.0},
        "mass_kg": 2200.0,
        "mtbf_hours": 5.3e5,   # NASA-STD-8739, communication systems
        "sources": ["NASA DSN Telecom Design Handbook 810-005"],
    }


def _docking_port_meta(i: int) -> dict:
    angle = ["45° (dorsal-port)", "135° (dorsal-stbd)", "225° (ventral-stbd)", "315° (ventral-port)"][i]
    return {
        "name": f"Docking Port {angle}",
        "subsystem": "structure",
        "description": "NASA-APAS-compatible airlock for crew transfer and cargo",
        "material": "Ti-6Al-4V",
        "dimensions_m": {"axial": 6.0, "radial": 6.0, "tangential": 6.0},
        "mass_kg": 1.0e4,
        "mtbf_hours": 2.6e5,
        "sources": ["APAS-89 docking system"],
    }


def _engine_bell_meta(i: int) -> dict:
    angles = ["45°", "135°", "225°", "315°"]
    return {
        "name": f"Attitude Thruster {angles[i]}",
        "subsystem": "propulsion",
        "description": "Secondary RCS nozzle — arc-jet xenon thruster for attitude + station-keeping",
        "material": "Inconel-718",
        "dimensions_m": {"bell_radius": 4.4, "length": 15.1},
        "mass_kg": 3600.0,
        "mtbf_hours": 1.0e5,   # hot hardware, ~12 yr
        "sources": ["Patterson 2007 NASA/TM-2014-218232 NEXT ion propulsion"],
    }


# Singletons the registry references
def _base_meta() -> dict:
    """Top-level parts that don't have an index suffix."""
    return {
        "hull_main": {
            "name": "Pressure Hull",
            "subsystem": "structure",
            "description": "712 m × 25 m Ti-6Al-4V pressure cylinder with 12 longitudinal stringers and 71 ring frames",
            "material": "Ti-6Al-4V",
            "dimensions_m": {"radius": 12.616, "length": 711.9, "wall_thickness": 0.080},
            "mass_kg": 2.0e7,
            "mtbf_hours": 2.2e6,
            "sources": ["NASA-SP-8007", "MMPDS-17"],
        },
        "habitat_ring": {
            "name": "Rotating Habitat Ring",
            "subsystem": "habitat",
            "description": "500 m-radius torus rotating at 1 RPM for 0.56 g simulated gravity; 24 living modules on outer rim",
            "material": "Al-Li-2195",
            "dimensions_m": {"major_radius": 500.0, "tube_radius": 20.0},
            "mass_kg": 5.5e7,
            "mtbf_hours": 8.8e5,
            "sources": ["O'Neill 1977", "Cramer 1985 (Coriolis tolerance)"],
        },
        "reactor_engine": {
            "name": "D/He-3 Fusion Reactor",
            "subsystem": "reactor",
            "description": "3 m × 6 m magnetic-confinement fusion chamber with Li-Pb breeding blanket + Be multiplier; ~100 MWth",
            "material": "EUROFER97",
            "dimensions_m": {"radius": 3.0, "length": 6.0},
            "mass_kg": 2.3e6,
            "mtbf_hours": 6.1e5,
            "sources": ["Abdou 2015 Fusion Eng. Des. 100", "ITER TBM Boccaccini 2016"],
        },
        "magnetic_nozzle": {
            "name": "Magnetic Nozzle",
            "subsystem": "propulsion",
            "description": "Plasma-exhaust flared bell with 4:1 expansion (3 m throat → 12 m exit)",
            "material": "EUROFER97",
            "dimensions_m": {"throat_radius": 3.0, "exit_radius": 12.0, "length": 60.0},
            "mass_kg": 1.2e5,
            "mtbf_hours": 3.5e5,
            "sources": ["Frisbee 2003 JPL/D-26963"],
        },
        "bow_sensor_ring": {
            "name": "Bow Sensor Array",
            "subsystem": "navigation",
            "description": "Navigation + LIDAR + comm antenna ring forward of bow shield stack",
            "material": "Al-6061-T6",
            "dimensions_m": {"major_radius": 25.2, "tube_radius": 1.0},
            "mass_kg": 4.5e4,
            "mtbf_hours": 4.4e5,
            "sources": ["comm_antenna + LIDAR datasheets"],
        },
    }


def _build_registry() -> Dict[str, dict]:
    """Static metadata for every ship part."""
    reg: Dict[str, dict] = dict(_base_meta())
    for i in range(5):  reg[f"hull_stiffener_{i}"] = _hull_stiffener_meta(i)
    for i, lab in enumerate(["A", "B", "C"]):
        reg[f"fuel_tank_{i}"] = _fuel_tank_meta(i, lab)
    for i in range(2):  reg[f"radiator_array_{i}"] = _radiator_wing_meta(i)
    for i in range(6):  reg[f"spoke_{i}"] = _spoke_meta(i)
    for i in range(24): reg[f"hab_module_{i}"] = _hab_module_meta(i)
    for i in range(7):  reg[f"shield_layer_{i}"] = _shield_layer_meta(i)
    for i in range(4):  reg[f"comm_antenna_{i}"] = _comm_antenna_meta(i)
    for i in range(4):  reg[f"docking_port_{i}"] = _docking_port_meta(i)
    for i in range(4):  reg[f"engine_bell_{i}"]  = _engine_bell_meta(i)
    return reg


_REGISTRY: Optional[Dict[str, dict]] = None


def _registry() -> Dict[str, dict]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


# ── Dynamic state computation ───────────────────────────────────────

def _position_xyz(part_id: str, params: ShipParameters) -> tuple[float, float, float]:
    """Best-guess nominal position for a part (for the UI to render a dot
    at the right place on the ship diagram). Matches export_gltf geometry."""
    hull_l = params.hull_length_m
    reactor_offset_x = -(hull_l / 2 + params.reactor_length_m / 2 + 0.5)
    if part_id == "hull_main":         return (0.0, 0.0, 0.0)
    if part_id == "habitat_ring":      return (0.0, 0.0, 0.0)
    if part_id == "reactor_engine":    return (reactor_offset_x, 0.0, 0.0)
    if part_id == "magnetic_nozzle":   return (reactor_offset_x - 30.0, 0.0, 0.0)
    if part_id == "bow_sensor_ring":   return (hull_l / 2 + 44.0, 0.0, 0.0)
    if part_id.startswith("hull_stiffener_"):
        i = int(part_id.split("_")[-1])
        fracs = [-2/5, -1/5, 0.0, 1/5, 2/5]
        return (hull_l * fracs[i], 0.0, 0.0)
    if part_id.startswith("fuel_tank_"):
        i = int(part_id.split("_")[-1])
        fracs = [-0.10, -0.26, -0.42]
        return (hull_l * fracs[i], 0.0, 0.0)
    if part_id.startswith("radiator_array_"):
        i = int(part_id.split("_")[-1])
        theta = math.radians([0.0, 180.0][i])
        r = params.hull_radius_m + 8.0 + 62.5
        return (-hull_l * 0.28, r * math.cos(theta), r * math.sin(theta))
    if part_id.startswith("spoke_"):
        i = int(part_id.split("_")[-1])
        theta = 2 * math.pi * i / 6
        return (0.0, 245.0 * math.cos(theta), 245.0 * math.sin(theta))
    if part_id.startswith("hab_module_"):
        i = int(part_id.split("_")[-1])
        theta = 2 * math.pi * i / 24
        r = params.habitat_ring_radius_m + params.habitat_ring_tube_radius_m + 4.0
        return (0.0, r * math.cos(theta), r * math.sin(theta))
    if part_id.startswith("shield_layer_"):
        i = int(part_id.split("_")[-1])
        n_from_inner = 6 - i
        return (hull_l / 2 + n_from_inner * 5.0 + 6.0, 0.0, 0.0)
    if part_id.startswith("comm_antenna_"):
        i = int(part_id.split("_")[-1])
        fracs = [-0.30, -0.05, 0.18, 0.38]
        return (hull_l * fracs[i], params.hull_radius_m + 6.0, 0.0)
    if part_id.startswith("docking_port_"):
        i = int(part_id.split("_")[-1])
        theta = math.radians(45.0 + i * 90.0)
        r = params.hull_radius_m + 3.0
        return (hull_l * 0.10, r * math.cos(theta), r * math.sin(theta))
    if part_id.startswith("engine_bell_"):
        i = int(part_id.split("_")[-1])
        theta = math.radians(45.0 + i * 90.0)
        r = params.hull_radius_m * 1.80
        return (reactor_offset_x - 4.0, r * math.cos(theta), r * math.sin(theta))
    return (0.0, 0.0, 0.0)


def _dynamic_state(part_id: str, meta: dict) -> dict:
    """Compute health / temperature / power / operational based on current
    startup state + mission phase. Derivations are rules-of-thumb, not
    full physics — the physics sim runs separately and publishes its own
    numbers; this is the lightweight inspection view."""
    phase = get_phase_controller()
    startup = get_startup_controller()
    phase_spec = phase.spec()

    subsystem = meta["subsystem"]
    operational = True
    health_pct = 100.0
    temperature_k: Optional[float] = None
    power_draw_w: Optional[float] = None
    duty_cycle_pct: Optional[float] = None
    failure_mode: Optional[str] = None

    # Subsystem-aware duty / power heuristics
    if subsystem == "reactor":
        duty = phase_spec.power_load_frac * 100.0
        temp = 300.0 + 1200.0 * phase_spec.power_load_frac   # 300 K cold → ~1500 K full plasma
        power = 1e8 * phase_spec.power_load_frac             # 100 MW thermal, duty-scaled
        duty_cycle_pct = duty
        temperature_k = round(temp, 1)
        power_draw_w = round(power, 0)
    elif subsystem == "thermal":
        duty_cycle_pct = phase_spec.thermal_load_frac * 100.0
        temperature_k = 500.0   # K-heatpipe hot-side per thermal_management.py
        power_draw_w = 50_000.0 * phase_spec.thermal_load_frac
    elif subsystem == "propulsion" and part_id == "magnetic_nozzle":
        duty_cycle_pct = phase_spec.main_thrust_frac * 100.0
        temperature_k = 1500.0 * phase_spec.main_thrust_frac + 300.0
        power_draw_w = 5e6 * phase_spec.main_thrust_frac
        if phase_spec.main_thrust_frac < 0.01:
            temperature_k = 290.0   # cold when off
            power_draw_w = 0.0
    elif subsystem == "propulsion" and part_id.startswith("engine_bell_"):
        duty_cycle_pct = phase_spec.rcs_load_frac * 100.0
        power_draw_w = 2e4 * phase_spec.rcs_load_frac
        temperature_k = 400.0 + 800.0 * phase_spec.rcs_load_frac
    elif subsystem == "propulsion" and part_id.startswith("fuel_tank_"):
        duty_cycle_pct = max(phase_spec.main_thrust_frac, phase_spec.rcs_load_frac) * 100.0
        temperature_k = 20.0    # cryo
        power_draw_w = 5000.0   # zero-boiloff cryocooler
    elif subsystem == "shielding":
        duty_cycle_pct = 100.0 if phase.current.value in ("boost", "cruise", "deceleration") else 50.0
        if part_id in ("shield_layer_1", "shield_layer_2"):
            power_draw_w = 1e6 * duty_cycle_pct / 100.0     # plasma + SC magnet
            temperature_k = 4.0 if part_id == "shield_layer_2" else 350.0
        elif part_id == "shield_layer_0":
            power_draw_w = 5000.0
            temperature_k = 280.0
    elif subsystem == "habitat":
        duty_cycle_pct = 100.0
        temperature_k = 293.15                   # 20 °C habitable
        power_draw_w = 10_000.0                  # ESTIMATE per module for ECLSS + lighting
    elif subsystem == "comms":
        duty_cycle_pct = 60.0                    # always-on telemetry
        temperature_k = 300.0
        power_draw_w = 2e4                        # 20 kW Ka-band transmit
    elif subsystem == "navigation":
        duty_cycle_pct = 100.0
        temperature_k = 270.0
        power_draw_w = 1500.0

    # Startup-aware operational flag: if any prerequisite startup step
    # hasn't succeeded yet, the part is NOT operational.
    prereq_map = {
        "reactor": "reactor_power_ramp",
        "thermal": "radiator_deploy",
        "habitat": "habitat_ring_spinup",
        "propulsion": "reactor_power_ramp",
        "comms": "comm_uplink",
        "navigation": "sensors_online",
    }
    req = prereq_map.get(subsystem)
    if req:
        step = startup.get_step(req)
        if step is None or step.status != StepStatus.SUCCESS:
            operational = False
            failure_mode = f"Waiting on startup step '{req}'"
            duty_cycle_pct = 0.0
            power_draw_w = 0.0

    # Aging: subtract tiny health for mission-time accumulation
    mission_time_hr = phase.elapsed_yr * 365.25 * 24.0
    if meta.get("mtbf_hours"):
        health_pct = round(100.0 * max(0.0, 1.0 - mission_time_hr / meta["mtbf_hours"]), 2)
        if health_pct < 70.0:
            failure_mode = failure_mode or "Approaching end-of-life; schedule service"
        # Past full MTBF → part is non-operational. Without this, the UI
        # shows a reactor at "Health 0 %" with "Status: ONLINE", which
        # is self-contradictory — an MTBF-exceeded part on a real ship
        # would have SCRAMed / been replaced. Mark non-operational so
        # operators + dependent-subsystem logic see the right state.
        if health_pct <= 0.01:
            operational = False
            failure_mode = failure_mode or "End-of-life: exceeded full MTBF — SCRAM/replace"
            # SCRAMed parts must also zero their duty + power output.
            # Reactor-offline with Duty=25%, Thermal P=25 MW was the old
            # UI contradiction — any downstream consumer (power bus,
            # thermal loop, UI panels) should see 0 not nominal.
            duty_cycle_pct = 0.0
            power_draw_w   = 0.0

    return {
        "operational": operational,
        "health_pct": health_pct,
        "temperature_k": temperature_k,
        "power_draw_w": power_draw_w,
        "duty_cycle_pct": duty_cycle_pct,
        "mission_time_hours": round(mission_time_hr, 1),
        "failure_mode": failure_mode,
    }


# ── Public API ──────────────────────────────────────────────────────

def list_parts() -> List[str]:
    """All known part IDs."""
    return sorted(_registry().keys())


def inspect_part(part_id: str) -> Optional[PartSnapshot]:
    """Return a full snapshot for `part_id` or None if unknown."""
    meta = _registry().get(part_id)
    if meta is None:
        return None
    params = ShipParameters()
    pos = _position_xyz(part_id, params)
    dyn = _dynamic_state(part_id, meta)
    graph = get_dependency_graph()
    deps_on = [e.dst for e in graph.depends_on(part_id)]
    fed_by  = [e.src for e in graph.feeds(part_id)]
    return PartSnapshot(
        part_id=part_id,
        name=meta["name"],
        subsystem=meta["subsystem"],
        description=meta["description"],
        position_xyz_m=pos,
        dimensions_m=meta["dimensions_m"],
        mass_kg=meta["mass_kg"],
        material=meta["material"],
        health_pct=dyn["health_pct"],
        operational=dyn["operational"],
        temperature_k=dyn["temperature_k"],
        power_draw_w=dyn["power_draw_w"],
        duty_cycle_pct=dyn["duty_cycle_pct"],
        mtbf_hours=meta.get("mtbf_hours"),
        mission_time_hours=dyn["mission_time_hours"],
        failure_mode=dyn["failure_mode"],
        depends_on=deps_on,
        feeds=fed_by,
        sources=meta.get("sources", []),
    )


def inspect_all() -> List[PartSnapshot]:
    return [s for s in (inspect_part(p) for p in list_parts()) if s is not None]


def snapshot_to_dict(s: PartSnapshot) -> dict:
    return asdict(s)
