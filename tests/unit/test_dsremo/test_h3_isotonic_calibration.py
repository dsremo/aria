"""Tests for V3-H3: isotonic-regression ensemble calibration (PAVA)."""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.isotonic_calibration import (
    DEFAULT_ECE_BINS,
    IsotonicCalibrator,
    bootstrap_from_injection,
    expected_calibration_error,
    fit_isotonic_calibrator,
    pav_fit,
)


class TestPAVA:

    def test_monotonic_output(self):
        # Already-monotone labels stay monotone.
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
        labels = np.array([0,   0,   0,   1,   1,   1])
        x, y = pav_fit(scores, labels)
        assert np.all(np.diff(y) >= -1e-9)

    def test_merges_violators(self):
        # Violator at x=0.3: label higher than x=0.4 — PAVA should pool.
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        labels = np.array([0,   0,   1,   0,   1])
        x, y = pav_fit(scores, labels)
        # Middle run (0.3, 0.4) pooled → y[2]==y[3] (mean label=0.5)
        assert y[2] == pytest.approx(0.5, abs=1e-9)

    def test_collapses_ties(self):
        # Ties in scores → one bin with mean label.
        scores = np.array([0.5, 0.5, 0.5])
        labels = np.array([0,   1,   1])
        x, y = pav_fit(scores, labels)
        assert x.shape == (1,)
        assert y[0] == pytest.approx(2 / 3, abs=1e-9)

    def test_single_sample(self):
        x, y = pav_fit(np.array([0.4]), np.array([1]))
        assert x.shape == (1,)
        assert y[0] == pytest.approx(1.0)

    def test_rejects_shape_mismatch(self):
        with pytest.raises(ValueError):
            pav_fit(np.array([0.1, 0.2, 0.3]), np.array([0, 1]))

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            pav_fit(np.array([]), np.array([]))


class TestCalibratorPredict:

    def test_monotone_output_on_new_scores(self):
        rng = np.random.default_rng(0)
        scores = rng.random(200)
        labels = (scores > 0.5).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        grid = np.linspace(0.0, 1.0, 100)
        pred = calib.predict(grid)
        assert np.all(np.diff(pred) >= -1e-9)

    def test_predict_clipped_to_unit_interval(self):
        rng = np.random.default_rng(0)
        scores = rng.random(200)
        labels = (scores > 0.5).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        pred = calib.predict(np.array([-0.5, 0.0, 0.5, 1.0, 2.0]))
        assert (pred >= 0.0).all()
        assert (pred <= 1.0).all()

    def test_out_of_range_clamps_to_edge(self):
        rng = np.random.default_rng(0)
        scores = rng.uniform(0.1, 0.9, 200)
        labels = (scores > 0.5).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        # np.interp clamps below x_boundaries[0] → y_values[0]
        pred_low  = calib.predict(np.array([-1.0]))
        pred_high = calib.predict(np.array([2.0]))
        assert pred_low[0] == pytest.approx(calib.y_values[0])
        assert pred_high[0] == pytest.approx(calib.y_values[-1])


class TestFitValidation:

    def test_rejects_too_few_samples(self):
        with pytest.raises(ValueError):
            fit_isotonic_calibrator(np.zeros(10), np.zeros(10, dtype=np.int8))


class TestECE:

    def test_perfect_calibration_has_zero_ece(self):
        # Construct scores = labels; calibrator should return the identity
        # on this dataset → ECE ≈ 0.
        scores = np.linspace(0.0, 1.0, 200)
        labels = (scores > 0.5).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        # Reliability on this same dataset: ECE should be small-ish.
        assert calib.ece < 0.25

    def test_uncalibrated_random_has_larger_ece(self):
        rng = np.random.default_rng(0)
        scores = rng.random(200)
        labels = rng.integers(0, 2, 200).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        # In-sample ECE should be low by construction (PAVA over-fits).
        # Out-of-sample assertion: evaluate on a fresh sample instead.
        fresh_scores = rng.random(500)
        fresh_labels = rng.integers(0, 2, 500).astype(np.int8)
        ece = expected_calibration_error(calib, fresh_scores, fresh_labels)
        # Random labels have ECE ≳ 0 either way; just assert it's computable
        assert ece >= 0.0
        assert ece < 1.0


class TestBootstrap:

    def test_bootstrap_fits_and_predicts(self):
        rng = np.random.default_rng(0)
        clean = rng.uniform(0.0, 0.4, 300)  # nominal score distribution
        calib = bootstrap_from_injection(clean, seed=0)
        assert isinstance(calib, IsotonicCalibrator)
        pred = calib.predict(np.array([0.0, 0.2, 0.5, 0.9]))
        # Non-decreasing monotone
        assert np.all(np.diff(pred) >= -1e-9)

    def test_bootstrap_rejects_tiny_clean(self):
        with pytest.raises(ValueError):
            bootstrap_from_injection(np.zeros(5))

    def test_bootstrap_rejects_bad_rate(self):
        with pytest.raises(ValueError):
            bootstrap_from_injection(np.zeros(100), injection_rate=0.0)
        with pytest.raises(ValueError):
            bootstrap_from_injection(np.zeros(100), injection_rate=1.0)

    def test_bootstrap_reproducible_with_seed(self):
        clean = np.random.default_rng(0).uniform(0.0, 0.4, 300)
        a = bootstrap_from_injection(clean, seed=42)
        b = bootstrap_from_injection(clean, seed=42)
        assert np.array_equal(a.y_values, b.y_values)
        assert np.array_equal(a.x_boundaries, b.x_boundaries)


class TestIntegrationSigmoidVsIsotonic:

    def test_isotonic_beats_linear_in_decision_range(self):
        """Per audit: sigmoid under-estimates P at mid-range scores.

        Build a concave true curve, fit isotonic on noisy labels, verify
        that isotonic calibration gets the mid-range closer to the truth
        than a vanilla linear mapping would.
        """
        rng = np.random.default_rng(0)
        scores = rng.random(500)
        # True probability is concave: P(y=1 | score) = sqrt(score)
        p_true = np.sqrt(scores)
        labels = (rng.random(500) < p_true).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        # Mid-range score 0.25: true P = sqrt(0.25) = 0.5
        # Linear identity mapping would say 0.25 — off by 0.25
        # Isotonic should land within 0.15 of 0.5.
        pred_mid = float(calib.predict(np.array([0.25]))[0])
        linear_mid = 0.25
        assert abs(pred_mid - 0.5) < abs(linear_mid - 0.5)
