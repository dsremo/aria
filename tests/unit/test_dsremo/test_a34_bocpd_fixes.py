"""Tests for V3-A3 + V3-A4 BOCPD fixes.

A-3: anomaly score is `sum(R_t[:detection_lag])`, not `R_t[0]`.  Retains
    elevated score for `detection_lag` samples after a changepoint, when
    the residual has actually become visibly anomalous.

A-4: empirical-Bayes prior — μ_0 ← calibration.ref_mean so the first
    post-calibration predictive is actually centred on the channel's
    natural level, not on the constructor's global `mu_0 = 0`.
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.bocpd_detector import BOCPDDetector
from aria.dsremo.detection.calibration import CalibrationState


def _make_calibration(ref_mean: float, ref_std: float) -> CalibrationState:
    cal = CalibrationState()
    cal.state        = "calibrated"
    cal.ref_mean     = float(ref_mean)
    cal.ref_std      = float(ref_std)
    cal.sample_count = 200
    return cal


class TestA3DetectionLag:

    def test_detection_lag_default_is_backward_compat(self):
        """Default is 1 — same semantics as the old R_t[0] score.  The
        A-3 cumulative window is opt-in because it needs a proportionally
        higher alarm_threshold to avoid false positives from the wider
        window; silently switching would break existing calibrations."""
        det = BOCPDDetector()
        assert det.detection_lag == 1

    def test_detection_lag_cumulative_opt_in(self):
        det = BOCPDDetector(detection_lag=10)
        assert det.detection_lag == 10

    def test_detection_lag_clamped_to_valid_range(self):
        # Zero or negative would silently disable the A-3 window; must clamp.
        det = BOCPDDetector(detection_lag=0)
        assert det.detection_lag == 1
        det = BOCPDDetector(detection_lag=-5)
        assert det.detection_lag == 1
        det = BOCPDDetector(max_run=300, detection_lag=10_000)
        assert det.detection_lag == 300

    def test_lag10_score_ge_lag1_score(self):
        """For the same stream, the detection_lag=10 score integrates over
        more run-length mass and must be ≥ the detection_lag=1 score
        (R_t[0]) at every step.  This is the structural correctness of
        the A-3 cumulative scoring — it never decreases evidence."""
        det1  = BOCPDDetector(detection_lag=1)
        det10 = BOCPDDetector(detection_lag=10)
        cal = _make_calibration(ref_mean=0.0, ref_std=1.0)
        rng = np.random.default_rng(42)
        signal = [float(rng.normal(0.0, 1.0)) for _ in range(50)]
        # Level shift.
        signal += [float(rng.normal(5.0, 1.0)) for _ in range(5)]
        for x in signal:
            r1  = det1.detect("K",  x, cal)
            r10 = det10.detect("K", x, cal)
            assert r10.score >= r1.score - 1e-12


class TestA4EmpiricalBayesPrior:

    def test_calibrated_prior_uses_ref_mean(self):
        """When calibration.ref_mean is 28.0 V, the predictive at the first
        post-calibration sample should peak near 28 V, not near 0 V.

        We check by comparing the cp_prob when the first sample is
        AT the calibration mean (should be small) versus when it is at
        zero (should be MUCH larger because zero is a massive shift
        from a 28 V-centred channel).
        """
        det_a = BOCPDDetector()
        det_b = BOCPDDetector()
        cal28 = _make_calibration(ref_mean=28.0, ref_std=0.5)

        result_at_mean = det_a.detect("A", 28.0, cal28)
        result_far_off = det_b.detect("B", 0.0, cal28)

        # A sample at the calibration mean should produce a much smaller
        # changepoint probability than a sample 28 V away from it.
        assert result_at_mean.score < result_far_off.score

    def test_without_calibration_uses_default_prior(self):
        """Warming-up state: A-4 path is skipped; the constructor's μ_0
        (default 0.0) is still used.  Detector must not crash and should
        still return a valid DetectorResult."""
        det = BOCPDDetector()
        cal = CalibrationState()   # default state = "warming_up"
        result = det.detect("K", 0.01, cal)
        assert result.severity is not None
        assert 0.0 <= result.score <= 1.0
