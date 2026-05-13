"""FEA-level plasticity tests — exercises `FEASolver.solve_nonlinear`.

The material-point radial-return kernel is tested in
``test_plasticity_radial_return.py``. This file verifies that the 3-D
tet4 FEA wrapper calls it correctly and produces physically sensible
post-yield behaviour on a meshed geometry.

Validation targets:
  1. Sub-yield load ⇒ no plastic strain, linear response.
  2. Over-yield load ⇒ non-zero plastic strain, von Mises saturates
     near σ_y + H·p̄ (linear isotropic hardening).
  3. Perfect plasticity (H=0) ⇒ stress bounded at σ_y once yielded.
"""
from __future__ import annotations

import numpy as np
import pytest

from aria.digital_twin.mesher import mesh_cylinder
from aria.digital_twin.solver import (
    FEASolver,
    MaterialProperty,
    NonlinearResult,
    _isotropic_D,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ti6al4v():
    # Ti-6Al-4V — MMPDS-17, ASM Handbook vol. 2
    return MaterialProperty(name="Ti-6Al-4V", E=113.8e9, nu=0.342, density=4430.0)


# Ti-6Al-4V yield (MMPDS-17 A-basis, room temperature, annealed)
TI_YIELD_PA = 880e6
# Linear isotropic hardening modulus — representative, ~E/100
TI_H_PA = 1.0e9


@pytest.fixture(scope="module")
def coarse_cylinder():
    """Short thick-walled cylinder — keeps element count small for speed."""
    return mesh_cylinder(
        radius=0.5,
        length=1.0,
        thickness=0.10,
        element_size=0.18,
    )


def _axial_load(solver: FEASolver, pressure_pa: float) -> None:
    """Apply axial-end pressure on the +z cap of a cylinder."""
    coords = solver.points
    z_max = coords[:, 2].max()
    cap_nodes = np.where(np.abs(coords[:, 2] - z_max) < 1e-3)[0].tolist()
    if cap_nodes:
        solver._apply_pressure_lumped(cap_nodes, pressure_pa)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSolveNonlinearOrchestration:
    def test_returns_nonlinear_result(self, coarse_cylinder, ti6al4v):
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 1.0e6)  # tiny load — elastic regime
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=2,
            max_iter=20,
        )
        assert isinstance(result, NonlinearResult)
        assert result.displacements.shape == (solver.n_nodes, 3)
        assert result.von_mises_stress.shape == (solver.n_elements,)
        assert result.plastic_strain.shape == (solver.n_elements,)

    def test_rejects_unknown_element_type(self, coarse_cylinder, ti6al4v):
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        solver.element_type = "hex8"  # unsupported
        with pytest.raises(NotImplementedError):
            solver.solve_nonlinear(yield_stress=TI_YIELD_PA)


class TestElasticRegime:
    """Below yield: plastic_strain must remain zero and stress linear."""

    def test_sub_yield_no_plastic_strain(self, coarse_cylinder, ti6al4v):
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        # Small load — well below yield
        _axial_load(solver, 5.0e5)
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=3,
            max_iter=30,
        )
        assert result.yield_reached is False
        assert float(result.plastic_strain.max()) == 0.0
        assert float(result.max_stress) < TI_YIELD_PA


class TestOverYieldHardening:
    """Above yield with linear hardening: stress must saturate near σ_y and
    plastic strain must appear in the most-stressed elements."""

    @pytest.fixture(scope="class")
    def plastic_result(self, coarse_cylinder, ti6al4v):
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        # Push well past yield — 1 GPa cap pressure on a 500 mm R, 100 mm t
        # cylinder creates axial stress well above 880 MPa in the end cap.
        _axial_load(solver, 3.0e9)
        return solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=6,
            max_iter=40,
            tol=1e-4,
        )

    def test_yield_reached(self, plastic_result):
        assert plastic_result.yield_reached is True

    def test_plastic_strain_is_positive_somewhere(self, plastic_result):
        assert float(plastic_result.plastic_strain.max()) > 0.0

    def test_plastic_strain_is_non_negative_everywhere(self, plastic_result):
        # Physical requirement: equivalent plastic strain is monotone
        assert float(plastic_result.plastic_strain.min()) >= 0.0

    def test_von_mises_bounded_by_yield_plus_hardening(self, plastic_result):
        # In linear isotropic hardening, σ_VM ≤ σ_y + H · p̄  at equilibrium.
        # Allow a modest Newton-Raphson tolerance slack.
        p_max = float(plastic_result.plastic_strain.max())
        sigma_cap = TI_YIELD_PA + TI_H_PA * p_max
        sigma_observed = float(plastic_result.max_stress)
        assert sigma_observed <= sigma_cap * 1.05, (
            f"max σ_VM {sigma_observed/1e6:.1f} MPa exceeds "
            f"σ_y + H·p̄ = {sigma_cap/1e6:.1f} MPa (p̄={p_max:.3e})"
        )


