"""Internal compartment layout for the ARIA generation ship.

Divides the cylindrical hull into seven functional zones (A-G)
separated by Ti-6Al-4V pressure bulkheads. Each compartment is
a labeled cylinder section assembled into a CadQuery Assembly.

Internal bulkheads include a central airlock hatch cutout (R=1 m)
for pressure-equalization passage between zones (ISS CBM derived,
NASA-STD-3001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


# ── Zone definitions ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ZoneSpec:
    """Specification for a single compartment zone."""

    label: str
    name: str
    z_start_m: float
    z_end_m: float
    description: str

    @property
    def length_m(self) -> float:
        """Axial length of this zone [m]."""
        return self.z_end_m - self.z_start_m


# Zone layout as FRACTIONS of hull length (bow=0, stern=1).
# Proportional allocation adapts to any hull length.
_ZONE_FRACTIONS: list[tuple[str, str, float, float, str]] = [
    ("A", "Command",       0.00, 0.10, "Command, navigation, sensor array"),
    ("B", "Habitat",       0.10, 0.35, "Crew habitat: quarters, recreation, medical"),
    ("C", "Agriculture",   0.35, 0.55, "Hydroponics, grow chambers, food processing"),
    ("D", "Manufacturing", 0.55, 0.70, "3D printers, recycling, workshops"),
    ("E", "Storage",       0.70, 0.82, "Fuel tanks, spare parts, raw materials"),
    ("F", "Power",         0.82, 0.93, "Reactor, turbines, power distribution"),
    ("G", "Propulsion",    0.93, 1.00, "Engine room, fuel injectors, magsail"),
]

# Default ZONE_SPECS (computed for default hull length ~712m)
ZONE_SPECS: List[ZoneSpec] = [
    ZoneSpec(label, name, 0.0, 0.0, desc)  # Populated by get_zone_specs()
    for label, name, _, _, desc in _ZONE_FRACTIONS
]

# Bulkhead material and thickness
BULKHEAD_THICKNESS_M: float = 0.010  # 10 mm Ti-6Al-4V
BULKHEAD_MATERIAL: str = "Ti-6Al-4V"
AIRLOCK_HATCH_RADIUS_M: float = 1.0  # ISS CBM derived (NASA-STD-3001)


# ── Geometry builders ────────────────────────────────────────────────────

def _create_compartment_solid(
    inner_radius: float,
    length: float,
    z_offset: float,
) -> cq.Workplane:
    """Create a single cylindrical compartment volume.

    The cylinder is centered on the Z axis with its base at *z_offset*.

    Parameters
    ----------
    inner_radius : float
        Interior radius of the hull [m].
    length : float
        Axial length of the compartment [m].
    z_offset : float
        Z-coordinate of the compartment's bow-side face [m].

    Returns
    -------
    cq.Workplane
        Solid cylinder representing the compartment air volume.
    """
    return (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, z_offset))
        .circle(inner_radius)
        .extrude(length)
    )


def _create_bulkhead(
    inner_radius: float,
    thickness: float,
    z_position: float,
    hatch_radius: float = 0.0,
) -> cq.Workplane:
    """Create a pressure bulkhead disc at a given Z position.

    Parameters
    ----------
    inner_radius : float
        Radius of the bulkhead disc [m] (fills the hull cross-section).
    thickness : float
        Axial thickness of the bulkhead [m].
    z_position : float
        Z-coordinate where the bulkhead is placed [m].
    hatch_radius : float
        If > 0, cut a central circular hole of this radius to represent
        an airlock hatch penetration [m].

    Returns
    -------
    cq.Workplane
        Solid disc, optionally with a central hatch cutout.
    """
    disc = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, z_position))
        .circle(inner_radius)
        .extrude(thickness)
    )
    if hatch_radius > 0.0:
        hatch_hole = (
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(0, 0, z_position - 0.01))
            .circle(hatch_radius)
            .extrude(thickness + 0.02)  # slight overcut for clean boolean
        )
        disc = disc.cut(hatch_hole)
    return disc


def get_zone_specs(params: ShipParameters) -> List[ZoneSpec]:
    """Return zone specs scaled proportionally to actual hull length.

    Zones are defined as fractions of hull length, so they automatically
    adapt when hull dimensions change (e.g., wall thickness affects length).

    Parameters
    ----------
    params : ShipParameters
        Ship dimension dataclass.

    Returns
    -------
    list[ZoneSpec]
        Zone specifications with absolute Z coordinates.
    """
    hull_len = params.hull_length_m
    return [
        ZoneSpec(
            label=label,
            name=name,
            z_start_m=round(f_start * hull_len, 1),
            z_end_m=round(f_end * hull_len, 1),
            description=desc,
        )
        for label, name, f_start, f_end, desc in _ZONE_FRACTIONS
    ]


def create_compartments(params: ShipParameters) -> cq.Assembly:
    """Build the internal compartment layout as a CadQuery Assembly.

    Each zone is a labeled cylinder section.  Pressure bulkheads are
    placed at every zone boundary (including bow and stern faces).

    Parameters
    ----------
    params : ShipParameters
        Ship dimension dataclass.

    Returns
    -------
    cq.Assembly
        Assembly containing named compartment volumes and bulkheads.
    """
    r_in = params.hull_inner_radius_m
    zones = get_zone_specs(params)

    assy = cq.Assembly()

    # Collect unique bulkhead positions (zone boundaries)
    bulkhead_positions: list[float] = []

    for zone in zones:
        # Compartment air volume
        comp = _create_compartment_solid(r_in, zone.length_m, zone.z_start_m)
        assy.add(
            comp,
            name=f"zone_{zone.label}_{zone.name}",
            color=cq.Color(*_zone_color(zone.label)),
        )

        # Record boundary positions for bulkheads
        if zone.z_start_m not in bulkhead_positions:
            bulkhead_positions.append(zone.z_start_m)
        if zone.z_end_m not in bulkhead_positions:
            bulkhead_positions.append(zone.z_end_m)

    # Create bulkheads at each boundary.
    # Internal bulkheads (not at z=0 bow or z=hull_length stern) get a
    # central airlock hatch cutout for inter-zone passage.
    sorted_positions = sorted(bulkhead_positions)
    bow_z = sorted_positions[0] if sorted_positions else 0.0
    stern_z = sorted_positions[-1] if sorted_positions else params.hull_length_m
    for i, z_pos in enumerate(sorted_positions):
        is_internal = (z_pos != bow_z and z_pos != stern_z)
        hatch_r = AIRLOCK_HATCH_RADIUS_M if is_internal else 0.0
        bh = _create_bulkhead(r_in, BULKHEAD_THICKNESS_M, z_pos, hatch_r)
        assy.add(
            bh,
            name=f"bulkhead_{i:02d}_z{z_pos:.0f}",
            color=cq.Color(0.7, 0.7, 0.7, 1.0),  # metallic grey
        )

    return assy


def _zone_color(label: str) -> tuple[float, float, float, float]:
    """Return an RGBA colour tuple for a zone label."""
    palette = {
        "A": (0.2, 0.4, 0.9, 0.6),   # blue — command
        "B": (0.2, 0.8, 0.3, 0.6),   # green — habitat
        "C": (0.1, 0.7, 0.1, 0.6),   # dark green — agriculture
        "D": (0.9, 0.6, 0.1, 0.6),   # orange — manufacturing
        "E": (0.6, 0.4, 0.2, 0.6),   # brown — storage
        "F": (0.9, 0.2, 0.2, 0.6),   # red — power
        "G": (0.7, 0.2, 0.9, 0.6),   # purple — propulsion
    }
    return palette.get(label, (0.5, 0.5, 0.5, 0.6))
