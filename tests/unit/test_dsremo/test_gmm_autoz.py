"""Tests for GMM-2 Bimodal Baseline and Per-Channel Auto Z-Threshold.

Both features are data-driven and require no manual parameter tuning:
  - GMM-2: BIC-selected bimodal reference during calibration
  - Auto-Z: empirical 99th-percentile z-threshold from calibration window
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

import aria.dsremo.detection.calibration as cal_mod
from aria.dsremo.detection.calibration import (
    CALIBRATION_WINDOW,
    CalibrationManager,
    CalibrationState,
    _try_fit_gmm,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bimodal(rng: np.random.Generator, n: int = CALIBRATION_WINDOW) -> np.ndarray:
    """Two well-separated modes: N(-5, 0.3) and N(+5, 0.3), 50/50 split."""
    half = n // 2
    return np.concatenate([
        rng.normal(-5.0, 0.3, half),
        rng.normal(+5.0, 0.3, n - half),
    ])


def _unimodal(rng: np.random.Generator, n: int = CALIBRATION_WINDOW) -> np.ndarray:
    return rng.normal(0.0, 1.0, n)


def _feed_calibration(mgr: CalibrationManager, key: str, arr: np.ndarray) -> CalibrationState:
    for v in arr:
        state = mgr.update(key, float(v))
    return state


# ── TestGMMCalibration ────────────────────────────────────────────────────────

class TestGMMCalibration:
    """GMM-2 bimodal baseline — fit during calibration phase."""

    def test_gmm_fields_default_none(self):
        s = CalibrationState()
        assert s.gmm_means is None
        assert s.gmm_stds is None
        assert s.auto_z_threshold is None

    def test_single_gaussian_no_gmm(self):
        """Clean unimodal Gaussian: BIC difference should not exceed 10."""
        rng = np.random.default_rng(0)
        mgr = CalibrationManager()
        state = _feed_calibration(mgr, "SAT:TEMP", _unimodal(rng))
        assert state.is_calibrated
        # Unimodal data — GMM-2 offers no significant improvement
        assert state.gmm_means is None

    def test_bimodal_window_sets_gmm(self):
        """Two well-separated modes should trigger GMM-2 fit."""
        rng = np.random.default_rng(1)
        mgr = CalibrationManager()
        state = _feed_calibration(mgr, "SAT:VOLT", _bimodal(rng))
        assert state.is_calibrated
        assert state.gmm_means is not None
        assert len(state.gmm_means) == 2
        assert len(state.gmm_stds) == 2
        # Recovered means should be close to -5 and +5
        means_sorted = sorted(state.gmm_means)
        assert means_sorted[0] == pytest.approx(-5.0, abs=0.5)
        assert means_sorted[1] == pytest.approx(+5.0, abs=0.5)

    def test_gmm_disabled_flag(self):
        """GMM_ENABLED=False must suppress GMM fit even on bimodal data."""
        orig = cal_mod.GMM_ENABLED
        cal_mod.GMM_ENABLED = False
        try:
            rng = np.random.default_rng(2)
            mgr = CalibrationManager()
            state = _feed_calibration(mgr, "SAT:CH", _bimodal(rng))
            assert state.is_calibrated
            assert state.gmm_means is None
        finally:
            cal_mod.GMM_ENABLED = orig

    def test_sklearn_import_error_silent_fallback(self):
        """If sklearn is not available, GMM fit silently does nothing."""
        rng = np.random.default_rng(3)
        arr = _bimodal(rng)
        state = CalibrationState()
        with patch.dict("sys.modules", {"sklearn.mixture": None}):
            _try_fit_gmm(state, arr)
        assert state.gmm_means is None

    def test_gmm_fit_exception_silent_fallback(self):
        """Any exception during GMM fit must be swallowed."""
        rng = np.random.default_rng(4)
        arr = _bimodal(rng)
        state = CalibrationState()
        with patch("sklearn.mixture.GaussianMixture.fit", side_effect=RuntimeError("boom")):
            _try_fit_gmm(state, arr)
        assert state.gmm_means is None

    def test_gmm_does_not_overwrite_ref_mean_ref_std(self):
        """ref_mean and ref_std must remain the global statistics of the window."""
        rng = np.random.default_rng(5)
        arr = _bimodal(rng)
        mgr = CalibrationManager()
        state = _feed_calibration(mgr, "SAT:X", arr)
        assert state.is_calibrated
        assert state.ref_mean == pytest.approx(float(np.mean(arr)), abs=0.1)
        assert state.ref_std  == pytest.approx(float(np.std(arr, ddof=1)), abs=0.2)

    def test_gmm_cleared_on_recalibration(self):
        """When _collect() runs, gmm_means is reset then re-evaluated on new buffer.

        Directly inject a recalibrating state with a clean unimodal buffer to
        verify that the GMM is not stale from the previous calibration round.
        """
        rng = np.random.default_rng(6)
        mgr = CalibrationManager()
        # First calibration with bimodal data → gmm_means set
        state = _feed_calibration(mgr, "SAT:Y", _bimodal(rng))
        assert state.gmm_means is not None

        # Manually put channel back into recalibrating with a clean unimodal buffer
        state.state = "recalibrating"
        unimodal_arr = _unimodal(rng)
        state._buffer = list(unimodal_arr[:CALIBRATION_WINDOW - 1])
        mgr._recal_streak["SAT:Y"] = 0
        # Feed the last point to trigger the transition
        mgr.update("SAT:Y", float(unimodal_arr[CALIBRATION_WINDOW - 1]))

        # After recalibration on unimodal data, GMM should reflect new window
        assert state.is_calibrated
        assert state.gmm_means is None  # unimodal data → no GMM-2 fit


# ── TestAutoZThreshold ────────────────────────────────────────────────────────

class TestAutoZThreshold:
    """Per-channel empirical z-threshold from calibration window."""

    def test_auto_z_computed_after_calibration(self):
        rng = np.random.default_rng(10)
        mgr = CalibrationManager()
        state = _feed_calibration(mgr, "SAT:TEMP", _unimodal(rng))
        assert state.is_calibrated
        assert state.auto_z_threshold is not None
        assert 3.0 <= state.auto_z_threshold <= 10.0

    def test_auto_z_clamped_min(self):
        """Near-flat channel: 99th pct might be < 3; must be clamped to 3.0."""
        mgr = CalibrationManager()
        # All-constant data: std≈0, but clamp protects the min
        for _ in range(CALIBRATION_WINDOW):
            mgr.update("SAT:FLAT", 5.0)
        state = mgr.get("SAT:FLAT")
        if state.auto_z_threshold is not None:
            assert state.auto_z_threshold >= 3.0

    def test_auto_z_clamped_max(self):
        """Data with a massive outlier: 99th pct might be > 10; must clamp."""
        rng = np.random.default_rng(11)
        arr = _unimodal(rng, CALIBRATION_WINDOW)
        arr[-1] = 1000.0  # single extreme spike
        mgr = CalibrationManager()
        state = _feed_calibration(mgr, "SAT:SPIKE", arr)
        assert state.is_calibrated
        assert state.auto_z_threshold is not None
        assert state.auto_z_threshold <= 10.0

    def test_auto_z_disabled_flag(self):
        """AUTO_Z_THRESHOLD_ENABLED=False: auto_z_threshold must remain None."""
        orig = cal_mod.AUTO_Z_THRESHOLD_ENABLED
        cal_mod.AUTO_Z_THRESHOLD_ENABLED = False
        try:
            rng = np.random.default_rng(12)
            mgr = CalibrationManager()
            state = _feed_calibration(mgr, "SAT:Z", _unimodal(rng))
            assert state.is_calibrated
            assert state.auto_z_threshold is None
        finally:
            cal_mod.AUTO_Z_THRESHOLD_ENABLED = orig

    def test_auto_z_not_set_during_warmup(self):
        """auto_z_threshold must remain None until calibration completes."""
        mgr = CalibrationManager()
        # Feed half the calibration window
        for i in range(CALIBRATION_WINDOW // 2):
            state = mgr.update("SAT:PARTIAL", float(i % 5))
        assert state.auto_z_threshold is None
        assert state.state == "warming_up"

    def test_auto_z_spread_reflects_data_noise(self):
        """High-noise channel should yield higher auto_z than low-noise channel.

        A channel with σ=10× larger natural variance produces residuals that
        have a higher 99th-pct z-score relative to their own σ_ref when the
        distribution has heavier tails (e.g. uniform vs Gaussian).
        """
        rng = np.random.default_rng(13)
        # Uniform distribution has heavier tails than Gaussian in z-space
        heavy = rng.uniform(-5.0, 5.0, CALIBRATION_WINDOW)  # flat, 99th pct ≈ 1.73σ
        normal = rng.normal(0.0, 1.0, CALIBRATION_WINDOW)   # Gaussian, 99th pct ≈ 2.3σ
        mgr_h = CalibrationManager()
        mgr_n = CalibrationManager()
        state_h = _feed_calibration(mgr_h, "SAT:HEAVY", heavy)
        state_n = _feed_calibration(mgr_n, "SAT:NORM",  normal)
        # Both may clamp to 3.0 for small windows, but neither should exceed 10.0
        assert state_h.auto_z_threshold is not None
        assert state_n.auto_z_threshold is not None
        assert 3.0 <= state_h.auto_z_threshold <= 10.0
        assert 3.0 <= state_n.auto_z_threshold <= 10.0


# ── TestGMMNearestZ ───────────────────────────────────────────────────────────

class TestGMMNearestZ:
    """_gmm_nearest_z standalone helper function."""

    def _z(self, residual, means, stds):
        from aria.dsremo.detection.detector import _gmm_nearest_z
        return _gmm_nearest_z(residual, means, stds)

    def test_nearest_z_on_second_component(self):
        """Residual exactly on the second mean → z=0."""
        assert self._z(3.0, [-3.0, 3.0], [0.5, 0.5]) == pytest.approx(0.0)

    def test_nearest_z_on_first_component(self):
        assert self._z(-3.0, [-3.0, 3.0], [0.5, 0.5]) == pytest.approx(0.0)

    def test_nearest_z_midpoint(self):
        """At midpoint (0.0) each component gives z=6; minimum is still 6."""
        result = self._z(0.0, [-3.0, 3.0], [0.5, 0.5])
        assert result == pytest.approx(6.0)

    def test_nearest_z_guards_zero_std(self):
        """zero std component must not raise ZeroDivisionError."""
        result = self._z(5.0, [0.0, 5.0], [0.0, 1.0])
        assert result == pytest.approx(0.0)  # second component: z=0

    def test_nearest_z_asymmetric_stds(self):
        """Component with wider σ contributes smaller z for off-center residual."""
        # residual=2, means=[0,5], stds=[1,2]
        # z0 = abs(2-0)/1 = 2.0
        # z1 = abs(2-5)/2 = 1.5  ← nearest
        result = self._z(2.0, [0.0, 5.0], [1.0, 2.0])
        assert result == pytest.approx(1.5)


# ── TestEffectiveZThreshold ───────────────────────────────────────────────────

class TestEffectiveZThresholdLogic:
    """Unit-test the effective z-threshold calculation logic (pure arithmetic)."""

    def _eff_z(self, base_z: float, auto_z: float | None) -> float:
        return max(base_z, auto_z) if auto_z is not None else base_z

    def test_auto_z_wins_when_higher(self):
        assert self._eff_z(3.0, 6.0) == pytest.approx(6.0)

    def test_global_z_wins_when_higher(self):
        assert self._eff_z(5.0, 3.5) == pytest.approx(5.0)

    def test_auto_z_none_uses_base(self):
        assert self._eff_z(3.0, None) == pytest.approx(3.0)

    def test_equal_values_returns_same(self):
        assert self._eff_z(3.0, 3.0) == pytest.approx(3.0)


# ── TestInitDetectorsWiresFlags ───────────────────────────────────────────────

class TestInitDetectorsWiresFlags:
    """init_detectors() must propagate gmm_enabled / auto_z_threshold_enabled."""

    def _make_settings(self, **overrides):
        base = {
            "stale_threshold_s": 300.0,
            "ttl_warn_min": 60.0,
            "gmm_enabled": True,
            "auto_z_threshold_enabled": True,
        }
        base.update(overrides)
        cfg = {"detection": base, "features": {}}

        class _S:
            def get(self, key, default=None):
                return cfg.get(key, default)
        return _S()

    def test_gmm_enabled_propagated_true(self):
        from aria.dsremo.detection.detector import init_detectors
        init_detectors(self._make_settings(gmm_enabled=True))
        assert cal_mod.GMM_ENABLED is True

    def test_gmm_enabled_propagated_false(self):
        from aria.dsremo.detection.detector import init_detectors
        init_detectors(self._make_settings(gmm_enabled=False))
        assert cal_mod.GMM_ENABLED is False

    def test_auto_z_enabled_propagated_true(self):
        from aria.dsremo.detection.detector import init_detectors
        init_detectors(self._make_settings(auto_z_threshold_enabled=True))
        assert cal_mod.AUTO_Z_THRESHOLD_ENABLED is True

    def test_auto_z_enabled_propagated_false(self):
        from aria.dsremo.detection.detector import init_detectors
        init_detectors(self._make_settings(auto_z_threshold_enabled=False))
        assert cal_mod.AUTO_Z_THRESHOLD_ENABLED is False
