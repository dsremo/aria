"""Parametric pressure hull geometry for the ARIA generation ship.

Creates the main cylindrical hull with hemispherical end caps,
forward and aft docking ports, internal structural stiffening
(longitudinal stringers, ring frames, spine truss), and airlock
hatch penetrations at each bulkhead, using CadQuery.

Structural references:
  - Ring-stiffened cylinder design follows Rotter & Schmidt (2013)
    "Buckling of Steel Shells: European Design Recommendations"
  - 12 longitudinal stringers at 30-deg spacing is standard for
    pressure-vessel stiffened-shell construction (NASA-SP-8007)
  - Spine truss concept from O'Neill colony structural studies
    (O'Neill 1977, "The High Frontier")
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


# ── Structural constants ────────────────────────────────────────────────

NUM_STRINGERS: int = 12
"""Number of longitudinal stringers around circumference (NASA-SP-8007)."""

STRINGER_WIDTH_M: float = 0.10
"""Stringer cross-section width [m] (Rotter & Schmidt 2013, Table 5.2)."""

STRINGER_HEIGHT_M: float = 0.05
"""Stringer cross-section height (radial) [m] (Rotter & Schmidt 2013)."""

RING_FRAME_WIDTH_M: float = 0.20
"""Ring frame axial width [m] (Rotter & Schmidt 2013, Ch. 6)."""

RING_FRAME_THICKNESS_M: float = 0.05
"""Ring frame radial thickness [m] (Rotter & Schmidt 2013, Ch. 6)."""

FULL_RING_SPACING_M: float = 10.0
"""Ring frame spacing in full-fidelity mode [m] (NASA-SP-8007)."""

SIMPLIFIED_RING_SPACING_M: float = 50.0
"""Ring frame spacing in simplified mode [m] — ~22 ribs for RAM efficiency."""

SPINE_OUTER_RADIUS_M: float = 1.0
"""Spine truss outer radius [m] (O'Neill 1977, structural spine concept)."""

SPINE_WALL_THICKNESS_M: float = 0.020
"""Spine truss wall thickness [m] — 20 mm Ti-6Al-4V (MMPDS-17)."""

AIRLOCK_HATCH_RADIUS_M: float = 1.0
"""Airlock hatch cutout radius [m] (ISS CBM derived, NASA-STD-3001)."""

# Bulkhead Z-positions for the 6 internal bulkheads (between 7 zones).
# Sourced from compartments.py zone boundaries.
INTERNAL_BULKHEAD_Z_POSITIONS: List[float] = [100, 300, 500, 700, 900, 1050]
"""Z-positions of inter-zone bulkheads [m] (from compartments.py)."""


# ── Main hull builder (original, kept for backward compatibility) ───────

def create_hull(params: ShipParameters) -> cq.Workplane:
    """Build the pressure hull as a CadQuery solid.

    Geometry:
      - Cylindrical shell (outer - inner) of length ``params.hull_length_m``
      - Two hemispherical end caps (forward / aft)
      - Forward docking port hole
      - Aft docking port hole

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    cq.Workplane
        The solid hull body on the XY workplane.
    """
    r_out = params.hull_radius_m
    r_in = params.hull_inner_radius_m
    length = params.hull_length_m
    dock_r = params.docking_port_radius_m

    # --- Outer cylinder ---------------------------------------------------
    outer_cyl = (
        cq.Workplane("XY")
        .circle(r_out)
        .extrude(length)
    )

    # --- Inner cylinder (cut to make a shell) -----------------------------
    inner_cyl = (
        cq.Workplane("XY")
        .circle(r_in)
        .extrude(length)
    )
    shell = outer_cyl.cut(inner_cyl)

    # --- Forward end cap (hemisphere at z = length) -----------------------
    fwd_cap_outer = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length))
        .sphere(r_out)
    )
    # Keep only the +Z half
    fwd_cut_box = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length - r_out))
        .box(r_out * 3, r_out * 3, r_out * 2, centered=True)
    )
    fwd_cap_outer = fwd_cap_outer.cut(fwd_cut_box)

    fwd_cap_inner = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length))
        .sphere(r_in)
    )
    fwd_cut_box_inner = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length - r_in))
        .box(r_in * 3, r_in * 3, r_in * 2, centered=True)
    )
    fwd_cap_inner = fwd_cap_inner.cut(fwd_cut_box_inner)

    fwd_cap = fwd_cap_outer.cut(fwd_cap_inner)

    # --- Aft end cap (hemisphere at z = 0) --------------------------------
    aft_cap_outer = (
        cq.Workplane("XY")
        .sphere(r_out)
    )
    aft_cut_box = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, r_out))
        .box(r_out * 3, r_out * 3, r_out * 2, centered=True)
    )
    aft_cap_outer = aft_cap_outer.cut(aft_cut_box)

    aft_cap_inner = (
        cq.Workplane("XY")
        .sphere(r_in)
    )
    aft_cut_box_inner = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, r_in))
        .box(r_in * 3, r_in * 3, r_in * 2, centered=True)
    )
    aft_cap_inner = aft_cap_inner.cut(aft_cut_box_inner)

    aft_cap = aft_cap_outer.cut(aft_cap_inner)

    # --- Combine shell + caps ---------------------------------------------
    hull = shell.union(fwd_cap).union(aft_cap)

    # --- Forward docking port (cylindrical hole through forward cap) ------
    dock_hole_fwd = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length))
        .circle(dock_r)
        .extrude(r_out * 1.5)
    )
    hull = hull.cut(dock_hole_fwd)

    # --- Aft docking port (cylindrical hole through aft cap) --------------
    dock_hole_aft = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, -r_out * 1.5))
        .circle(dock_r)
        .extrude(r_out * 1.5)
    )
    hull = hull.cut(dock_hole_aft)

    return hull


