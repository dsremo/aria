"""Parametric propulsion geometry for the ARIA generation ship.

Creates the fusion drive magnetic nozzle and a symbolic magsail coil.

NOTE ON NOZZLE: D-T fusion plasma at ~10⁸ K cannot contact any solid
material. The nozzle is a MAGNETIC nozzle (field-reversed configuration)
where superconducting coils shape the exhaust without material contact.
The cone geometry here represents the magnetic field envelope, not a
physical material cone. (Tarditi & Steinhauer 2014, FRC nozzle design)
"""

from __future__ import annotations

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def create_propulsion(params: ShipParameters) -> cq.Assembly:
    """Build the propulsion subsystem.

    Components:
      1. Fusion drive nozzle — conical, base R=5 m, length=10 m
      2. Magsail coil — symbolic thin disc (R=100 m stand-in for the
         actual 50 km coil, which is far too large for CAD)

    The nozzle exhaust points in the -Z direction (aft).

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass (reserved for future parametric use).

    Returns
    -------
    cq.Assembly
        Assembly containing the nozzle and magsail symbol.
    """
    assy = cq.Assembly(name="propulsion")

    nozzle = _make_nozzle(base_radius=5.0, length=10.0)
    assy.add(nozzle, name="fusion_drive_nozzle",
             color=cq.Color(0.9, 0.4, 0.1, 1.0))

    magsail = _make_magsail_symbol(symbol_radius=100.0, thickness=0.5)
    # Place magsail behind the nozzle
    assy.add(magsail, name="magsail_coil_50km",
             loc=cq.Location(cq.Vector(0, 0, -15.0)),
             color=cq.Color(0.1, 0.4, 0.9, 0.5))

    return assy


def _make_nozzle(base_radius: float, length: float) -> cq.Workplane:
    """Conical nozzle pointing in -Z direction.

    Built as a cone: circle at base (z=0) tapering to a small throat
    at z = -length. The throat radius is 10% of the base for a
    convergent nozzle shape.
    """
    throat_radius = base_radius * 0.1
    # Loft between two circles
    nozzle = (
        cq.Workplane("XY")
        .circle(base_radius)
        .workplane(offset=-length)
        .circle(throat_radius)
        .loft(combine=True)
    )
    return nozzle


def _make_magsail_symbol(symbol_radius: float, thickness: float) -> cq.Workplane:
    """Symbolic magsail coil — thin disc standing in for the 50 km coil.

    The actual magnetic sail coil has a 50 km radius which cannot be
    represented in CAD at ship scale. This 100 m disc serves as a
    symbolic placeholder.
    """
    disc = (
        cq.Workplane("XY")
        .circle(symbol_radius)
        .circle(symbol_radius * 0.9)  # annular ring shape
        .extrude(thickness)
    )
    return disc
