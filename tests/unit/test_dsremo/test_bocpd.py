"""Tests for the BOCPD (Bayesian Online Changepoint Detection) detector.

Covers:
  - Nominal signal: no alarm, scores stay near hazard rate
  - Abrupt mean shift: alarm fires within a few samples of the changepoint
  - Variance shift: alarm fires on sudden increase in noise level
  - Calibration warm-up: is_anomaly=False before calibration, state still updates
  - Prior scaling: informed beta_0 from calibration.ref_std changes score distribution
  - Severity mapping: cp_prob → NOMINAL / WATCH / WARNING / CRITICAL
  - Reset: per-channel and global reset clears state
  - Determinism: same seed → same scores
"""

import math

import numpy as np
import pytest

from aria.dsremo.core.models import Severity
from aria.dsremo.detection.bocpd_detector import BOCPDDetector
from aria.dsremo.detection.calibration import CalibrationState


# ── Helpers ──────────────────────────────────────────────────────────────────


def _calibrated(ref_std: float = 1.0) -> CalibrationState:
    """Return a CalibrationState in the 'calibrated' state."""
    return CalibrationState(state="calibrated", ref_std=ref_std, ref_mean=0.0)


def _warming_up() -> CalibrationState:
    """Return a CalibrationState that has not yet completed warm-up."""
    return CalibrationState(state="warming_up", ref_std=0.0, ref_mean=0.0)


def _run_signal(
    det: BOCPDDetector,
    signal: np.ndarray,
    cal: CalibrationState,
    key: str = "sat:ch",
) -> np.ndarray:
    """Feed signal through det and return array of scores."""
    return np.array([det.detect(key, float(x), cal).score for x in signal])


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestBOCPDNominal:
    def test_stable_signal_no_alarm(self):
        rng = np.random.default_rng(0)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=1.0)
        signal = rng.normal(0.0, 1.0, 300)
        results = [det.detect("sat:ch", float(x), cal) for x in signal]
        # After warm-up, no alarm expected on stationary N(0,1)
        assert all(not r.is_anomaly for r in results), \
            "Stable N(0,1) should not trigger BOCPD alarm"

    def test_scores_bounded(self):
        rng = np.random.default_rng(1)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=1.0)
        signal = rng.normal(0.0, 1.0, 200)
        scores = _run_signal(det, signal, cal)
        assert np.all(scores >= 0.0), "Scores must be non-negative"
        assert np.all(scores <= 1.0), "Scores must be <= 1.0"

    def test_score_near_hazard_on_nominal(self):
        """Scores should stay roughly near the hazard rate on stationary data."""
        rng = np.random.default_rng(2)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=1.0)
        signal = rng.normal(0.0, 1.0, 500)
        scores = _run_signal(det, signal, cal)
        # Mean score << alarm threshold (0.3)
        assert scores.mean() < 0.05, \
            f"Mean score on nominal data too high: {scores.mean():.4f}"


class TestBOCPDMeanShift:
    def test_detects_abrupt_mean_shift(self):
        rng = np.random.default_rng(42)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=1.0)
        pre  = rng.normal(0.0, 1.0, 200)
        post = rng.normal(5.0, 1.0, 50)
        signal = np.concatenate([pre, post])

        scores = _run_signal(det, signal, cal)
        pre_max  = scores[:195].max()
        post_max = scores[200:215].max()

        assert post_max > pre_max * 3, \
            f"Post-CP max {post_max:.4f} should be >> pre-CP max {pre_max:.4f}"
        assert post_max >= 0.3, \
            f"Expected alarm after mean shift, got max score {post_max:.4f}"

    def test_alarm_fires_promptly(self):
        """Alarm should fire within 5 samples of the changepoint."""
        rng = np.random.default_rng(42)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=1.0)
        pre  = rng.normal(0.0, 1.0, 200)
        post = rng.normal(5.0, 1.0, 30)
        signal = np.concatenate([pre, post])

        results = [det.detect("sat:ch", float(x), cal) for x in signal]
        first_alarm = next(
            (i for i, r in enumerate(results) if r.is_anomaly), None
        )
        assert first_alarm is not None, "Expected at least one alarm after mean shift"
        assert first_alarm >= 200, "Alarm must not fire before the changepoint"
        assert first_alarm <= 205, \
            f"Alarm should fire within 5 samples of CP, fired at {first_alarm}"