# ── Structural stiffening components ────────────────────────────────────

def _create_stringers_simplified(
    params: ShipParameters,
    n_stringers: int = NUM_STRINGERS,
) -> cq.Assembly:
    """Create longitudinal stringers as CadQuery wires (simplified mode).

    In simplified mode, each stringer is a thin wire (edge) running the
    full hull length on the inner surface. This avoids generating solid
    geometry for 12 long bars, keeping memory usage low.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions.
    n_stringers : int
        Number of stringers around circumference.

    Returns
    -------
    cq.Assembly
        Assembly of stringer wires.
    """
    r_place = params.hull_inner_radius_m  # on inner wall surface
    length = params.hull_length_m
    assy = cq.Assembly()

    for i in range(n_stringers):
        angle_deg = i * (360.0 / n_stringers)
        angle_rad = math.radians(angle_deg)
        x = r_place * math.cos(angle_rad)
        y = r_place * math.sin(angle_rad)

        # Use a very thin box (1 mm x 1 mm cross-section) as a lightweight
        # proxy for a wire, since CadQuery lineTo on transformed workplanes
        # can fail for axis-aligned lines.
        wire = (
            cq.Workplane("XY")
            .transformed(
                offset=cq.Vector(x, y, 0),
                rotate=cq.Vector(0, 0, angle_deg),
            )
            .rect(0.001, 0.001)
            .extrude(length)
        )
        assy.add(wire, name=f"stringer_{i:02d}_{angle_deg:.0f}deg")

    return assy


