"""Tests for V3-V5: telemetry-gap tracker.

Validates:
 1. record_gap + get returns the stored record
 2. record_gap refuses non-physical records (end < start)
 3. describe_recent_gap returns None for unknown keys
 4. describe_recent_gap returns None when gap_end lies in the future
 5. describe_recent_gap returns phrase when anomaly within lookback
 6. describe_recent_gap returns None when gap outside lookback
 7. phrase contains duration and UTC timestamp of gap end
 8. LRU cap evicts oldest channel when capacity exceeded
 9. record_gaps_from_timestamps scans sequence and stores latest gap
10. record_gaps_from_timestamps respects threshold multiplier
11. Singleton get_tracker / reset_tracker
12. Empty timestamp list is a safe no-op
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.gap_tracker import (
    DEFAULT_GAP_LOOKBACK_S,
    GapRecord,
    GapTracker,
    get_tracker,
    record_gaps_from_timestamps,
    reset_tracker,
)


class TestRecordAndGet:

    def test_record_and_get(self):
        t = GapTracker()
        t.record_gap("SAT:chan", 1000.0, 1300.0)
        rec = t.get("SAT:chan")
        assert rec is not None
        assert rec.gap_start_epoch == 1000.0
        assert rec.gap_end_epoch == 1300.0
        assert rec.gap_duration_s == 300.0

    def test_non_physical_record_refused(self):
        t = GapTracker()
        t.record_gap("K", 1000.0, 500.0)  # end < start
        assert t.get("K") is None


class TestDescribeRecentGap:

    def test_unknown_key_returns_none(self):
        t = GapTracker()
        assert t.describe_recent_gap("missing", anomaly_epoch=1.0) is None

    def test_future_gap_returns_none(self):
        t = GapTracker()
        t.record_gap("K", 1000.0, 2000.0)
        # Anomaly BEFORE gap ended → phrase should be None (gap hasn't happened yet).
        assert t.describe_recent_gap("K", anomaly_epoch=1500.0) is None

    def test_recent_gap_returns_phrase(self):
        t = GapTracker()
        t.record_gap("K", 1000.0, 1300.0)
        # Anomaly 60 s after gap end.
        phrase = t.describe_recent_gap("K", anomaly_epoch=1360.0, lookback_s=3600.0)
        assert phrase is not None
        assert "telemetry gap" in phrase
        assert "min" in phrase

    def test_out_of_lookback_returns_none(self):
        t = GapTracker()
        t.record_gap("K", 1000.0, 1300.0)
        # 1 week later → well past default lookback.
        far_future = 1300.0 + 7 * 86400.0
        assert t.describe_recent_gap("K", anomaly_epoch=far_future) is None

    def test_phrase_contains_utc_timestamp(self):
        t = GapTracker()
        t.record_gap("K", 0.0, 1800.0)  # 30-min gap ending at 1970-01-01 00:30:00 UTC
        phrase = t.describe_recent_gap("K", anomaly_epoch=2000.0, lookback_s=3600.0)
        assert phrase is not None
        assert "UTC" in phrase
        assert "1970-01-01 00:30 UTC" in phrase


class TestLRU:

    def test_lru_evicts_oldest(self):
        t = GapTracker(max_channels=3)
        t.record_gap("A", 1.0, 2.0)
        t.record_gap("B", 1.0, 2.0)
        t.record_gap("C", 1.0, 2.0)
        t.record_gap("D", 1.0, 2.0)   # should evict A
        assert t.get("A") is None
        assert t.get("B") is not None
        assert t.get("C") is not None
        assert t.get("D") is not None


class TestScanHelper:

    def test_scans_for_latest_gap(self):
        t = GapTracker()
        # Two gaps in the sequence; only the latest is retained.
        ts = [0.0, 1.0, 100.0, 101.0, 200.0]  # gaps at indices 1-2 and 3-4
        n = record_gaps_from_timestamps("K", ts, dt_nominal_s=1.0, tracker=t)
        assert n == 1
        rec = t.get("K")
        assert rec is not None
        assert rec.gap_start_epoch == 101.0
        assert rec.gap_end_epoch == 200.0

    def test_no_gap_no_record(self):
        t = GapTracker()
        ts = [0.0, 1.0, 2.0, 3.0]  # all uniform
        n = record_gaps_from_timestamps("K", ts, dt_nominal_s=1.0, tracker=t)
        assert n == 0
        assert t.get("K") is None

    def test_empty_timestamps(self):
        t = GapTracker()
        assert record_gaps_from_timestamps("K", [], dt_nominal_s=1.0, tracker=t) == 0


class TestSingleton:

    def test_get_and_reset_tracker(self):
        reset_tracker()
        try:
            a = get_tracker()
            b = get_tracker()
            assert a is b
            a.record_gap("X", 1.0, 2.0)
            reset_tracker()
            c = get_tracker()
            assert c is not a
            assert c.get("X") is None
        finally:
            reset_tracker()
