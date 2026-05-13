"""Ship Part Manifest — Bill of Materials for every structural part.

Maps each physical component of the ARIA generation ship to a material
from :mod:`aria.digital_twin.materials.material_db`, with parametric
dimensions and computed mass.

The 36-part manifest covers all subsystems: structure, shield, power,
propulsion, ECLSS, habitat ring, radiators, computing, and manufacturing.

References
----------
Long (2012) "Deep Space Propulsion" Springer, Ch.5 mass budgets.
Matloff (2005) "Deep Space Probes" Springer-Praxis.
NASA-SP-8007 Buckling criteria for thin-walled cylinders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.digital_twin.materials.material_db import MATERIAL_DATABASE, get_material


@dataclass
class PartEntry:
    """A single part in the ship Bill of Materials.

    Parameters
    ----------
    name : str
        Human-readable part name (unique within manifest).
    subsystem : str
        Functional subsystem (structure, shield, power, propulsion,
        eclss, habitat_ring, radiators, computing, manufacturing).
    quantity : int
        Number of identical copies.
    material_name : str
        Key into :data:`MATERIAL_DATABASE`.
    dimensions_m : dict
        Parametric dimensions.  Acceptable key sets:
          - width, height, depth (rectangular)
          - radius, length (cylinder / sphere)
          - wall_thickness (hollow shells)
    mass_kg : float
        Computed mass of ONE instance [kg].  Auto-computed from
        dimensions x density if not overridden.
    has_3d_geometry : bool
        True if a CadQuery model exists for this part.
    """

    name: str
    subsystem: str
    quantity: int
    material_name: str
    dimensions_m: Dict[str, float]
    mass_kg: float
    has_3d_geometry: bool = False


def _cylinder_shell_mass(
    radius: float,
    length: float,
    wall_thickness: float,
    density: float,
) -> float:
    """Mass of a thin-walled cylinder [kg]."""
    r_outer = radius
    r_inner = radius - wall_thickness
    volume = math.pi * (r_outer**2 - r_inner**2) * length
    return volume * density


def _cylinder_solid_mass(radius: float, length: float, density: float) -> float:
    """Mass of a solid cylinder [kg]."""
    return math.pi * radius**2 * length * density


def _sphere_shell_mass(
    radius: float,
    wall_thickness: float,
    density: float,
) -> float:
    """Mass of a thin-walled sphere [kg]."""
    r_o = radius
    r_i = radius - wall_thickness
    volume = (4.0 / 3.0) * math.pi * (r_o**3 - r_i**3)
    return volume * density


def _hemisphere_shell_mass(
    radius: float,
    wall_thickness: float,
    density: float,
) -> float:
    """Mass of a thin-walled hemisphere [kg]."""
    return _sphere_shell_mass(radius, wall_thickness, density) / 2.0


def _torus_shell_mass(
    major_radius: float,
    minor_radius: float,
    wall_thickness: float,
    density: float,
) -> float:
    """Mass of a thin-walled torus [kg]."""
    # Surface area of torus = 4 * pi^2 * R * r
    surface = 4.0 * math.pi**2 * major_radius * minor_radius
    volume = surface * wall_thickness
    return volume * density


def _slab_mass(
    width: float,
    height: float,
    depth: float,
    density: float,
) -> float:
    """Mass of a rectangular slab [kg]."""
    return width * height * depth * density


# ---------------------------------------------------------------------------
# The canonical 36-part manifest
# ---------------------------------------------------------------------------

def _build_manifest() -> List[PartEntry]:
    """Construct the 36-part ship manifest with computed masses."""
    parts: List[PartEntry] = []

    # Helper: resolve density
    def rho(mat: str) -> float:
        return get_material(mat).density_kg_m3

    # ── STRUCTURE (parts 1-6) ────────────────────────────────────────

    # 1. Pressure hull — cylindrical shell, Ti-6Al-4V.
    # Read from ShipParameters so manifest stays consistent with the
    # mass_budget. Previously hull_L was hardcoded at 2840 m (the length
    # for a 20 mm wall) but hull_t was 80 mm, producing a phantom 79.6 Mt
    # hull mass — 4× the budget's 20 Mt. Now both come from the same
    # parametric source.
    from aria.digital_twin.parameters import ShipParameters as _SP
    _params = _SP()
    hull_r = _params.hull_radius_m
    hull_t = _params.hull_wall_thickness_m
    hull_L = _params.hull_length_m
    parts.append(PartEntry(
        name="Pressure Hull",
        subsystem="structure",
        quantity=1,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": hull_r, "length": hull_L, "wall_thickness": hull_t},
        mass_kg=_cylinder_shell_mass(hull_r, hull_L, hull_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 2. Forward end cap — hemisphere
    parts.append(PartEntry(
        name="Forward End Cap",
        subsystem="structure",
        quantity=1,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": hull_r, "wall_thickness": hull_t},
        mass_kg=_hemisphere_shell_mass(hull_r, hull_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 3. Aft end cap — hemisphere
    parts.append(PartEntry(
        name="Aft End Cap",
        subsystem="structure",
        quantity=1,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": hull_r, "wall_thickness": hull_t},
        mass_kg=_hemisphere_shell_mass(hull_r, hull_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 4. Internal bulkheads — disc plates every 50 m
    n_bulkheads = int(hull_L / 50)
    bulkhead_t = 0.010  # 10 mm
    r_inner = hull_r - hull_t
    parts.append(PartEntry(
        name="Internal Bulkheads",
        subsystem="structure",
        quantity=n_bulkheads,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": r_inner, "depth": bulkhead_t},
        mass_kg=_cylinder_solid_mass(r_inner, bulkhead_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 5. Ring frames — stiffening rings every 10 m
    # Dimensions match mass_budget.py (NASA-SP-8007 §5.2, Chen R6 audit)
    n_frames = int(hull_L / 10)
    frame_depth = 0.20  # 200 mm annular ring width (mass_budget.py)
    frame_thickness = 0.05  # 50 mm radial thickness (mass_budget.py)
    parts.append(PartEntry(
        name="Ring Frames",
        subsystem="structure",
        quantity=n_frames,
        material_name="Ti-6Al-4V",
        dimensions_m={
            "radius": r_inner,
            "depth": frame_depth,
            "wall_thickness": frame_thickness,
        },
        mass_kg=2.0 * math.pi * r_inner * frame_depth * frame_thickness * rho("Ti-6Al-4V"),
        has_3d_geometry=False,
    ))

    # 6. Longitudinal stringers — 12 stringers full length
    # Dimensions match mass_budget.py (O'Neill 1977 Ch.4, Chen R6 audit)
    stringer_w = 0.10  # 100 mm bar width (mass_budget.py)
    stringer_h = 0.05  # 50 mm bar thickness (mass_budget.py)
    parts.append(PartEntry(
        name="Longitudinal Stringers",
        subsystem="structure",
        quantity=12,
        material_name="Ti-6Al-4V",
        dimensions_m={"width": stringer_w, "height": stringer_h, "depth": hull_L},
        mass_kg=_slab_mass(stringer_w, stringer_h, hull_L, rho("Ti-6Al-4V")),
        has_3d_geometry=False,
    ))

    # ── SHIELD (parts 7-12) ──────────────────────────────────────────

    # 7. Ablation ice shield — thick disc in front
    # Read actual thickness from the shield layer named "ablation_ice"
    ice_t = next((l.thickness_m for l in _params.shield_layers
                  if "ablation" in l.name or "ice" in l.name), 5.45)
    ice_r = hull_r + 2.0  # extends beyond hull radius
    parts.append(PartEntry(
        name="Ablation Ice Shield",
        subsystem="shield",
        quantity=1,
        material_name="Water-Ice",
        dimensions_m={"radius": ice_r, "depth": ice_t},
        mass_kg=_cylinder_solid_mass(ice_r, ice_t, rho("Water-Ice")),
        has_3d_geometry=True,
    ))

    # 8. Whipple shield bumper — Kevlar-49 fabric layer
    whipple_t = 0.005  # 5 mm aramid
    whipple_area = math.pi * hull_r**2  # forward-facing disc
    parts.append(PartEntry(
        name="Whipple Shield Bumper",
        subsystem="shield",
        quantity=1,
        material_name="Kevlar-49",
        dimensions_m={"radius": hull_r, "depth": whipple_t},
        mass_kg=whipple_area * whipple_t * rho("Kevlar-49"),
        has_3d_geometry=True,
    ))

    # 9. Whipple shield backstop — Al-7075-T6 plate
    backstop_t = 0.002  # 2 mm aluminium
    parts.append(PartEntry(
        name="Whipple Shield Backstop",
        subsystem="shield",
        quantity=1,
        material_name="Al-7075-T6",
        dimensions_m={"radius": hull_r, "depth": backstop_t},
        mass_kg=whipple_area * backstop_t * rho("Al-7075-T6"),
        has_3d_geometry=True,
    ))

    # 10. Magnetic deflector coil — MgB2 superconductor
    coil_r = hull_r + 3.0  # outside hull
    coil_cross_r = 0.20  # 200 mm cross-section radius
    coil_length = 2.0 * math.pi * coil_r  # circumference
    parts.append(PartEntry(
        name="Magnetic Deflector Coil",
        subsystem="shield",
        quantity=4,  # 4 coils around ship
        material_name="MgB2",
        dimensions_m={"radius": coil_cross_r, "length": coil_length},
        mass_kg=_cylinder_solid_mass(coil_cross_r, coil_length, rho("MgB2")),
        has_3d_geometry=True,
    ))

    # 11. Electrostatic grid — Tungsten mesh
    grid_r = hull_r + 1.0
    grid_t = 0.001  # 1 mm mesh
    grid_length = 10.0  # 10 m forward section
    parts.append(PartEntry(
        name="Electrostatic Grid",
        subsystem="shield",
        quantity=1,
        material_name="Tungsten",
        dimensions_m={"radius": grid_r, "length": grid_length, "wall_thickness": grid_t},
        # Mesh is ~10% fill factor, so multiply shell mass by 0.1
        mass_kg=_cylinder_shell_mass(grid_r, grid_length, grid_t, rho("Tungsten")) * 0.10,
        has_3d_geometry=True,
    ))

    # 12. UHMWPE radiation shield — polyethylene blanket around habitable zones
    rad_shield_t = 0.10  # 100 mm thick
    rad_shield_L = 200.0  # covers 200 m habitable section
    parts.append(PartEntry(
        name="UHMWPE Radiation Blanket",
        subsystem="shield",
        quantity=1,
        material_name="UHMWPE",
        dimensions_m={"radius": hull_r, "length": rad_shield_L, "wall_thickness": rad_shield_t},
        mass_kg=_cylinder_shell_mass(hull_r, rad_shield_L, rad_shield_t, rho("UHMWPE")),
        has_3d_geometry=False,
    ))

    # ── POWER / REACTOR (parts 13-19) ────────────────────────────────

    # 13. Fusion reactor vessel — EUROFER97
    reactor_r = _params.reactor_radius_m
    reactor_L = _params.reactor_length_m
    reactor_t = 0.060  # 60 mm
    parts.append(PartEntry(
        name="Fusion Reactor Vessel",
        subsystem="power",
        quantity=1,
        material_name="EUROFER97",
        dimensions_m={"radius": reactor_r, "length": reactor_L, "wall_thickness": reactor_t},
        mass_kg=_cylinder_shell_mass(reactor_r, reactor_L, reactor_t, rho("EUROFER97")),
        has_3d_geometry=True,
    ))

    # 14. Plasma-facing tiles — HfB2 UHTC
    tile_w = 0.05  # 50 mm square tiles
    tile_h = 0.05
    tile_d = 0.01  # 10 mm thick
    first_wall_area = 4.0 * math.pi * reactor_r * 1.0  # ~38 m^2
    n_tiles = int(first_wall_area / (tile_w * tile_h))
    parts.append(PartEntry(
        name="Plasma-Facing Tiles",
        subsystem="power",
        quantity=n_tiles,
        material_name="HfB2",
        dimensions_m={"width": tile_w, "height": tile_h, "depth": tile_d},
        mass_kg=_slab_mass(tile_w, tile_h, tile_d, rho("HfB2")),
        has_3d_geometry=False,
    ))

    # 15. Breeding blanket — Li2TiO3 ceramic pebble bed
    blanket_r_outer = 3.5  # 0.5 m thick shell
    blanket_r_inner = 3.0
    blanket_L = 8.0
    parts.append(PartEntry(
        name="Tritium Breeding Blanket",
        subsystem="power",
        quantity=1,
        material_name="Li2TiO3",
        dimensions_m={
            "radius": blanket_r_outer,
            "length": blanket_L,
            "wall_thickness": blanket_r_outer - blanket_r_inner,
        },
        # Pebble bed packing fraction ~0.64 (random close-packing)
        mass_kg=_cylinder_shell_mass(
            blanket_r_outer, blanket_L,
            blanket_r_outer - blanket_r_inner, rho("Li2TiO3"),
        ) * 0.64,  # packing fraction (German & Park 2008)
        has_3d_geometry=True,
    ))

    # 16. Neutron shield — B4C layer around reactor
    b4c_r = 4.0
    b4c_t = 0.30  # 300 mm
    b4c_L = 10.0
    parts.append(PartEntry(
        name="Neutron Shield (B4C)",
        subsystem="power",
        quantity=1,
        material_name="B4C",
        dimensions_m={"radius": b4c_r, "length": b4c_L, "wall_thickness": b4c_t},
        mass_kg=_cylinder_shell_mass(b4c_r, b4c_L, b4c_t, rho("B4C")),
        has_3d_geometry=True,
    ))

    # 17. Biological shield — borated concrete around reactor bay
    bio_r = 5.0
    bio_t = 1.0  # 1 m thick
    bio_L = 12.0
    parts.append(PartEntry(
        name="Biological Shield",
        subsystem="power",
        quantity=1,
        material_name="Borated-Concrete",
        dimensions_m={"radius": bio_r, "length": bio_L, "wall_thickness": bio_t},
        mass_kg=_cylinder_shell_mass(bio_r, bio_L, bio_t, rho("Borated-Concrete")),
        has_3d_geometry=False,
    ))

    # 18. Reactor coolant piping — SS-316L
    pipe_r = 0.15  # 150 mm radius
    pipe_t = 0.008  # 8 mm wall
    pipe_L = 500.0  # total piping run
    parts.append(PartEntry(
        name="Reactor Coolant Piping",
        subsystem="power",
        quantity=8,  # 8 primary loops
        material_name="SS-316L",
        dimensions_m={"radius": pipe_r, "length": pipe_L, "wall_thickness": pipe_t},
        mass_kg=_cylinder_shell_mass(pipe_r, pipe_L, pipe_t, rho("SS-316L")),
        has_3d_geometry=False,
    ))

    # 19. Reactor magnet casing — Inconel-718 high-temp superalloy
    mag_r = 2.0
    mag_t = 0.025  # 25 mm
    mag_L = 6.0
    parts.append(PartEntry(
        name="Reactor Magnet Casing",
        subsystem="power",
        quantity=12,  # 12 toroidal field coil casings
        material_name="Inconel-718",
        dimensions_m={"radius": mag_r, "length": mag_L, "wall_thickness": mag_t},
        mass_kg=_cylinder_shell_mass(mag_r, mag_L, mag_t, rho("Inconel-718")),
        has_3d_geometry=False,
    ))

    # ── PROPULSION (parts 20-22) ─────────────────────────────────────

    # 20. Magnetic nozzle — Inconel-718
    nozzle_r = 2.5
    nozzle_t = 0.030  # 30 mm
    nozzle_L = 8.0
    parts.append(PartEntry(
        name="Magnetic Nozzle",
        subsystem="propulsion",
        quantity=1,
        material_name="Inconel-718",
        dimensions_m={"radius": nozzle_r, "length": nozzle_L, "wall_thickness": nozzle_t},
        mass_kg=_cylinder_shell_mass(nozzle_r, nozzle_L, nozzle_t, rho("Inconel-718")),
        has_3d_geometry=True,
    ))

    # 21. D-T fuel tanks — Ti-6Al-4V cryogenic spheres
    # Petrov (Cryogenics PDR): switched from SS-316L to Ti-6Al-4V. Austenitic
    # stainless (316L) suffers hydrogen embrittlement at cryogenic temperatures
    # (San Marchi & Somerday, Sandia SAND2012-7321, "Technical Reference for
    # Hydrogen Compatibility of Materials"). Ti-6Al-4V ELI is qualified for
    # liquid-hydrogen tankage per NASA MSFC-STD-3029 and has flight heritage
    # on Centaur / Saturn-IVB LH2 tank bosses.
    fuel_tank_r = 5.0
    fuel_tank_t = 0.020  # 20 mm
    parts.append(PartEntry(
        name="D-T Fuel Tanks",
        subsystem="propulsion",
        quantity=4,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": fuel_tank_r, "wall_thickness": fuel_tank_t},
        mass_kg=_sphere_shell_mass(fuel_tank_r, fuel_tank_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 22. RCS thruster pods — Ti-6Al-4V
    rcs_r = 0.30
    rcs_L = 1.5
    rcs_t = 0.005  # 5 mm
    parts.append(PartEntry(
        name="RCS Thruster Pods",
        subsystem="propulsion",
        quantity=16,  # 4 quads of 4
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": rcs_r, "length": rcs_L, "wall_thickness": rcs_t},
        mass_kg=_cylinder_shell_mass(rcs_r, rcs_L, rcs_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # ── ECLSS (parts 23-25) ──────────────────────────────────────────

    # 23. Water storage tanks — SS-316L
    water_tank_r = 3.0
    water_tank_t = 0.012  # 12 mm
    parts.append(PartEntry(
        name="Water Storage Tanks",
        subsystem="eclss",
        quantity=4,
        material_name="SS-316L",
        dimensions_m={"radius": water_tank_r, "wall_thickness": water_tank_t},
        mass_kg=_sphere_shell_mass(water_tank_r, water_tank_t, rho("SS-316L")),
        has_3d_geometry=True,
    ))

    # 24. O2/N2 high-pressure gas tanks — Ti-6Al-4V
    gas_tank_r = 1.5
    gas_tank_t = 0.015  # 15 mm
    parts.append(PartEntry(
        name="Atmosphere Gas Tanks",
        subsystem="eclss",
        quantity=8,
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": gas_tank_r, "wall_thickness": gas_tank_t},
        mass_kg=_sphere_shell_mass(gas_tank_r, gas_tank_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 25. ECLSS piping network — SS-316L
    eclss_pipe_r = 0.05
    eclss_pipe_t = 0.003  # 3 mm
    eclss_pipe_L = 2000.0  # total run in ship
    parts.append(PartEntry(
        name="ECLSS Piping Network",
        subsystem="eclss",
        quantity=1,
        material_name="SS-316L",
        dimensions_m={"radius": eclss_pipe_r, "length": eclss_pipe_L, "wall_thickness": eclss_pipe_t},
        mass_kg=_cylinder_shell_mass(eclss_pipe_r, eclss_pipe_L, eclss_pipe_t, rho("SS-316L")),
        has_3d_geometry=False,
    ))

    # ── HABITAT RING (parts 26-28) ───────────────────────────────────

    # 26. Habitat torus shell — CNT-Composite
    # Read from params so manifest stays consistent with mass_budget.
    hab_R = _params.habitat_ring_radius_m
    hab_r = _params.habitat_ring_tube_radius_m
    hab_t = 0.020  # 20 mm CNT wall — ESTIMATE (same as mass_budget.py)
    parts.append(PartEntry(
        name="Habitat Torus Shell",
        subsystem="habitat_ring",
        quantity=1,
        material_name="CNT-Composite",
        dimensions_m={
            "radius": hab_R,
            "length": hab_r,  # minor radius stored as length
            "wall_thickness": hab_t,
        },
        mass_kg=_torus_shell_mass(hab_R, hab_r, hab_t, rho("CNT-Composite")),
        has_3d_geometry=True,
    ))

    # 27. Habitat spokes — CNT-Composite tubes connecting hull to ring
    spoke_r = _params.habitat_spoke_radius_m  # 2.0 m default
    spoke_t = 0.020  # 20 mm CNT wall — matches torus wall + mass_budget.py
    spoke_L = hab_R  # radial distance
    parts.append(PartEntry(
        name="Habitat Spokes",
        subsystem="habitat_ring",
        quantity=_params.habitat_spoke_count,
        material_name="CNT-Composite",
        dimensions_m={"radius": spoke_r, "length": spoke_L, "wall_thickness": spoke_t},
        mass_kg=_cylinder_shell_mass(spoke_r, spoke_L, spoke_t, rho("CNT-Composite")),
        has_3d_geometry=True,
    ))

    # 28. Habitat viewport windows — Fused Silica
    window_w = 1.0
    window_h = 0.8
    window_d = 0.040  # 40 mm triple-pane
    parts.append(PartEntry(
        name="Habitat Viewport Windows",
        subsystem="habitat_ring",
        quantity=200,
        material_name="Fused-Silica",
        dimensions_m={"width": window_w, "height": window_h, "depth": window_d},
        mass_kg=_slab_mass(window_w, window_h, window_d, rho("Fused-Silica")),
        has_3d_geometry=False,
    ))

    # ── RADIATORS (parts 29-30) ──────────────────────────────────────

    # 29. Radiator panels — Al-7075-T6 honeycomb with NaK tubes
    panel_w = 25.0
    panel_h = 20.0
    panel_d = 0.015  # 15 mm honeycomb
    parts.append(PartEntry(
        name="Thermal Radiator Panels",
        subsystem="radiators",
        quantity=100,
        material_name="Al-7075-T6",
        dimensions_m={"width": panel_w, "height": panel_h, "depth": panel_d},
        mass_kg=_slab_mass(panel_w, panel_h, panel_d, rho("Al-7075-T6")),
        has_3d_geometry=True,
    ))

    # 30. Radiator NaK coolant loops (piping mass only)
    nak_pipe_r = 0.025  # 25 mm
    nak_pipe_t = 0.003  # 3 mm SS wall
    nak_pipe_L = 100.0 * 50.0  # 100 panels x 50 m average loop
    parts.append(PartEntry(
        name="Radiator Coolant Piping",
        subsystem="radiators",
        quantity=1,
        material_name="SS-316L",
        dimensions_m={"radius": nak_pipe_r, "length": nak_pipe_L, "wall_thickness": nak_pipe_t},
        mass_kg=_cylinder_shell_mass(nak_pipe_r, nak_pipe_L, nak_pipe_t, rho("SS-316L")),
        has_3d_geometry=False,
    ))

    # ── THERMAL INSULATION (parts 31-32) ─────────────────────────────

    # 31. Aerogel insulation blankets — cryogenic zones
    aero_w = 1.0  # per-blanket
    aero_h = 1.0
    aero_d = 0.050  # 50 mm
    n_blankets = 5000  # coverage of cryogenic + reactor zones
    parts.append(PartEntry(
        name="Aerogel Insulation Blankets",
        subsystem="thermal",
        quantity=n_blankets,
        material_name="Aerogel",
        dimensions_m={"width": aero_w, "height": aero_h, "depth": aero_d},
        mass_kg=_slab_mass(aero_w, aero_h, aero_d, rho("Aerogel")),
        has_3d_geometry=False,
    ))

    # 32. MLI blankets — external hull insulation
    mli_w = 2.0
    mli_h = 2.0
    mli_d = 0.025  # 25 mm (20 layers typical)
    n_mli = 3000
    parts.append(PartEntry(
        name="MLI Insulation Blankets",
        subsystem="thermal",
        quantity=n_mli,
        material_name="MLI-Mylar",
        dimensions_m={"width": mli_w, "height": mli_h, "depth": mli_d},
        mass_kg=_slab_mass(mli_w, mli_h, mli_d, rho("MLI-Mylar")),
        has_3d_geometry=False,
    ))

    # ── SOLAR + OPTICS (parts 33-34) ─────────────────────────────────

    # 33. Backup solar panels — GaAs triple-junction cells
    solar_w = 5.0
    solar_h = 3.0
    solar_d = 0.003  # 3 mm cell + substrate
    parts.append(PartEntry(
        name="Backup Solar Panels",
        subsystem="power",
        quantity=4,
        material_name="GaAs",
        dimensions_m={"width": solar_w, "height": solar_h, "depth": solar_d},
        mass_kg=_slab_mass(solar_w, solar_h, solar_d, rho("GaAs")),
        has_3d_geometry=True,
    ))

    # 34. Sensor optical windows — Fused Silica
    sensor_r = 0.15  # 150 mm aperture
    sensor_d = 0.020  # 20 mm thick
    parts.append(PartEntry(
        name="Sensor Optical Windows",
        subsystem="computing",
        quantity=24,
        material_name="Fused-Silica",
        dimensions_m={"radius": sensor_r, "depth": sensor_d},
        mass_kg=math.pi * sensor_r**2 * sensor_d * rho("Fused-Silica"),
        has_3d_geometry=False,
    ))

    # ── DOCKING + ACCESS (parts 35-36) ───────────────────────────────

    # 35. Docking port rings — Ti-6Al-4V
    dock_r = 2.0
    dock_t = 0.025  # 25 mm
    dock_L = 3.0
    parts.append(PartEntry(
        name="Docking Port Assemblies",
        subsystem="structure",
        quantity=3,  # forward + 2 lateral
        material_name="Ti-6Al-4V",
        dimensions_m={"radius": dock_r, "length": dock_L, "wall_thickness": dock_t},
        mass_kg=_cylinder_shell_mass(dock_r, dock_L, dock_t, rho("Ti-6Al-4V")),
        has_3d_geometry=True,
    ))

    # 36. Cargo bay doors — Al-7075-T6
    cargo_w = 8.0
    cargo_h = 6.0
    cargo_d = 0.012  # 12 mm
    parts.append(PartEntry(
        name="Cargo Bay Doors",
        subsystem="structure",
        quantity=2,
        material_name="Al-7075-T6",
        dimensions_m={"width": cargo_w, "height": cargo_h, "depth": cargo_d},
        mass_kg=_slab_mass(cargo_w, cargo_h, cargo_d, rho("Al-7075-T6")),
        has_3d_geometry=True,
    ))

    return parts


# Pre-built singleton
SHIP_MANIFEST: List[PartEntry] = _build_manifest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_manifest() -> List[PartEntry]:
    """Return the complete 36-part Bill of Materials."""
    return list(SHIP_MANIFEST)


def get_mass_by_material() -> Dict[str, float]:
    """Return total mass [kg] per material across all parts.

    Each entry sums ``part.mass_kg * part.quantity`` for every part using
    that material.
    """
    totals: Dict[str, float] = {}
    for part in SHIP_MANIFEST:
        key = part.material_name
        totals[key] = totals.get(key, 0.0) + part.mass_kg * part.quantity
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def validate_manifest() -> List[str]:
    """Validate every manifest entry and return a list of errors (empty = OK).

    Checks
    ------
    1. Every ``material_name`` exists in :data:`MATERIAL_DATABASE`.
    2. Every ``mass_kg`` is positive.
    3. All dimensions are positive and physically reasonable (< 10 km).
    4. Quantity is at least 1.
    """
    errors: List[str] = []
    for part in SHIP_MANIFEST:
        # Material exists
        if part.material_name not in MATERIAL_DATABASE:
            errors.append(
                f"[{part.name}] Unknown material '{part.material_name}'"
            )

        # Mass positive
        if part.mass_kg <= 0:
            errors.append(
                f"[{part.name}] Non-positive mass: {part.mass_kg:.2f} kg"
            )

        # Quantity at least 1
        if part.quantity < 1:
            errors.append(
                f"[{part.name}] Invalid quantity: {part.quantity}"
            )

        # Dimensions positive and reasonable
        for dim_name, dim_val in part.dimensions_m.items():
            if dim_val <= 0:
                errors.append(
                    f"[{part.name}] Dimension '{dim_name}' is non-positive: {dim_val}"
                )
            if dim_val > 10_000:
                errors.append(
                    f"[{part.name}] Dimension '{dim_name}' exceeds 10 km: {dim_val}"
                )

    return errors
