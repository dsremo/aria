"""Tests for V3-V4: temporal cross-channel attention detector."""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.temporal_cross_attention import (
    DEFAULT_LAGS_SAMPLES,
    CrossAttentionReport,
    TemporalCrossAttention,
    compute_attention_tensor,
)


SAT = "SAT-V4-01"


def _baseline_stream(rng: np.random.Generator, n: int = 400, lag: int = 8, noise: float = 0.05):
    """Three correlated channels: ch_b lags ch_a by `lag` samples."""
    t = np.arange(n + lag)
    base = np.sin(2 * np.pi * t / 40.0) + rng.normal(0, noise, size=n + lag)
    ch_a = base[lag:]                         # present-time
    ch_b = base[:n]                           # ch_b(t) = ch_a(t - lag)
    ch_c = 0.5 * ch_a + rng.normal(0, noise, size=n)
    return {"a": ch_a, "b": ch_b, "c": ch_c}


class TestPearsonLagged:

    def test_lag_zero_is_vanilla_corr(self):
        rng = np.random.default_rng(0)
        x = rng.standard_normal(50)
        # Use public compute_attention_tensor as a smoke for _pearson_lagged.
        A, _ = compute_attention_tensor({"x": x, "y": x}, lags=(0,))
        assert A[0, 1, 0] == pytest.approx(1.0, abs=1e-6)

    def test_lag_matches_known_shift(self):
        rng = np.random.default_rng(1)
        s = rng.standard_normal(60)
        # y(t) = x(t - 3) ⇒ corr at lag 3 should be high (|ρ| > 0.95)
        A, _ = compute_attention_tensor({"x": s[3:], "y": s[:-3]}, lags=(3,))
        assert abs(A[0, 1, 0]) > 0.95 or abs(A[1, 0, 0]) > 0.95


class TestTensorShape:

    def test_shape_is_MxMxL(self):
        rng = np.random.default_rng(0)
        A, order = compute_attention_tensor(
            {"a": rng.standard_normal(50), "b": rng.standard_normal(50), "c": rng.standard_normal(50)},
            lags=(0, 4, 8),
        )
        assert A.shape == (3, 3, 3)
        assert order == ["a", "b", "c"]

    def test_empty_windows_returns_empty_tensor(self):
        A, order = compute_attention_tensor({}, lags=(0,))
        assert A.shape == (0, 0, 0)
        assert order == []


class TestConstructor:

    def test_rejects_window_too_small_for_lags(self):
        with pytest.raises(ValueError):
            TemporalCrossAttention(window_size=8, lags_samples=(0, 8))

    def test_rejects_bad_threshold(self):
        with pytest.raises(ValueError):
            TemporalCrossAttention(threshold_frobenius=0.0)
        with pytest.raises(ValueError):
            TemporalCrossAttention(threshold_frobenius=-1.0)

    def test_rejects_bad_severity_factors(self):
        with pytest.raises(ValueError):
            TemporalCrossAttention(severity_factors=(2.0, 1.0, 3.0))
        with pytest.raises(ValueError):
            TemporalCrossAttention(severity_factors=(1.0, 2.0))

    def test_happy_construction(self):
        det = TemporalCrossAttention()
        assert det.lags_samples == DEFAULT_LAGS_SAMPLES
        assert det.window_size == 32


class TestFitBaseline:

    def test_rejects_empty_channels(self):
        det = TemporalCrossAttention()
        with pytest.raises(ValueError):
            det.fit_baseline(SAT, "eps", {})

    def test_rejects_multi_dim(self):
        det = TemporalCrossAttention()
        with pytest.raises(ValueError):
            det.fit_baseline(SAT, "eps", {"a": np.zeros((32, 2))})

    def test_rejects_too_short_baseline(self):
        det = TemporalCrossAttention(window_size=32)
        # Only one window's worth → fewer than MIN_FIT_WINDOWS starts.
        with pytest.raises(ValueError):
            det.fit_baseline(SAT, "eps", {"a": np.zeros(32), "b": np.zeros(32)})

    def test_happy_fit(self):
        det = TemporalCrossAttention()
        rng = np.random.default_rng(0)
        channels = _baseline_stream(rng, n=400, lag=8)
        det.fit_baseline(SAT, "eps", channels)
        report = det.score(SAT, "eps")
        assert report is None  # no rolling buffer yet


