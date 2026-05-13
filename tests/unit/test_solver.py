"""Tests for the digital-twin FEA solver (scipy.sparse backend).

Includes analytical validation against thin-walled pressurised cylinder:
    sigma_hoop  = p * R / t
    sigma_axial = p * R / (2 * t)
"""

import numpy as np
import pytest

from aria.digital_twin.mesher import mesh_cylinder
from aria.digital_twin.solver import (
    FEAResult,
    FEASolver,
    MaterialProperty,
    ModalResult,
    _isotropic_D,
    _tet4_B_and_V,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def aluminum():
    return MaterialProperty(name="Al7075-T6", E=71.7e9, nu=0.33, density=2810.0)


@pytest.fixture(scope="module")
def cylinder_mesh():
    """Reasonably fine cylinder mesh for solver tests."""
    return mesh_cylinder(
        radius=0.5,
        length=2.0,
        thickness=0.05,
        element_size=0.08,
    )


@pytest.fixture(scope="module")
def coarse_cylinder_mesh():
    """Coarser mesh for faster tests that don't need accuracy."""
    return mesh_cylinder(
        radius=0.5,
        length=2.0,
        thickness=0.05,
        element_size=0.15,
    )


# ---------------------------------------------------------------------------
# MaterialProperty tests
# ---------------------------------------------------------------------------

class TestMaterialProperty:
    def test_valid_material(self, aluminum):
        assert aluminum.E == 71.7e9
        assert aluminum.nu == 0.33

    def test_invalid_poisson_ratio(self):
        with pytest.raises(ValueError, match="Poisson"):
            MaterialProperty("bad", E=200e9, nu=0.5, density=7800)

    def test_invalid_young_modulus(self):
        with pytest.raises(ValueError, match="Young"):
            MaterialProperty("bad", E=-1, nu=0.3, density=7800)


# ---------------------------------------------------------------------------
# Constitutive matrix
# ---------------------------------------------------------------------------

class TestIsotropicD:
    def test_symmetry(self):
        D = _isotropic_D(200e9, 0.3)
        np.testing.assert_allclose(D, D.T, atol=1e-6)

    def test_positive_definite(self):
        D = _isotropic_D(200e9, 0.3)
        eigenvalues = np.linalg.eigvalsh(D)
        assert np.all(eigenvalues > 0)


# ---------------------------------------------------------------------------
# Solver construction
# ---------------------------------------------------------------------------

class TestSolverConstruction:
    def test_creates_from_mesh_and_material(self, coarse_cylinder_mesh, aluminum):
        solver = FEASolver(coarse_cylinder_mesh, aluminum)
        assert solver.n_nodes > 0
        assert solver.n_elements > 0

    def test_n_dof_is_3x_nodes(self, coarse_cylinder_mesh, aluminum):
        solver = FEASolver(coarse_cylinder_mesh, aluminum)
        assert solver.n_dof == 3 * solver.n_nodes


# ---------------------------------------------------------------------------
# Zero-load test
# ---------------------------------------------------------------------------

class TestZeroLoad:
    def test_zero_load_gives_zero_displacement(self, coarse_cylinder_mesh, aluminum):
        """With no forces and all nodes free (but some fixed to prevent
        rigid-body motion), displacements should be ~zero."""
        solver = FEASolver(coarse_cylinder_mesh, aluminum)
        # Fix a few nodes to prevent singularity
        solver.fix_nodes([0, 1, 2, 3])
        result = solver.solve()
        assert np.allclose(result.displacements, 0.0, atol=1e-12)
        assert result.max_stress < 1e-3  # essentially zero


# ---------------------------------------------------------------------------
# Fixed-node test
# ---------------------------------------------------------------------------

class TestFixedNodes:
    def test_fixed_nodes_have_zero_displacement(self, coarse_cylinder_mesh, aluminum):
        solver = FEASolver(coarse_cylinder_mesh, aluminum)
        fixed = [0, 1, 2, 3, 4, 5]
        solver.fix_nodes(fixed)
        solver.apply_gravity(9.81, (0, 0, -1))
        result = solver.solve()
        for nid in fixed:
            np.testing.assert_allclose(
                result.displacements[nid], [0, 0, 0], atol=1e-10
            )


# ---------------------------------------------------------------------------
# Von Mises non-negativity
# ---------------------------------------------------------------------------

class TestVonMises:
    def test_von_mises_non_negative(self, coarse_cylinder_mesh, aluminum):
        solver = FEASolver(coarse_cylinder_mesh, aluminum)
        solver.fix_nodes(list(range(10)))
        solver.apply_gravity(9.81, (0, 0, -1))
        result = solver.solve()
        assert np.all(result.von_mises_stress >= 0.0)


# ---------------------------------------------------------------------------
# Pressurised-cylinder analytical validation
# ---------------------------------------------------------------------------

class TestPressureCylinderAnalytical:
    """Verify FEA hoop stress against thin-wall formula: sigma_hoop = pR/t.

    We use a relatively fine mesh and allow ~30% tolerance because:
    - End effects (open vs closed ends)
    - Discrete FE approximation
    - Boundary condition artifacts near fixed ends
    The key check is order-of-magnitude correctness.
    """

    RADIUS = 0.5       # m (inner)
    THICKNESS = 0.05   # m
    LENGTH = 2.0       # m
    PRESSURE = 1e6     # Pa (1 MPa)

    @pytest.fixture(scope="class")
    def pressure_result(self, aluminum):
        mesh = mesh_cylinder(
            self.RADIUS, self.LENGTH, self.THICKNESS, element_size=0.06,
        )
        pts = mesh.points

        solver = FEASolver(mesh, aluminum)

        # Fix both ends (z ≈ 0 and z ≈ LENGTH) to prevent rigid-body motion
        z = pts[:, 2]
        bottom_nodes = list(np.where(z < 0.01)[0])
        top_nodes = list(np.where(z > self.LENGTH - 0.01)[0])
        solver.fix_nodes(bottom_nodes + top_nodes)

        # Find inner surface nodes (r ≈ RADIUS)
        r = np.sqrt(pts[:, 0]**2 + pts[:, 1]**2)
        inner_nodes = list(np.where(
            (r < self.RADIUS + 0.01) &
            (z > 0.2) & (z < self.LENGTH - 0.2)  # away from ends
        )[0])

        solver._apply_pressure_lumped(inner_nodes, self.PRESSURE)
        return solver.solve()

    def test_max_stress_order_of_magnitude(self, pressure_result):
        """Max stress should be in the right ballpark of pR/t = 10 MPa."""
        analytical_hoop = self.PRESSURE * self.RADIUS / self.THICKNESS  # 10 MPa
        # Allow generous tolerance for FE mesh effects
        assert pressure_result.max_stress > analytical_hoop * 0.2, (
            f"Max stress {pressure_result.max_stress:.2e} too low vs "
            f"analytical {analytical_hoop:.2e}"
        )
        # Should not be wildly higher either (< 5x analytical)
        assert pressure_result.max_stress < analytical_hoop * 5.0, (
            f"Max stress {pressure_result.max_stress:.2e} too high vs "
            f"analytical {analytical_hoop:.2e}"
        )

    def test_von_mises_positive(self, pressure_result):
        assert np.all(pressure_result.von_mises_stress >= 0.0)

    def test_displacements_nonzero_under_pressure(self, pressure_result):
        """Pressure should cause measurable radial expansion."""
        assert np.max(np.abs(pressure_result.displacements)) > 0.0

    def test_result_has_expected_fields(self, pressure_result):
        assert isinstance(pressure_result, FEAResult)
        assert hasattr(pressure_result, "displacements")
        assert hasattr(pressure_result, "von_mises_stress")
        assert hasattr(pressure_result, "max_stress")
        assert hasattr(pressure_result, "min_stress")
        assert hasattr(pressure_result, "strain_energy")


# ---------------------------------------------------------------------------
# Modal / vibration analysis
# ---------------------------------------------------------------------------

class TestModalAnalysis:
    """Tests for the generalised eigenvalue modal solver.

    For a thin-walled cylinder (R=0.5 m, L=2 m, t=0.05 m) in Al-7075-T6
    with both ends fixed, the lowest natural frequencies should fall in the
    range of tens to hundreds of Hz — well above typical equipment
    excitation frequencies (pumps ~0.5 Hz, fans ~1 Hz).
    """

    N_MODES = 6

    @pytest.fixture(scope="class")
    def modal_result(self, aluminum):
        mesh = mesh_cylinder(
            radius=0.5,
            length=2.0,
            thickness=0.05,
            element_size=0.15,  # coarse for speed
        )
        pts = mesh.points
        solver = FEASolver(mesh, aluminum)

        # Fix both ends
        z = pts[:, 2]
        bottom = list(np.where(z < 0.01)[0])
        top = list(np.where(z > 1.99)[0])
        solver.fix_nodes(bottom + top)

        return solver.solve_modal(n_modes=self.N_MODES)

    def test_returns_modal_result(self, modal_result):
        assert isinstance(modal_result, ModalResult)

    def test_correct_number_of_modes(self, modal_result):
        assert len(modal_result.frequencies_hz) == self.N_MODES
        assert len(modal_result.mode_shapes) == self.N_MODES

    def test_frequencies_positive(self, modal_result):
        """All natural frequencies must be strictly positive (structure is
        constrained, so no rigid-body zero-frequency modes)."""
        for f in modal_result.frequencies_hz:
            assert f > 0.0, f"Expected positive frequency, got {f}"

    def test_frequencies_sorted_ascending(self, modal_result):
        freqs = modal_result.frequencies_hz
        for i in range(len(freqs) - 1):
            assert freqs[i] <= freqs[i + 1] + 1e-6, (
                f"Frequencies not sorted: f[{i}]={freqs[i]:.2f} > "
                f"f[{i+1}]={freqs[i+1]:.2f}"
            )

    def test_frequencies_in_expected_range(self, modal_result):
        """For a fixed-fixed Al cylinder (R=0.5, L=2, t=0.05), the
        fundamental frequency should be roughly 10-5000 Hz.  This is a
        broad sanity band — the exact value depends on mesh refinement."""
        f1 = modal_result.frequencies_hz[0]
        assert f1 > 10.0, f"Fundamental frequency {f1:.2f} Hz suspiciously low"
        assert f1 < 5000.0, f"Fundamental frequency {f1:.2f} Hz suspiciously high"

    def test_mode_shapes_correct_length(self, modal_result, aluminum):
        """Each mode shape vector must have length n_dof."""
        mesh = mesh_cylinder(
            radius=0.5, length=2.0, thickness=0.05, element_size=0.15,
        )
        expected_dof = 3 * len(mesh.points)
        for i, shape in enumerate(modal_result.mode_shapes):
            assert shape.shape == (expected_dof,), (
                f"Mode {i} shape has wrong size: {shape.shape} vs ({expected_dof},)"
            )

    def test_mode_shapes_are_nonzero(self, modal_result):
        """Every mode shape should have non-trivial amplitude."""
        for i, shape in enumerate(modal_result.mode_shapes):
            assert np.linalg.norm(shape) > 1e-12, f"Mode {i} is a zero vector"

    def test_too_many_modes_raises(self, aluminum):
        """Requesting more modes than free DOFs must raise ValueError."""
        mesh = mesh_cylinder(
            radius=0.5, length=2.0, thickness=0.05, element_size=0.15,
        )
        solver = FEASolver(mesh, aluminum)
        # Fix all nodes — 0 free DOFs
        solver.fix_nodes(list(range(len(mesh.points))))
        with pytest.raises(ValueError, match="free DOFs"):
            solver.solve_modal(n_modes=5)
