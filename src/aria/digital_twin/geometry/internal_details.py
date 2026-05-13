"""Internal structural details — parts previously missing from geometry.

Adds: expansion joints, habitat internal decks, rotation bearing,
radiator deployment hinges, and coolant loop routing.

These complete the ship to 100% part coverage.
"""

from __future__ import annotations

import math

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def create_expansion_joints(params: ShipParameters) -> cq.Assembly:
    """Create thermal expansion joints along the hull.

    Bellows joints every 50m absorb 129mm of thermal growth (Ti-6Al-4V
    CTE=8.6×10⁻⁶/K at ΔT=300K). (MMPDS-17, Parker Hannifin catalog)

    Each joint is a short corrugated section (0.3m long gap in the hull).
    """
    assy = cq.Assembly()
    r = params.hull_radius_m
    spacing = params.thermal_expansion_joint_spacing_m
    n_joints = int(params.hull_length_m / spacing) - 1

    for i in range(n_joints):
        z = spacing * (i + 1)
        # Bellows: thin annular ring representing the expansion gap
        joint = (
            cq.Workplane("XY")
            .workplane(offset=z)
            .circle(r + 0.05)  # Slightly proud of hull
            .circle(r - 0.01)
            .extrude(0.3)  # 300mm bellows length
        )
        assy.add(joint, name=f"expansion_joint_{i}", color=cq.Color(0.8, 0.8, 0.0))

    return assy


def create_habitat_decks(params: ShipParameters, n_decks: int = 13) -> cq.Assembly:
    """Create internal deck floors for the habitat ring.

    13 decks at 3m spacing inside the 40m-diameter habitat tube.
    Each deck is a flat annular disc (simplified — no columns or walls).
    Deck thickness: 50mm composite floor panel.
    (NASA-STD-3001 Vol.2: 2.44m minimum ceiling height)
    """
    assy = cq.Assembly()
    r_tube = params.habitat_ring_tube_radius_m  # 20m
    R_major = params.habitat_ring_radius_m  # 500m
    deck_height = 3.0  # m (NASA-STD-3001)
    deck_thickness = 0.05  # 50mm floor panel

    for i in range(n_decks):
        # Decks run from bottom of tube upward
        y_offset = -r_tube + deck_height * (i + 0.5)
        if abs(y_offset) >= r_tube:
            continue

        # Chord width at this height: w = 2 × sqrt(r² - y²)
        chord_half = math.sqrt(max(0, r_tube**2 - y_offset**2))

        # Simplified: represent each deck as a thin box
        deck = (
            cq.Workplane("XY")
            .box(chord_half * 2, deck_thickness, 10.0)  # 10m section length
        )
        assy.add(deck, name=f"deck_{i+1}",
                 loc=cq.Location(cq.Vector(0, y_offset, 0)),
                 color=cq.Color(0.9, 0.85, 0.7))

    return assy


def create_rotation_bearing(params: ShipParameters) -> cq.Assembly:
    """Create the magnetic levitation bearing interface.

    The habitat ring rotates at 1 RPM relative to the non-rotating hull.
    A magnetic bearing (maglev) provides frictionless support.
    (Earnshaw 1842 theorem + active feedback control)

    Modeled as an annular ring at the spoke-hull junction.
    """
    assy = cq.Assembly()
    r_hull = params.hull_radius_m
    bearing_width = 0.5  # 500mm bearing race width
    bearing_height = 0.3  # 300mm bearing height

    for i in range(params.habitat_spoke_count):
        angle = i * (360 / params.habitat_spoke_count)
        # Bearing ring at hull surface where spoke connects
        bearing = (
            cq.Workplane("XY")
            .circle(r_hull + bearing_height)
            .circle(r_hull)
            .extrude(bearing_width)
        )
        z_pos = params.hull_length_m / 2  # Midship where spokes attach
        assy.add(bearing, name=f"bearing_{i}",
                 loc=cq.Location(cq.Vector(0, 0, z_pos)),
                 color=cq.Color(0.3, 0.7, 1.0))
        break  # One representative bearing (they overlap at same Z)

    return assy


def create_radiator_hinges(params: ShipParameters, n_hinges: int = 10) -> cq.Assembly:
    """Create radiator panel deployment hinge mechanisms.

    Each radiator panel attaches to the hull via a motorized hinge
    that deploys the panel to 45° from the hull surface.
    (Scaled from ISS SARJ solar array rotary joint, Messerschmid 2013)

    Simplified: small cylinder at panel base representing the hinge axis.
    """
    assy = cq.Assembly()
    r_hull = params.hull_radius_m
    hinge_r = 0.15  # 150mm radius hinge barrel
    hinge_l = 1.0   # 1m hinge length

    for i in range(n_hinges):
        angle_rad = 2 * math.pi * i / n_hinges
        x = r_hull * math.cos(angle_rad)
        y = r_hull * math.sin(angle_rad)
        z = params.hull_length_m * 0.4  # Radiator zone

        hinge = (
            cq.Workplane("XY")
            .cylinder(hinge_l, hinge_r)
        )
        assy.add(hinge, name=f"hinge_{i}",
                 loc=cq.Location(cq.Vector(x, y, z)),
                 color=cq.Color(0.5, 0.5, 0.5))

    return assy


def create_coolant_routing(params: ShipParameters) -> cq.Assembly:
    """Create NaK coolant loop routing geometry.

    NaK-78 (eutectic sodium-potassium) coolant circulates from the
    reactor to the radiator panels and back. (Lyon 1952, Foust 1972)

    Main loop: 2 pipes (supply + return), each 150mm diameter,
    running the full hull length.
    """
    assy = cq.Assembly()
    pipe_r = 0.075  # 75mm radius (150mm OD)
    wall = 0.005    # 5mm pipe wall (SS-316L)
    length = params.hull_length_m

    for i, offset_angle in enumerate([0.25, 0.75]):  # Two pipes, opposite sides
        angle = offset_angle * 2 * math.pi
        x = (params.hull_radius_m - 0.5) * math.cos(angle)
        y = (params.hull_radius_m - 0.5) * math.sin(angle)

        pipe = (
            cq.Workplane("XY")
            .circle(pipe_r)
            .circle(pipe_r - wall)
            .extrude(length)
        )
        name = "supply" if i == 0 else "return"
        assy.add(pipe, name=f"coolant_{name}",
                 loc=cq.Location(cq.Vector(x, y, 0)),
                 color=cq.Color(1.0, 0.3, 0.0) if i == 0 else cq.Color(0.0, 0.3, 1.0))

    return assy