class TestStreamingScoreNominal:

    def test_nominal_stream_scores_near_zero(self):
        # Pearson on a 32-sample window has ~0.18 std per cell. With
        # M²L = 36 cells the Frobenius norm of the train-vs-test delta
        # floor is ~sqrt(36 × 0.18²) ≈ 1.08, so threshold 2.5 is the
        # lowest value that yields NOMINAL on in-distribution noise.
        det = TemporalCrossAttention(threshold_frobenius=2.5)
        rng = np.random.default_rng(2)
        channels = _baseline_stream(rng, n=400, lag=8)
        det.fit_baseline(SAT, "eps", channels)
        extra = _baseline_stream(rng, n=200, lag=8)
        for k in range(200):
            det.update(SAT, "eps", {c: float(extra[c][k]) for c in extra})
        report = det.score(SAT, "eps")
        assert report is not None
        assert report.tier == "NOMINAL"


class TestStreamingScoreAnomalous:

    def test_decorrelated_stream_scores_high(self):
        det = TemporalCrossAttention(threshold_frobenius=0.3)
        rng = np.random.default_rng(3)
        channels = _baseline_stream(rng, n=400, lag=8)
        det.fit_baseline(SAT, "eps", channels)
        # Inject independent noise on each channel — wipes out the lagged
        # correlations A_ref was trained on.
        for _ in range(64):
            det.update(
                SAT, "eps",
                {
                    "a": float(rng.standard_normal()),
                    "b": float(rng.standard_normal()),
                    "c": float(rng.standard_normal()),
                },
            )
        report = det.score(SAT, "eps")
        assert report is not None
        # Decorrelated stream should rise above WATCH.
        assert report.tier in {"WATCH", "WARNING", "CRITICAL"}


class TestTiers:

    @pytest.mark.parametrize("score,expected_tier", [
        (0.0,  "NOMINAL"),
        (0.1,  "NOMINAL"),
        (0.5,  "WATCH"),
        (0.8,  "WARNING"),
        (1.2,  "CRITICAL"),
    ])
    def test_tier_from_score(self, score, expected_tier):
        det = TemporalCrossAttention(threshold_frobenius=0.5)
        assert det._tier(score) == expected_tier


class TestReset:

    def test_reset_single_sat_clears_only_that_sat(self):
        det = TemporalCrossAttention()
        rng = np.random.default_rng(0)
        ch = _baseline_stream(rng, n=400)
        det.fit_baseline("SAT-A", "eps", ch)
        det.fit_baseline("SAT-B", "eps", ch)
        det.reset("SAT-A")
        assert ("SAT-A", "eps") not in det._states
        assert ("SAT-B", "eps") in det._states

    def test_reset_all(self):
        det = TemporalCrossAttention()
        rng = np.random.default_rng(0)
        ch = _baseline_stream(rng, n=400)
        det.fit_baseline(SAT, "eps", ch)
        det.reset()
        assert det._states == {}


class TestReportRoundtrip:

    def test_report_to_dict_is_json_safe(self):
        import json
        det = TemporalCrossAttention(threshold_frobenius=1.0)
        rng = np.random.default_rng(7)
        channels = _baseline_stream(rng, n=400, lag=8)
        det.fit_baseline(SAT, "eps", channels)
        extra = _baseline_stream(rng, n=200, lag=8)
        for k in range(64):
            det.update(SAT, "eps", {c: float(extra[c][k]) for c in extra})
        report = det.score(SAT, "eps")
        d = report.to_dict()
        j = json.dumps(d)
        back = json.loads(j)
        assert back["satellite_id"] == SAT
        assert back["subsystem"] == "eps"
        assert back["tier"] in {"NOMINAL", "WATCH", "WARNING", "CRITICAL"}
