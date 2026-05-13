"""Tests for aria.digital_twin.lbm_cfd_3d — D3Q19 Lattice Boltzmann CFD."""
from __future__ import annotations

import math

import numpy as np
import pytest

from aria.digital_twin.lbm_cfd_3d import (
    CFD3DResult,
    HabitatCFD3D,
    _CX, _CY, _CZ, _W, _OPP, _NQ, _CS2,
)


# ════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def small_cfd() -> HabitatCFD3D:
    """Small grid for fast tests (nx=20, ny=8, nz=8)."""
    return HabitatCFD3D(nx=20, ny=8, nz=8, omega_rad_s=0.1047)


@pytest.fixture
def result(small_cfd: HabitatCFD3D) -> CFD3DResult:
    return small_cfd.run(n_steps=200)


# ════════════════════════════════════════════════════════════════
#  D3Q19 LATTICE CONSTANTS
# ════════════════════════════════════════════════════════════════

class TestLatticeConstants:

    def test_nq_is_19(self):
        assert _NQ == 19

    def test_weights_sum_to_one(self):
        assert abs(float(np.sum(_W)) - 1.0) < 1e-12

    def test_rest_weight(self):
        assert abs(_W[0] - 1.0 / 3.0) < 1e-12

    def test_axis_aligned_weights(self):
        for i in range(1, 7):
            assert abs(_W[i] - 1.0 / 18.0) < 1e-12

    def test_diagonal_weights(self):
        for i in range(7, 19):
            assert abs(_W[i] - 1.0 / 36.0) < 1e-12

    def test_opposite_directions_are_symmetric(self):
        """_OPP[q] must be the index of −(cx,cy,cz)."""
        for q in range(_NQ):
            opp = _OPP[q]
            assert _CX[opp] == -_CX[q]
            assert _CY[opp] == -_CY[q]
            assert _CZ[opp] == -_CZ[q]

    def test_opposite_is_its_own_inverse(self):
        for q in range(_NQ):
            assert _OPP[_OPP[q]] == q

    def test_cs2_value(self):
        assert abs(_CS2 - 1.0 / 3.0) < 1e-12

    def test_velocities_are_integers(self):
        for arr in (_CX, _CY, _CZ):
            for val in arr:
                assert int(val) == val

    def test_velocity_magnitudes_max_sqrt2(self):
        """D3Q19 has no body-diagonal velocities — max speed = √2."""
        speeds = np.sqrt(_CX**2 + _CY**2 + _CZ**2)
        assert float(speeds.max()) <= math.sqrt(2) + 1e-10


# ════════════════════════════════════════════════════════════════
#  GRID CREATION
# ════════════════════════════════════════════════════════════════

class TestGridCreation:

    def test_distribution_function_shape(self):
        cfd = HabitatCFD3D(nx=20, ny=8, nz=8)
        assert cfd.f.shape == (_NQ, 8, 8, 20)
        assert cfd.g.shape == (_NQ, 8, 8, 20)

    def test_macroscopic_field_shapes(self):
        cfd = HabitatCFD3D(nx=20, ny=8, nz=8)
        assert cfd.rho.shape == (8, 8, 20)
        assert cfd.ux.shape == (8, 8, 20)
        assert cfd.uy.shape == (8, 8, 20)
        assert cfd.uz.shape == (8, 8, 20)
        assert cfd.T.shape == (8, 8, 20)

    def test_initial_density_uniform(self, small_cfd: HabitatCFD3D):
        assert np.allclose(small_cfd.rho, 1.0)

    def test_initial_velocity_zero(self, small_cfd: HabitatCFD3D):
        assert np.allclose(small_cfd.ux, 0.0)
        assert np.allclose(small_cfd.uy, 0.0)
        assert np.allclose(small_cfd.uz, 0.0)

    def test_initial_temperature_gradient(self, small_cfd: HabitatCFD3D):
        """Floor (y=0) should be hot, ceiling (y=ny-1) should be cool."""
        T_floor = float(small_cfd.T[:, 0, :].mean())
        T_ceil = float(small_cfd.T[:, -1, :].mean())
        assert T_floor > T_ceil

    def test_default_omega(self):
        cfd = HabitatCFD3D()
        assert cfd.omega_rad_s == pytest.approx(2.0 * math.pi / 60.0, rel=1e-3)

    def test_tau_stability(self, small_cfd: HabitatCFD3D):
        """τ > 0.5 is required for LBM stability."""
        assert small_cfd.tau > 0.5


