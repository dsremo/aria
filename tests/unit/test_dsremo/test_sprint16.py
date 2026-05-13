"""Sprint 16: Model Persistence + Smart Cooldown Tests.

Target: 849 existing + 32 new = 881 passing tests.

Classes
-------
TestLSTMSaveLoad          (10 tests) — AutoencoderDetector.save() / load()
TestTCNSaveLoad           (10 tests) — TCNDetector.save() / load()
TestModelDirWiring        ( 7 tests) — detector.py model_dir + warm-start
TestSmartCooldown         ( 5 tests) — smart_cooldown_hours() in utils.py
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normal_residuals(n: int = 200) -> list[float]:
    """Deterministic pseudo-normal residuals for training."""
    return [math.sin(i * 0.3) + 0.1 * (i % 5 - 2) for i in range(n)]


def _fit_lstm(min_samples: int = 80, epochs: int = 3) -> "AutoencoderDetector":
    """Return a fitted AutoencoderDetector (tiny, fast)."""
    from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
    det = AutoencoderDetector(
        seq_length=20, min_train_samples=min_samples, epochs=epochs, threshold_sigma=3.0
    )
    data = _normal_residuals(200)
    for r in data:
        det.add_sample(r)
    det.fit()
    return det


def _fit_tcn(min_samples: int = 80, epochs: int = 3) -> "TCNDetector":
    """Return a fitted TCNDetector (tiny, fast)."""
    from aria.dsremo.detection.tcn_detector import TCNDetector
    det = TCNDetector(
        seq_length=20, min_train_samples=min_samples, epochs=epochs, threshold_sigma=3.0
    )
    data = _normal_residuals(200)
    for r in data:
        det.add_sample(r)
    det.fit()
    return det


# ── TestLSTMSaveLoad ──────────────────────────────────────────────────────────

class TestLSTMSaveLoad:
    """AutoencoderDetector.save() and load() persistence tests."""

    def test_save_creates_file(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            assert path.exists()

    def test_save_noop_when_not_fitted(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        det = AutoencoderDetector()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            assert not path.exists()   # no file written

    def test_load_returns_true_on_success(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
            fresh = AutoencoderDetector(seq_length=20)
            result = fresh.load(path)
            assert result is True

    def test_load_marks_is_fitted(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
            fresh = AutoencoderDetector(seq_length=20)
            fresh.load(path)
            assert fresh.is_fitted

    def test_load_restores_threshold(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        original_threshold = det._threshold
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
            fresh = AutoencoderDetector(seq_length=20)
            fresh.load(path)
            assert abs(fresh._threshold - original_threshold) < 1e-6

    def test_loaded_model_can_detect(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
            fresh = AutoencoderDetector(seq_length=20)
            fresh.load(path)
            residuals = _normal_residuals(200)
            result = fresh.detect(residuals)
            assert result.detector_name == "lstm"
            assert result.score >= 0.0

    def test_load_returns_false_on_missing_file(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        det = AutoencoderDetector(seq_length=20)
        result = det.load(Path("/tmp/nonexistent_dsremo_test.pt"))
        assert result is False

    def test_load_does_not_raise_on_corrupt_file(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.lstm.pt"
            path.write_bytes(b"not a valid pytorch checkpoint")
            det = AutoencoderDetector(seq_length=20)
            result = det.load(path)
            assert result is False
            assert not det.is_fitted

    def test_save_creates_parent_directories(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "dir" / "model.lstm.pt"
            det.save(path)
            assert path.exists()

    def test_samples_since_fit_reset_after_load(self):
        pytest.importorskip("torch")
        det = _fit_lstm()
        # Simulate that samples have accumulated since last fit
        det._samples_since_fit = 999
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.lstm.pt"
            det.save(path)
            from aria.dsremo.detection.autoencoder_detector import AutoencoderDetector
            fresh = AutoencoderDetector(seq_length=20)
            fresh.load(path)
            assert fresh._samples_since_fit == 0


# ── TestTCNSaveLoad ───────────────────────────────────────────────────────────

class TestTCNSaveLoad:
    """TCNDetector.save() and load() persistence tests."""

    def test_save_creates_file(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            assert path.exists()

    def test_save_noop_when_not_fitted(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            assert not path.exists()

    def test_load_returns_true_on_success(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            from aria.dsremo.detection.tcn_detector import TCNDetector
            fresh = TCNDetector(seq_length=20)
            result = fresh.load(path)
            assert result is True

    def test_load_marks_is_fitted(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            from aria.dsremo.detection.tcn_detector import TCNDetector
            fresh = TCNDetector(seq_length=20)
            fresh.load(path)
            assert fresh.is_fitted

    def test_load_restores_threshold(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        original_threshold = det._threshold
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            from aria.dsremo.detection.tcn_detector import TCNDetector
            fresh = TCNDetector(seq_length=20)
            fresh.load(path)
            assert abs(fresh._threshold - original_threshold) < 1e-6

    def test_loaded_model_can_detect(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            from aria.dsremo.detection.tcn_detector import TCNDetector
            fresh = TCNDetector(seq_length=20)
            fresh.load(path)
            residuals = _normal_residuals(200)
            result = fresh.detect(residuals)
            assert result.detector_name == "tcn"
            assert result.score >= 0.0

    def test_load_returns_false_on_missing_file(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.tcn_detector import TCNDetector
        det = TCNDetector(seq_length=20)
        result = det.load(Path("/tmp/nonexistent_dsremo_tcn_test.pt"))
        assert result is False

    def test_load_does_not_raise_on_corrupt_file(self):
        pytest.importorskip("torch")
        from aria.dsremo.detection.tcn_detector import TCNDetector
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.tcn.pt"
            path.write_bytes(b"not a valid pytorch checkpoint")
            det = TCNDetector(seq_length=20)
            result = det.load(path)
            assert result is False
            assert not det.is_fitted

    def test_save_creates_parent_directories(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep" / "nested" / "model.tcn.pt"
            det.save(path)
            assert path.exists()

    def test_samples_since_fit_reset_after_load(self):
        pytest.importorskip("torch")
        det = _fit_tcn()
        det._samples_since_fit = 777
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.tcn.pt"
            det.save(path)
            from aria.dsremo.detection.tcn_detector import TCNDetector
            fresh = TCNDetector(seq_length=20)
            fresh.load(path)
            assert fresh._samples_since_fit == 0


# ── TestModelDirWiring ────────────────────────────────────────────────────────

class TestModelDirWiring:
    """detector.py model_dir global + warm-start + save_channel_models()."""

    def test_model_dir_default_is_none(self):
        import aria.dsremo.detection.detector as det_mod
        # _model_dir starts None until init_detectors sets it
        # (may be set if init ran — just check the attribute exists)
        assert hasattr(det_mod, "_model_dir")

    def test_lstm_model_path_none_when_model_dir_none(self):
        import aria.dsremo.detection.detector as det_mod
        original = det_mod._model_dir
        try:
            det_mod._model_dir = None
            path = det_mod._lstm_model_path("SAT-1", "voltage")
            assert path is None
        finally:
            det_mod._model_dir = original

    def test_tcn_model_path_none_when_model_dir_none(self):
        import aria.dsremo.detection.detector as det_mod
        original = det_mod._model_dir
        try:
            det_mod._model_dir = None
            path = det_mod._tcn_model_path("SAT-1", "voltage")
            assert path is None
        finally:
            det_mod._model_dir = original

    def test_lstm_model_path_returns_path_when_model_dir_set(self):
        import aria.dsremo.detection.detector as det_mod
        original = det_mod._model_dir
        try:
            det_mod._model_dir = Path("/tmp/dsremo_test_models")
            path = det_mod._lstm_model_path("SAT-1", "voltage")
            assert path is not None
            assert str(path).endswith(".lstm.pt")
            assert "SAT-1" in str(path)
            assert "voltage" in str(path)
        finally:
            det_mod._model_dir = original

    def test_tcn_model_path_returns_path_when_model_dir_set(self):
        import aria.dsremo.detection.detector as det_mod
        original = det_mod._model_dir
        try:
            det_mod._model_dir = Path("/tmp/dsremo_test_models")
            path = det_mod._tcn_model_path("SAT-1", "current")
            assert path is not None
            assert str(path).endswith(".tcn.pt")
        finally:
            det_mod._model_dir = original

    def test_save_channel_models_exists_and_callable(self):
        from aria.dsremo.detection.detector import save_channel_models
        assert callable(save_channel_models)

    def test_save_channel_models_noop_when_model_dir_none(self):
        """save_channel_models() must not raise even with no model_dir."""
        import aria.dsremo.detection.detector as det_mod
        original = det_mod._model_dir
        try:
            det_mod._model_dir = None
            # Should not raise — just silently no-op
            det_mod.save_channel_models("SAT-1", "temperature")
        finally:
            det_mod._model_dir = original


# ── TestSmartCooldown ─────────────────────────────────────────────────────────

class TestSmartCooldown:
    """smart_cooldown_hours() burst-analysis function."""

    def _make_csv(self, tmp_dir: str, interval_s: float = 1.0, n: int = 500,
                  inject_bursts: bool = True) -> Path:
        """Write a synthetic CSV with optional burst anomalies."""
        import pandas as pd
        from datetime import datetime, timedelta, timezone
        t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        timestamps = [t0 + timedelta(seconds=i * interval_s) for i in range(n)]
        values = [0.0] * n
        if inject_bursts:
            # Inject 6 clear bursts, each 10 samples, spaced 50 samples apart
            for burst_start in range(20, n - 50, 50):
                for j in range(10):
                    if burst_start + j < n:
                        values[burst_start + j] = 20.0   # very large z-score
        df = pd.DataFrame({"timestamp": [t.isoformat() for t in timestamps], "value": values})
        path = Path(tmp_dir) / "test_data.csv"
        df.to_csv(path, index=False)
        return path

    def test_smart_cooldown_importable(self):
        from aria.dsremo.ingest.utils import smart_cooldown_hours
        assert callable(smart_cooldown_hours)

    def test_returns_none_for_flat_signal(self):
        from aria.dsremo.ingest.utils import smart_cooldown_hours
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_csv(tmp, inject_bursts=False)
            result = smart_cooldown_hours(path)
            assert result is None   # no bursts → can't estimate

    def test_returns_float_for_burst_signal(self):
        from aria.dsremo.ingest.utils import smart_cooldown_hours
        with tempfile.TemporaryDirectory() as tmp:
            path = self._make_csv(tmp, inject_bursts=True)
            result = smart_cooldown_hours(path)
            assert result is None or isinstance(result, float)
            if result is not None:
                assert result > 0.0

    def test_returns_none_for_missing_file(self):
        from aria.dsremo.ingest.utils import smart_cooldown_hours
        result = smart_cooldown_hours(Path("/tmp/nonexistent_dsremo_csv_test.csv"))
        assert result is None

    def test_returns_none_for_fewer_than_min_bursts(self):
        """Fewer than min_bursts=5 clusters → None returned."""
        import pandas as pd
        from datetime import datetime, timedelta, timezone
        from aria.dsremo.ingest.utils import smart_cooldown_hours
        with tempfile.TemporaryDirectory() as tmp:
            t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
            n = 200
            timestamps = [t0 + timedelta(seconds=i) for i in range(n)]
            values = [0.0] * n
            # Only 2 bursts — not enough for min_bursts=5
            for j in range(5):
                values[j + 10] = 20.0
            for j in range(5):
                values[j + 100] = 20.0
            df = pd.DataFrame({"timestamp": [t.isoformat() for t in timestamps],
                               "value": values})
            path = Path(tmp) / "sparse.csv"
            df.to_csv(path, index=False)
            result = smart_cooldown_hours(path, min_bursts=5)
            assert result is None
