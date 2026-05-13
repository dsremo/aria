"""Additional ship geometry accessories for the ARIA generation ship.

Antenna arrays, escape pods, and observation viewports — all mounted on
the hull exterior at specific longitudinal zones.

All geometries are lightweight CadQuery representations suitable for
visualisation without excessive tessellation cost.
"""

from __future__ import annotations

import math

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


# ── Antenna array ───────────────────────────────────────────────────────


def _single_dish(radius: float) -> cq.Workplane:
    """Create a single antenna dish: cylinder base + spherical cap.

    Parameters
    ----------
    radius : float
        Dish radius [m].

    Returns
    -------
    cq.Workplane
        Dish solid oriented along +Z.
    """
    base_height = 0.5  # 500 mm pedestal (typical antenna mount height)
    cap_sphere_r = radius * 1.5  # sphere radius for shallow parabolic approximation

    # Cylindrical pedestal
    base = cq.Workplane("XY").circle(radius * 0.3).extrude(base_height)

    # Spherical cap approximation: intersect a sphere with a cylinder
    # to get a shallow dish shape
    cap = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, base_height))
        .sphere(cap_sphere_r)
    )
    # Cut it to keep only the top cap region
    trim_box = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, base_height))
        .box(
            cap_sphere_r * 3, cap_sphere_r * 3, cap_sphere_r * 2,
            centered=True,
        )
        .translate(cq.Vector(0, 0, -cap_sphere_r + radius * 0.3))
    )
    dish_cap = cap.intersect(trim_box)

    # Union pedestal and cap
    return base.union(dish_cap)


def create_antenna_array(params: ShipParameters) -> cq.Assembly:
    """Build 4 dish antennas mounted on the hull at the command zone (Z=50m).

    Each dish has R=3m (typical high-gain antenna, DSN 3.7m class;
    Imbriale 2003, Large Antennas of the DSN).

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    cq.Assembly
        Assembly containing 4 antenna dishes.
    """
    assy = cq.Assembly(name="antenna_array")

    dish_radius = 3.0  # 3 m dish radius (DSN high-gain class; Imbriale 2003)
    z_mount = 50.0  # command zone longitudinal position [m]
    hull_r = params.hull_radius_m
    n_dishes = 4

    dish = _single_dish(dish_radius)

    for i in range(n_dishes):
        theta = 2.0 * math.pi * i / n_dishes
        x = hull_r * math.cos(theta)
        y = hull_r * math.sin(theta)

        assy.add(
            dish,
            name=f"antenna_{i:02d}",
            loc=cq.Location(
                cq.Vector(x, y, z_mount),
                cq.Vector(0, 0, 1),
                math.degrees(theta),
            ),
            color=cq.Color(0.85, 0.85, 0.9, 1.0),
        )

    return assy


# ── Escape pods ─────────────────────────────────────────────────────────


def _single_pod(radius: float, length: float) -> cq.Workplane:
    """Create a single escape pod: cylinder + hemispherical cap.

    Parameters
    ----------
    radius : float
        Pod radius [m].
    length : float
        Cylinder length [m] (cap adds to total length).

    Returns
    -------
    cq.Workplane
        Pod solid oriented along +Z.
    """
    # Cylinder body
    body = cq.Workplane("XY").circle(radius).extrude(length)

    # Hemispherical cap at the far end
    cap = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length))
        .sphere(radius)
    )
    # Keep only the positive-Z hemisphere
    half_box = (
        cq.Workplane("XY")
        .transformed(offset=cq.Vector(0, 0, length + radius / 2.0))
        .box(radius * 3, radius * 3, radius, centered=True)
    )
    hemisphere = cap.intersect(half_box)

    return body.union(hemisphere)


def create_escape_pods(
    params: ShipParameters,
    n_pods: int = 4,
) -> cq.Assembly:
    """Build escape pods mounted flush to hull at the habitat zone (Z=200m).

    Each pod is a small cylinder (R=1.5m, L=4m) with a hemispherical cap
    (Soyuz descent module scale; Sforza 2016, Commercial Spacecraft).
    4 pods are modelled to keep CadQuery lightweight; they conceptually
    represent 20 pods evenly distributed around the hull.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.
    n_pods : int
        Number of pods to model (default 4, representing 20 conceptually).

    Returns
    -------
    cq.Assembly
        Assembly containing escape pods.
    """
    assy = cq.Assembly(name="escape_pods")

    pod_radius = 1.5  # 1.5 m radius (Soyuz descent module scale; Sforza 2016)
    pod_length = 4.0  # 4 m cylinder length
    z_mount = 200.0  # habitat zone longitudinal position [m]
    hull_r = params.hull_radius_m

    pod = _single_pod(pod_radius, pod_length)

    for i in range(n_pods):
        theta = 2.0 * math.pi * i / n_pods
        x = hull_r * math.cos(theta)
        y = hull_r * math.sin(theta)

        # Pods radiate outward from hull surface
        assy.add(
            pod,
            name=f"escape_pod_{i:02d}",
            loc=cq.Location(
                cq.Vector(x, y, z_mount),
                cq.Vector(0, 0, 1),
                math.degrees(theta),
            ),
            color=cq.Color(0.9, 0.6, 0.2, 1.0),
        )

    return assy


# ── Observation viewports ───────────────────────────────────────────────


def create_viewports(
    params: ShipParameters,
    n_ports: int = 8,
) -> cq.Assembly:
    """Create viewport cutout markers on the hull at Z=150m (habitat zone).

    Each viewport is a thin disc (R=0.5m) positioned on the hull surface,
    representing a circular hole. Actual boolean subtraction from the hull
    is deferred to assembly-level operations to keep each module independent.

    Viewport radius 0.5m follows ISS Cupola pane sizing
    (ESA, Columbus module viewport spec; 0.4-0.8m range).

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.
    n_ports : int
        Number of viewports (default 8).

    Returns
    -------
    cq.Assembly
        Assembly containing viewport disc markers (holes, no glass).
    """
    assy = cq.Assembly(name="viewports")

    viewport_radius = 0.5  # 0.5 m radius (ISS Cupola pane class; ESA spec)
    viewport_depth = params.hull_wall_thickness_m + 0.01  # through-hull cut
    z_mount = 150.0  # habitat zone [m]
    hull_r = params.hull_radius_m

    # Each viewport is a thin cylinder representing the cutout volume
    viewport = (
        cq.Workplane("XY")
        .circle(viewport_radius)
        .extrude(viewport_depth)
    )

    for i in range(n_ports):
        theta = 2.0 * math.pi * i / n_ports
        x = hull_r * math.cos(theta)
        y = hull_r * math.sin(theta)

        assy.add(
            viewport,
            name=f"viewport_{i:02d}",
            loc=cq.Location(
                cq.Vector(x, y, z_mount),
                cq.Vector(0, 0, 1),
                math.degrees(theta),
            ),
            color=cq.Color(0.1, 0.1, 0.1, 0.5),  # dark — represents hole
        )

    return assy
