"""Export the ARIA generation ship as a glTF 2.0 file.

Builds a simplified 3D mesh from ShipParameters and writes it to
``data/exports/ship.gltf`` so the web-based 3D viewer can load it.

Usage:
    python -m aria.digital_twin.export_gltf
    python -m aria.digital_twin.export_gltf --output /custom/path/ship.gltf
"""

from __future__ import annotations

import json
import math
import struct
import base64
from pathlib import Path
from typing import Any

from aria.digital_twin.parameters import ShipParameters


def _cylinder_mesh(
    radius: float,
    length: float,
    segments: int = 48,
    axis: str = "x",
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate vertices and triangle indices for an open cylinder.

    The cylinder is centered at the origin along the given axis.
    """
    verts: list[list[float]] = []
    tris: list[list[int]] = []
    half = length / 2.0

    for ring in range(2):
        t = -half + ring * length
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            if axis == "x":
                verts.append([t, radius * math.cos(angle), radius * math.sin(angle)])
            elif axis == "y":
                verts.append([radius * math.cos(angle), t, radius * math.sin(angle)])
            else:
                verts.append([radius * math.cos(angle), radius * math.sin(angle), t])

    # Side faces
    for i in range(segments):
        i_next = (i + 1) % segments
        a = i
        b = i_next
        c = segments + i
        d = segments + i_next
        tris.append([a, c, b])
        tris.append([b, c, d])

    # Cap faces
    base_bot = len(verts)
    if axis == "x":
        verts.append([-half, 0.0, 0.0])
    elif axis == "y":
        verts.append([0.0, -half, 0.0])
    else:
        verts.append([0.0, 0.0, -half])

    base_top = len(verts)
    if axis == "x":
        verts.append([half, 0.0, 0.0])
    elif axis == "y":
        verts.append([0.0, half, 0.0])
    else:
        verts.append([0.0, 0.0, half])

    for i in range(segments):
        i_next = (i + 1) % segments
        tris.append([base_bot, i_next, i])
        tris.append([base_top, segments + i, segments + i_next])

    return verts, tris


def _cone_mesh(
    radius: float,
    height: float,
    segments: int = 48,
    offset_x: float = 0.0,
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate a cone pointing in +X direction."""
    verts: list[list[float]] = []
    tris: list[list[int]] = []

    # Base circle
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        verts.append([offset_x, radius * math.cos(angle), radius * math.sin(angle)])

    # Tip
    tip_idx = len(verts)
    verts.append([offset_x + height, 0.0, 0.0])

    # Base center
    base_idx = len(verts)
    verts.append([offset_x, 0.0, 0.0])

    for i in range(segments):
        i_next = (i + 1) % segments
        tris.append([i, i_next, tip_idx])
        tris.append([base_idx, i, i_next])

    return verts, tris


def _torus_mesh(
    major_r: float,
    minor_r: float,
    major_segs: int = 64,
    minor_segs: int = 24,
    center_x: float = 0.0,
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate a torus in the YZ plane centered at (center_x, 0, 0)."""
    verts: list[list[float]] = []
    tris: list[list[int]] = []

    for i in range(major_segs):
        theta = 2.0 * math.pi * i / major_segs
        cx = 0.0
        cy = major_r * math.cos(theta)
        cz = major_r * math.sin(theta)
        for j in range(minor_segs):
            phi = 2.0 * math.pi * j / minor_segs
            ny = math.cos(theta) * math.cos(phi)
            nz = math.sin(theta) * math.cos(phi)
            nx = math.sin(phi)
            verts.append([
                center_x + cx + minor_r * nx,
                cy + minor_r * ny,
                cz + minor_r * nz,
            ])

    for i in range(major_segs):
        i_next = (i + 1) % major_segs
        for j in range(minor_segs):
            j_next = (j + 1) % minor_segs
            a = i * minor_segs + j
            b = i * minor_segs + j_next
            c = i_next * minor_segs + j
            d = i_next * minor_segs + j_next
            tris.append([a, c, b])
            tris.append([b, c, d])

    return verts, tris


def _spoke_mesh(
    inner_r: float,
    outer_r: float,
    spoke_r: float,
    angle: float,
    segments: int = 8,
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate a radial spoke cylinder in the YZ plane at the given angle.

    The spoke runs from inner_r (hull surface) to outer_r (ring inner edge),
    centred on the ship X-axis. Used to connect the habitat ring to the hull.

    Parameters
    ----------
    inner_r : float
        Start radius (hull surface).
    outer_r : float
        End radius (ring inner edge = habitat_major - habitat_minor).
    spoke_r : float
        Spoke cross-section radius (metres).
    angle : float
        Rotation angle in the YZ plane (radians).
    segments : int
        Circumferential segments for the spoke cylinder.
    """
    length = outer_r - inner_r
    center_dist = inner_r + length / 2.0

    # Build cylinder along Y, centered at (0, center_dist, 0)
    verts, tris = _cylinder_mesh(spoke_r, length, segments=segments, axis="y")
    for v in verts:
        v[1] += center_dist  # offset to correct radial distance

    # Rotate by angle in the YZ plane
    ca, sa = math.cos(angle), math.sin(angle)
    for v in verts:
        y, z = v[1], v[2]
        v[1] = y * ca - z * sa
        v[2] = y * sa + z * ca

    return verts, tris


def _box_mesh(
    sx: float, sy: float, sz: float,
    cx: float = 0.0, cy: float = 0.0, cz: float = 0.0,
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate a box (12 triangles)."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    verts = [
        [cx - hx, cy - hy, cz - hz], [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz], [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz], [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz], [cx - hx, cy + hy, cz + hz],
    ]
    tris = [
        [0, 2, 1], [0, 3, 2],  # -Z
        [4, 5, 6], [4, 6, 7],  # +Z
        [0, 1, 5], [0, 5, 4],  # -Y
        [2, 3, 7], [2, 7, 6],  # +Y
        [0, 4, 7], [0, 7, 3],  # -X
        [1, 2, 6], [1, 6, 5],  # +X
    ]
    return verts, tris


def _frustum_mesh(
    r1: float,
    r2: float,
    length: float,
    segments: int = 48,
    offset_x: float = 0.0,
) -> tuple[list[list[float]], list[list[int]]]:
    """Generate a truncated cone (frustum) along the +X direction.

    r1 is the radius at x=offset_x (first end),
    r2 is the radius at x=offset_x+length (second end).
    Both end caps are closed.
    """
    verts: list[list[float]] = []
    tris: list[list[int]] = []

    # First ring at x=offset_x with radius r1
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        verts.append([offset_x, r1 * math.cos(angle), r1 * math.sin(angle)])

    # Second ring at x=offset_x+length with radius r2
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        verts.append([offset_x + length, r2 * math.cos(angle), r2 * math.sin(angle)])

    # Side faces (quads as two triangles)
    for i in range(segments):
        i_next = (i + 1) % segments
        a, b = i, i_next
        c, d = segments + i, segments + i_next
        tris.append([a, c, b])
        tris.append([b, c, d])

    # Cap faces
    cap1 = len(verts)
    verts.append([offset_x, 0.0, 0.0])
    cap2 = len(verts)
    verts.append([offset_x + length, 0.0, 0.0])

    for i in range(segments):
        i_next = (i + 1) % segments
        tris.append([cap1, i_next, i])
        tris.append([cap2, segments + i, segments + i_next])

    return verts, tris


def _radiator_panel_mesh(
    width_x: float,
    height_r: float,
    thickness: float,
    center_x: float,
    radial_dist: float,
    angle_yz: float,
) -> tuple[list[list[float]], list[list[int]]]:
    """Flat rectangular radiator panel deployed radially at a given angle.

    Creates a box in local space (X = spine direction, Y = radial outward,
    Z = tangential), offsets Y by radial_dist so the panel centre sits at
    that distance from the hull axis, then rotates around the X axis by
    angle_yz so the panel faces in the requested direction in the YZ plane.

    Parameters
    ----------
    width_x : float
        Panel extent along the ship spine [m].
    height_r : float
        Panel extent in the radial direction [m].
    thickness : float
        Panel thickness (tangential direction) [m].
    center_x : float
        Centre of the panel along the ship spine [m].
    radial_dist : float
        Distance from ship axis to the panel centre [m].
    angle_yz : float
        Deployment angle in the YZ plane (radians). 0 = +Y axis.
    """
    hx = width_x / 2
    hy = height_r / 2
    hz = thickness / 2

    # Local box: Y is radial outward, Z is tangential
    local_verts = [
        [-hx, -hy, -hz], [+hx, -hy, -hz],
        [+hx, +hy, -hz], [-hx, +hy, -hz],
        [-hx, -hy, +hz], [+hx, -hy, +hz],
        [+hx, +hy, +hz], [-hx, +hy, +hz],
    ]
    tris = [
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [2, 3, 7], [2, 7, 6],
        [0, 4, 7], [0, 7, 3],
        [1, 2, 6], [1, 6, 5],
    ]

    ca = math.cos(angle_yz)
    sa = math.sin(angle_yz)
    final_verts = []
    for v in local_verts:
        # Translate radially then rotate around X axis
        lx, ly, lz = v[0], v[1] + radial_dist, v[2]
        ny = ly * ca - lz * sa
        nz = ly * sa + lz * ca
        final_verts.append([center_x + lx, ny, nz])

    return final_verts, tris


def _encode_mesh_to_gltf_node(
    name: str,
    verts: list[list[float]],
    tris: list[list[int]],
) -> dict[str, Any]:
    """Encode a mesh as a base64 data-URI embedded glTF primitive dict.

    Returns a dict with keys: name, vertices_b64, indices_b64, and
    bounding box info for building the full glTF JSON.
    """
    # Flatten and compute bounds
    flat_pos = []
    mins = [1e30, 1e30, 1e30]
    maxs = [-1e30, -1e30, -1e30]
    for v in verts:
        for k in range(3):
            flat_pos.append(v[k])
            mins[k] = min(mins[k], v[k])
            maxs[k] = max(maxs[k], v[k])

    flat_idx = []
    for tri in tris:
        flat_idx.extend(tri)

    # Binary encode
    pos_bytes = struct.pack(f"<{len(flat_pos)}f", *flat_pos)
    idx_bytes = struct.pack(f"<{len(flat_idx)}I", *flat_idx)

    return {
        "name": name,
        "pos_b64": base64.b64encode(pos_bytes).decode("ascii"),
        "idx_b64": base64.b64encode(idx_bytes).decode("ascii"),
        "pos_byte_length": len(pos_bytes),
        "idx_byte_length": len(idx_bytes),
        "vertex_count": len(verts),
        "index_count": len(flat_idx),
        "min": mins,
        "max": maxs,
    }


def build_ship_gltf(params: ShipParameters | None = None) -> dict[str, Any]:
    """Build a glTF 2.0 JSON dict representing the generation ship.

    Uses embedded base64 buffers (no external .bin files) so the result
    is a single self-contained .gltf file.
    """
    if params is None:
        params = ShipParameters()

    # Real engineering scale — Three.js camera adapts via fitCam()
    # All units in metres. Ship is ~712m long, habitat ring ~500m radius.
    hull_r = params.hull_radius_m
    hull_l = params.hull_length_m
    reactor_r = params.reactor_radius_m
    reactor_l = params.reactor_length_m
    habitat_major = params.habitat_ring_radius_m
    habitat_minor = params.habitat_ring_tube_radius_m
    shield_r = params.hull_radius_m + params.total_shield_thickness_m

    # Generate meshes
    meshes_data = []

    # ── 1. Main hull (pressurised cylindrical spine) ──────────────
    v, t = _cylinder_mesh(hull_r, hull_l, segments=96, axis="x")   # smooth silhouette at close zoom
    meshes_data.append(_encode_mesh_to_gltf_node("hull_main", v, t))

    # ── 2. Shield stack (7 telescoping cones, one per layer) ──────
    # ShipParameters.shield_layers lists 7 layers ordered bow → stern
    # (outer → inner: detection_lidar at index 0, structural_hull at index 6).
    # Each layer is drawn as a cone with base radius = cumulative radial extent
    # up to that layer and base position offset progressively forward, so the
    # stack visibly telescopes like a pagoda rather than collapsing into one cone.
    SHIELD_VIS_GAP = 5.0      # ESTIMATE — 5 m visual forward offset per layer so every shell is clearly distinguishable at normal zoom
    SHIELD_CONE_H  = 12.0     # ESTIMATE — 12 m uniform cone tip height (visual) so the 7-layer stack reads as a pagoda, not a nub
    n_layers = len(params.shield_layers)
    # Iterate innermost (6) → outermost (0) so the outer cones are drawn last and
    # render on top of the inner ones around the overlapping bow.
    for n_from_inner, i in enumerate(reversed(range(n_layers))):
        layer = params.shield_layers[i]
        outer_r = hull_r + sum(L.thickness_m for L in params.shield_layers[i:])
        base_x = hull_l / 2 + n_from_inner * SHIELD_VIS_GAP
        v, t = _cone_mesh(outer_r, SHIELD_CONE_H, segments=64, offset_x=base_x)
        meshes_data.append(_encode_mesh_to_gltf_node(f"shield_layer_{i}", v, t))

    # ── 3. Reactor module (stern, fusion chamber) ─────────────────
    v, t = _cylinder_mesh(reactor_r, reactor_l, segments=64, axis="x")   # reactor is small but zoomable
    reactor_offset_x = -(hull_l / 2 + reactor_l / 2 + 0.5)
    for vert in v:
        vert[0] += reactor_offset_x
    meshes_data.append(_encode_mesh_to_gltf_node("reactor_engine", v, t))

    # ── 4. Habitat ring (rotating torus — 1g at rim) ──────────────
    # Per-ship-class branching: when `habitat_ring_radius_m == 0` the
    # class is a non-ring design (Stealth Recon, Interstellar Cargo).
    # We skip the torus entirely — and the spokes + hab modules below.
    # Non-zero radius → render normally.
    has_habitat_ring = habitat_major > 0 and habitat_minor > 0
    if has_habitat_ring:
        v, t = _torus_mesh(
            habitat_major, habitat_minor, major_segs=128, minor_segs=32, center_x=0.0,   # most prominent ring — deserves the geometry budget
        )
        meshes_data.append(_encode_mesh_to_gltf_node("habitat_ring", v, t))

    # ── 5. Hull stiffener rings (5 visual, 71 structural) ─────────
    # NASA-SP-8007 buckling control requires `ring_frame_spacing_m = 10 m`,
    # which means 712/10 ≈ 71 ring frames on the full hull. Rendering all 71
    # would visually clutter the model at normal zoom (they'd merge into a
    # texture). We therefore render ONLY 5 MAJOR bulkhead frames as distinct
    # geometry; the 66 intermediate frames are assumed present but abstracted.
    # The structural FEA (shield_system / engineering_detail) uses the full
    # 71-frame count for buckling calculations — only the 3D twin simplifies.
    stiffener_ring_r = hull_r * 1.30   # ESTIMATE — frame flange 30 % wider than hull (aerospace stiffener proportion)
    stiffener_tube_r = hull_r * 0.12   # ESTIMATE — visual tube cross-section radius
    stiffener_xs = [hull_l * f for f in (-2.0 / 5, -1.0 / 5, 0.0, 1.0 / 5, 2.0 / 5)]
    for idx, cx in enumerate(stiffener_xs):
        v, t = _torus_mesh(
            stiffener_ring_r, stiffener_tube_r,
            major_segs=64, minor_segs=16, center_x=cx,   # stiffener ring — 2× smoother than before
        )
        meshes_data.append(_encode_mesh_to_gltf_node(f"hull_stiffener_{idx}", v, t))

    # ── 6. Fuel-tank clusters (3 cryogenic D/He-3 tanks) ──────────
    # Tanks wider than hull so the ship reads as "segmented" rather than a bare tube.
    # Placed stern-ward of centre, ahead of the reactor module.
    fuel_tank_r = hull_r * 2.50        # ESTIMATE — cryo tanks 2.5× hull radius (Frisbee 2003, JPL/D-26963 fusion rocket studies)
    fuel_tank_l = hull_l * 0.10        # ESTIMATE — 10 % hull length per tank section
    fuel_tank_xs = [hull_l * f for f in (-0.10, -0.26, -0.42)]
    for idx, cx in enumerate(fuel_tank_xs):
        v, t = _cylinder_mesh(fuel_tank_r, fuel_tank_l, segments=64, axis="x")
        for vert in v:
            vert[0] += cx
        meshes_data.append(_encode_mesh_to_gltf_node(f"fuel_tank_{idx}", v, t))

    # ── 7. Radiator arrays — parametric wing count from ShipParameters ────
    # Wings placed symmetrically around the hull, starting at +Y (top) and
    # spaced 360° / wing_count apart. For 2 wings → 0°/180° (top/bottom).
    # Per-class branching: Stealth Recon has wing_count=0 to eliminate
    # the warm-plume signature (uses an LOX sublimator instead) — skip
    # the radiator pass entirely in that case.
    if params.radiator_wing_count > 0:
        rad_panel_x = params.radiator_wing_width_m    # along spine
        rad_panel_r = params.radiator_wing_height_m   # radial extent
        rad_panel_t = 2.0                             # ESTIMATE — 2 m thickness (heat-pipe manifold depth)
        rad_center_x = -(hull_l * 0.28)               # centred aft of ship centre, away from habitat-ring spokes at x=0
        rad_radial = hull_r + 8.0 + rad_panel_r / 2.0
        for idx in range(params.radiator_wing_count):
            deg = 360.0 * idx / params.radiator_wing_count
            angle = math.radians(deg)
            v, t = _radiator_panel_mesh(
                rad_panel_x, rad_panel_r, rad_panel_t,
                center_x=rad_center_x,
                radial_dist=rad_radial,
                angle_yz=angle,
            )
            meshes_data.append(_encode_mesh_to_gltf_node(f"radiator_array_{idx}", v, t))

    # ── 8. Habitat ring spokes (parametric count from ShipParameters) ─
    # Parameter-driven — ShipParameters.habitat_spoke_count is the source of truth.
    # O'Neill 1977 default is 6 (Stanford Torus). Spokes at 360°/N intervals.
    # Skip entirely when the ship has no ring (non-ring classes like
    # Stealth or Interstellar-Cargo carry no spokes to attach to).
    if has_habitat_ring and params.habitat_spoke_count > 0:
        spoke_inner = hull_r
        spoke_outer = habitat_major - habitat_minor
        spoke_r = max(8.0, hull_r * 0.55)           # ESTIMATE — visual truss diameter
        num_spokes = params.habitat_spoke_count
        for i in range(num_spokes):
            angle = (i / num_spokes) * 2.0 * math.pi
            v, t = _spoke_mesh(spoke_inner, spoke_outer, spoke_r, angle, segments=24)   # circular cross-section smooth at ring-zoom
            meshes_data.append(_encode_mesh_to_gltf_node(f"spoke_{i}", v, t))

    # ── 9. Magnetic nozzle (plasma exhaust bell, flared aft) ──────
    # Expansion ratio 4:1 — conservative vs 6:1 ideal for ICF/magnetic-confinement
    # fusion exhausts (Frisbee 2003, JPL/D-26963 "How to Build an Antimatter Rocket").
    # Throat radius matches reactor first-wall radius for smooth plasma hand-off.
    nozzle_throat_r = reactor_r         # throat = reactor exit for plasma continuity (was hull_r, geometrically wrong)
    nozzle_exit_r = reactor_r * 4.00    # ESTIMATE — 4:1 magnetic-nozzle expansion (Frisbee 2003)
    nozzle_l = 60.0                    # ESTIMATE — 60 m bell length
    nozzle_throat_x = reactor_offset_x - reactor_l / 2 - 1.0  # just aft of reactor
    nozzle_exit_x = nozzle_throat_x - nozzle_l                # exit bell further aft (more −X)
    # Frustum in +X direction: r1=large at exit (aft end), r2=small at throat (near reactor)
    v, t = _frustum_mesh(
        nozzle_exit_r, nozzle_throat_r, nozzle_l,
        segments=96, offset_x=nozzle_exit_x,   # nozzle is a hero shape — 96 sides = near-perfect circle
    )
    meshes_data.append(_encode_mesh_to_gltf_node("magnetic_nozzle", v, t))

    # ── 10. Engine bells (4 secondary attitude thrusters) ─────────
    # 4-way symmetric secondary thrusters at 45° offsets around the stern
    # (ESTIMATE — standard cruciform config for attitude control).
    bell_r = hull_r * 0.35             # ESTIMATE — ~4.4 m bell radius
    bell_l = hull_r * 1.20             # ESTIMATE — ~15 m nozzle length
    bell_radial = hull_r * 1.80        # ESTIMATE — ~22.7 m offset from axis
    bell_base_x = reactor_offset_x - reactor_l / 2 - 0.5
    for idx in range(4):
        bell_angle = math.radians(idx * 90.0 + 45.0)   # 45°, 135°, 225°, 315°
        by = math.cos(bell_angle) * bell_radial
        bz = math.sin(bell_angle) * bell_radial
        # Cone points in +X (toward reactor); we want nozzle opening facing aft.
        # Place cone tip near reactor, base opening aft.
        v, t = _cone_mesh(bell_r, bell_l, segments=32, offset_x=0.0)
        # Flip in X so the opening (base) faces −X (aft)
        for vert in v:
            vert[0] = -vert[0]
            vert[0] += bell_base_x
            vert[1] += by
            vert[2] += bz
        # Flip triangle winding to preserve outward normals after mirror
        t = [[tri[0], tri[2], tri[1]] for tri in t]
        meshes_data.append(_encode_mesh_to_gltf_node(f"engine_bell_{idx}", v, t))

    # ── 11. Bow sensor ring (star trackers + LIDAR + comm) ────────
    # Sensor-suite ring forward of the hull bow — navigation instruments,
    # LIDAR micrometeoroid detection and comm antenna stack.
    bow_sensor_major = hull_r * 2.00   # ESTIMATE — 2× hull radius
    bow_sensor_tube = hull_r * 0.08    # ESTIMATE — thin sensor ring
    # Place the sensor ring just forward of the outermost shield layer so it's
    # visible rather than buried inside the telescoping bow cone stack.
    # Must match SHIELD_VIS_GAP and SHIELD_CONE_H above.
    shield_forward_extent = (len(params.shield_layers) - 1) * 5.0 + 12.0
    bow_sensor_x = hull_l / 2 + shield_forward_extent + 2.0
    v, t = _torus_mesh(
        bow_sensor_major, bow_sensor_tube,
        major_segs=64, minor_segs=16, center_x=bow_sensor_x,   # bow sensor ring — visible at Focus zoom
    )
    meshes_data.append(_encode_mesh_to_gltf_node("bow_sensor_ring", v, t))

    # ── 12. Habitat ring crew-quarter modules (24 pods on outer rim) ──
    # The torus itself is the structural pressure shell. Actual crew quarters /
    # greenhouses / ECLSS modules are perched on the OUTER rim (where centrifugal
    # gravity is strongest). 24 modules at 15° spacing — matches O'Neill 1977
    # island-community layout: ~40 people per module × 24 ≈ 960 crew.
    # Skipped entirely on classes with no ring (Stealth Recon,
    # Interstellar Cargo) — habitat_ring_radius_m = 0 drops this pass.
    if has_habitat_ring:
        num_modules = 24
        mod_axial = 14.0             # ESTIMATE — 14 m along ship X (pod length)
        mod_radial = 8.0             # ESTIMATE — 8 m radially outward from ring outer rim
        mod_tangential = 16.0        # ESTIMATE — 16 m around ring circumference
        mod_perch_r = habitat_major + habitat_minor + mod_radial / 2.0  # sit on outer edge of tube
        for idx in range(num_modules):
            angle = (idx / num_modules) * 2.0 * math.pi
            v, t = _radiator_panel_mesh(
                mod_axial, mod_radial, mod_tangential,
                center_x=0.0,
                radial_dist=mod_perch_r,
                angle_yz=angle,
            )
            meshes_data.append(_encode_mesh_to_gltf_node(f"hab_module_{idx}", v, t))

    # ── 13. Docking ports (4 at cardinal+45° angles, mid-ship on hull) ────
    # Crew transfer / resupply / EVA airlocks. Placed at 45°/135°/225°/315°
    # (half-way BETWEEN the 6 habitat-ring spokes at 0°/60°/120°/…) so the
    # ports don't physically overlap a spoke at the same angle.
    # Note: ports are at hull mid-ship (x=+71 m, 10 % forward of centre) and
    # spokes cross x=0, so even if angles clashed the axial offset gives some
    # clearance — but the 15°-minimum angular separation is belt-and-braces.
    dock_axial = 6.0             # ESTIMATE — 6 m along X
    dock_radial = 6.0            # ESTIMATE — 6 m radial extent from hull
    dock_tangential = 6.0        # ESTIMATE — 6 m across
    dock_perch_r = hull_r + dock_radial / 2.0
    dock_center_x = hull_l * 0.10   # 10 % forward of ship centre
    for idx in range(4):
        angle = math.radians(45.0 + idx * 90.0)   # 45°, 135°, 225°, 315°
        v, t = _radiator_panel_mesh(
            dock_axial, dock_radial, dock_tangential,
            center_x=dock_center_x,
            radial_dist=dock_perch_r,
            angle_yz=angle,
        )
        meshes_data.append(_encode_mesh_to_gltf_node(f"docking_port_{idx}", v, t))

    # ── 14. Communication arrays (4 dorsal antennas along hull) ──────
    # High-gain comm dishes for Earth-uplink during cruise (Ka-band, DSN-compatible).
    # All placed dorsally (angle 90° = +Y up) at 4 axial positions along the hull.
    ant_axial = 2.0
    ant_radial = 10.0            # ESTIMATE — 10 m antenna + mast
    ant_tangential = 4.0
    ant_perch_r = hull_r + ant_radial / 2.0
    ant_positions_x = [-hull_l * 0.30, -hull_l * 0.05, hull_l * 0.18, hull_l * 0.38]
    for idx, ax in enumerate(ant_positions_x):
        v, t = _radiator_panel_mesh(
            ant_axial, ant_radial, ant_tangential,
            center_x=ax,
            radial_dist=ant_perch_r,
            angle_yz=math.radians(90.0),    # all dorsal
        )
        meshes_data.append(_encode_mesh_to_gltf_node(f"comm_antenna_{idx}", v, t))

    # ── Assemble glTF 2.0 JSON ──
    buffers: list[dict] = []
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []
    node_indices: list[int] = []
    gltf_materials: list[dict] = []

    byte_offset_total = 0
    all_bin = b""

    for i, md in enumerate(meshes_data):
        idx_b = base64.b64decode(md["idx_b64"])
        pos_b = base64.b64decode(md["pos_b64"])

        # Pad to 4-byte alignment
        while len(idx_b) % 4 != 0:
            idx_b += b"\x00"
        while len(pos_b) % 4 != 0:
            pos_b += b"\x00"

        chunk = idx_b + pos_b
        buf_idx = len(buffers)
        buffers.append({
            "uri": "data:application/octet-stream;base64," + base64.b64encode(chunk).decode("ascii"),
            "byteLength": len(chunk),
        })

        # Buffer view for indices
        bv_idx = len(buffer_views)
        buffer_views.append({
            "buffer": buf_idx,
            "byteOffset": 0,
            "byteLength": len(idx_b),
            "target": 34963,  # ELEMENT_ARRAY_BUFFER
        })

        # Buffer view for positions
        bv_pos = len(buffer_views)
        buffer_views.append({
            "buffer": buf_idx,
            "byteOffset": len(idx_b),
            "byteLength": len(pos_b),
            "target": 34962,  # ARRAY_BUFFER
        })

        # Accessor for indices
        acc_idx = len(accessors)
        accessors.append({
            "bufferView": bv_idx,
            "byteOffset": 0,
            "componentType": 5125,  # UNSIGNED_INT
            "count": md["index_count"],
            "type": "SCALAR",
            "max": [md["index_count"] - 1],
            "min": [0],
        })

        # Accessor for positions
        acc_pos = len(accessors)
        accessors.append({
            "bufferView": bv_pos,
            "byteOffset": 0,
            "componentType": 5126,  # FLOAT
            "count": md["vertex_count"],
            "type": "VEC3",
            "max": md["max"],
            "min": md["min"],
        })

        # Per-part glTF base colours — Three.js overrides with PART_MATS but
        # keep these consistent so offline viewers (Blender, glTF Viewer) work.
        PART_COLORS_RGBA = {
            "hull_main":        [0.753, 0.753, 0.753, 1.0],  # Ti-6Al-4V silver
            "reactor_engine":   [1.000, 0.267, 0.267, 1.0],  # reactor red-orange
            "habitat_ring":     [0.867, 0.667, 0.200, 1.0],  # habitat gold
            "magnetic_nozzle":  [0.200, 0.350, 0.700, 1.0],  # plasma blue
            "bow_sensor_ring":  [0.700, 0.720, 0.750, 1.0],  # sensor-array grey
            # 7 shield layers — colour coded per material science:
            "shield_layer_0":   [0.800, 0.900, 1.000, 1.0],  # detection_lidar — sensor cyan-white
            "shield_layer_1":   [0.700, 0.400, 0.900, 1.0],  # active_deflection (plasma) — magenta/purple
            "shield_layer_2":   [0.950, 0.800, 0.250, 1.0],  # magnetic_deflector (superconducting) — gold
            "shield_layer_3":   [0.850, 0.550, 0.300, 1.0],  # electrostatic_grid (tungsten mesh) — copper
            "shield_layer_4":   [0.600, 0.850, 0.980, 1.0],  # ablation_ice (water ice) — pale cyan
            "shield_layer_5":   [0.500, 0.520, 0.570, 1.0],  # whipple_shield (SiC/Kevlar/Al) — steel grey
            "shield_layer_6":   [0.770, 0.770, 0.780, 1.0],  # structural_hull (Ti-6Al-4V+HealTech) — titanium
            **{f"hull_stiffener_{i}": [0.600, 0.620, 0.650, 1.0] for i in range(5)},
            **{f"fuel_tank_{i}":      [0.820, 0.860, 0.900, 1.0] for i in range(3)},
            **{f"radiator_array_{i}": [0.200, 0.500, 0.900, 1.0] for i in range(2)},
            **{f"spoke_{i}":          [0.400, 0.420, 0.460, 1.0] for i in range(6)},
            **{f"engine_bell_{i}":    [0.900, 0.500, 0.100, 1.0] for i in range(4)},
            # Habitat ring modules (24 crew-quarter pods) — warm off-white with window glow
            **{f"hab_module_{i}":     [0.950, 0.880, 0.700, 1.0] for i in range(24)},
            # Docking ports (4 cardinal)
            **{f"docking_port_{i}":   [0.720, 0.780, 0.850, 1.0] for i in range(4)},
            # Communication antenna arrays (4 dorsal)
            **{f"comm_antenna_{i}":   [0.880, 0.900, 0.950, 1.0] for i in range(4)},
        }
        rgba = PART_COLORS_RGBA.get(md["name"], [0.533, 0.533, 0.533, 1.0])
        mat_idx = len(gltf_materials)
        gltf_materials.append({
            "name": md["name"] + "_mat",
            "pbrMetallicRoughness": {
                "baseColorFactor": rgba,
                "metallicFactor": 0.6,
                "roughnessFactor": 0.4,
            },
        })

        mesh_idx = len(meshes)
        meshes.append({
            "name": md["name"],
            "primitives": [{
                "attributes": {"POSITION": acc_pos},
                "indices": acc_idx,
                "mode": 4,  # TRIANGLES
                "material": mat_idx,
            }],
        })

        node_idx = len(nodes)
        nodes.append({
            "name": md["name"],
            "mesh": mesh_idx,
        })
        node_indices.append(node_idx)

    # Root node containing all parts
    root_idx = len(nodes)
    nodes.append({
        "name": "ARIA_Ship",
        "children": node_indices,
    })

    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "ARIA Digital Twin Export",
        },
        "scene": 0,
        "scenes": [{"name": "ShipScene", "nodes": [root_idx]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": gltf_materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": buffers,
    }

    return gltf


def export_gltf(output_path: str | Path | None = None) -> Path:
    """Build and write the ship glTF file.

    Parameters
    ----------
    output_path : str or Path, optional
        Destination file path. Defaults to ``data/exports/ship.gltf``
        relative to the project root.

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    if output_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        output_path = project_root / "data" / "exports" / "ship.gltf"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    params = ShipParameters()
    gltf = build_ship_gltf(params)

    with open(output_path, "w") as f:
        json.dump(gltf, f, indent=2)

    print(f"Exported ship glTF to {output_path}")
    print(f"  Hull: {params.hull_radius_m:.1f} m radius x {params.hull_length_m:.1f} m length")
    print(f"  Shield: {params.total_shield_thickness_m:.2f} m total thickness")
    print(f"  Habitat ring: {params.habitat_ring_radius_m:.0f} m major radius")
    print(f"  Reactor: {params.reactor_radius_m:.1f} m radius x {params.reactor_length_m:.1f} m")
    print(f"  Radiator panels: {params.radiator_total_panels} x {params.radiator_panel_area_m2:.0f} m^2")

    # Mass-budget closure — per Round-1 audit finding #13
    mb = _estimate_mass_budget(params)
    target = params.ship_mass_kg
    total = sum(mb.values())
    closure = 100.0 * total / target
    print(f"\nMass budget (closure vs ship_mass_kg={target:.2e} kg):")
    for name, m in sorted(mb.items(), key=lambda x: -x[1]):
        print(f"  {name:<20s} {m:>12.3e} kg   ({100*m/target:5.1f} %)")
    print(f"  {'TOTAL':<20s} {total:>12.3e} kg   ({closure:5.1f} %)")
    if closure < 80 or closure > 120:
        print(f"  ⚠️  closure outside ±20 % tolerance — investigate subsystem masses")

    # Centre of mass — per Round-2 audit finding #4
    com_x = _estimate_com_x(params, mb)
    print(f"\nCentre of mass (along ship X-axis): {com_x:+.1f} m")
    print(f"  Hull ends: −{params.hull_length_m/2:.0f} m (stern) to +{params.hull_length_m/2:.0f} m (bow)")
    print(f"  Nozzle exit at x ≈ −{params.hull_length_m/2 + params.reactor_length_m + 61.5:.0f} m → thrust-line offset from CoM")

    return output_path.resolve()


def _estimate_mass_budget(params: ShipParameters) -> dict[str, float]:
    """Lightweight mass inventory per subsystem using parametric dimensions × material density.

    Not physically exhaustive — intended as a closure sanity check against
    `ship_mass_kg`. Densities come from `material_db.py` citations.
    """
    # Hull shell: thin cylinder, 2πR × t × L × ρ_Ti-6Al-4V (MMPDS-17)
    rho_ti = 4430.0              # kg/m³ Ti-6Al-4V (MMPDS-17)
    hull_mass = (2 * math.pi * params.hull_radius_m
                 * params.hull_wall_thickness_m
                 * params.hull_length_m
                 * rho_ti)

    # Shield: dominated by ablation ice, 5.45 m × 2000 m² × ρ_water_ice
    rho_ice = 917.0              # kg/m³ water ice at 260 K (NIST)
    ice_area_m2 = 2000.0         # ESTIMATE — bow cross-section per Cucinotta 2014 Table B.3
    ice_mass = 5.45 * ice_area_m2 * rho_ice   # ~10⁷ kg

    # Reactor + blanket: πR²L × ρ_EUROFER97 + blanket mass
    rho_eurofer = 7800.0         # kg/m³ EUROFER97 (MMPDS-17, fusion steel)
    reactor_shell_vol = math.pi * params.reactor_radius_m**2 * params.reactor_length_m
    rho_lipb = 9500.0            # kg/m³ Li-Pb eutectic (Giancarli 2010)
    blanket_vol = (math.pi *
                   ((params.reactor_radius_m + params.reactor_blanket_thickness_m)**2
                    - params.reactor_radius_m**2)
                   * params.reactor_length_m)
    reactor_mass = reactor_shell_vol * rho_eurofer + blanket_vol * rho_lipb

    # Habitat ring: toroidal shell, thin wall, 2π²R·r·t × ρ_Al (lightweight composite frame)
    rho_al = 2780.0              # kg/m³ Al-2219-T87 (MMPDS-17)
    ring_wall_thickness = 0.05   # ESTIMATE — 50 mm composite shell, typical for pressurised habitats
    ring_surface_area = 4 * math.pi**2 * params.habitat_ring_radius_m * params.habitat_ring_tube_radius_m
    ring_mass = ring_surface_area * ring_wall_thickness * rho_al

    # Habitat modules: 24 × enclosed volume × air density + structural shell
    n_modules = 24
    mod_volume = 14.0 * 16.0 * 8.0   # m³ per pod (dims from hab_module geometry)
    mod_shell_mass = mod_volume * 50.0   # ESTIMATE — 50 kg/m³ aerospace avg (Al-Li + composites)
    module_mass = n_modules * mod_shell_mass

    # Radiators: 2 wings × area × thickness × ρ_Al
    radiator_mass = (params.radiator_wing_count
                     * params.radiator_wing_width_m
                     * params.radiator_wing_height_m
                     * 0.010  # ESTIMATE — 10 mm effective thickness (panel + heat-pipe + manifold)
                     * rho_al)

    # Fuel: cryogenic D + He-3 — 15 % of ship mass budget for interstellar (Frisbee 2003)
    fuel_mass = 0.15 * params.ship_mass_kg

    # Other (avionics, power distribution, ECLSS hardware, spare parts, margin)
    other_mass = 0.08 * params.ship_mass_kg

    return {
        "hull":             hull_mass,
        "shield_ice":       ice_mass,
        "reactor+blanket":  reactor_mass,
        "habitat_ring":     ring_mass,
        "hab_modules":      module_mass,
        "radiators":        radiator_mass,
        "fuel":             fuel_mass,
        "other/margin":     other_mass,
    }


def _estimate_com_x(params: ShipParameters, mb: dict[str, float]) -> float:
    """Approximate centre-of-mass along ship X axis using subsystem masses
    and their nominal X positions. Positive X = bow, negative = stern.
    """
    positions = {
        "hull":             0.0,                                        # centred on origin
        "shield_ice":       params.hull_length_m / 2 + 3.0,             # ~bow, shield stack
        "reactor+blanket":  -(params.hull_length_m / 2 + params.reactor_length_m / 2 + 0.5),
        "habitat_ring":     0.0,                                        # at ship midpoint
        "hab_modules":      0.0,                                        # on the ring
        "radiators":        -params.hull_length_m * 0.28,               # matches rad_center_x in builder
        "fuel":             -params.hull_length_m * 0.26,               # matches central fuel tank x
        "other/margin":     0.0,                                        # assumed centred
    }
    total = sum(mb.values())
    if total <= 0:
        return 0.0
    return sum(mb[k] * positions[k] for k in mb) / total


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export ARIA ship as glTF 2.0")
    parser.add_argument("--output", "-o", default=None, help="Output file path")
    args = parser.parse_args()

    export_gltf(args.output)


if __name__ == "__main__":
    main()
