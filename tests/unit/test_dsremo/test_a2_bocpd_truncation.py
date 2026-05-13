"""Tests for V3-A2: overflow-aware R_t truncation in BOCPD.

Before the fix, probability mass past `max_run` was silently dropped, so
`sum(R_t)` drifted below 1.0 on long stable regimes — which inflated
R_t[0] during the next normalisation step and caused spurious
changepoint detections after ~max_run samples.

After the fix, overflow mass is absorbed into R_t[max_run] and total
probability stays at 1.0 indefinitely.
"""

from __future__ import annotations

import numpy as np

from aria.dsremo.detection.bocpd_detector import BOCPDDetector
from aria.dsremo.detection.calibration import CalibrationState


def _calibrated(ref_mean: float = 0.0, ref_std: float = 1.0) -> CalibrationState:
    cal = CalibrationState()
    cal.state        = "calibrated"
    cal.ref_mean     = ref_mean
    cal.ref_std      = ref_std
    cal.sample_count = 200
    return cal


class TestTruncationMassConservation:

    def test_rt_sums_to_one_before_overflow(self):
        """For t ≤ max_run, R_t already sums to 1 — no change."""
        det = BOCPDDetector(max_run=50, detection_lag=1)
        cal = _calibrated()
        rng = np.random.default_rng(0)
        for _ in range(30):
            det.detect("K", float(rng.normal(0.0, 1.0)), cal)
        state = det._states["K"]
        assert abs(state.R.sum() - 1.0) < 1e-10

    def test_rt_sums_to_one_after_overflow(self):
        """For t > max_run, the fix routes overflow mass into R_t[max_run]
        so total probability stays at 1.  Before the fix this would
        drift below 1 (typically 0.5-0.8 after 3× max_run samples)."""
        det = BOCPDDetector(max_run=50, detection_lag=1)
        cal = _calibrated()
        rng = np.random.default_rng(0)
        for _ in range(250):  # 5× max_run
            det.detect("K", float(rng.normal(0.0, 1.0)), cal)
        state = det._states["K"]
        assert abs(state.R.sum() - 1.0) < 1e-9

    def test_mass_concentrated_at_tail_in_long_stable_run(self):
        """After a long stable regime the bulk of the run-length mass
        should sit at R_t[max_run] (operator sees "we've been stable
        for a long time"), not scattered across the middle of the
        distribution or piled on R_t[0]."""
        det = BOCPDDetector(max_run=50, hazard=0.001, detection_lag=1)
        cal = _calibrated()
        rng = np.random.default_rng(0)
        for _ in range(500):  # 10× max_run
            det.detect("K", float(rng.normal(0.0, 1.0)), cal)
        state = det._states["K"]
        # Final bin should dominate.
        assert state.R[state.R.size - 1] > 0.5
        # And R_t[0] should remain small (no spurious changepoints on a
        # stable regime — precisely what A-2 was supposed to prevent).
        assert state.R[0] < 0.05
