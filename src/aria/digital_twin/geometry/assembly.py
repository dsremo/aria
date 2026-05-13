"""Top-level ship assembly — hull + all subsystems.

Combines all sub-geometries into a single CadQuery Assembly and
provides export helpers for STEP and glTF (via trimesh).
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.geometry.hull import create_hull
from aria.digital_twin.geometry.radiator_array import create_radiator_array
from aria.digital_twin.geometry.reactor_module import create_reactor_module
from aria.digital_twin.geometry.shield_stack import create_shield_stack
from aria.digital_twin.geometry.habitat_ring import create_habitat_ring
from aria.digital_twin.geometry.propulsion import create_propulsion
from aria.digital_twin.geometry.utility_systems import (
    create_fuel_tanks,
    create_water_tanks,
    create_gas_tanks,
    create_cargo_bay,
    create_docking_ports,
    create_solar_backup,
)


def assemble_ship(
    params: ShipParameters,
    include_habitat: bool = False,
    habitat_simplified: bool = True,
) -> cq.Assembly:
    """Assemble the complete ship from sub-components.

    Parameters
    ----------
    params : ShipParameters
        Parametric ship dimensions.
    include_habitat : bool
        Whether to include the habitat ring (default False because
        at 500 m major radius it is extremely large and slow to build).
    habitat_simplified : bool
        If including the habitat ring, use the lightweight wireframe
        representation (default True).

    Returns
    -------
    cq.Assembly
        Top-level assembly containing all subsystems.
    """
    ship = cq.Assembly(name="aria_generation_ship")

    length = params.hull_length_m

    # Hull — positioned at origin, extends along +Z
    hull_solid = create_hull(params)
    ship.add(hull_solid, name="hull", color=cq.Color(0.7, 0.7, 0.75, 1.0))

    # Radiator array — 10 representative panels
    radiators = create_radiator_array(params, n_panels=10)
    ship.add(radiators, name="radiators")

    # Reactor module — placed at aft end (z = 0), centered on reactor length
    reactor = create_reactor_module(params)
    reactor_z = params.reactor_length_m / 2.0  # center the reactor at aft
    ship.add(reactor, name="reactor_module",
             loc=cq.Location(cq.Vector(0, 0, reactor_z)),
             color=cq.Color(0.9, 0.3, 0.3, 1.0))

    # Shield stack — placed at forward end (z = hull_length)
    shields = create_shield_stack(params)
    ship.add(shields, name="shield_stack",
             loc=cq.Location(cq.Vector(0, 0, length)))

    # Propulsion — placed behind reactor (aft of z = 0)
    propulsion = create_propulsion(params)
    ship.add(propulsion, name="propulsion",
             loc=cq.Location(cq.Vector(0, 0, -5.0)))

    # Fuel tanks — D-T propellant in Storage zone E
    fuel_tanks = create_fuel_tanks(params, n_tanks=4)
    ship.add(fuel_tanks, name="fuel_tanks")

    # Water tanks — ECLSS reserves in Habitat zone B
    water_tanks = create_water_tanks(params)
    ship.add(water_tanks, name="water_tanks")

    # O2/N2 gas tanks — high-pressure spheres in Habitat zone B
    gas_tanks = create_gas_tanks(params)
    ship.add(gas_tanks, name="gas_tanks")

    # Cargo bay — logistics volume in Manufacturing zone D
    cargo_bay = create_cargo_bay(params)
    ship.add(cargo_bay, name="cargo_bay")

    # Docking ports — forward, lateral, and aft
    docking_ports = create_docking_ports(params)
    ship.add(docking_ports, name="docking_ports")

    # Solar backup array — 4 panels near Command zone A
    solar_backup = create_solar_backup(params)
    ship.add(solar_backup, name="solar_backup")

    # Habitat ring — at midpoint, optional due to extreme size
    if include_habitat:
        habitat = create_habitat_ring(params, simplified=habitat_simplified)
        ship.add(habitat, name="habitat_ring",
                 loc=cq.Location(cq.Vector(0, 0, length / 2.0)))

    return ship


def export_step(assembly: cq.Assembly, output_path: str | Path) -> Path:
    """Export the full assembly to STEP.

    Parameters
    ----------
    assembly : cq.Assembly
        The ship assembly.
    output_path : str | Path
        Destination .step file.

    Returns
    -------
    Path
        The written file.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    assembly.save(str(out), exportType="STEP")
    return out


