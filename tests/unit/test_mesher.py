"""Tests for the digital-twin mesh generator (Gmsh backend)."""

import numpy as np
import pytest

from aria.digital_twin.mesher import mesh_cylinder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RADIUS = 0.5       # 0.5 m inner radius
LENGTH = 2.0       # 2 m long cylinder
THICKNESS = 0.05   # 50 mm wall


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMeshCylinder:
    """Tests for mesh_cylinder."""

    def test_creates_valid_mesh_with_nodes_and_cells(self):
        """mesh_cylinder must return a mesh with points and tet cells."""
        mesh = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.15)
        assert mesh.points is not None
        assert len(mesh.points) > 0
        assert len(mesh.cells) > 0

    def test_mesh_has_tetrahedral_cells(self):
        """All cell blocks must be tetrahedral."""
        mesh = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.15)
        for block in mesh.cells:
            assert block.type in ("tetra", "tetra10"), (
                f"Unexpected cell type: {block.type}"
            )

    def test_element_count_scales_with_element_size(self):
        """A finer mesh (smaller element_size) should produce more elements."""
        coarse = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.2)
        fine = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.1)

        n_coarse = sum(len(b.data) for b in coarse.cells)
        n_fine = sum(len(b.data) for b in fine.cells)

        assert n_fine > n_coarse, (
            f"Fine mesh ({n_fine} elems) should have more elements "
            f"than coarse ({n_coarse} elems)"
        )

    def test_nodes_are_3d(self):
        """Points array must have shape (N, 3)."""
        mesh = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.15)
        assert mesh.points.shape[1] == 3

    def test_node_coordinates_within_expected_bounds(self):
        """All mesh nodes should lie within the cylinder bounding box."""
        mesh = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.15)
        pts = mesh.points
        outer_r = RADIUS + THICKNESS

        # Radial distance from z-axis (cylinder axis is along z)
        r = np.sqrt(pts[:, 0]**2 + pts[:, 1]**2)
        assert r.max() <= outer_r + 0.01, f"Max radial {r.max():.4f} > outer {outer_r}"
        assert r.min() >= RADIUS - 0.01, f"Min radial {r.min():.4f} < inner {RADIUS}"

        # Axial bounds
        assert pts[:, 2].min() >= -0.01
        assert pts[:, 2].max() <= LENGTH + 0.01

    def test_tet_connectivity_valid_indices(self):
        """All node indices in cell connectivity must be valid."""
        mesh = mesh_cylinder(RADIUS, LENGTH, THICKNESS, element_size=0.15)
        n_pts = len(mesh.points)
        for block in mesh.cells:
            assert block.data.min() >= 0
            assert block.data.max() < n_pts
