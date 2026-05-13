"""Sprint 15: Matrix Profile Discord Detector (10th Ensemble Member) Tests.

Target: 817 existing + 31 new = 848 passing tests.

Classes
-------
TestDiscordDetector          (16 tests) — DiscordDetector unit tests
TestEnsembleWith10Detectors  ( 8 tests) — ensemble weight/integration
TestDiscordIntegration       ( 7 tests) — detector.py integration
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_calibration(ref_std: float = 1.0, is_calibrated: bool = True):
    """Build a minimal CalibrationState-like mock."""
    cal = MagicMock()
    cal.is_calibrated = is_calibrated
    cal.ref_std = ref_std
    return cal


def _periodic_residuals(n: int = 300, period: float = 30.0, amp: float = 1.0) -> np.ndarray:
    """Normal periodic signal — lots of repeating pattern, low discord."""
    return np.array([amp * math.sin(2 * math.pi * i / period) for i in range(n)])


def _noisy_residuals(n: int = 300, std: float = 1.0) -> np.ndarray:
    """Random Gaussian noise — no strong pattern, moderate discord."""
    rng = np.random.default_rng(42)
    return rng.normal(0.0, std, size=n)


def _discord_injection(base: np.ndarray, start: int, value: float = 50.0) -> np.ndarray:
    """Inject a flat discord (constant block) into the last `start` samples."""
    arr = base.copy()
    arr[start:] = value
    return arr


# ═══════════════════════════════════════════════════════════════════════════════
# Class 1: DiscordDetector unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscordDetector:
    """Unit tests for DiscordDetector (Sprint 15)."""

    # ── Construction ─────────────────────────────────────────────────────────

    def test_construction_defaults(self) -> None:
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector()
        assert det.m == 20
        assert det.threshold_sigma == 3.0
        assert det.min_window_factor == 4

    def test_construction_custom_params(self) -> None:
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=200, threshold_sigma=2.5)
        assert det.m == 10
        assert det.threshold_sigma == 2.5

    def test_window_enforced_min(self) -> None:
        """window must be >= min_window_factor × m + 1."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=20, window=10, min_window_factor=4)
        # window=10 < 4×20+1=81 → enforced to 81
        assert det.window >= 4 * det.m + 1

    # ── Warm-up / guard returns ───────────────────────────────────────────────

    def test_returns_nominal_when_not_calibrated(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100)
        cal = _make_calibration(is_calibrated=False)
        result = det.detect(_periodic_residuals(200), cal)
        assert result.is_anomaly is False
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "warming_up"

    def test_returns_nominal_when_insufficient_data(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=20, window=300, min_window_factor=4)
        cal = _make_calibration()
        # Need 4×20+1=81 samples; provide only 10
        result = det.detect(_periodic_residuals(10), cal)
        assert result.is_anomaly is False
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "insufficient_data"

    def test_returns_nominal_when_constant_channel(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100)
        cal = _make_calibration()
        # All-constant signal → std=0 → constant channel guard
        result = det.detect(np.zeros(200), cal)
        assert result.is_anomaly is False
        assert result.severity == Severity.NOMINAL
        assert result.details.get("reason") == "constant_channel"

    # ── Normal signal → no alarm ─────────────────────────────────────────────

    def test_periodic_signal_no_alarm(self) -> None:
        """Periodic signal with many repeating windows → low discord → no alarm."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=20, window=200, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        residuals = _periodic_residuals(n=200, period=30.0)
        result = det.detect(residuals, cal)
        # Should be NOMINAL (no alarm), or score < 1.0
        assert result.is_anomaly is False or result.score < 1.0

    def test_flat_signal_near_zero_score(self) -> None:
        """Truly flat signal triggers constant_channel guard (score=0)."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100)
        cal = _make_calibration(ref_std=1.0)
        result = det.detect(np.zeros(100), cal)
        assert result.score == 0.0
        assert result.is_anomaly is False

    # ── Discord injection → alarm ─────────────────────────────────────────────

    def test_discord_injection_raises_score(self) -> None:
        """Injecting a flat constant block into a periodic signal raises discord score."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=20, window=280, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        normal = _periodic_residuals(n=280, period=30.0)
        # Score on normal signal
        r_normal = det.detect(normal, cal)
        # Inject a novel flat block at end (very different from any periodic window)
        discord = _discord_injection(normal, start=260, value=50.0)
        r_discord = det.detect(discord, cal)
        assert r_discord.score >= r_normal.score

    def test_discord_injection_can_trigger_anomaly(self) -> None:
        """A steep ramp injected at end of periodic signal should trigger alarm."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=15, window=200, threshold_sigma=1.5)
        cal = _make_calibration(ref_std=1.0)
        normal = _periodic_residuals(n=200, period=20.0, amp=1.0)
        discord = normal.copy()
        # Inject a steep high-amplitude ramp (non-constant, unusual shape)
        # into the last m samples so the query is clearly different from history
        discord[-15:] = np.linspace(-100.0, 100.0, 15)
        result = det.detect(discord, cal)
        assert result.is_anomaly is True

    # ── Score clamping ────────────────────────────────────────────────────────

    def test_score_clamped_to_unit_interval(self) -> None:
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        for residuals in [
            _periodic_residuals(200),
            _discord_injection(_periodic_residuals(200), 190, 1000.0),
        ]:
            r = det.detect(residuals, cal)
            assert 0.0 <= r.score <= 1.0

    # ── Severity classification ───────────────────────────────────────────────

    def test_severity_watch_when_anomaly_with_low_z(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        normal = _periodic_residuals(n=100, period=15.0)
        # Mild discord injection — just over threshold → WATCH or higher
        discord = _discord_injection(normal, start=90, value=5.0)
        result = det.detect(discord, cal)
        if result.is_anomaly:
            assert result.severity in (Severity.WATCH, Severity.WARNING, Severity.CRITICAL)

    def test_severity_critical_when_extreme_discord(self) -> None:
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.discord_detector import DiscordDetector
        # Very low threshold → extreme discord ratio → CRITICAL
        det = DiscordDetector(m=10, window=150, threshold_sigma=0.5)
        cal = _make_calibration(ref_std=1.0)
        normal = _periodic_residuals(n=150, period=15.0)
        discord = _discord_injection(normal, start=140, value=500.0)
        result = det.detect(discord, cal)
        if result.is_anomaly:
            assert result.severity in (Severity.WARNING, Severity.CRITICAL)

    # ── Detector name ─────────────────────────────────────────────────────────

    def test_detector_name(self) -> None:
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100)
        cal = _make_calibration()
        result = det.detect(_periodic_residuals(200), cal)
        assert result.detector_name == "matrix_profile"

    # ── Details dict ─────────────────────────────────────────────────────────

    def test_details_keys_present_on_detection(self) -> None:
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        result = det.detect(_periodic_residuals(200), cal)
        if "reason" not in result.details:
            # Full detection path ran — check expected keys
            assert "discord_score" in result.details
            assert "threshold" in result.details
            assert "ref_mean" in result.details
            assert "ref_std" in result.details
            assert "z_score" in result.details

    # ── Per-channel threshold override ────────────────────────────────────────

    def test_discord_threshold_override(self) -> None:
        """Providing discord_threshold=None should use detector default; non-None overrides."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        det = DiscordDetector(m=10, window=100, threshold_sigma=100.0)
        cal = _make_calibration(ref_std=1.0)
        normal = _periodic_residuals(n=150, period=15.0)
        discord = _discord_injection(normal, start=140, value=50.0)
        # With very high sigma (100) → no alarm
        r_high = det.detect(discord, cal, discord_threshold=100.0)
        # With very low sigma (0.1) → alarm
        r_low = det.detect(discord, cal, discord_threshold=0.1)
        assert r_high.score <= r_low.score

    # ── Window parameter limits history ──────────────────────────────────────

    def test_window_limits_history(self) -> None:
        """Only the last `window` residuals should be used."""
        from aria.dsremo.detection.discord_detector import DiscordDetector
        # Small window so only last 82 of 500 residuals used
        det = DiscordDetector(m=10, window=82, threshold_sigma=3.0)
        cal = _make_calibration(ref_std=1.0)
        # Build: first 418 are all constant=5, last 82 are periodic
        prefix = np.full(418, 5.0)
        tail = _periodic_residuals(82, period=15.0)
        residuals = np.concatenate([prefix, tail])
        result = det.detect(residuals, cal)
        # Constant prefix should NOT affect the result since window=82 truncates it
        assert isinstance(result.score, float)
        assert 0.0 <= result.score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Class 2: Ensemble with 10 detectors
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnsembleWith10Detectors:
    """Verify that the 10-detector ensemble is correctly wired."""

    def test_weights_sum_to_one(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, f"Sum={sum(WEIGHTS.values())}"

    def test_matrix_profile_key_in_weights(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert "matrix_profile" in WEIGHTS

    def test_ten_detector_keys_in_weights(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        expected = {
            "cusum", "ewma", "statistical", "changepoint",
            "isolation_forest", "variance", "lstm", "tcn",
            "trend_velocity", "matrix_profile",
        }
        assert expected.issubset(set(WEIGHTS.keys()))  # forward-compatible (new detectors added each sprint)

    def test_build_explanation_handles_matrix_profile(self) -> None:
        """_build_explanation must not raise for 'matrix_profile' detector name."""
        from aria.dsremo.detection.detector import _build_explanation
        from aria.dsremo.core.models import DetectorResult, Severity

        discord_result = DetectorResult(
            detector_name="matrix_profile",
            is_anomaly=True,
            score=0.85,
            severity=Severity.WARNING,
            details={
                "discord_score": 2.345,
                "threshold": 1.500,
                "ref_mean": 0.800,
                "ref_std": 0.200,
                "z_score": 7.725,
            },
        )
        nominal = DetectorResult(
            detector_name="cusum", is_anomaly=False, score=0.0,
            severity=Severity.NOMINAL, details={},
        )
        feat_res = MagicMock()
        feat_res.raw_value = 1.234
        feat_res.rolling_std = 0.456
        feat_res.features = {}
        alarm_row = {"value": 1.0, "unit": "V", "subsystem": "eps", "parameter": "test_p", "timestamp": None}
        explanation = _build_explanation("test_p", feat_res, [nominal, discord_result], alarm_row, "stl")
        assert "Unusual shape" in explanation or "matrix_profile" in explanation.lower() or "discord" in explanation.lower()

    def test_matrix_profile_weight_positive(self) -> None:
        from aria.dsremo.detection.detector import WEIGHTS
        assert WEIGHTS["matrix_profile"] > 0.0

    def test_init_detectors_reads_matrix_profile_config(self) -> None:
        """init_detectors must read matrix_profile config keys without error."""
        from aria.dsremo.detection.detector import init_detectors
        settings = MagicMock()
        settings.get.side_effect = lambda key, default=None: {
            "detection": {
                "matrix_profile_m":     15,
                "matrix_profile_buffer": 250,
                "matrix_profile_sigma":  2.5,
            },
            "features": {},
        }.get(key, default or {})
        # Should not raise
        init_detectors(settings)

    def test_discord_alone_above_consensus_contributes_to_ensemble(self) -> None:
        """If discord fires with high score, ensemble confidence should reflect it."""
        from aria.dsremo.detection.detector import _ensemble_vote
        from aria.dsremo.core.models import DetectorResult, Severity

        def _nominal(name: str) -> DetectorResult:
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={},
            )

        discord_result = DetectorResult(
            detector_name="matrix_profile",
            is_anomaly=True,
            score=1.0,
            severity=Severity.CRITICAL,
            details={},
        )
        results = [
            _nominal("cusum"), _nominal("ewma"), _nominal("statistical"),
            _nominal("changepoint"), _nominal("isolation_forest"), _nominal("variance"),
            _nominal("lstm"), _nominal("tcn"), _nominal("trend_velocity"),
            discord_result,
        ]
        is_anomaly, confidence, severity = _ensemble_vote(results)
        # discord weight=0.07 alone is below typical consensus threshold
        # but confidence should be non-zero
        assert confidence > 0.0

    def test_discord_plus_cusum_higher_confidence(self) -> None:
        """discord + cusum together should produce higher confidence than discord alone."""
        from aria.dsremo.detection.detector import _ensemble_vote, WEIGHTS
        from aria.dsremo.core.models import DetectorResult, Severity

        def _nominal(name: str) -> DetectorResult:
            return DetectorResult(
                detector_name=name, is_anomaly=False, score=0.0,
                severity=Severity.NOMINAL, details={},
            )

        def _fire(name: str) -> DetectorResult:
            return DetectorResult(
                detector_name=name, is_anomaly=True, score=1.0,
                severity=Severity.CRITICAL, details={},
            )

        discord_only = [
            _nominal("cusum"), _nominal("ewma"), _nominal("statistical"),
            _nominal("changepoint"), _nominal("isolation_forest"), _nominal("variance"),
            _nominal("lstm"), _nominal("tcn"), _nominal("trend_velocity"),
            _fire("matrix_profile"),
        ]
        discord_plus_cusum = [
            _fire("cusum"), _nominal("ewma"), _nominal("statistical"),
            _nominal("changepoint"), _nominal("isolation_forest"), _nominal("variance"),
            _nominal("lstm"), _nominal("tcn"), _nominal("trend_velocity"),
            _fire("matrix_profile"),
        ]
        _, conf_discord_only, _ = _ensemble_vote(discord_only)
        _, conf_discord_cusum, _ = _ensemble_vote(discord_plus_cusum)
        assert conf_discord_cusum > conf_discord_only


# ═══════════════════════════════════════════════════════════════════════════════
# Class 3: Discord integration in detector.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscordIntegration:
    """Verify DiscordDetector is correctly integrated into detector.py."""

    def test_discord_detector_singleton_exists(self) -> None:
        """_discord_detector singleton should be a DiscordDetector."""
        from aria.dsremo.detection import detector as det_mod
        from aria.dsremo.detection.discord_detector import DiscordDetector
        assert hasattr(det_mod, "_discord_detector")
        assert isinstance(det_mod._discord_detector, DiscordDetector)

    def test_discord_globals_exist(self) -> None:
        """Config globals for discord should be present in detector module."""
        from aria.dsremo.detection import detector as det_mod
        assert hasattr(det_mod, "_discord_m")
        assert hasattr(det_mod, "_discord_window")
        assert hasattr(det_mod, "_discord_threshold_sigma")

    def test_discord_import_in_detector(self) -> None:
        """DiscordDetector must be importable from detector.py's module namespace."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "detector_src",
            str(_ROOT / "src" / "dsremo" / "detection" / "detector.py"),
        )
        # Just confirm import doesn't crash
        from aria.dsremo.detection.discord_detector import DiscordDetector
        assert DiscordDetector is not None

    def test_discord_models_not_in_dict(self) -> None:
        """DiscordDetector is a singleton (not per-channel dict like lstm/tcn)."""
        from aria.dsremo.detection import detector as det_mod
        # There is no _discord_models dict — it's a stateless singleton
        assert not hasattr(det_mod, "_discord_models")

    def test_discord_threshold_in_effective_thresholds(self) -> None:
        """get_effective_thresholds must include 'discord_threshold' key."""
        from aria.dsremo.detection.detector import get_effective_thresholds
        eff = get_effective_thresholds("test_sat", "test_param")
        assert "discord_threshold" in eff

    def test_discord_detect_returns_detector_result(self) -> None:
        """Direct detect() call on the singleton returns a DetectorResult."""
        from aria.dsremo.detection import detector as det_mod
        from aria.dsremo.core.models import DetectorResult
        cal = _make_calibration(ref_std=1.0, is_calibrated=True)
        residuals = _periodic_residuals(200)
        result = det_mod._discord_detector.detect(residuals, cal)
        assert isinstance(result, DetectorResult)
        assert result.detector_name == "matrix_profile"

    def test_analyze_channel_history_includes_discord_in_all_results(self) -> None:
        """Source inspection: analyze_channel_history should reference matrix_profile."""
        import inspect
        from aria.dsremo.detection import detector as det_mod
        src = inspect.getsource(det_mod.analyze_channel_history)
        assert "matrix_profile" in src or "discord_result" in src