def export_gltf(assembly: cq.Assembly, output_path: str | Path) -> Path:
    """Export the assembly to glTF via STL intermediary + trimesh.

    CadQuery does not natively export glTF, so we:
      1. Export each solid to an in-memory STL.
      2. Load them into a trimesh Scene.
      3. Export the scene as glTF (.glb).

    Parameters
    ----------
    assembly : cq.Assembly
        The ship assembly.
    output_path : str | Path
        Destination .glb / .gltf file.

    Returns
    -------
    Path
        The written file.

    Raises
    ------
    ImportError
        If trimesh is not installed.
    """
    import io
    import tempfile

    try:
        import trimesh
    except ImportError as exc:
        raise ImportError(
            "trimesh is required for glTF export. Install with: pip install trimesh"
        ) from exc

    scene = trimesh.Scene()

    # Walk the assembly tree and tessellate each shape
    for name, shape in _iter_shapes(assembly):
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=True) as tmp:
            cq.exporters.export(shape, tmp.name, exportType="STL")
            mesh = trimesh.load(tmp.name, file_type="stl")
            scene.add_geometry(mesh, node_name=name)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out))
    return out


def compute_center_of_mass(params: ShipParameters) -> dict:
    """Estimate the ship's center of mass along the thrust axis (Z).

    Subsystem mass fractions adapted from Larson & Wertz 1999
    *Space Mission Analysis and Design* 3rd ed (SMAD) Table 10-20
    "Typical subsystem mass breakdown for a long-duration crewed
    spacecraft". Real mass breakdown would come from a full FEM;
    the parametric fractions below are consistent with the SMAD
    range.

    Mass fractions (SMAD Table 10-20 midpoints adapted to a
    generation-ship architecture):
      - Hull structure: 20 % (SMAD 18-25 % structure)
      - Shield system:  15 % (generation-ship specific — ice +
        Whipple + magnets; adapted from SMAD 5 % thermal)
      - Reactor module:  8 % (SMAD 6-10 % power)
      - Propulsion:      7 % (SMAD 4-10 %)
      - Habitat ring:   30 % (SMAD 25-35 % for human-rated systems)
      - Payload/other:  20 % (SMAD residual category)

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    dict
        {"z_com_m": float, "on_thrust_axis": bool, "offset_m": float}
        - z_com_m: axial centre-of-mass position [m] from aft end
        - on_thrust_axis: True if CoM is within hull length bounds
        - offset_m: distance from hull geometric centre (L/2)
    """
    length = params.hull_length_m
    shield_t = params.total_shield_thickness_m
    reactor_l = params.reactor_length_m

    # Subsystem mass fractions and Z-centroid positions
    # fmt: off
    subsystems = [
        # (name,          mass_frac, z_centroid)
        ("hull",           0.20,     length / 2.0),                      # uniform cylinder, CoM at L/2
        ("shield",         0.15,     length + shield_t / 2.0),           # forward of hull
        ("reactor",        0.08,     reactor_l / 2.0),                   # aft end, centred on reactor
        ("propulsion",     0.07,     -5.0),                              # behind reactor (from assembly.py placement)
        ("habitat_ring",   0.30,     length / 2.0),                      # midship (from assembly.py placement)
        ("payload",        0.20,     length / 2.0),                      # distributed along hull
    ]
    # fmt: on

    total_mass_frac = sum(s[1] for s in subsystems)
    z_com = sum(s[1] * s[2] for s in subsystems) / total_mass_frac

    hull_mid = length / 2.0
    offset = z_com - hull_mid
    on_axis = 0.0 <= z_com <= length

    return {
        "z_com_m": round(z_com, 3),
        "on_thrust_axis": on_axis,
        "offset_m": round(offset, 3),
    }


def _iter_shapes(assy: cq.Assembly, prefix: str = ""):
    """Recursively yield (name, cq.Workplane) for every leaf shape."""
    name = prefix + (assy.name or "unnamed")
    if assy.obj is not None:
        yield name, cq.Workplane("XY").add(assy.obj)
    for child in assy.children:
        yield from _iter_shapes(child, prefix=name + "/")
