"""Parametric habitat ring geometry for the ARIA generation ship.

O'Neill-style rotating torus habitat with spoke connections to the hull.
Supports a simplified wireframe mode for the large (500 m major radius)
default geometry.
"""

from __future__ import annotations

import math

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def create_habitat_ring(
    params: ShipParameters,
    simplified: bool = True,
) -> cq.Assembly:
    """Build the rotating habitat ring.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.
    simplified : bool
        If True (default), create a lightweight wireframe representation
        using thin annular cross-sections and spoke outlines instead of
        the full revolved torus solid. The full torus at R_major=500 m
        is extremely expensive in CadQuery.

    Returns
    -------
    cq.Assembly
        Assembly containing the torus (or its cross-section) and spokes.
    """
    assy = cq.Assembly(name="habitat_ring")

    r_major = params.habitat_ring_radius_m   # 500 m
    r_minor = params.habitat_ring_tube_radius_m  # 10 m

    if simplified:
        # Simplified mode: cross-section ring (annulus) + spoke outlines
        ring = _make_annular_profile(r_major, r_minor)
        assy.add(ring, name="habitat_torus_profile",
                 color=cq.Color(0.3, 0.7, 0.3, 0.6))
    else:
        # Full torus — only viable for small radii in tests
        torus = _make_torus(r_major, r_minor)
        assy.add(torus, name="habitat_torus",
                 color=cq.Color(0.3, 0.7, 0.3, 0.6))

    # Spokes: cylindrical tubes from origin to the torus
    spoke_r = params.habitat_spoke_radius_m  # 2 m default
    n_spokes = params.habitat_spoke_count    # 6 default (O'Neill 1977)
    for i in range(n_spokes):
        theta = 2.0 * math.pi * i / n_spokes
        spoke = _make_spoke(r_major, spoke_r, theta)
        assy.add(spoke, name=f"spoke_{i:02d}",
                 color=cq.Color(0.6, 0.6, 0.65, 1.0))

    return assy


def get_habitat_decks(params: ShipParameters) -> list[dict]:
    """Return a list of deck descriptions for the habitat ring interior.

    The tube cross-section diameter (2 * r_minor) is divided into decks
    of standard 3.0 m height (NASA-STD-3001 Vol.2, Table 6.2.2-1,
    minimum overhead clearance 1.98 m + utilities = ~3.0 m).

    Each deck is a horizontal slice through the circular tube
    cross-section.  Floor area is computed as the chord width at that
    deck height times the torus circumference (2 * pi * R_major).

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    list[dict]
        One entry per deck with keys:
        - deck_number: int (1 = outermost / highest-g)
        - radius_from_center_m: float (distance from tube centre)
        - floor_area_m2: float (usable floor area)
        - purpose: str (assigned function)
    """
    r_minor = params.habitat_ring_tube_radius_m  # 20 m
    r_major = params.habitat_ring_radius_m       # 500 m
    tube_diameter = 2.0 * r_minor                # 40 m
    deck_height = 3.0  # 3.0 m per deck (NASA-STD-3001 Vol.2)
    n_decks = int(tube_diameter / deck_height)   # 13

    # Purpose assignments by deck band
    _purposes = {
        range(1, 4):   "living_quarters",    # decks 1-3
        range(4, 6):   "recreation",         # decks 4-5
        range(6, 8):   "agriculture",        # decks 6-7
        range(8, 10):  "laboratory",         # decks 8-9
        range(10, 12): "medical",            # decks 10-11
        range(12, 14): "storage",            # decks 12-13
    }

    def _purpose_for(deck_num: int) -> str:
        for rng, purpose in _purposes.items():
            if deck_num in rng:
                return purpose
        return "unassigned"

    decks = []
    for i in range(n_decks):
        # Distance from tube centre: deck 1 is at the bottom (outer rim,
        # highest gravity), deck n_decks is near the top (inner rim).
        # y position within the circular cross-section, measured from
        # the bottom of the tube (-r_minor).
        y_from_bottom = (i + 0.5) * deck_height
        y_from_centre = y_from_bottom - r_minor  # [-r_minor, +r_minor]

        # Chord half-width at this height: sqrt(r^2 - y^2)
        if abs(y_from_centre) >= r_minor:
            chord_half = 0.0
        else:
            chord_half = math.sqrt(r_minor**2 - y_from_centre**2)

        # Floor width = full chord = 2 * chord_half
        chord_width = 2.0 * chord_half

        # Floor area = chord_width * torus circumference
        floor_area = chord_width * 2.0 * math.pi * r_major

        decks.append({
            "deck_number": i + 1,
            "radius_from_center_m": round(abs(y_from_centre), 3),
            "floor_area_m2": round(floor_area, 1),
            "purpose": _purpose_for(i + 1),
        })

    return decks


def _make_torus(major_r: float, minor_r: float) -> cq.Workplane:
    """Full revolved torus. Expensive for large radii."""
    torus = (
        cq.Workplane("XZ")
        .transformed(offset=cq.Vector(major_r, 0, 0))
        .circle(minor_r)
        .revolve(360, (0, 0, 0), (0, 0, 1))
    )
    return torus


def _make_annular_profile(major_r: float, minor_r: float) -> cq.Workplane:
    """Lightweight representation: a thin annular disc at the torus location.

    Creates a flat washer shape at the major radius to indicate the
    torus cross-section location without the full revolve.
    """
    thickness = 0.5  # 0.5 m thin disc for visibility
    outer_r = major_r + minor_r
    inner_r = major_r - minor_r

    annulus = (
        cq.Workplane("XY")
        .circle(outer_r)
        .circle(inner_r)
        .extrude(thickness)
    )
    return annulus


def _make_spoke(major_r: float, spoke_r: float, theta: float) -> cq.Workplane:
    """Cylindrical spoke from origin to the torus ring.

    The spoke lies in the XY plane at angle theta, extending from
    the hull center (r=0) outward to the torus major radius.
    """
    # Build a cylinder along X, then rotate to the correct azimuthal angle
    spoke = (
        cq.Workplane("YZ")
        .circle(spoke_r)
        .extrude(major_r)
    )
    # Rotate around Z axis by theta
    if theta != 0.0:
        spoke = spoke.rotate((0, 0, 0), (0, 0, 1), math.degrees(theta))
    return spoke