def _create_stringers_full(
    params: ShipParameters,
    n_stringers: int = NUM_STRINGERS,
) -> cq.Assembly:
    """Create longitudinal stringers as solid bars (full mode for FEA).

    Each stringer is a rectangular cross-section bar (0.10 m x 0.05 m)
    placed on the inner hull surface at equal angular spacing.

    WARNING: Slow for long hulls. Use simplified mode for visualization.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions.
    n_stringers : int
        Number of stringers around circumference.

    Returns
    -------
    cq.Assembly
        Assembly of solid stringer bars.
    """
    r_place = params.hull_inner_radius_m - (STRINGER_HEIGHT_M / 2.0)
    length = params.hull_length_m
    assy = cq.Assembly()

    for i in range(n_stringers):
        angle_deg = i * (360.0 / n_stringers)
        angle_rad = math.radians(angle_deg)
        x = r_place * math.cos(angle_rad)
        y = r_place * math.sin(angle_rad)

        bar = (
            cq.Workplane("XY")
            .transformed(
                offset=cq.Vector(x, y, 0),
                rotate=cq.Vector(0, 0, angle_deg),
            )
            .rect(STRINGER_WIDTH_M, STRINGER_HEIGHT_M)
            .extrude(length)
        )
        assy.add(
            bar,
            name=f"stringer_{i:02d}_{angle_deg:.0f}deg",
            color=cq.Color(0.8, 0.8, 0.2, 1.0),  # yellow
        )

    return assy


def _create_ring_frames(
    params: ShipParameters,
    spacing_m: float = SIMPLIFIED_RING_SPACING_M,
    solid: bool = False,
) -> cq.Assembly:
    """Create ring frames (ribs) along the hull length.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions.
    spacing_m : float
        Axial distance between ring frames [m].
    solid : bool
        If True, create solid annular discs (for FEA).
        If False, create thin wire circles (simplified).

    Returns
    -------
    cq.Assembly
        Assembly of ring frames.
    """
    r_outer = params.hull_inner_radius_m
    r_inner = r_outer - RING_FRAME_THICKNESS_M
    length = params.hull_length_m
    assy = cq.Assembly()

    # Place rings from spacing_m to (length - spacing_m) to avoid end caps
    n_rings = int(length / spacing_m) - 1
    positions = [spacing_m + i * spacing_m for i in range(n_rings)
                 if spacing_m + i * spacing_m < length]

    for idx, z_pos in enumerate(positions):
        if solid:
            ring = (
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(0, 0, z_pos))
                .circle(r_outer)
                .circle(r_inner)
                .extrude(RING_FRAME_WIDTH_M)
            )
        else:
            # Simplified: thin annular disc (1 mm thick for visibility)
            ring = (
                cq.Workplane("XY")
                .transformed(offset=cq.Vector(0, 0, z_pos))
                .circle(r_outer)
                .circle(r_inner)
                .extrude(0.001)  # 1 mm token thickness
            )
        assy.add(
            ring,
            name=f"ring_frame_{idx:03d}_z{z_pos:.0f}",
            color=cq.Color(0.6, 0.6, 0.6, 1.0),  # steel grey
        )

    return assy


def _create_spine_truss(params: ShipParameters) -> cq.Workplane:
    """Create the central spine truss as a hollow cylinder.

    The spine is the primary axial load path, running the full hull
    length along the Z axis at the center.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions.

    Returns
    -------
    cq.Workplane
        Solid hollow-cylinder spine.
    """
    length = params.hull_length_m
    r_outer = SPINE_OUTER_RADIUS_M
    r_inner = r_outer - SPINE_WALL_THICKNESS_M

    outer = (
        cq.Workplane("XY")
        .circle(r_outer)
        .extrude(length)
    )
    inner = (
        cq.Workplane("XY")
        .circle(r_inner)
        .extrude(length)
    )
    return outer.cut(inner)


