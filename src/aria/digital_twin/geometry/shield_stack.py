"""Parametric forward shield stack geometry for the ARIA generation ship.

Creates a 7-layer shield stack aligned along the forward (+Z) axis.
Each layer is a disc or simplified solid stacked with gaps between them.
"""

from __future__ import annotations

import math

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def create_shield_stack(params: ShipParameters) -> cq.Assembly:
    """Build the 7-layer forward shield stack.

    Layers (bow to stern, stacked along +Z descending):
      1. Detection sensor disc (0.01 m)
      2. Laser ablation array disc with turret holes (0.05 m)
      3. Magnetic deflector coil — simplified torus
      4. Electrostatic grid disc (0.02 m)
      5. Ablation ice shield (shield_ice_thickness from params)
      6. Whipple bumper (bumper + standoff + backstop ~ 0.2 m)
      7. Structural hull (thin disc, 0.006 m — inner hull ref)

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    cq.Assembly
        Assembly of all shield layers.
    """
    assy = cq.Assembly(name="shield_stack")

    hull_r = params.hull_radius_m
    gap = 1.0  # 1 m gap between layers

    # Extract thicknesses from params.shield_layers
    layers = params.shield_layers
    # layers[0] = detection_lidar, [1] = active_deflection, ...

    # Build each layer as a simple disc at the correct Z offset
    z_cursor = 0.0  # start at the outermost (forward) position

    # Layer 1: Detection sensor disc
    t1 = layers[0].thickness_m  # 0.10 m
    disc1 = _make_disc(hull_r, t1)
    assy.add(disc1, name="L1_detection_sensors",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.2, 0.8, 0.2, 1.0))
    z_cursor -= t1 + gap

    # Layer 2: Laser ablation array (disc with 8 turret holes)
    t2 = layers[1].thickness_m  # 0.50 m
    disc2 = _make_ablation_array(hull_r, t2, n_turrets=8, turret_r=0.5)
    assy.add(disc2, name="L2_laser_ablation",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.8, 0.2, 0.2, 1.0))
    z_cursor -= t2 + gap

    # Layer 3: Magnetic deflector coil (simplified torus)
    t3 = layers[2].thickness_m  # 0.30 m
    coil_major_r = hull_r * 0.9  # slightly inside hull radius
    coil_tube_r = t3  # tube radius = layer thickness
    torus3 = _make_torus(coil_major_r, coil_tube_r)
    assy.add(torus3, name="L3_magnetic_deflector",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.2, 0.2, 0.9, 1.0))
    z_cursor -= coil_tube_r * 2 + gap

    # Layer 4: Electrostatic grid disc
    t4 = layers[3].thickness_m  # 0.001 m — use minimum 0.02 for visibility
    t4_vis = max(t4, 0.02)
    disc4 = _make_disc(hull_r, t4_vis)
    assy.add(disc4, name="L4_electrostatic_grid",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.9, 0.9, 0.1, 1.0))
    z_cursor -= t4_vis + gap

    # Layer 5: Ablation ice shield (thick disc)
    t5 = layers[4].thickness_m  # 5.45 m
    disc5 = _make_disc(hull_r, t5)
    assy.add(disc5, name="L5_ablation_ice",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.8, 0.9, 1.0, 0.8))
    z_cursor -= t5 + gap

    # Layer 6: Whipple bumper (bumper disc + standoff gap + backstop disc)
    t6 = layers[5].thickness_m  # 0.209 m
    disc6 = _make_whipple(hull_r, t6)
    assy.add(disc6, name="L6_whipple_bumper",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.6, 0.6, 0.6, 1.0))
    z_cursor -= t6 + gap

    # Layer 7: Structural hull disc (reference only — actual hull in hull.py)
    t7 = layers[6].thickness_m  # 0.006 m — use 0.02 for visibility
    t7_vis = max(t7, 0.02)
    disc7 = _make_disc(hull_r, t7_vis)
    assy.add(disc7, name="L7_structural_hull",
             loc=cq.Location(cq.Vector(0, 0, z_cursor)),
             color=cq.Color(0.5, 0.5, 0.55, 1.0))

    return assy


# ── Helper builders ──────────────────────────────────────────────────────

def _make_disc(radius: float, thickness: float) -> cq.Workplane:
    """Simple circular disc centered on origin."""
    return (
        cq.Workplane("XY")
        .circle(radius)
        .extrude(thickness)
    )


def _make_ablation_array(
    radius: float,
    thickness: float,
    n_turrets: int = 8,
    turret_r: float = 0.5,
) -> cq.Workplane:
    """Disc with holes for laser turrets arranged in a ring."""
    disc = _make_disc(radius, thickness)
    turret_ring_r = radius * 0.6
    for i in range(n_turrets):
        theta = 2.0 * math.pi * i / n_turrets
        x = turret_ring_r * math.cos(theta)
        y = turret_ring_r * math.sin(theta)
        hole = (
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(x, y, 0))
            .circle(turret_r)
            .extrude(thickness * 2)
        )
        disc = disc.cut(hole)
    return disc


def _make_torus(major_r: float, tube_r: float) -> cq.Workplane:
    """Torus via revolving a circle around an offset axis."""
    # Draw cross-section circle at (major_r, 0) in the XZ plane,
    # then revolve 360 degrees around the Z axis.
    torus = (
        cq.Workplane("XZ")
        .transformed(offset=cq.Vector(major_r, 0, 0))
        .circle(tube_r)
        .revolve(360, (0, 0, 0), (0, 0, 1))
    )
    return torus


def _make_whipple(radius: float, total_thickness: float) -> cq.Workplane:
    """Simplified Whipple shield: bumper + standoff + backstop as one disc.

    For visual simplicity we model the full thickness as a single disc.
    The internal bumper/standoff/backstop structure is not resolved.
    """
    return _make_disc(radius, total_thickness)