# ════════════════════════════════════════════════════════════════
#  EQUILIBRIUM DISTRIBUTION
# ════════════════════════════════════════════════════════════════

class TestEquilibriumDistribution:

    def test_feq_sums_to_density(self, small_cfd: HabitatCFD3D):
        """Σ_q f_eq_q = ρ (Kruger eq. 4.43)."""
        feq = small_cfd._compute_feq(
            small_cfd.rho, small_cfd.ux, small_cfd.uy, small_cfd.uz
        )
        rho_recovered = np.sum(feq, axis=0)
        assert np.allclose(rho_recovered, small_cfd.rho, atol=1e-12)

    def test_geq_sums_to_temperature(self, small_cfd: HabitatCFD3D):
        """Σ_q g_eq_q = T (He et al. 1998)."""
        geq = small_cfd._compute_geq(
            small_cfd.T, small_cfd.ux, small_cfd.uy, small_cfd.uz
        )
        T_recovered = np.sum(geq, axis=0)
        assert np.allclose(T_recovered, small_cfd.T, atol=1e-12)

    def test_feq_momentum_x(self, small_cfd: HabitatCFD3D):
        """Σ_q f_eq_q c_xq = ρ u_x."""
        feq = small_cfd._compute_feq(
            small_cfd.rho, small_cfd.ux, small_cfd.uy, small_cfd.uz
        )
        mx = sum(feq[q] * _CX[q] for q in range(_NQ))
        expected = small_cfd.rho * small_cfd.ux
        assert np.allclose(mx, expected, atol=1e-12)

    def test_feq_nonnegative_at_rest(self, small_cfd: HabitatCFD3D):
        """At zero velocity, all f_eq ≥ 0."""
        feq = small_cfd._compute_feq(
            small_cfd.rho,
            np.zeros_like(small_cfd.ux),
            np.zeros_like(small_cfd.uy),
            np.zeros_like(small_cfd.uz),
        )
        assert np.all(feq >= 0.0)


# ════════════════════════════════════════════════════════════════
#  SIMULATION RUNS
# ════════════════════════════════════════════════════════════════

class TestSimulationRuns:

    def test_result_type(self, result: CFD3DResult):
        assert isinstance(result, CFD3DResult)

    def test_velocity_field_shape(self, result: CFD3DResult):
        """velocity_field shape should be (3, nz, ny, nx)."""
        assert result.velocity_field.shape == (3, 8, 8, 20)

    def test_temperature_field_shape(self, result: CFD3DResult):
        assert result.temperature_field.shape == (8, 8, 20)

    def test_velocity_nonzero_after_run(self, result: CFD3DResult):
        """Buoyancy and Coriolis drive nonzero flow."""
        speed = np.sqrt(
            result.velocity_field[0] ** 2
            + result.velocity_field[1] ** 2
            + result.velocity_field[2] ** 2
        )
        assert float(np.max(speed)) > 0.0

    def test_max_velocity_positive(self, result: CFD3DResult):
        assert result.max_velocity_ms > 0.0

    def test_density_mass_conservation(self, small_cfd: HabitatCFD3D):
        """Total mass (Σρ) should be conserved to floating-point precision."""
        mass_0 = float(np.sum(small_cfd.rho))
        small_cfd.step(50)
        mass_50 = float(np.sum(small_cfd.rho))
        assert abs(mass_50 - mass_0) / mass_0 < 1e-8

    def test_step_advances_state(self, small_cfd: HabitatCFD3D):
        """After stepping, f must differ from the initial equilibrium state."""
        f_before = small_cfd.f.copy()
        small_cfd.step(10)
        # Use array_equal (exact comparison) since any BGK step modifies f
        assert not np.array_equal(small_cfd.f, f_before)