class TestBOCPDVarianceShift:
    def test_detects_variance_increase(self):
        """Sudden increase in noise (e.g. sensor degradation) should trigger."""
        rng = np.random.default_rng(7)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated(ref_std=0.1)   # calibrated on low-noise channel
        pre  = rng.normal(0.0, 0.1, 200)
        post = rng.normal(0.0, 3.0, 30)   # sudden noise spike
        signal = np.concatenate([pre, post])

        scores = _run_signal(det, signal, cal)
        assert scores[200:].max() > scores[:195].max() * 2, \
            "Variance shift should increase BOCPD score significantly"


class TestBOCPDCalibrationWarmUp:
    def test_no_alarm_during_warmup(self):
        """is_anomaly must be False while calibration is in warming_up state."""
        rng = np.random.default_rng(3)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _warming_up()
        # Feed a strong signal that would alarm on a calibrated channel
        signal = np.concatenate([rng.normal(0, 1, 50), rng.normal(10, 1, 50)])
        results = [det.detect("sat:ch", float(x), cal) for x in signal]
        assert all(not r.is_anomaly for r in results), \
            "Must not alarm during warm-up regardless of data"

    def test_warmup_still_updates_state(self):
        """State (t counter) should advance even during warm-up."""
        rng = np.random.default_rng(4)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _warming_up()
        signal = rng.normal(0, 1, 30)
        for x in signal:
            det.detect("sat:ch", float(x), cal)
        state = det.get_state("sat:ch")
        assert state["t"] == 30, "State counter must advance during warm-up"

    def test_score_still_returned_during_warmup(self):
        """score field should be in [0,1] even during warm-up."""
        rng = np.random.default_rng(5)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _warming_up()
        for x in rng.normal(0, 1, 20):
            r = det.detect("sat:ch", float(x), cal)
            assert 0.0 <= r.score <= 1.0


class TestBOCPDPriorScaling:
    def test_informed_prior_from_ref_std(self):
        """A mismatched prior produces a higher peak score on the first few observations.

        When ref_std is wildly under-estimated (0.01 vs actual σ=1), the prior
        predicts almost zero variance.  The first few observations look like huge
        outliers relative to that prior, so BOCPD fires a high P(changepoint) spike.
        A well-matched prior (ref_std=1) stays near the hazard rate throughout.

        Note: BOCPD self-corrects quickly (conjugate posterior update), so the
        *mean* score is not reliably different — only the peak score differs.
        """
        rng = np.random.default_rng(6)
        signal = rng.normal(0.0, 1.0, 200)
        cal_matched = _calibrated(ref_std=1.0)
        cal_wrong   = _calibrated(ref_std=0.01)   # wildly under-estimated noise

        det_matched = BOCPDDetector()
        det_wrong   = BOCPDDetector()

        scores_matched = _run_signal(det_matched, signal, cal_matched, "sat:a")
        scores_wrong   = _run_signal(det_wrong,   signal, cal_wrong,   "sat:b")

        # Under-estimated prior → spike on early observations when data σ >> prior σ
        assert scores_wrong.max() > scores_matched.max(), \
            f"Mismatched prior should produce higher peak score: " \
            f"wrong={scores_wrong.max():.4f} matched={scores_matched.max():.4f}"


