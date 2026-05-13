"""Parametric radiator array geometry for the ARIA generation ship.

Creates an array of flat rectangular panels deployed at an angle from the
hull surface.  Only ``n_panels`` panels are modelled (default 10) to keep
the CAD lightweight; each panel conceptually represents
``params.radiator_total_panels / n_panels`` physical panels.

STRUCTURAL NOTE: Each panel is 25m × 20m × 50mm. At 0.56g with Al-7075:
  σ_bending = 6M/(bt²) = 6×(2500×5.5×25/2)/(20×0.05²) ≈ 20.6 MPa
  vs σ_yield = 503 MPa → SF = 24×. Adequate at 50mm thickness.
  Real panels would have honeycomb core or truss reinforcement
  (ISS radiators use honeycomb aluminum, Messerschmid 2013).
"""

from __future__ import annotations

import math

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def _single_panel(width: float, height: float, thickness: float = 0.05) -> cq.Workplane:
    """Create one flat rectangular radiator panel.

    Parameters
    ----------
    width : float
        Panel width [m].
    height : float
        Panel height [m].
    thickness : float
        Panel thickness [m] (default 50 mm composite).

    Returns
    -------
    cq.Workplane
        A thin box centred on the origin.
    """
    return (
        cq.Workplane("XY")
        .box(width, height, thickness, centered=True)
    )


def create_radiator_array(
    params: ShipParameters,
    n_panels: int = 10,
) -> cq.Assembly:
    """Build a radiator array as a CadQuery Assembly.

    Panels are distributed evenly around the hull circumference at
    the midpoint of the cylinder, each tilted outward by
    ``params.radiator_deploy_angle_deg``.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.
    n_panels : int
        Number of panels to model (default 10 for visualisation).

    Returns
    -------
    cq.Assembly
        Assembly containing all radiator panels.
    """
    assy = cq.Assembly(name="radiator_array")

    panel_solid = _single_panel(
        params.radiator_panel_width_m,
        params.radiator_panel_height_m,
    )

    r = params.hull_radius_m
    z_mid = params.hull_length_m / 2.0
    deploy_rad = math.radians(params.radiator_deploy_angle_deg)

    for i in range(n_panels):
        theta = 2.0 * math.pi * i / n_panels  # azimuthal angle

        # Position: on hull surface at azimuthal angle theta, midship
        x = r * math.cos(theta)
        y = r * math.sin(theta)

        # The panel is tilted outward from the hull by deploy_angle
        # around the tangent direction.  We compose rotations:
        #   1. Rotate about Z to face outward at angle theta
        #   2. Tilt about the local tangent (Y') by deploy_angle
        assy.add(
            panel_solid,
            name=f"radiator_{i:03d}",
            loc=cq.Location(
                cq.Vector(x, y, z_mid),
                cq.Vector(0, 0, 1),
                math.degrees(theta),
            ) * cq.Location(
                cq.Vector(0, 0, 0),
                cq.Vector(0, 1, 0),
                math.degrees(deploy_rad),
            ),
        )

    return assy
