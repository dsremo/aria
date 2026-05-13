"""Tests for FEA result visualizer.

Covers VTK export, cross-section plotting, hotspot detection,
and input validation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import meshio
import numpy as np
import pytest

from aria.digital_twin.fea_visualizer import FEAVisualizer


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_tet_mesh(n_cells: int = 20, z_extent: float = 100.0) -> meshio.Mesh:
    """Create a simple tetrahedral mesh for testing.

    Generates *n_cells* tetrahedra distributed along the Z axis
    inside a cylindrical envelope.
    """
    rng = np.random.RandomState(42)
    # Generate random points in a cylinder
    n_points = n_cells * 4  # more than enough vertices
    theta = rng.uniform(0, 2 * np.pi, n_points)
    r = rng.uniform(0, 5.0, n_points)
    z = rng.uniform(0, z_extent, n_points)
    points = np.column_stack([r * np.cos(theta), r * np.sin(theta), z])

    # Build tetrahedra by grouping consecutive vertices
    cells_data = []
    for i in range(n_cells):
        idx = rng.choice(n_points, size=4, replace=False)
        cells_data.append(idx)

    cells = [meshio.CellBlock("tetra", np.array(cells_data))]
    return meshio.Mesh(points=points, cells=cells)


def _make_tri_mesh(n_cells: int = 10) -> meshio.Mesh:
    """Create a simple triangle surface mesh for testing."""
    rng = np.random.RandomState(99)
    n_points = n_cells * 3
    points = rng.uniform(-10, 10, (n_points, 3))
    cells_data = []
    for i in range(n_cells):
        idx = rng.choice(n_points, size=3, replace=False)
        cells_data.append(idx)
    cells = [meshio.CellBlock("triangle", np.array(cells_data))]
    return meshio.Mesh(points=points, cells=cells)


@pytest.fixture
def tet_mesh() -> meshio.Mesh:
    return _make_tet_mesh(20)


@pytest.fixture
def tet_stress() -> np.ndarray:
    rng = np.random.RandomState(7)
    return rng.uniform(50, 500, 20)


@pytest.fixture
def viz(tet_mesh, tet_stress) -> FEAVisualizer:
    return FEAVisualizer(tet_mesh, tet_stress)


# ── Initialization tests ────────────────────────────────────────────────

class TestInit:
    """Verify FEAVisualizer construction and validation."""

    def test_accepts_valid_input(self, tet_mesh, tet_stress):
        """Should construct without error for matching sizes."""
        v = FEAVisualizer(tet_mesh, tet_stress)
        assert v.stress.shape == (20,)

    def test_rejects_mismatched_stress(self, tet_mesh):
        """Should raise ValueError when stress length != cell count."""
        bad_stress = np.zeros(5)
        with pytest.raises(ValueError, match="does not match"):
            FEAVisualizer(tet_mesh, bad_stress)

    def test_stress_dtype_float64(self, viz):
        """Stress array should be cast to float64."""
        assert viz.stress.dtype == np.float64

    def test_accepts_integer_stress(self, tet_mesh):
        """Should accept integer stress arrays (auto-cast)."""
        int_stress = np.ones(20, dtype=np.int32) * 100
        v = FEAVisualizer(tet_mesh, int_stress)
        assert v.stress.dtype == np.float64


# ── VTK export tests ────────────────────────────────────────────────────

class TestExportVTK:
    """Verify VTK file generation."""

    def test_creates_file(self, viz):
        """export_vtk must create a file on disk."""
        with tempfile.TemporaryDirectory() as td:
            out = viz.export_vtk(str(Path(td) / "result.vtu"))
            assert out.exists()
            assert out.stat().st_size > 0

    def test_vtk_contains_stress_data(self, viz):
        """The exported mesh should contain the stress cell data."""
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "result.vtu")
            viz.export_vtk(path)
            reloaded = meshio.read(path)
            assert "von_mises_stress_MPa" in reloaded.cell_data
            total = sum(len(a) for a in reloaded.cell_data["von_mises_stress_MPa"])
            assert total == 20

    def test_creates_parent_dirs(self, viz):
        """Should create intermediate directories if they don't exist."""
        with tempfile.TemporaryDirectory() as td:
            deep_path = str(Path(td) / "a" / "b" / "c" / "out.vtu")
            out = viz.export_vtk(deep_path)
            assert out.exists()


# ── Cross-section plot tests ─────────────────────────────────────────────

class TestPlotCrossSection:
    """Verify cross-section plot generation."""

    def test_creates_image(self, viz):
        """plot_cross_section must produce a PNG file."""
        with tempfile.TemporaryDirectory() as td:
            out = viz.plot_cross_section(50.0, str(Path(td) / "section.png"))
            assert out.exists()
            assert out.suffix == ".png"
            assert out.stat().st_size > 0

    def test_empty_slice_still_produces_image(self, viz):
        """A slice with no cells should still produce a valid image."""
        with tempfile.TemporaryDirectory() as td:
            # z = -9999 is far outside the mesh
            out = viz.plot_cross_section(
                -9999.0, str(Path(td) / "empty.png"), tolerance=0.001,
            )
            assert out.exists()
            assert out.stat().st_size > 0

    def test_custom_tolerance(self, viz):
        """Should accept a custom tolerance parameter."""
        with tempfile.TemporaryDirectory() as td:
            out = viz.plot_cross_section(
                50.0, str(Path(td) / "custom.png"), tolerance=25.0,
            )
            assert out.exists()


# ── Hotspot detection tests ──────────────────────────────────────────────

class TestGetHotspots:
    """Verify hotspot identification."""

    def test_returns_list(self, viz):
        """get_hotspots must return a list."""
        result = viz.get_hotspots(250.0)
        assert isinstance(result, list)

    def test_all_above_threshold(self, viz):
        """Every returned hotspot must exceed the threshold."""
        threshold = 300.0
        hotspots = viz.get_hotspots(threshold)
        for h in hotspots:
            assert h["stress_mpa"] > threshold

    def test_hotspot_fields(self, viz):
        """Each hotspot dict must contain required keys."""
        hotspots = viz.get_hotspots(0.0)  # threshold 0 => all cells
        assert len(hotspots) == 20  # all cells should be returned
        required_keys = {"cell_index", "stress_mpa", "centroid", "cell_type"}
        for h in hotspots:
            assert required_keys.issubset(h.keys())

    def test_sorted_descending(self, viz):
        """Hotspots must be sorted by stress descending."""
        hotspots = viz.get_hotspots(0.0)
        stresses = [h["stress_mpa"] for h in hotspots]
        assert stresses == sorted(stresses, reverse=True)

    def test_centroid_is_3d_tuple(self, viz):
        """Centroid must be a 3-tuple of floats."""
        hotspots = viz.get_hotspots(0.0)
        for h in hotspots:
            assert len(h["centroid"]) == 3
            assert all(isinstance(c, float) for c in h["centroid"])

    def test_high_threshold_returns_empty(self, viz):
        """A threshold above all stress values should return nothing."""
        hotspots = viz.get_hotspots(99999.0)
        assert hotspots == []

    def test_works_with_triangle_mesh(self):
        """Should work with non-tet cell types (triangles)."""
        mesh = _make_tri_mesh(10)
        stress = np.linspace(100, 1000, 10)
        v = FEAVisualizer(mesh, stress)
        hotspots = v.get_hotspots(500.0)
        assert all(h["cell_type"] == "triangle" for h in hotspots)
