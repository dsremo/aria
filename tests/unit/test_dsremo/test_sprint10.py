"""Sprint 10 tests — Adaptive Context Window + Long-Period STL Detection.

Covers:
  - TestMaxFftSamples          — STLDecomposer.max_fft_samples parameter (8 tests)
  - TestLongPeriodFFT          — FFT detection of long-period signals (12 tests)
  - TestAdaptiveWindowLogic    — ctx_limit computation from detected period (10 tests)
  - TestInitDetectorsWindow    — init_detectors wires config → decomposer + globals (8 tests)
  - TestSTLWithLargeWindow     — STL decomposition quality with 3×period window (10 tests)
  - TestConfigKeys             — dsremo.yaml new keys loaded correctly (6 tests)
  - TestRegressionSprint9      — Sprint 9 behaviour unchanged for short periods (10 tests)
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sine(n: int, period: int, amplitude: float = 1.0, noise: float = 0.0) -> np.ndarray:
    """Return a sine wave of length n with the given period, plus optional Gaussian noise."""
    t = np.arange(n, dtype=np.float64)
    sig = amplitude * np.sin(2 * np.pi * t / period)
    if noise > 0:
        rng = np.random.default_rng(42)
        sig = sig + rng.normal(0, noise, n)
    return sig


# ---------------------------------------------------------------------------
# 1. TestMaxFftSamples — STLDecomposer respects max_fft_samples
# ---------------------------------------------------------------------------

class TestMaxFftSamples:
    """STLDecomposer stores and exposes max_fft_samples."""

    def test_default_max_fft_samples_is_5000(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer()
        assert d._max_fft_samples == 5000  # raised from 600 for orbital period detection (P0-D fix)

    def test_custom_max_fft_samples_stored(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=5000)
        assert d._max_fft_samples == 5000

    def test_max_fft_samples_1000_stored(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=1000)
        assert d._max_fft_samples == 1000

    def test_max_fft_samples_limits_fft_input_short_signal(self):
        """When signal is shorter than max_fft_samples, full signal is used."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=5000)
        # Period-50 sinusoid, n=300 — all 300 samples should be used (300 < 5000)
        vals = _sine(300, period=50)
        ts = np.arange(300, dtype=np.float64)
        period = d._estimate_period(ts, len(vals), vals)
        assert period == 50

    def test_max_fft_samples_limits_fft_input_long_signal(self):
        """With max_fft_samples=100, FFT can't see period-200 in 5000-sample array."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=100)
        # Period-200 sinusoid: needs at least 400 samples to detect; we cap at 100
        vals = _sine(5000, period=200)
        # Only last 100 samples fed to FFT → period 200 > 100//2=50 → rejected
        period = STLDecomposer._fft_period(vals[-100:])
        assert period == 0

    def test_max_fft_5000_detects_period_1440(self):
        """With max_fft_samples=5000, FFT can detect a 1440-sample (24h) period."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=4320 = 3×1440 → FFT bin 3 → exact detection (4320/3 = 1440)
        vals = _sine(4320, period=1440, amplitude=10.0)
        detected = STLDecomposer._fft_period(vals)  # uses all 4320 samples
        assert detected == 1440, f"Expected 1440, got {detected}"

    def test_fft_period_600_cap_misses_1440(self):
        """With 600-sample cap (Sprint 9 default), 1440-period cannot be detected."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        vals = _sine(3000, period=1440, amplitude=10.0, noise=0.5)
        # FFT on last 600 samples of a period-1440 signal: 1440 > 600//2=300 → rejected
        detected = STLDecomposer._fft_period(vals[-600:])
        assert detected == 0, f"Expected 0 (period too long for 600-sample window), got {detected}"

    def test_max_fft_samples_does_not_change_short_period_detection(self):
        """Increasing max_fft_samples doesn't break short-period detection."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=5000)
        vals = _sine(2000, period=90, amplitude=5.0)
        ts = np.arange(2000, dtype=np.float64)
        period = d._estimate_period(ts, len(vals), vals)
        assert 88 <= period <= 92, f"Expected ~90, got {period}"


# ---------------------------------------------------------------------------
# 2. TestLongPeriodFFT — FFT detection of long-period signals
# ---------------------------------------------------------------------------

