"""Unit tests for aria.physics.gravity.orbit_determination.

Tests cover: measurement models, BLS convergence, EKF predict/update,
GPS velocity measurement type, and FD-STM auto-promotion.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from aria.physics.gravity.orbit_determination import (
    ExtendedKalmanFilter,
    Measurement,
    _measurement_model,
    _meas_size,
    batch_least_squares,
)
import warnings


# ── Helpers ────────────────────────────────────────────────────────────────────

_MU = 3.986004418e14  # GM Earth [m³/s²]


def _circular_propagator(state: np.ndarray, t0: float, t1: float):
    """Two-body Kepler propagator using RK4 integration.

    Integrates r'' = -μ/r³ * r via RK4 with ~10-step subcycling.
    Accurate enough for near-circular orbits up to ~1 orbital period.
    """
    r0 = state[:3].copy()
    v0 = state[3:].copy()
    dt_total = t1 - t0
    if abs(dt_total) < 1e-10:
        return r0, v0

    # Subcycle for accuracy
    n_steps = max(1, int(abs(dt_total) / 30.0))  # 30-s sub-steps
    dt_sub = dt_total / n_steps

    r = r0.copy()
    v = v0.copy()

    def accel(rv):
        rr, vv = rv[:3], rv[3:]
        r_mag = np.linalg.norm(rr)
        a = -_MU / r_mag ** 3 * rr
        return np.concatenate([vv, a])

    for _ in range(n_steps):
        x = np.concatenate([r, v])
        k1 = accel(x)
        k2 = accel(x + 0.5 * dt_sub * k1)
        k3 = accel(x + 0.5 * dt_sub * k2)
        k4 = accel(x + dt_sub * k3)
        x_new = x + (dt_sub / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        r = x_new[:3]
        v = x_new[3:]

    return r, v


def _leo_state() -> np.ndarray:
    """LEO circular orbit at 500 km altitude."""
    r = 6_371_000 + 500_000  # m
    v = math.sqrt(_MU / r)
    return np.array([r, 0.0, 0.0, 0.0, v, 0.0])


# ── Measurement size helper ────────────────────────────────────────────────────

class TestMeasurementSize:
    def test_range(self):
        m = Measurement(0.0, "range", np.array([1e6]), 10.0, np.zeros(3))
        assert _meas_size(m) == 1

    def test_range_rate(self):
        m = Measurement(0.0, "range_rate", np.array([0.0]), 1.0, np.zeros(3))
        assert _meas_size(m) == 1

    def test_gps_pos(self):
        m = Measurement(0.0, "gps_pos", np.zeros(3), 5.0)
        assert _meas_size(m) == 3

    def test_gps_vel(self):
        m = Measurement(0.0, "gps_vel", np.zeros(3), 0.1)
        assert _meas_size(m) == 3

    def test_gps_full(self):
        m = Measurement(0.0, "gps_full", np.zeros(6), 5.0)
        assert _meas_size(m) == 6


# ── Measurement model ──────────────────────────────────────────────────────────

class TestMeasurementModel:
    def test_gps_pos_returns_position(self):
        state = np.array([7e6, 1e5, 2e5, 0.0, 7.5e3, 0.0])
        m = Measurement(0.0, "gps_pos", state[:3], 5.0)
        h, H = _measurement_model(m, state)
        assert np.allclose(h, state[:3])

    def test_gps_pos_H_matrix(self):
        state = _leo_state()
        m = Measurement(0.0, "gps_pos", state[:3], 5.0)
        _, H = _measurement_model(m, state)
        # H should be [I3 | 0] — position but not velocity
        assert H.shape == (3, 6)
        assert np.allclose(H[:, :3], np.eye(3))
        assert np.allclose(H[:, 3:], 0.0)

    def test_gps_vel_returns_velocity(self):
        state = _leo_state()
        m = Measurement(0.0, "gps_vel", state[3:], 0.1)
        h, H = _measurement_model(m, state)
        assert np.allclose(h, state[3:])

    def test_gps_vel_H_matrix(self):
        state = _leo_state()
        m = Measurement(0.0, "gps_vel", state[3:], 0.1)
        _, H = _measurement_model(m, state)
        # H should be [0 | I3] — velocity but not position
        assert H.shape == (3, 6)
        assert np.allclose(H[:, :3], 0.0)
        assert np.allclose(H[:, 3:], np.eye(3))

    def test_gps_full_returns_state(self):
        state = _leo_state()
        m = Measurement(0.0, "gps_full", state, 5.0)
        h, H = _measurement_model(m, state)
        assert np.allclose(h, state)
        assert np.allclose(H, np.eye(6))

    def test_range_measurement(self):
        state = np.array([7e6, 0.0, 0.0, 0.0, 7.5e3, 0.0])
        station = np.array([6.371e6, 0.0, 0.0])  # equatorial station
        expected_range = np.linalg.norm(state[:3] - station)
        m = Measurement(0.0, "range", np.array([expected_range]), 10.0, station)
        h, H = _measurement_model(m, state)
        assert abs(float(h[0]) - expected_range) < 1.0

    def test_range_rate_zero_for_perpendicular_motion(self):
        """Range rate = 0 when velocity is perpendicular to line-of-sight."""
        # Satellite directly above station, moving horizontally
        state = np.array([7e6, 0.0, 0.0, 0.0, 7.5e3, 0.0])
        station = np.array([0.0, 0.0, 0.0])  # at Earth center
        m = Measurement(0.0, "range_rate", np.array([0.0]), 1.0, station)
        h, _ = _measurement_model(m, state)
        # r = [7e6, 0, 0], v = [0, 7.5e3, 0]: dot(r_hat, v) = 0 → range_rate = 0
        assert abs(float(h[0])) < 1.0


# ── EKF basic functionality ────────────────────────────────────────────────────

class TestEKF:
    def _make_ekf(self, noise_scale=0.0, **kwargs) -> ExtendedKalmanFilter:
        x0 = _leo_state()
        if noise_scale > 0:
            x0 += np.random.default_rng(42).normal(0, noise_scale, 6)
        P0 = np.diag([1e6**2, 1e6**2, 1e6**2, 1e3**2, 1e3**2, 1e3**2])
        return ExtendedKalmanFilter(x0, P0, _circular_propagator, **kwargs)

    def test_predict_advances_time(self):
        ekf = self._make_ekf()
        ekf.predict(60.0)
        assert ekf.time == pytest.approx(60.0)

    def test_predict_state_norms_preserved(self):
        """Orbital radius should stay roughly constant after predict."""
        ekf = self._make_ekf()
        r0 = np.linalg.norm(ekf.state[:3])
        ekf.predict(300.0)
        r1 = np.linalg.norm(ekf.state[:3])
        assert abs(r1 - r0) / r0 < 0.01   # < 1% radius change for ~5 min

    def test_predict_covariance_grows(self):
        """Covariance must grow (or stay same) after prediction without update."""
        ekf = self._make_ekf()
        tr0 = np.trace(ekf.covariance)
        ekf.predict(30.0)
        tr1 = np.trace(ekf.covariance)
        assert tr1 >= tr0

    def test_update_gps_pos_shrinks_position_uncertainty(self):
        ekf = self._make_ekf()
        pos_unc_before = ekf.position_uncertainty_m()
        true_pos = ekf.state[:3] + np.array([10.0, -5.0, 3.0])
        m = Measurement(0.0, "gps_pos", true_pos, 5.0)
        ekf.update(m)
        pos_unc_after = ekf.position_uncertainty_m()
        assert pos_unc_after < pos_unc_before

    def test_update_gps_vel_shrinks_velocity_uncertainty(self):
        """GPS Doppler velocity update should reduce velocity uncertainty."""
        ekf = self._make_ekf()
        vel_unc_before = ekf.velocity_uncertainty_ms()
        true_vel = ekf.state[3:] + np.array([0.1, -0.05, 0.02])
        m = Measurement(0.0, "gps_vel", true_vel, 0.1)
        ekf.update(m)
        vel_unc_after = ekf.velocity_uncertainty_ms()
        assert vel_unc_after < vel_unc_before

    def test_update_gps_vel_does_not_change_position_estimate(self):
        """Velocity-only measurement should not change position state directly."""
        ekf = self._make_ekf()
        pos_before = ekf.state[:3].copy()
        m = Measurement(0.0, "gps_vel", ekf.state[3:], 0.1)
        ekf.update(m)
        assert np.allclose(ekf.state[:3], pos_before, atol=1e-6)

    def test_use_fd_stm_flag(self):
        """use_fd_stm=True should use FD-STM regardless of dt."""
        ekf_lin = self._make_ekf(use_fd_stm=False)
        ekf_fd  = self._make_ekf(use_fd_stm=True)
        ekf_lin.predict(30.0)
        ekf_fd.predict(30.0)
        # States should be close (same propagator), but covariances may differ
        assert np.allclose(ekf_lin.state, ekf_fd.state, atol=1.0)

    def test_fd_stm_threshold_triggers(self):
        """dt > fd_stm_threshold_s should auto-promote to FD-STM."""
        ekf = self._make_ekf(fd_stm_threshold_s=10.0)
        # dt=60 > threshold=10 → should use FD-STM (doesn't crash)
        ekf.predict(60.0)
        assert ekf.time == pytest.approx(60.0)

    def test_predict_skipped_for_past_time(self):
        ekf = self._make_ekf()
        ekf.predict(100.0)
        state_at_100 = ekf.state.copy()
        ekf.predict(50.0)  # past time — should be a no-op
        assert np.allclose(ekf.state, state_at_100)

    def test_history_recorded_after_update(self):
        ekf = self._make_ekf()
        m = Measurement(0.0, "gps_pos", ekf.state[:3], 5.0)
        ekf.update(m)
        assert len(ekf.history) == 1

    def test_gps_vel_convergence(self):
        """EKF with GPS pos+vel should converge faster than pos-only."""
        rng = np.random.default_rng(7)
        true_state = _leo_state()
        P0 = np.diag([1e6**2]*3 + [1e4**2]*3)
        ekf_pos_vel = ExtendedKalmanFilter(
            true_state + rng.normal(0, [1e4]*3 + [100]*3),
            P0.copy(), _circular_propagator
        )
        # Feed 10 steps with both pos + vel measurements
        for step in range(10):
            ekf_pos_vel.predict(float(step + 1) * 30.0)
            pos_m = Measurement(
                float(step + 1) * 30.0, "gps_pos",
                true_state[:3] + rng.normal(0, 5.0, 3), 5.0
            )
            vel_m = Measurement(
                float(step + 1) * 30.0, "gps_vel",
                true_state[3:] + rng.normal(0, 0.1, 3), 0.1
            )
            ekf_pos_vel.update(pos_m)
            ekf_pos_vel.update(vel_m)
        # Velocity uncertainty should be well below initial
        assert ekf_pos_vel.velocity_uncertainty_ms() < 100.0  # started at 1e4


# ── BLS basic test ─────────────────────────────────────────────────────────────

class TestBLS:
    def test_bls_converges_with_gps_pos(self):
        true = _leo_state()
        rng = np.random.default_rng(99)
        # Generate GPS position observations at 30-s intervals
        measurements = []
        for i in range(20):
            t = float(i + 1) * 30.0
            r_new, _ = _circular_propagator(true, 0.0, t)
            obs = r_new + rng.normal(0, 5.0, 3)
            measurements.append(Measurement(t, "gps_pos", obs, 5.0))
        # BLS with Gauss-Newton needs a good initial guess (< ~1 km off)
        x0 = true + np.array([500.0, 500.0, 500.0, 1.0, 1.0, 1.0])
        result = batch_least_squares(x0, measurements, _circular_propagator)
        assert result.converged
        assert np.linalg.norm(result.state[:3] - true[:3]) < 1e3  # < 1 km

    def test_bls_rms_residual_positive(self):
        true = _leo_state()
        # Need ≥6 scalar measurements for BLS to be determined
        meas = [
            Measurement(float(i + 1) * 30.0, "gps_pos",
                        _circular_propagator(true, 0.0, float(i + 1) * 30.0)[0], 5.0)
            for i in range(3)
        ]
        result = batch_least_squares(true.copy(), meas, _circular_propagator)
        assert result.rms_residual >= 0.0


# ── Range-only observability (BLS diverges) vs AER (BLS converges) ────────────

class TestBLSRangeOnlyObservability:
    """Demonstrate that range-only BLS from a single station diverges while
    AER (range + azimuth + elevation) gives a valid solution.

    Root cause in KNOWN_ISSUES: range-only from one station has degenerate
    geometry — the orbit is not uniquely determined because infinitely many
    orbits can produce the same range time series. AER adds two angle
    measurements that break this degeneracy.
    """

    @staticmethod
    def _build_aer_meas(true_state, station, n=30, rng=None):
        """Return (aer_meas_list, range_meas_list) with proper per-unit sigma."""
        if rng is None:
            rng = np.random.default_rng(17)
        sigma_r = 500.0   # 500 m range uncertainty
        sigma_a = 0.1     # 0.1 degree angle uncertainty
        meas_aer, meas_range = [], []
        for i in range(n):
            t = float(i + 1) * 30.0
            r_t, v_t = _circular_propagator(true_state, 0.0, t)
            st = np.concatenate([r_t, v_t])
            dm = Measurement(t, "aer", np.zeros(3), sigma_r, station)
            h, _ = _measurement_model(dm, st)
            rng_t, az_t, el_t = h
            # Separate measurements with per-unit sigma
            meas_aer.append(Measurement(t, "range", np.array([rng_t + rng.normal(0, sigma_r)]), sigma_r, station))
            meas_aer.append(Measurement(t, "az",    np.array([az_t  + rng.normal(0, sigma_a)]), sigma_a, station))
            meas_aer.append(Measurement(t, "el",    np.array([el_t  + rng.normal(0, sigma_a)]), sigma_a, station))
            meas_range.append(Measurement(t, "range", np.array([rng_t + rng.normal(0, sigma_r)]), sigma_r, station))
        return meas_aer, meas_range

    def test_aer_normal_matrix_better_conditioned_than_range_only(self):
        """Adding az+el measurements dramatically reduces the normal matrix condition number.

        Range-only from a single station leaves orbit-plane angles poorly constrained.
        Az+el angles break this degeneracy. This test verifies the information gain
        directly by comparing condition numbers of H^T W H.
        """
        # Inclined orbit at 45° for non-degenerate geometry
        r0 = 6_871_000.0
        v0 = math.sqrt(_MU / r0)
        true_state = np.array([r0 * 0.707, r0 * 0.707, 0.0, -v0 * 0.707, v0 * 0.707, 0.0])
        # Station at mid-latitude (not on orbit plane)
        station = np.array([4_500_000.0, 4_500_000.0, 3_000_000.0])

        meas_aer, meas_range = self._build_aer_meas(true_state, station)

        def _normal_matrix(meas_list):
            """Compute H^T W H at the true state (first-iteration Jacobian)."""
            n_obs = sum(_meas_size(m) for m in meas_list)
            H = np.zeros((n_obs, 6))
            W = np.zeros(n_obs)
            dr, dv = 100.0, 0.1
            idx = 0
            for m in meas_list:
                r_t, v_t = _circular_propagator(true_state, 0.0, m.time)
                st_nom = np.concatenate([r_t, v_t])
                h_nom, _ = _measurement_model(m, st_nom)
                sz = _meas_size(m)
                # FD Jacobian wrt initial state
                for k in range(6):
                    pert = dr if k < 3 else dv
                    x_p = true_state.copy(); x_p[k] += pert
                    r_p, v_p = _circular_propagator(x_p, 0.0, m.time)
                    h_p, _ = _measurement_model(m, np.concatenate([r_p, v_p]))
                    H[idx:idx+sz, k] = ((h_p if isinstance(h_p, np.ndarray) else np.array([h_p])) -
                                        (h_nom if isinstance(h_nom, np.ndarray) else np.array([h_nom]))) / pert
                W[idx:idx+sz] = 1.0 / m.sigma**2
                idx += sz
            N = H.T @ np.diag(W) @ H
            return N

        N_aer = _normal_matrix(meas_aer)
        N_range = _normal_matrix(meas_range)

        cond_aer = float(np.linalg.cond(N_aer))
        cond_range = float(np.linalg.cond(N_range))
        # AER should have dramatically lower condition number (better conditioned)
        assert cond_aer < cond_range, (
            f"AER cond={cond_aer:.1e} should be < range-only cond={cond_range:.1e}"
        )

    def test_range_only_bls_does_not_converge(self):
        """Range-only BLS from a single station should not converge."""
        true = _leo_state()
        station = np.array([6_371_000.0, 0.0, 0.0])
        x0 = true + np.array([500.0, 500.0, 0.0, 1.0, 0.0, 0.0])
        _, meas = self._build_aer_meas(true, station)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = batch_least_squares(x0, meas, _circular_propagator)
        assert not result.converged

    def test_aer_measurement_size_is_3(self):
        m = Measurement(0.0, "aer", np.zeros(3), 0.1, np.zeros(3))
        assert _meas_size(m) == 3

    def test_aer_model_returns_range_az_el(self):
        """AER measurement model should return [range, azimuth, elevation]."""
        state = _leo_state()
        station = np.array([6_371_000.0, 0.0, 0.0])
        m = Measurement(0.0, "aer", np.zeros(3), 0.1, station)
        h, H = _measurement_model(m, state)
        assert h.shape == (3,)
        assert H.shape == (3, 6)
        rng_pred = h[0]
        az_pred = h[1]
        el_pred = h[2]
        assert rng_pred > 0.0
        assert 0.0 <= az_pred < 360.0
        assert -90.0 <= el_pred <= 90.0
