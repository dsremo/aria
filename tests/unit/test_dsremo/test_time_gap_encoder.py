"""Tests for V3-V1 time-gap encoder (Shukla & Marlin 2021).

Validates:
 1. encode: raises on dt_nominal_s <= 0
 2. encode: raises on mismatched lengths
 3. encode: raises on non-1D inputs
 4. encode: empty input returns (0,2) values + empty mask
 5. encode: first token always has log_dt = 0
 6. encode: uniform sampling at nominal Δt → all log_dt = 0
 7. encode: faster-than-nominal Δt → negative log_dt
 8. encode: slower-than-nominal but < GAP_THRESHOLD → positive log_dt
 9. encode: gap > GAP_THRESHOLD inserts GAP token + real sample (2 tokens)
10. encode: multiple gaps → mask aligns with inserted tokens
11. encode: gap-token value equals GAP_TOKEN_VALUE
12. encode: gap-token log_dt equals GAP_LOG_DT
13. encode: gap-token timestamp is midpoint of the gap
14. encode: insert_gap_tokens=False skips gap insertion (just log Δt grows)
15. encode: very small Δt is clipped to MIN_DT_FRAC × dt_nominal_s
16. reconstruction_loss_mask: returns 1.0 at real tokens, 0.0 at gap tokens
17. effective_sample_count: excludes gap tokens
18. detect_nominal_cadence_s: returns 0 when too few samples
19. detect_nominal_cadence_s: returns median interval on regular stream
20. detect_nominal_cadence_s: robust to a single large gap
21. EncodedSequence.values has shape (T, 2)
22. Real spacecraft scenario: 1 Hz residuals with 30 s AOS gap → 1 gap token inserted
23. Encoded output length = input length + number of gap tokens
"""

from __future__ import annotations

import numpy as np
import pytest

from aria.dsremo.detection.time_gap_encoder import (
    GAP_LOG_DT,
    GAP_THRESHOLD,
    GAP_TOKEN_VALUE,
    MIN_DT_FRAC,
    detect_nominal_cadence_s,
    effective_sample_count,
    encode,
    reconstruction_loss_mask,
)


class TestInputValidation:

    def test_raises_on_zero_dt_nominal(self):
        with pytest.raises(ValueError):
            encode(np.zeros(3), np.arange(3, dtype=float), dt_nominal_s=0.0)

    def test_raises_on_length_mismatch(self):
        with pytest.raises(ValueError):
            encode(np.zeros(5), np.arange(3, dtype=float), dt_nominal_s=1.0)

    def test_raises_on_non_1d(self):
        with pytest.raises(ValueError):
            encode(np.zeros((3, 2)), np.arange(3, dtype=float), dt_nominal_s=1.0)

    def test_empty_input_returns_empty(self):
        out = encode(np.zeros(0), np.zeros(0), dt_nominal_s=1.0)
        assert out.values.shape == (0, 2)
        assert out.gap_mask.shape == (0,)


class TestUniformSampling:

    def test_first_token_has_zero_log_dt(self):
        out = encode(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0]), dt_nominal_s=1.0)
        assert out.values[0, 1] == 0.0

    def test_all_log_dt_zero_when_on_schedule(self):
        out = encode(np.ones(5), np.arange(5.0), dt_nominal_s=1.0)
        assert np.allclose(out.values[:, 1], 0.0)

    def test_negative_log_dt_when_fast(self):
        """Samples arriving at 0.5 × nominal → log(0.5) < 0."""
        ts = np.cumsum(np.full(4, 0.5))  # Δt=0.5 each
        res = np.zeros(4)
        out = encode(res, ts, dt_nominal_s=1.0)
        # Skip first token (log_dt=0 by convention); following entries negative.
        assert all(out.values[1:, 1] < 0.0)

    def test_positive_log_dt_when_slow_but_not_gap(self):
        """Δt = 2 × nominal < GAP_THRESHOLD → positive log_dt."""
        ts = np.cumsum(np.full(4, 2.0))
        res = np.zeros(4)
        out = encode(res, ts, dt_nominal_s=1.0)
        assert all(out.values[1:, 1] > 0.0)
        # No gap tokens inserted.
        assert not out.gap_mask.any()