# ════════════════════════════════════════════════════════════════
#  TEMPERATURE
# ════════════════════════════════════════════════════════════════

class TestTemperature:

    def test_temperature_bounded(self, result: CFD3DResult):
        """Temperature must stay between boundary values."""
        T = result.temperature_field
        assert np.all(T >= 20.0 - 0.5)
        assert np.all(T <= 28.0 + 0.5)

    def test_mean_temperature_within_range(self, result: CFD3DResult):
        T_mean = float(result.temperature_field.mean())
        assert 20.0 <= T_mean <= 28.0

    def test_floor_warmer_than_ceiling(self, result: CFD3DResult):
        T = result.temperature_field
        T_floor_mean = float(T[:, 0, :].mean())
        T_ceil_mean = float(T[:, -1, :].mean())
        assert T_floor_mean > T_ceil_mean


# ════════════════════════════════════════════════════════════════
#  CORIOLIS
# ════════════════════════════════════════════════════════════════

class TestCoriolisDeflection:

    def test_coriolis_deflection_nonnegative(self, result: CFD3DResult):
        assert result.coriolis_deflection_deg >= 0.0

    def test_coriolis_deflection_finite(self, result: CFD3DResult):
        assert math.isfinite(result.coriolis_deflection_deg)

    def test_coriolis_deflection_at_most_90_deg(self, result: CFD3DResult):
        assert result.coriolis_deflection_deg <= 90.0

    def test_zero_omega_less_deflection_than_rotating(self):
        """With ω=0 the Coriolis x-force is zero — should give less tangential flow."""
        cfd_rot = HabitatCFD3D(nx=16, ny=6, nz=6, omega_rad_s=0.1047)
        cfd_no = HabitatCFD3D(nx=16, ny=6, nz=6, omega_rad_s=0.0)
        res_rot = cfd_rot.run(n_steps=150)
        res_no = cfd_no.run(n_steps=150)
        assert res_rot.coriolis_deflection_deg >= res_no.coriolis_deflection_deg


# ════════════════════════════════════════════════════════════════
#  SMAGORINSKY LES
# ════════════════════════════════════════════════════════════════

class TestSmagorinsky:

    def test_tau_eff_shape(self, small_cfd: HabitatCFD3D):
        tau_eff = small_cfd._smagorinsky_tau()
        assert tau_eff.shape == (small_cfd.nz, small_cfd.ny, small_cfd.nx)

    def test_tau_eff_above_stability_limit(self, small_cfd: HabitatCFD3D):
        """τ_eff ≥ 0.505 everywhere (stability floor)."""
        tau_eff = small_cfd._smagorinsky_tau()
        assert float(np.min(tau_eff)) >= 0.505

    def test_smagorinsky_zero_returns_uniform_tau(self):
        cfd = HabitatCFD3D(nx=12, ny=6, nz=6, cs_smagorinsky=0.0)
        tau_eff = cfd._smagorinsky_tau()
        assert np.allclose(tau_eff, cfd.tau)

    def test_turbulent_viscosity_populated_after_run(self, result: CFD3DResult):
        """nu_t_ratio populated when Smagorinsky is active."""
        assert result.turbulent_viscosity_field is not None
        assert result.turbulent_viscosity_field.shape == (8, 8, 20)


# ════════════════════════════════════════════════════════════════
#  PRESSURE FIELD
# ════════════════════════════════════════════════════════════════

class TestPressureField:

    def test_pressure_field_shape(self, result: CFD3DResult):
        assert result.pressure_field.shape == (8, 8, 20)

    def test_pressure_mean_near_zero(self, result: CFD3DResult):
        """Pressure field is relative to mean — mean should be ~0."""
        assert abs(float(result.pressure_field.mean())) < 0.1
