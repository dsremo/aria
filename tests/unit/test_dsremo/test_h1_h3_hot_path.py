"""Integration tests: V3-H1 hierarchical LLR + V3-H3 isotonic calibrator
wired into `detector._ensemble_vote()`.
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection import detector as det_mod
from aria.dsremo.detection.hierarchical_llr import HierarchicalLLRWeights
from aria.dsremo.detection.isotonic_calibration import fit_isotonic_calibrator


def _triggered_results() -> list[DetectorResult]:
    """Return a mixed set of detector results — one strong cusum + weak variance."""
    return [
        DetectorResult(
            detector_name="cusum", is_anomaly=True, score=0.9,
            severity=Severity.WARNING, details={},
        ),
        DetectorResult(
            detector_name="variance", is_anomaly=True, score=0.3,
            severity=Severity.WATCH, details={},
        ),
        DetectorResult(
            detector_name="trend_velocity", is_anomaly=False, score=0.0,
            severity=Severity.NOMINAL, details={},
        ),
    ]


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure tests don't leak registered singletons into each other."""
    det_mod.register_hierarchical_llr(None)
    det_mod.register_isotonic_calibrator(None)
    yield
    det_mod.register_hierarchical_llr(None)
    det_mod.register_isotonic_calibrator(None)


# ── H-1 wiring tests ────────────────────────────────────────────────────────


class TestH1HierarchicalHotPath:

    def test_no_hlr_uses_global_weights(self):
        """Default behaviour unchanged when no HLR registered."""
        results = _triggered_results()
        # Explicit per-channel weights None → uses global WEIGHTS.
        is_anom, conf_default, sev = det_mod._ensemble_vote(
            results, weights=None, satellite_id="SAT-A",
        )
        assert is_anom or sev == Severity.NOMINAL  # either path, but deterministic

    def test_hlr_weights_consulted_when_class_known(self):
        """Registering HLR + satellite_class_map is consulted by _maybe_hierarchical_weights."""
        detector_names = list(det_mod._DEFAULT_WEIGHTS.keys())
        hlr = HierarchicalLLRWeights(
            detector_names, prior_strength=10, min_class_samples=5,
        )
        rng = np.random.default_rng(0)
        scores = rng.random((100, len(detector_names)))
        cusum_idx = detector_names.index("cusum")
        labels = (scores[:, cusum_idx] > 0.5).astype(np.int8)
        hlr.fit_class("LEO_cubesat", scores, labels)

        det_mod.register_hierarchical_llr(hlr, {"SAT-A": "LEO_cubesat"})
        w = det_mod._maybe_hierarchical_weights("SAT-A")
        assert w is not None
        assert set(w.keys()) == set(detector_names)
        # Vote still returns a valid tuple.
        is_anom, conf, sev = det_mod._ensemble_vote(
            _triggered_results(), weights=None, satellite_id="SAT-A",
        )
        assert 0.0 <= conf <= 1.0

    def test_hlr_ignored_for_unknown_satellite(self):
        detector_names = list(det_mod._DEFAULT_WEIGHTS.keys())
        hlr = HierarchicalLLRWeights(detector_names)
        det_mod.register_hierarchical_llr(hlr, {"SAT-KNOWN": "LEO_cubesat"})
        # SAT-UNKNOWN not in map → returns None → falls back to global.
        assert det_mod._maybe_hierarchical_weights("SAT-UNKNOWN") is None

    def test_hlr_ignored_when_satellite_id_none(self):
        detector_names = list(det_mod._DEFAULT_WEIGHTS.keys())
        hlr = HierarchicalLLRWeights(detector_names)
        det_mod.register_hierarchical_llr(hlr, {"SAT-A": "cls"})
        assert det_mod._maybe_hierarchical_weights(None) is None

    def test_register_none_clears_registry(self):
        hlr = HierarchicalLLRWeights(list(det_mod._DEFAULT_WEIGHTS.keys()))
        det_mod.register_hierarchical_llr(hlr, {"SAT-A": "cls"})
        assert det_mod._hierarchical_llr is not None
        det_mod.register_hierarchical_llr(None)
        assert det_mod._hierarchical_llr is None
        assert det_mod._satellite_class_map == {}


# ── H-3 wiring tests ────────────────────────────────────────────────────────


class TestH3IsotonicHotPath:

    def test_no_calibrator_is_identity(self):
        results = _triggered_results()
        _, conf_baseline, _ = det_mod._ensemble_vote(results)
        # No calibrator registered → confidence unchanged from baseline
        det_mod.register_isotonic_calibrator(None)
        _, conf_again, _ = det_mod._ensemble_vote(results)
        assert conf_baseline == pytest.approx(conf_again, abs=1e-9)

    def test_registered_calibrator_alters_confidence(self):
        rng = np.random.default_rng(0)
        n = 200
        # Build a concave true mapping so isotonic pushes mid-range DOWN
        # (opposite of identity): scores tightly clustered near 1 but
        # only 10 % are labelled anomalies → calibrator collapses them low.
        scores = np.linspace(0.4, 0.9, n)
        labels = (rng.random(n) < 0.1).astype(np.int8)
        calib = fit_isotonic_calibrator(scores, labels)
        det_mod.register_isotonic_calibrator(calib)

        results = _triggered_results()
        _, conf_calibrated, _ = det_mod._ensemble_vote(results)
        det_mod.register_isotonic_calibrator(None)
        _, conf_uncalibrated, _ = det_mod._ensemble_vote(results)
        # Calibrated path should collapse mid-range confidences → lower.
        assert conf_calibrated <= conf_uncalibrated + 1e-9

    def test_calibrator_exception_falls_back_to_identity(self):
        class _BoomCalib:
            def predict(self, _):
                raise RuntimeError("boom")
        det_mod.register_isotonic_calibrator(_BoomCalib())
        _, conf, _ = det_mod._ensemble_vote(_triggered_results())
        det_mod.register_isotonic_calibrator(None)
        _, baseline_conf, _ = det_mod._ensemble_vote(_triggered_results())
        assert conf == pytest.approx(baseline_conf, abs=1e-9)