def _create_airlock_cutouts(
    params: ShipParameters,
    bulkhead_z_positions: List[float] | None = None,
) -> List[cq.Workplane]:
    """Create cylindrical volumes for airlock hatch cutouts.

    Each cutout is a cylinder of radius AIRLOCK_HATCH_RADIUS_M that can
    be subtracted from a bulkhead disc to create the hatch penetration.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions.
    bulkhead_z_positions : list[float] | None
        Z-positions of internal bulkheads. Defaults to
        INTERNAL_BULKHEAD_Z_POSITIONS.

    Returns
    -------
    list[cq.Workplane]
        One cutout cylinder per bulkhead position.
    """
    if bulkhead_z_positions is None:
        bulkhead_z_positions = INTERNAL_BULKHEAD_Z_POSITIONS

    cutouts = []
    for z_pos in bulkhead_z_positions:
        hole = (
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(0, 0, z_pos - 0.1))
            .circle(AIRLOCK_HATCH_RADIUS_M)
            .extrude(0.2)  # slightly thicker than any bulkhead for clean cut
        )
        cutouts.append(hole)
    return cutouts


# ── Composite structural assembly ───────────────────────────────────────

def create_hull_structure(
    params: ShipParameters,
    simplified: bool = True,
) -> cq.Assembly:
    """Build the complete structurally-realistic hull assembly.

    Includes:
      - Pressure hull with forward + aft docking ports
      - Longitudinal stringers (12, evenly spaced)
      - Ring frames (ribs) at regular intervals
      - Central spine truss
      - Airlock hatch penetration markers at each internal bulkhead

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.
    simplified : bool
        If True (default), use wire stringers and widely-spaced thin
        ring frames (~22 ribs at 50 m intervals). RAM-friendly for
        16 GB workstations. If False, generate full solid geometry
        suitable for FEA meshing (~114 ribs at 10 m, solid stringers).

    Returns
    -------
    cq.Assembly
        Assembly with named sub-components.
    """
    assy = cq.Assembly()

    # 1. Pressure hull (with both docking ports)
    hull = create_hull(params)
    assy.add(hull, name="pressure_hull", color=cq.Color(0.7, 0.7, 0.8, 0.4))

    # 2. Stringers
    if simplified:
        stringers = _create_stringers_simplified(params)
    else:
        stringers = _create_stringers_full(params)
    assy.add(stringers, name="stringers")

    # 3. Ring frames
    if simplified:
        rings = _create_ring_frames(
            params, spacing_m=SIMPLIFIED_RING_SPACING_M, solid=False,
        )
    else:
        rings = _create_ring_frames(
            params, spacing_m=FULL_RING_SPACING_M, solid=True,
        )
    assy.add(rings, name="ring_frames")

    # 4. Spine truss
    spine = _create_spine_truss(params)
    assy.add(spine, name="spine_truss", color=cq.Color(0.9, 0.3, 0.1, 0.8))

    # 5. Airlock hatch markers (just small token cylinders for visualization)
    airlock_cutouts = _create_airlock_cutouts(params)
    airlock_assy = cq.Assembly()
    for idx, cutout in enumerate(airlock_cutouts):
        airlock_assy.add(
            cutout,
            name=f"airlock_hatch_{idx:02d}_z{INTERNAL_BULKHEAD_Z_POSITIONS[idx]:.0f}",
            color=cq.Color(1.0, 0.0, 0.0, 0.8),  # red for visibility
        )
    assy.add(airlock_assy, name="airlock_hatches")

    return assy


# ── Export helpers (unchanged) ──────────────────────────────────────────

def export_step(hull: cq.Workplane, output_path: str | Path) -> Path:
    """Export hull geometry to STEP format.

    Parameters
    ----------
    hull : cq.Workplane
        The hull solid.
    output_path : str | Path
        Destination file path (.step).

    Returns
    -------
    Path
        The written file path.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(hull, str(out), exportType="STEP")
    return out


def export_stl(hull: cq.Workplane, output_path: str | Path) -> Path:
    """Export hull geometry to STL format.

    Parameters
    ----------
    hull : cq.Workplane
        The hull solid.
    output_path : str | Path
        Destination file path (.stl).

    Returns
    -------
    Path
        The written file path.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(hull, str(out), exportType="STL")
    return out