class TestBOCPDSeverity:
    def test_severity_nominal_below_threshold(self):
        det = BOCPDDetector(alarm_threshold=0.3)
        cal = _calibrated()
        # Feed nominal data; expect NOMINAL severity
        rng = np.random.default_rng(10)
        for x in rng.normal(0, 1, 50):
            r = det.detect("sat:ch", float(x), cal)
            if not r.is_anomaly:
                assert r.severity == Severity.NOMINAL

    def test_severity_watch_at_threshold(self):
        """Directly test _severity() at watch boundary."""
        det = BOCPDDetector(alarm_threshold=0.3)
        assert det._severity(0.30) == Severity.WATCH
        assert det._severity(0.59) == Severity.WATCH

    def test_severity_warning_at_0_60(self):
        det = BOCPDDetector(alarm_threshold=0.3)
        assert det._severity(0.60) == Severity.WARNING
        assert det._severity(0.79) == Severity.WARNING

    def test_severity_critical_at_0_80(self):
        det = BOCPDDetector(alarm_threshold=0.3)
        assert det._severity(0.80) == Severity.CRITICAL
        assert det._severity(1.00) == Severity.CRITICAL

    def test_severity_nominal_below_watch(self):
        det = BOCPDDetector(alarm_threshold=0.3)
        assert det._severity(0.29) == Severity.NOMINAL


class TestBOCPDReset:
    def test_reset_channel_clears_state(self):
        rng = np.random.default_rng(11)
        det = BOCPDDetector()
        cal = _calibrated()
        for x in rng.normal(0, 1, 50):
            det.detect("sat:ch", float(x), cal)
        assert det.get_state("sat:ch")["t"] == 50
        det.reset("sat:ch")
        assert det.get_state("sat:ch") == {}

    def test_reset_all_clears_all_channels(self):
        rng = np.random.default_rng(12)
        det = BOCPDDetector()
        cal = _calibrated()
        for key in ("sat:a", "sat:b", "sat:c"):
            for x in rng.normal(0, 1, 20):
                det.detect(key, float(x), cal)
        det.reset()
        for key in ("sat:a", "sat:b", "sat:c"):
            assert det.get_state(key) == {}

    def test_channel_isolation(self):
        """Two channels should have independent state."""
        rng = np.random.default_rng(13)
        det = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        cal = _calibrated()
        # Channel A: nominal
        for x in rng.normal(0, 1, 100):
            det.detect("sat:a", float(x), cal)
        # Channel B: abrupt shift
        pre  = rng.normal(0, 1, 100)
        post = rng.normal(8, 1, 10)
        scores_b = []
        for x in np.concatenate([pre, post]):
            scores_b.append(det.detect("sat:b", float(x), cal).score)
        # State for A must not be contaminated by B's changepoint
        state_a = det.get_state("sat:a")
        state_b = det.get_state("sat:b")
        assert state_a["t"] == 100
        assert state_b["t"] == 110
        # B should have seen a peak; A should still have low run_length_mode or
        # at least the two channels should have different run-length modes
        # (independent state verification)
        assert state_a != state_b


class TestBOCPDDeterminism:
    def test_same_seed_same_scores(self):
        """Identical inputs must yield identical outputs (no random state in detector)."""
        cal = _calibrated()
        rng = np.random.default_rng(99)
        signal = rng.normal(0, 1, 100).tolist()
        signal[50:] = (rng.normal(5, 1, 50)).tolist()

        det1 = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)
        det2 = BOCPDDetector(hazard=0.002, alarm_threshold=0.3)

        scores1 = _run_signal(det1, np.array(signal), cal, "ch")
        scores2 = _run_signal(det2, np.array(signal), cal, "ch")

        np.testing.assert_array_equal(scores1, scores2)


class TestBOCPDConstructorValidation:
    def test_hazard_zero_raises(self):
        with pytest.raises(ValueError, match="hazard"):
            BOCPDDetector(hazard=0.0)

    def test_hazard_one_raises(self):
        with pytest.raises(ValueError, match="hazard"):
            BOCPDDetector(hazard=1.0)

    def test_alpha_le_one_raises(self):
        with pytest.raises(ValueError, match="alpha_0"):
            BOCPDDetector(alpha_0=1.0)
