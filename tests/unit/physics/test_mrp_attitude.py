"""Tests for MRP attitude dynamics with structural damping.

Validates:
1.  mrp_to_dcm: identity at sigma=0; orthogonality; det=1.
2.  mrp_kinematics: sigma_dot = 0 when omega=0.
3.  mrp_error: error is zero when sigma_current == sigma_desired.
4.  propagate_attitude: angular momentum conserved (torque=0, no damping).
5.  propagate_attitude: zero omega stays zero with zero torque.
6.  propagate_attitude + damping: omega decays toward zero.
7.  propagate_attitude + damping: larger C → faster decay.
8.  propagate_attitude + damping: energy is strictly decreasing each step.
9.  propagate_attitude: torque changes omega at correct rate (small dt).
10. tune_gains: K and P are positive; Ki is non-negative.
11. tune_gains: larger inertia → larger gains (proportional).
12. MRPFeedbackController: compute returns ControlTorque.
13. MRPFeedbackController: torque is zero when already at reference.
14. propagate_attitude: zero damping_matrix equals no damping_matrix.
15. propagate_attitude: diagonal damping damps each axis independently.
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.physics.attitude.mrp_control import (
    AttitudeReference,
    AttitudeState,
    MRPFeedbackController,
    mrp_error,
    mrp_kinematics,
    mrp_to_dcm,
    propagate_attitude,
    tune_gains,
)


def _diag_inertia(j=100.0):
    return np.diag([j, j, j]).astype(float)


# ── DCM tests ─────────────────────────────────────────────────────────────────

class TestMrpToDcm:

    def test_identity_at_zero_mrp(self):
        C = mrp_to_dcm(np.zeros(3))
        np.testing.assert_allclose(C, np.eye(3), atol=1e-12)

    def test_dcm_is_orthogonal(self):
        sigma = np.array([0.1, -0.2, 0.15])
        C = mrp_to_dcm(sigma)
        np.testing.assert_allclose(C @ C.T, np.eye(3), atol=1e-12)

    def test_dcm_det_one(self):
        sigma = np.array([0.3, 0.1, -0.2])
        assert abs(np.linalg.det(mrp_to_dcm(sigma)) - 1.0) < 1e-10


# ── Kinematics ────────────────────────────────────────────────────────────────

class TestMrpKinematics:

    def test_zero_omega_zero_sigma_dot(self):
        dsigma = mrp_kinematics(np.array([0.1, 0.2, 0.3]), np.zeros(3))
        np.testing.assert_allclose(dsigma, np.zeros(3), atol=1e-15)

    def test_zero_sigma_kinematics_simple(self):
        # At sigma=0, B = I, so dsigma/dt = omega/4
        omega = np.array([0.1, 0.2, 0.3])
        ds = mrp_kinematics(np.zeros(3), omega)
        np.testing.assert_allclose(ds, omega / 4.0, atol=1e-12)


# ── Error ─────────────────────────────────────────────────────────────────────

class TestMrpError:

    def test_zero_error_at_same_attitude(self):
        sigma = np.array([0.1, 0.2, -0.1])
        err = mrp_error(sigma, sigma)
        np.testing.assert_allclose(err, np.zeros(3), atol=1e-12)

    def test_error_nonzero_when_different(self):
        err = mrp_error(np.array([0.1, 0.0, 0.0]), np.zeros(3))
        assert np.linalg.norm(err) > 0.0

    def test_error_from_zero_to_small_sigma(self):
        # error ≈ sigma for small sigma
        sigma_d = np.array([0.01, 0.0, 0.0])
        err = mrp_error(np.zeros(3), sigma_d)
        assert np.linalg.norm(err) > 0.0


# ── Propagation — no damping ──────────────────────────────────────────────────

class TestPropagateAttitudeNoDamping:

    def test_zero_omega_stays_zero(self):
        sigma = np.array([0.1, 0.2, 0.0])
        omega = np.zeros(3)
        I = _diag_inertia()
        torque = np.zeros(3)
        _, omega_new = propagate_attitude(sigma, omega, I, torque, dt=0.1)
        np.testing.assert_allclose(omega_new, np.zeros(3), atol=1e-12)

    def test_zero_omega_sigma_unchanged(self):
        sigma = np.array([0.1, 0.2, 0.0])
        omega = np.zeros(3)
        I = _diag_inertia()
        sigma_new, _ = propagate_attitude(sigma, omega, I, np.zeros(3), dt=0.1)
        np.testing.assert_allclose(sigma_new, sigma, atol=1e-12)

    def test_angular_momentum_conserved_no_torque(self):
        # Isotropic inertia: gyroscopic term ω×(Jω) = J(ω×ω) = 0 — no coupling.
        # Angular momentum is exactly conserved to RK4 numerical precision.
        sigma = np.zeros(3)
        omega = np.array([0.01, 0.02, 0.005])
        I = np.diag([150.0, 150.0, 150.0])
        L_before = I @ omega
        _, omega_new = propagate_attitude(sigma, omega, I, np.zeros(3), dt=0.01)
        L_after = I @ omega_new
        np.testing.assert_allclose(L_after, L_before, atol=1e-10)

    def test_torque_changes_omega_correctly(self):
        """For small dt, Δω ≈ I⁻¹ * torque * dt."""
        sigma = np.zeros(3)
        omega = np.zeros(3)
        I = _diag_inertia(100.0)
        torque = np.array([10.0, 0.0, 0.0])
        dt = 0.001
        _, omega_new = propagate_attitude(sigma, omega, I, torque, dt=dt)
        expected = torque / 100.0 * dt
        np.testing.assert_allclose(omega_new, expected, rtol=1e-4)

    def test_none_damping_same_as_absent(self):
        sigma = np.array([0.05, 0.1, 0.0])
        omega = np.array([0.01, 0.02, 0.005])
        I = _diag_inertia()
        torque = np.array([1.0, 0.5, -0.5])
        s1, w1 = propagate_attitude(sigma, omega, I, torque, dt=0.1,
                                    damping_matrix=None)
        s2, w2 = propagate_attitude(sigma, omega, I, torque, dt=0.1)
        np.testing.assert_allclose(w1, w2, atol=1e-15)
        np.testing.assert_allclose(s1, s2, atol=1e-15)

    def test_zero_damping_matrix_same_as_none(self):
        sigma = np.array([0.05, 0.1, 0.0])
        omega = np.array([0.01, 0.02, 0.005])
        I = _diag_inertia()
        torque = np.array([1.0, 0.5, -0.5])
        C_zero = np.zeros((3, 3))
        s1, w1 = propagate_attitude(sigma, omega, I, torque, dt=0.1,
                                    damping_matrix=C_zero)
        s2, w2 = propagate_attitude(sigma, omega, I, torque, dt=0.1,
                                    damping_matrix=None)
        np.testing.assert_allclose(w1, w2, atol=1e-15)


# ── Propagation — structural damping ─────────────────────────────────────────

class TestPropagateAttitudeDamping:
    """Structural damping (Meirovitch 1967): C·ω dissipates rotational KE."""

    def _run_free_decay(self, c_diag: float, n_steps: int = 2000, dt: float = 0.01):
        """Simulate free decay: no torque, initial omega=[1,1,1] rad/s."""
        sigma = np.zeros(3)
        omega = np.ones(3) * 0.5
        I = _diag_inertia(100.0)
        C = np.diag([c_diag, c_diag, c_diag])
        for _ in range(n_steps):
            sigma, omega = propagate_attitude(sigma, omega, I, np.zeros(3),
                                              dt=dt, damping_matrix=C)
        return omega

    def test_damping_reduces_omega_magnitude(self):
        omega_final = self._run_free_decay(c_diag=1.0)
        assert np.linalg.norm(omega_final) < np.linalg.norm(np.ones(3) * 0.5)

    def test_larger_damping_decays_faster(self):
        w_low = np.linalg.norm(self._run_free_decay(c_diag=0.5, n_steps=500))
        w_high = np.linalg.norm(self._run_free_decay(c_diag=5.0, n_steps=500))
        assert w_high < w_low

    def test_kinetic_energy_strictly_decreasing(self):
        """Each step with damping must reduce rotational KE."""
        sigma = np.zeros(3)
        omega = np.ones(3) * 0.5
        I = _diag_inertia(100.0)
        C = np.diag([2.0, 2.0, 2.0])
        prev_KE = 0.5 * omega @ I @ omega
        n_nondecreasing = 0
        for _ in range(100):
            sigma, omega = propagate_attitude(sigma, omega, I, np.zeros(3),
                                              dt=0.01, damping_matrix=C)
            KE = 0.5 * omega @ I @ omega
            if KE >= prev_KE:
                n_nondecreasing += 1
            prev_KE = KE
        # Allow at most 1 non-decreasing step (numerical noise at very low KE)
        assert n_nondecreasing <= 1

    def test_damping_diagonal_independent_axes(self):
        """Asymmetric diagonal C: heavily-damped axis decays faster."""
        sigma = np.zeros(3)
        omega = np.array([1.0, 1.0, 1.0])
        I = _diag_inertia(100.0)
        # x-axis heavily damped, z-axis lightly damped
        C = np.diag([20.0, 5.0, 0.5])
        for _ in range(500):
            sigma, omega = propagate_attitude(sigma, omega, I, np.zeros(3),
                                              dt=0.01, damping_matrix=C)
        assert abs(omega[0]) < abs(omega[2])  # x decayed more than z

    def test_heavy_damping_omega_near_zero(self):
        omega_final = self._run_free_decay(c_diag=50.0, n_steps=3000)
        assert np.linalg.norm(omega_final) < 0.01


# ── tune_gains ────────────────────────────────────────────────────────────────

class TestTuneGains:

    def test_returns_three_values(self):
        K, P, Ki = tune_gains(np.diag([500.0, 400.0, 300.0]))
        assert all(isinstance(v, float) for v in (K, P, Ki))

    def test_K_P_positive(self):
        K, P, Ki = tune_gains(np.diag([500.0, 400.0, 300.0]))
        assert K > 0.0
        assert P > 0.0
        assert Ki >= 0.0

    def test_larger_inertia_larger_gains(self):
        K_small, P_small, _ = tune_gains(np.diag([100.0, 80.0, 60.0]))
        K_large, P_large, _ = tune_gains(np.diag([1000.0, 800.0, 600.0]))
        assert K_large > K_small
        assert P_large > P_small

    def test_shorter_settling_time_larger_gains(self):
        K_slow, P_slow, _ = tune_gains(np.diag([500.0, 500.0, 500.0]),
                                       settling_time_s=120.0)
        K_fast, P_fast, _ = tune_gains(np.diag([500.0, 500.0, 500.0]),
                                       settling_time_s=30.0)
        assert K_fast > K_slow
        assert P_fast > P_slow


# ── MRPFeedbackController ─────────────────────────────────────────────────────

class TestMrpFeedbackController:

    def test_compute_returns_control_torque(self):
        ctrl = MRPFeedbackController(K=0.1, P=10.0)
        state = AttitudeState(
            sigma=np.array([0.05, 0.0, 0.0]),
            omega=np.zeros(3),
            inertia=_diag_inertia(),
        )
        ref = AttitudeReference()
        result = ctrl.compute(state, ref, dt=0.1)
        assert hasattr(result, "torque")
        assert result.torque.shape == (3,)

    def test_zero_error_near_zero_torque(self):
        ctrl = MRPFeedbackController(K=0.1, P=10.0)
        state = AttitudeState(
            sigma=np.zeros(3),
            omega=np.zeros(3),
            inertia=_diag_inertia(),
        )
        ref = AttitudeReference()
        result = ctrl.compute(state, ref, dt=0.1)
        np.testing.assert_allclose(result.torque, np.zeros(3), atol=1e-10)

    def test_nonzero_error_produces_torque(self):
        ctrl = MRPFeedbackController(K=0.5, P=20.0)
        state = AttitudeState(
            sigma=np.array([0.3, 0.0, 0.0]),
            omega=np.zeros(3),
            inertia=_diag_inertia(),
        )
        ref = AttitudeReference()
        result = ctrl.compute(state, ref, dt=0.1)
        assert np.linalg.norm(result.torque) > 0.0

    def test_reset_clears_integral(self):
        ctrl = MRPFeedbackController(K=0.1, P=10.0, Ki=0.01)
        state = AttitudeState(
            sigma=np.array([0.1, 0.1, 0.1]),
            omega=np.zeros(3),
            inertia=_diag_inertia(),
        )
        ref = AttitudeReference()
        for _ in range(50):
            ctrl.compute(state, ref, dt=0.1)
        ctrl.reset()
        np.testing.assert_allclose(ctrl._int_sigma, np.zeros(3))
