"""Tests for V3-V1 time-aware extensions on AbstractMLDetector.

Validates:
 1. Plain add_sample() keeps _ts_buffer empty
 2. add_sample_with_time() populates both buffers in sync
 3. Mixing add_sample with add_sample_with_time creates length mismatch → get_encoded_sequence returns None
 4. get_encoded_sequence returns None when no timestamps have been recorded
 5. get_encoded_sequence returns an EncodedSequence when timestamps are present
 6. Encoded sequence preserves sample count for uniform cadence
 7. Encoded sequence inserts gap token on large temporal gap
 8. sample_count works identically for add_sample / add_sample_with_time
 9. Re-using the detector (add then add_with_time) yields unsynced buffers → None
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.base_ml_detector import AbstractMLDetector


class _StubDetector(AbstractMLDetector):
    """Minimal concrete subclass for testing the base class contract."""

    _detector_name = "stub"
    _log_prefix = "stub"

    def _build_model(self):
        raise NotImplementedError

    def _model_config(self) -> dict:
        return {}

    def _load_model_from_config(self, cfg: dict):
        raise NotImplementedError


def _make() -> _StubDetector:
    return _StubDetector(
        seq_length=8,
        epochs=1,
        lr=1e-3,
        min_train_samples=30,
        retrain_interval=50,
        threshold_sigma=3.0,
    )


class TestBuffers:

    def test_plain_add_sample_keeps_ts_buffer_empty(self):
        det = _make()
        for x in [1.0, 2.0, 3.0]:
            det.add_sample(x)
        assert det.sample_count == 3
        assert det._ts_buffer == []

    def test_add_with_time_populates_both_buffers(self):
        det = _make()
        for i, x in enumerate([1.0, 2.0, 3.0]):
            det.add_sample_with_time(x, float(i))
        assert det.sample_count == 3
        assert len(det._ts_buffer) == 3
        assert det._ts_buffer == [0.0, 1.0, 2.0]

    def test_mixed_usage_breaks_sync_and_returns_none(self):
        det = _make()
        det.add_sample_with_time(1.0, 0.0)
        det.add_sample(2.0)       # no timestamp → breaks parity
        det.add_sample_with_time(3.0, 2.0)
        assert det.get_encoded_sequence(dt_nominal_s=1.0) is None


class TestEncodedSequence:

    def test_none_when_no_timestamps(self):
        det = _make()
        for x in [1.0, 2.0, 3.0]:
            det.add_sample(x)
        assert det.get_encoded_sequence(dt_nominal_s=1.0) is None

    def test_returns_encoded_sequence_on_uniform_stream(self):
        det = _make()
        for i in range(5):
            det.add_sample_with_time(float(i), float(i))
        enc = det.get_encoded_sequence(dt_nominal_s=1.0)
        assert enc is not None
        # Uniform cadence → no gap tokens inserted → length = input length.
        assert enc.values.shape == (5, 2)
        assert not enc.gap_mask.any()

    def test_gap_token_inserted_on_large_interval(self):
        det = _make()
        det.add_sample_with_time(0.0, 0.0)
        det.add_sample_with_time(1.0, 1.0)
        det.add_sample_with_time(2.0, 500.0)  # huge gap
        enc = det.get_encoded_sequence(dt_nominal_s=1.0)
        assert enc is not None
        # Exactly one gap token injected.
        assert enc.gap_mask.sum() == 1


class TestCounts:

    def test_sample_count_matches_add_sample_with_time(self):
        det = _make()
        for i in range(7):
            det.add_sample_with_time(float(i), float(i))
        assert det.sample_count == 7