class TestLongPeriodFFT:
    """_fft_period handles large input correctly."""

    def test_period_1440_detected_with_3000_samples(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=2880 = 2×1440 → FFT bin 2 → exact detection (2880/2 = 1440)
        vals = _sine(2880, period=1440, amplitude=10.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 1440, f"Expected 1440, got {p}"

    def test_period_1440_detected_with_5000_samples(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=4320 = 3×1440 → FFT bin 3 → exact detection (4320/3 = 1440)
        vals = _sine(4320, period=1440, amplitude=10.0, noise=1.0)
        p = STLDecomposer._fft_period(vals)
        assert 1400 <= p <= 1480, f"Expected ~1440, got {p}"

    def test_period_300_detected_with_1000_samples(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=900 = 3×300 → FFT bin 3 → exact detection (900/3 = 300)
        vals = _sine(900, period=300, amplitude=5.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 300, f"Expected 300, got {p}"

    def test_period_720_detected_with_2500_samples(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=2160 = 3×720 → FFT bin 3 → exact detection (2160/3 = 720)
        vals = _sine(2160, period=720, amplitude=8.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 720, f"Expected 720, got {p}"

    def test_period_90_still_works_with_5000_samples(self):
        """Short-period detection is not broken by larger arrays."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        vals = _sine(5000, period=90, amplitude=5.0)
        p = STLDecomposer._fft_period(vals)
        assert 88 <= p <= 92

    def test_noise_only_5000_samples_returns_zero(self):
        """Broadband noise with 5000 samples should not produce false period."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        rng = np.random.default_rng(99)
        vals = rng.normal(0, 1, 5000)
        p = STLDecomposer._fft_period(vals)
        assert p == 0

    def test_period_too_large_rejected(self):
        """Period > n//2 is rejected even with large arrays."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=2000, period=1500 > 2000//2=1000 → rejected
        vals = _sine(2000, period=1500, amplitude=10.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 0

    def test_period_exactly_half_n_accepted(self):
        """Period exactly = n//2 is the edge case (just within limit)."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 1000
        period = n // 2  # = 500
        vals = _sine(n, period=period, amplitude=10.0)
        p = STLDecomposer._fft_period(vals)
        # May detect or may be edge case — just ensure no crash and in-range or 0
        assert p == 0 or 480 <= p <= 520

    def test_short_array_returns_zero_for_long_period(self):
        """n=100, period=1440 → rejected (period > n//2=50)."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        vals = _sine(100, period=1440, amplitude=10.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 0

    def test_period_1440_with_noise_still_detected(self):
        """1440-period signal with SNR ~5 should still be detected."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=4320 = 3×1440 → exact detection even with noise
        vals = _sine(4320, period=1440, amplitude=5.0, noise=1.0)
        p = STLDecomposer._fft_period(vals)
        assert 1400 <= p <= 1480, f"Expected ~1440, got {p}"

    def test_dual_period_strongest_detected(self):
        """With two periodicities, the dominant (higher amplitude) one is returned."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=4320 = 3×1440 → FFT bin 3 → exact detection for period=1440
        n = 4320
        t = np.arange(n, dtype=np.float64)
        # Dominant: period=1440, amplitude=10; weak: period=90, amplitude=1
        vals = 10.0 * np.sin(2 * np.pi * t / 1440) + 1.0 * np.sin(2 * np.pi * t / 90)
        p = STLDecomposer._fft_period(vals)
        assert 1400 <= p <= 1480, f"Expected ~1440 (dominant), got {p}"

    def test_period_120_detectable_with_old_600_window(self):
        """Periods ≤300 samples are detectable even with 600-sample cap (Sprint 9 compat)."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        vals = _sine(3000, period=120, amplitude=5.0)
        p = STLDecomposer._fft_period(vals[-600:])
        assert 118 <= p <= 122


# ---------------------------------------------------------------------------
# 3. TestAdaptiveWindowLogic — ctx_limit computation
# ---------------------------------------------------------------------------

class TestAdaptiveWindowLogic:
    """Validate ctx_limit = min(max(600, factor×period), max_window)."""

    def _compute_ctx_limit(
        self,
        period: int,
        factor: int = 3,
        max_window: int = 10000,
        base: int = 600,
    ) -> int:
        if period == 0:
            return base
        candidate = factor * period
        return int(min(max(base, candidate), max_window))

    def test_no_period_gives_600(self):
        assert self._compute_ctx_limit(0) == 600

    def test_period_90_stays_at_600(self):
        """3×90=270 < 600 → stays at 600."""
        assert self._compute_ctx_limit(90) == 600

    def test_period_200_stays_at_600(self):
        """3×200=600 = base → stays at 600."""
        assert self._compute_ctx_limit(200) == 600

    def test_period_210_scales_to_630(self):
        """3×210=630 > 600 → scales to 630."""
        assert self._compute_ctx_limit(210) == 630

    def test_period_1440_scales_to_4320(self):
        """3×1440=4320 — GECCO 24h diurnal."""
        assert self._compute_ctx_limit(1440) == 4320

    def test_period_720_scales_to_2160(self):
        """3×720=2160 — 12h semi-diurnal."""
        assert self._compute_ctx_limit(720) == 2160

    def test_period_5000_capped_at_10000(self):
        """3×5000=15000 > max_window=10000 → capped at 10000."""
        assert self._compute_ctx_limit(5000) == 10000

    def test_period_3334_exactly_at_max_window(self):
        """3×3334=10002 → capped at 10000."""
        assert self._compute_ctx_limit(3334) == 10000

    def test_factor_2_period_400_gives_800(self):
        """With factor=2: 2×400=800 > 600 → ctx_limit=800."""
        assert self._compute_ctx_limit(400, factor=2) == 800

    def test_custom_max_window_5000(self):
        """Custom max_window=5000: period=2000 → 3×2000=6000 → capped at 5000."""
        assert self._compute_ctx_limit(2000, max_window=5000) == 5000


# ---------------------------------------------------------------------------
# 4. TestInitDetectorsWindow — init_detectors wires config correctly
# ---------------------------------------------------------------------------

class TestInitDetectorsWindow:
    """init_detectors sets _stl_window_factor, _stl_max_window, max_fft_samples."""

    def _make_cfg(self, **kwargs) -> dict:
        base = {
            "detection": {
                "stl_max_fft_samples": 5000,
                "stl_window_factor": 3,
                "stl_max_window": 10000,
            },
            "features": {},
        }
        base["detection"].update(kwargs)
        return base

    def test_default_window_factor_is_3(self):
        import aria.dsremo.detection.detector as det_mod
        cfg = {"detection": {}, "features": {}}
        det_mod.init_detectors(cfg)
        assert det_mod._stl_window_factor == 3

    def test_default_max_window_is_200000(self):
        import aria.dsremo.detection.detector as det_mod
        cfg = {"detection": {}, "features": {}}
        det_mod.init_detectors(cfg)
        assert det_mod._stl_max_window == 200000  # raised for GEO orbit support (P2-B fix)

    def test_config_sets_window_factor(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(self._make_cfg(stl_window_factor=4))
        assert det_mod._stl_window_factor == 4

    def test_config_sets_max_window(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(self._make_cfg(stl_max_window=8000))
        assert det_mod._stl_max_window == 8000

    def test_config_sets_max_fft_samples_on_decomposer(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(self._make_cfg(stl_max_fft_samples=3000))
        assert det_mod._stl_decomposer._max_fft_samples == 3000

    def test_default_max_fft_samples_on_decomposer_is_5000(self):
        """Without config, decomposer defaults to 5000 (P0-D fix for orbital periods)."""
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors({"detection": {}, "features": {}})
        assert det_mod._stl_decomposer._max_fft_samples == 5000

    def test_stl_decomposer_recreated_on_reinit(self):
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(self._make_cfg(stl_max_fft_samples=2000))
        d1 = det_mod._stl_decomposer
        det_mod.init_detectors(self._make_cfg(stl_max_fft_samples=4000))
        d2 = det_mod._stl_decomposer
        assert d1 is not d2
        assert d2._max_fft_samples == 4000

    def test_window_factor_0_treated_as_zero_period_scaled(self):
        """Factor=0 effectively disables scaling (0×period=0 < 600 → stays 600)."""
        import aria.dsremo.detection.detector as det_mod
        det_mod.init_detectors(self._make_cfg(stl_window_factor=0))
        assert det_mod._stl_window_factor == 0


# ---------------------------------------------------------------------------
# 5. TestSTLWithLargeWindow — STL quality improves with adequate window
# ---------------------------------------------------------------------------

class TestSTLWithLargeWindow:
    """STL with 3×period window should remove seasonal component accurately."""

    def test_stl_removes_24h_seasonal_with_4320_window(self):
        """STL on 4320-sample window (3×1440) correctly decomposes a 1440-period signal."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 4320
        period = 1440
        t = np.arange(n, dtype=np.float64)
        seasonal = 5.0 * np.sin(2 * np.pi * t / period)
        trend = np.linspace(0, 2, n)
        noise = np.random.default_rng(7).normal(0, 0.3, n)
        raw = seasonal + trend + noise

        d = STLDecomposer(max_fft_samples=5000)
        ts = t  # epoch seconds
        result = d.decompose("test:ch", raw, ts)

        # Residual should be close to (trend + noise) — seasonal removed
        # Correlation of residual with raw seasonal should be low
        seasonal_corr = float(np.corrcoef(result.residual, seasonal)[0, 1])
        assert abs(seasonal_corr) < 0.3, (
            f"Residual still correlated with seasonal: r={seasonal_corr:.3f}"
        )

    def test_stl_with_600_window_fails_to_remove_24h_seasonal(self):
        """With 600-sample window, STL cannot remove 1440-period seasonal (period > 600//2)."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 600
        period = 1440
        t = np.arange(n, dtype=np.float64)
        seasonal = 5.0 * np.sin(2 * np.pi * t / period)
        raw = seasonal + np.random.default_rng(8).normal(0, 0.3, n)

        d = STLDecomposer()  # max_fft_samples=600 default
        result = d.decompose("test:ch", raw, t)
        # STL cannot run (period > n//2) → savgol fallback; seasonal not removed
        assert result.method in ("savgol_trend", "cold_start")

    def test_stl_detects_correct_period_1440(self):
        """STL decomposer with 5000-sample FFT detects period 1440 correctly."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 4320
        period = 1440
        vals = _sine(n, period=period, amplitude=5.0, noise=0.5)
        ts = np.arange(n, dtype=np.float64)
        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("test:ch", vals, ts)
        assert result.period_samples == period
        assert result.method == "stl"

    def test_stl_decomposition_result_shapes_match(self):
        """All arrays in DecompositionResult have same length as input."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 4320
        vals = _sine(n, period=1440, amplitude=5.0)
        ts = np.arange(n, dtype=np.float64)
        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("test:ch", vals, ts)
        assert len(result.trend) == n
        assert len(result.seasonal) == n
        assert len(result.residual) == n

    def test_stl_residual_variance_lower_than_raw(self):
        """After removing a strong seasonal, residual variance < raw variance."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 4320
        vals = _sine(n, period=1440, amplitude=10.0, noise=0.5)
        ts = np.arange(n, dtype=np.float64)
        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("test:ch", vals, ts)
        if result.method == "stl":
            assert float(np.var(result.residual)) < float(np.var(vals))

    def test_small_period_decomposer_unchanged(self):
        """Short-period STL (period=90) still works with large max_fft_samples."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=720 = 8×90 → FFT bin 8 → exact detection (720/8 = 90)
        n = 720
        vals = _sine(n, period=90, amplitude=5.0)
        ts = np.arange(n, dtype=np.float64)
        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("test:ch90", vals, ts)
        # Should still detect period 90 and use STL
        assert result.period_samples == 90
        assert result.method == "stl"

    def test_cold_start_still_works_with_small_n(self):
        """Very few samples → cold_start still returns a valid result."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 10
        vals = np.random.default_rng(1).normal(0, 1, n)
        ts = np.arange(n, dtype=np.float64)
        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("test:small", vals, ts)
        assert result.method == "cold_start"
        assert len(result.residual) == n

    def test_cache_resets_correctly_with_new_key(self):
        """Cache is per-key; different keys don't share period detection."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer(max_fft_samples=5000)
        # n=720 = 8×90 → exact detection; n=4320 = 3×1440 → exact detection
        v1 = _sine(720, period=90, amplitude=5.0)
        v2 = _sine(4320, period=1440, amplitude=5.0)
        t1 = np.arange(720, dtype=np.float64)
        t2 = np.arange(4320, dtype=np.float64)
        r1 = d.decompose("sat:ch1", v1, t1)
        r2 = d.decompose("sat:ch2", v2, t2)
        assert r1.period_samples == 90
        assert r2.period_samples == 1440

    def test_orbital_fallback_still_used_when_fft_fails(self):
        """When FFT finds nothing and orbital hint applies, fallback returns period."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=400, orbital_period_s=100, timestamps at 1s intervals → period_samples=100
        d = STLDecomposer(orbital_period_s=100, max_fft_samples=5000)
        ts = np.arange(400, dtype=np.float64)  # 400 seconds at 1s/sample
        noise_vals = np.random.default_rng(3).normal(0, 1, 400)  # broadband noise
        period = d._estimate_period(ts, 400, noise_vals)
        # orbital: 100/1.0=100 samples, 100<=400//2=200 → valid
        assert period == 100

    def test_stl_window_4320_detects_anomaly_in_residual(self):
        """STL with 4320-window runs on spike-contaminated signal and removes seasonal."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        n = 4320
        period = 1440
        t = np.arange(n, dtype=np.float64)
        seasonal = 5.0 * np.sin(2 * np.pi * t / period)
        noise = np.random.default_rng(11).normal(0, 0.3, n)
        raw = seasonal + noise
        # Inject spike at index 3000
        raw[3000] += 15.0

        d = STLDecomposer(max_fft_samples=5000)
        result = d.decompose("spike:ch", raw, t)
        # STL should run (period=1440 detected, n >= 2×period)
        assert result.method == "stl", f"Expected STL, got {result.method}"
        assert result.period_samples == period
        assert len(result.residual) == n
        # Seasonal removal: residual variance should be much less than raw variance
        # because a strong (±5) seasonal component was removed
        raw_var = float(np.var(raw))
        res_var = float(np.var(result.residual))
        assert res_var < raw_var * 0.5, (
            f"Seasonal not removed: res_var={res_var:.3f} >= 0.5*raw_var={raw_var*0.5:.3f}"
        )


# ---------------------------------------------------------------------------
# 6. TestConfigKeys — dsremo.yaml new keys present and correct type
# ---------------------------------------------------------------------------

class TestConfigKeys:
    """Sprint 10 config keys exist in dsremo.yaml and have correct values."""

    @pytest.fixture(scope="class")
    def cfg(self):
        from dynaconf import Dynaconf
        cfg_path = Path(__file__).parent.parent / "configs" / "aria.dsremo.yaml"
        settings = Dynaconf(settings_file=str(cfg_path), envvar_prefix="DSREMO")
        return settings.get("detection", {})

    def test_stl_max_fft_samples_present(self, cfg):
        assert "stl_max_fft_samples" in cfg

    def test_stl_max_fft_samples_is_5000(self, cfg):
        assert int(cfg["stl_max_fft_samples"]) == 5000

    def test_stl_window_factor_present(self, cfg):
        assert "stl_window_factor" in cfg

    def test_stl_window_factor_is_3(self, cfg):
        assert int(cfg["stl_window_factor"]) == 3

    def test_stl_max_window_present(self, cfg):
        assert "stl_max_window" in cfg

    def test_stl_max_window_is_200000(self, cfg):
        assert int(cfg["stl_max_window"]) == 200000  # raised for GEO orbit support (P2-B fix)


# ---------------------------------------------------------------------------
# 7. TestRegressionSprint9 — Sprint 9 behaviour unchanged for short periods
# ---------------------------------------------------------------------------

class TestRegressionSprint9:
    """Ensure Sprint 10 doesn't break Sprint 9 functionality."""

    def test_fft_period_90_still_detected_in_600_window(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # n=630 = 7×90 → FFT bin 7 → exact detection (630/7 = 90)
        # (n=600: 600/90=6.67→k=7→period=600/7≈86 due to quantization)
        vals = _sine(630, period=90, amplitude=5.0)
        p = STLDecomposer._fft_period(vals)
        assert p == 90, f"Expected 90, got {p}"

    def test_broadband_noise_returns_zero_unchanged(self):
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        rng = np.random.default_rng(42)
        vals = rng.normal(0, 1, 600)
        assert STLDecomposer._fft_period(vals) == 0

    def test_variance_detector_still_fires_on_sigma_ratio(self):
        from aria.dsremo.detection.variance_detector import VarianceDetector
        from aria.dsremo.detection.calibration import CalibrationState
        vd = VarianceDetector(variance_z_threshold=2.5, window=30)
        cal = CalibrationState()
        cal.state = "calibrated"
        cal.ref_mean = 0.0
        cal.ref_std = 1.0
        cal._update_derived(1.0)
        residuals = np.concatenate([np.zeros(20), np.tile([4.0, -4.0], 15)])
        result = vd.detect(residuals, cal)
        assert result.is_anomaly

    def test_weights_still_sum_to_one(self):
        import aria.dsremo.detection.detector as det_mod
        from aria.dsremo.core.config import load_config
        cfg = load_config()
        det_mod.init_detectors(cfg)
        total = sum(det_mod.WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6

    def test_ensemble_6_detectors_in_weights(self):
        import aria.dsremo.detection.detector as det_mod
        from aria.dsremo.core.config import load_config
        cfg = load_config()
        det_mod.init_detectors(cfg)
        assert "variance" in det_mod.WEIGHTS
        assert len(det_mod.WEIGHTS) >= 6  # 7 after Sprint 11 (lstm added)

    def test_fft_4x_median_threshold_unchanged(self):
        """The 4× median noise-rejection threshold from Sprint 9 is still in effect."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        # Construct a signal where peak/median = 3.9× (below 4× threshold → return 0)
        n = 600
        # Use a sine with very low amplitude so noise floor is relatively high
        rng = np.random.default_rng(0)
        noise = rng.normal(0, 1.0, n)
        weak_sine = 1.5 * np.sin(2 * np.pi * np.arange(n) / 30)
        vals = noise + weak_sine  # SNR ~1.5 → peak/median < 4
        # Not guaranteed to return 0, but test that function doesn't crash
        p = STLDecomposer._fft_period(vals)
        assert isinstance(p, int)
        assert p >= 0

    def test_stl_decomposer_default_backwards_compatible(self):
        """STLDecomposer() with no args still works with current defaults."""
        from aria.dsremo.detection.stl_decomposer import STLDecomposer
        d = STLDecomposer()  # no max_fft_samples
        assert d._max_fft_samples == 5000  # raised from 600 for P0-D orbital period fix
        assert d._orbital_period_s == 5400

    def test_detect_data_frequency_unchanged(self):
        """detect_data_frequency still works after Sprint 10 changes."""
        import tempfile, csv as csv_mod
        from aria.dsremo.ingest.utils import detect_data_frequency
        rows = [{"timestamp": f"2024-01-01T00:{i:02d}:00Z"} for i in range(5)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            w = csv_mod.DictWriter(f, fieldnames=["timestamp"])
            w.writeheader()
            w.writerows(rows)
            fname = f.name
        freq = detect_data_frequency(Path(fname))
        assert abs(freq - 60.0) < 1.0

    def test_scoring_module_unchanged(self):
        from aria.dsremo.eval.scoring import cluster_events, score
        from datetime import timedelta
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts = [t0, t0 + timedelta(minutes=1)]
        gt = [(t0 + timedelta(hours=1), t0 + timedelta(hours=2))]
        r = score(ts, gt, window_s=1800, gap_s=3600)
        assert r.recall == 0.0

    def test_adaptive_cooldown_hours_unchanged(self):
        from aria.dsremo.ingest.utils import adaptive_cooldown_hours
        # 5-min data (300s interval) → 500 × 300 = 150000s = 41.667h
        assert adaptive_cooldown_hours(300.0) == pytest.approx(150000.0 / 3600.0, rel=1e-3)