class TestGapInsertion:

    def test_single_gap_inserts_one_gap_token(self):
        """3 samples with a huge gap between index 1 and 2 → 4 output tokens."""
        ts = np.array([0.0, 1.0, 100.0])  # gap of 99 s at nominal 1 s
        res = np.array([0.1, 0.2, 0.3])
        out = encode(res, ts, dt_nominal_s=1.0)
        assert len(out.gap_mask) == 4
        assert out.gap_mask.tolist() == [False, False, True, False]

    def test_gap_token_values_and_log_dt(self):
        ts = np.array([0.0, 1.0, 100.0])
        res = np.array([0.0, 0.0, 0.0])
        out = encode(res, ts, dt_nominal_s=1.0)
        gap_idx = int(np.where(out.gap_mask)[0][0])
        assert out.values[gap_idx, 0] == GAP_TOKEN_VALUE
        assert out.values[gap_idx, 1] == GAP_LOG_DT

    def test_gap_token_timestamp_is_midpoint(self):
        # First two samples are nominal (Δt=1); the 100.0 creates one gap.
        ts = np.array([0.0, 1.0, 100.0])
        res = np.zeros(3)
        out = encode(res, ts, dt_nominal_s=1.0)
        gap_idx = int(np.where(out.gap_mask)[0][0])
        # Midpoint of [1, 100] = 50.5
        assert abs(out.timestamps[gap_idx] - 50.5) < 1e-9

    def test_disable_gap_tokens(self):
        ts = np.array([0.0, 1.0, 100.0])
        res = np.array([0.0, 0.0, 0.0])
        out = encode(res, ts, dt_nominal_s=1.0, insert_gap_tokens=False)
        # No gap token inserted — length equals input length.
        assert len(out.gap_mask) == 3
        assert not out.gap_mask.any()
        # log_dt for the large interval is just log(99/1).
        assert out.values[2, 1] > GAP_THRESHOLD

    def test_multiple_gaps(self):
        ts = np.array([0.0, 1.0, 100.0, 101.0, 200.0])
        res = np.zeros(5)
        out = encode(res, ts, dt_nominal_s=1.0)
        # 5 input samples + 2 gap tokens (between indices 1-2 and 3-4) = 7 tokens
        assert len(out.gap_mask) == 7
        assert out.gap_mask.sum() == 2


class TestClipping:

    def test_small_dt_clipped_to_min_frac(self):
        """Δt of 0.0 between samples → clipped to MIN_DT_FRAC × dt_nominal_s."""
        ts = np.array([0.0, 0.0, 1.0])
        res = np.zeros(3)
        out = encode(res, ts, dt_nominal_s=1.0)
        # log_dt for index 1 should be log(MIN_DT_FRAC).
        assert abs(out.values[1, 1] - np.log(MIN_DT_FRAC)) < 1e-9


class TestMasksAndCounts:

    def test_reconstruction_loss_mask_is_inverse(self):
        ts = np.array([0.0, 1.0, 100.0])
        res = np.zeros(3)
        out = encode(res, ts, dt_nominal_s=1.0)
        mask = reconstruction_loss_mask(out)
        assert mask.tolist() == [1.0, 1.0, 0.0, 1.0]

    def test_effective_sample_count_excludes_gap_tokens(self):
        ts = np.array([0.0, 1.0, 100.0, 101.0])
        res = np.zeros(4)
        out = encode(res, ts, dt_nominal_s=1.0)
        assert effective_sample_count(out) == 4

    def test_output_shape_is_T_by_2(self):
        ts = np.arange(10.0)
        res = np.random.randn(10)
        out = encode(res, ts, dt_nominal_s=1.0)
        assert out.values.shape[1] == 2


class TestCadenceDetection:

    def test_returns_zero_when_too_few_samples(self):
        assert detect_nominal_cadence_s(np.arange(3.0)) == 0.0

    def test_returns_median_interval(self):
        ts = np.arange(20.0) * 0.1  # Δt = 0.1 s
        assert abs(detect_nominal_cadence_s(ts) - 0.1) < 1e-9

    def test_robust_to_single_large_gap(self):
        """19 samples at Δt=1 + 1 large gap → median still 1.0."""
        ts = np.concatenate([np.arange(20.0), np.array([5000.0])])
        assert abs(detect_nominal_cadence_s(ts) - 1.0) < 1e-9


class TestSpacecraftScenario:

    def test_leo_aos_gap_scenario(self):
        """1 Hz residuals with an 80-min LOS gap: encoder inserts exactly
        one gap token, and total output length = inputs + 1.
        """
        before = np.arange(100.0)                   # 100 s of data before LOS
        after  = before[-1] + 80 * 60 + np.arange(100.0, dtype=float)   # 80-min gap
        ts     = np.concatenate([before, after])
        res    = np.random.randn(len(ts))
        out    = encode(res, ts, dt_nominal_s=1.0)
        assert out.gap_mask.sum() == 1
        assert len(out.gap_mask) == len(ts) + 1