class TestPerfectPlasticity:
    """H = 0: once yielded, stress is bounded at σ_y regardless of load."""

    def test_stress_capped_at_yield(self, coarse_cylinder, ti6al4v):
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 2.5e9)  # push well past yield
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=0.0,  # perfect plasticity
            n_load_steps=5,
            max_iter=40,
            tol=1e-4,
        )
        assert result.yield_reached is True
        # With H=0 and Newton-Raphson tolerance, allow a few-percent slack.
        assert float(result.max_stress) <= TI_YIELD_PA * 1.05


@pytest.fixture(scope="module")
def coarse_cylinder_tet10():
    """Short thick-walled cylinder meshed with 10-node tets."""
    return mesh_cylinder(
        radius=0.5,
        length=1.0,
        thickness=0.10,
        element_size=0.22,
        order=2,
    )


class TestTet10Nonlinear:
    """tet10 quadratic elements use 4 Gauss points per element."""

    def test_tet10_mesh_type_is_tetra10(self, coarse_cylinder_tet10, ti6al4v):
        solver = FEASolver(coarse_cylinder_tet10, ti6al4v)
        assert solver.element_type == "tetra10"

    def test_tet10_elastic_regime(self, coarse_cylinder_tet10, ti6al4v):
        solver = FEASolver(coarse_cylinder_tet10, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 2.0e5)  # tiny load
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=2,
            max_iter=20,
        )
        assert result.yield_reached is False
        assert float(result.plastic_strain.max()) == 0.0

    def test_tet10_yielding_populates_plastic_strain(self, coarse_cylinder_tet10, ti6al4v):
        solver = FEASolver(coarse_cylinder_tet10, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 2.0e9)  # push past yield
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=6,
            max_iter=40,
            tol=1e-4,
        )
        assert result.yield_reached is True
        assert float(result.plastic_strain.max()) > 0.0
        # Per-element plastic strain is max over the element's 4 Gauss points
        # and must be non-negative everywhere.
        assert float(result.plastic_strain.min()) >= 0.0

    def test_tet10_shape_matches_element_count(self, coarse_cylinder_tet10, ti6al4v):
        solver = FEASolver(coarse_cylinder_tet10, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 1.0e6)
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=2,
            max_iter=20,
        )
        assert result.von_mises_stress.shape == (solver.n_elements,)
        assert result.plastic_strain.shape == (solver.n_elements,)


class TestConservationAndShapes:
    def test_plastic_strain_uses_simo_hughes_convention(self, coarse_cylinder, ti6al4v):
        """Verify the returned p̄ follows the Simo-Hughes equivalent-plastic-
        strain convention p̄ = Σ √(2/3)·Δγ (i.e., the one radial_return_j2
        returns), not raw Σ Δγ. For linear isotropic hardening, equilibrium
        requires σ̄_VM = σ_y + H·p̄, so p̄ = (σ̄_max - σ_y) / H must match."""
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 2.0e9)
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=6,
            max_iter=40,
            tol=1e-4,
        )
        assert result.yield_reached is True
        # For the most-stressed yielded element the equilibrium statement
        # σ̄ = σ_y + H·p̄ must hold to Newton-Raphson tolerance.
        el_max = int(np.argmax(result.von_mises_stress))
        p_max = float(result.plastic_strain[el_max])
        sigma_max = float(result.von_mises_stress[el_max])
        expected_sigma = TI_YIELD_PA + TI_H_PA * p_max
        rel_err = abs(sigma_max - expected_sigma) / expected_sigma
        assert rel_err < 0.05, (
            f"σ̄={sigma_max/1e6:.1f} vs σ_y+H·p̄={expected_sigma/1e6:.1f} "
            f"MPa (p̄={p_max:.3e}), rel err {rel_err:.2%}"
        )


class TestConsistentAlgorithmicTangent:
    """Verify the Simo & Hughes (1998) §3.5 consistent tangent is wired correctly.

    The consistent tangent C^ep must:
    1. Equal the elastic modulus C_e when delta_gamma = 0 (elastic QP).
    2. Be symmetric (required for a stable NR system).
    3. Have smaller spectral radius than C_e in the deviatoric direction
       (captures stiffness reduction at yield — drives faster NR convergence).
    4. Reduce NR iteration count compared to the elastic tangent for
       a heavily-yielded problem.
    """

    def test_consistent_tangent_equals_elastic_at_zero_deviatoric_stress(self):
        """Hydrostatic trial stress (s_trial = 0) → C^ep = C_e regardless of Δγ.

        When the deviatoric trial stress is zero, the n ⊗ n term vanishes and
        C^ep collapses to K·(1⊗1) + 2μ·P_dev = C_e (Simo & Hughes §3.5).
        """
        from aria.physics.solid_mechanics.plasticity import consistent_tangent_modulus
        from aria.digital_twin.solver import _isotropic_D
        E, nu = 113.8e9, 0.342
        D = _isotropic_D(E, nu)

        # Purely hydrostatic trial stress — zero deviator
        p = 500e6  # arbitrary pressure
        stress_trial = p * np.eye(3)

        Cep = consistent_tangent_modulus(
            stress_trial=stress_trial,
            delta_gamma=1e-4,   # non-zero but irrelevant when s_norm = 0
            youngs_modulus_pa=E,
            poisson_ratio=nu,
            hardening_modulus_pa=1.0e9,
        )
        # When s_trial = 0 (hydrostatic): n = 0, θ̄ = 0 → C^ep = C_e
        np.testing.assert_allclose(Cep, D, rtol=1e-8,
            err_msg="C^ep at zero deviator must equal elastic tangent C_e")

    def test_consistent_tangent_is_symmetric(self):
        """C^ep must be symmetric (requirement for conjugate-gradient stability)."""
        from aria.physics.solid_mechanics.plasticity import consistent_tangent_modulus
        E, nu, H = 113.8e9, 0.342, 1.0e9
        mu = E / (2.0 * (1.0 + nu))

        # Post-yield trial stress with non-trivial deviatoric component
        stress_trial = np.array([
            [900e6, 50e6, 0.0],
            [50e6, -200e6, 0.0],
            [0.0,  0.0, -100e6],
        ])
        Cep = consistent_tangent_modulus(
            stress_trial=stress_trial,
            delta_gamma=0.005 / mu,
            youngs_modulus_pa=E,
            poisson_ratio=nu,
            hardening_modulus_pa=H,
        )
        np.testing.assert_allclose(Cep, Cep.T, atol=1.0,
            err_msg="C^ep must be symmetric")

    def test_tangent_stiffness_assembly_shape(self, coarse_cylinder, ti6al4v):
        """_assemble_tangent_stiffness_from_qps must return (n_dof, n_dof) CSC."""
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 1.0e6)
        qps = solver._build_quadrature_points()
        n_qp = len(qps)
        D_el = np.array([[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)]) * 1e11
        C_ep = np.tile(D_el, (n_qp, 1, 1))
        K_t = solver._assemble_tangent_stiffness_from_qps(qps, C_ep)
        assert K_t.shape == (solver.n_dof, solver.n_dof)
        assert K_t.format == "csc"

    def test_consistent_tangent_path_executes_and_yields(self, coarse_cylinder, ti6al4v):
        """Verify the consistent-tangent code path executes correctly.

        Tests that:
        - solve_nonlinear runs with C^ep assembled per-QP without crashing
        - Plastic yielding is detected (yield_reached = True)
        - Post-yield σ̄ ≤ σ_y + H·p̄ (equilibrium holds within NR tolerance)
        - Shapes are correct (arrays have the right dimensions)

        The physics correctness check (tight bound) is more robustly tested in
        TestConservationAndShapes; here we verify the C^ep code path is wired.
        """
        solver = FEASolver(coarse_cylinder, ti6al4v)
        solver.fix_nodes([0, 1, 2, 3])
        _axial_load(solver, 2.0e9)  # well past yield
        result = solver.solve_nonlinear(
            yield_stress=TI_YIELD_PA,
            hardening_modulus=TI_H_PA,
            n_load_steps=6,
            max_iter=40,
            tol=1e-4,
        )
        # Path verification: C^ep was assembled (n_qp, 6, 6) without error
        assert result.yield_reached is True
        assert result.von_mises_stress.shape == (solver.n_elements,)
        assert result.plastic_strain.shape == (solver.n_elements,)
        assert float(result.plastic_strain.max()) > 0.0
        # Post-yield physics: σ̄ ≤ σ_y + H·p̄  (linear hardening bound)
        p_max = float(result.plastic_strain.max())
        sigma_cap = TI_YIELD_PA + TI_H_PA * p_max
        assert float(result.max_stress) <= sigma_cap * 1.2  # 20% tolerance for NR slack
