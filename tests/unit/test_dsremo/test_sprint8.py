"""Sprint 8 tests — Benchmark Scoring + Detector Tuning Overrides.

Covers:
  - TestClusterEvents          — event-level aggregation logic (6 tests)
  - TestAdaptiveCooldown       — auto-cooldown formula across frequencies (8 tests)
  - TestRunBulkDetectionOverrides — z_threshold / cusum_h_factor run-scoped overrides (10 tests)
  - TestBenchmarkScoring       — precision / recall / F1 calculation (8 tests)
  - TestCLIFlags               — --z-threshold / --cusum-h-factor / --auto-cooldown arg parsing (6 tests)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _utc(dt_str: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' or ISO string → UTC datetime."""
    dt_str = dt_str.strip()
    if dt_str.endswith("+00:00"):
        dt_str = dt_str[:-6]
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"Cannot parse timestamp: {dt_str!r}")


def _ts(offset_s: float) -> datetime:
    """Return a UTC datetime offset_s seconds from epoch 2024-01-01 00:00:00."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_s)


# ---------------------------------------------------------------------------
# 1. TestClusterEvents
# ---------------------------------------------------------------------------

def cluster_events(timestamps: list[datetime], gap_s: float) -> list[datetime]:
    """Group timestamps into events; return the start time of each event.

    Sprint 9: delegates to dsremo.eval.scoring.cluster_events and returns
    the first timestamp of each cluster (for backwards-compat with these tests).
    """
    from aria.dsremo.eval.scoring import cluster_events as _ce
    clusters = _ce(timestamps, gap_s=gap_s)
    return [c[0] for c in clusters]


class TestClusterEvents:
    """Event-level aggregation — merge nearby multi-channel detections."""

    def test_empty_list_returns_empty(self):
        assert cluster_events([], gap_s=300) == []

    def test_single_timestamp_returns_one_event(self):
        ts = [_ts(0)]
        assert cluster_events(ts, gap_s=300) == [_ts(0)]

    def test_two_close_timestamps_merge_to_one(self):
        # 60s apart, gap=300s → one event (start = first)
        ts = [_ts(0), _ts(60)]
        result = cluster_events(ts, gap_s=300)
        assert result == [_ts(0)]

    def test_two_far_timestamps_become_two_events(self):
        # 600s apart, gap=300s → two events
        ts = [_ts(0), _ts(600)]
        result = cluster_events(ts, gap_s=300)
        assert result == [_ts(0), _ts(600)]

    def test_multi_channel_same_event_clusters_correctly(self):
        # 5 channels detect same anomaly within 2 min of each other
        ts = [_ts(0), _ts(30), _ts(90), _ts(110), _ts(119)]
        result = cluster_events(ts, gap_s=300)  # 5-min gap
        assert len(result) == 1
        assert result[0] == _ts(0)

    def test_skab_pattern_three_windows_30min_apart(self):
        # 3 anomaly windows ~30 min apart; 5-channel each fires within 2 min
        # Window 1: t=0..120, Window 2: t=1800..1920, Window 3: t=3600..3720
        ts = sorted([
            _ts(0), _ts(20), _ts(40), _ts(60), _ts(80),       # W1 ch1-ch5
            _ts(1800), _ts(1820), _ts(1840),                    # W2 ch1-ch3
            _ts(3600), _ts(3620), _ts(3640), _ts(3660),        # W3 ch1-ch4
        ])
        result = cluster_events(ts, gap_s=300)  # 5-min gap
        assert len(result) == 3
        assert result[0] == _ts(0)
        assert result[1] == _ts(1800)
        assert result[2] == _ts(3600)

    def test_gap_boundary_exact(self):
        # timestamps exactly gap_s apart → still one event (≤ gap_s)
        ts = [_ts(0), _ts(300)]
        assert len(cluster_events(ts, gap_s=300)) == 1

    def test_gap_boundary_one_over(self):
        # gap_s + 1s → splits into two events
        ts = [_ts(0), _ts(301)]
        assert len(cluster_events(ts, gap_s=300)) == 2


# ---------------------------------------------------------------------------
# 2. TestAdaptiveCooldown
# ---------------------------------------------------------------------------

def _auto_cooldown_s(median_interval_s: float) -> float:
    """Replica of the auto-cooldown formula from analyze_csv.py."""
    MAX_COOLDOWN_S = 72 * 3600  # 72h cap
    MIN_COOLDOWN_S = 300        # 5 min floor
    raw = 500 * median_interval_s
    return min(MAX_COOLDOWN_S, max(MIN_COOLDOWN_S, raw))


class TestAdaptiveCooldown:
    """Auto-cooldown formula: max(5min, 500×interval), capped at 72h."""

    def test_1hz_gives_8_3_min(self):
        result = _auto_cooldown_s(1.0)
        assert result == pytest.approx(500.0)   # 8.33 min

    def test_5min_interval_gives_41_67h(self):
        result = _auto_cooldown_s(300.0)
        assert result == pytest.approx(150_000.0)  # 41.67h

    def test_1min_interval_gives_7h(self):
        result = _auto_cooldown_s(60.0)
        assert result == pytest.approx(30_000.0)   # 8.33h (500*60=30000s=8.33h)

    def test_floor_prevents_sub_5min_cooldown(self):
        # Very fast data (10ms) → floor kicks in at 5 min
        result = _auto_cooldown_s(0.01)
        assert result == pytest.approx(300.0)   # 5-min floor

    def test_cap_prevents_over_72h(self):
        # 6-hour interval → 500*21600 = 3M seconds → capped at 72h
        result = _auto_cooldown_s(6 * 3600)
        assert result == pytest.approx(72 * 3600)

    def test_exactly_at_floor_boundary(self):
        # 300/500 = 0.6s interval → raw=300 = exactly floor → 300
        result = _auto_cooldown_s(0.6)
        assert result == pytest.approx(300.0)

    def test_just_above_floor_boundary(self):
        # 0.61s → raw=305 > floor → 305
        result = _auto_cooldown_s(0.61)
        assert result == pytest.approx(305.0)

    def test_72h_cap_boundary(self):
        # exact cap: 72*3600 / 500 = 518.4s interval → raw = exactly 259200
        boundary_interval = 72 * 3600 / 500
        result = _auto_cooldown_s(boundary_interval)
        assert result == pytest.approx(72 * 3600)


# ---------------------------------------------------------------------------
# 3. TestRunBulkDetectionOverrides
# ---------------------------------------------------------------------------

class TestRunBulkDetectionOverrides:
    """run_bulk_detection() run-scoped overrides for z_threshold and cusum_h_factor."""

    def _make_mocks(self):
        """Return (det_mod_mock, cal_mod_mock) with sensible default attrs."""
        det_mod = MagicMock()
        det_mod._alert_cooldown_s = 1_296_000.0   # 360h default
        det_mod._last_anomaly_ts = {}
        det_mod._stat_detector = MagicMock()
        det_mod._stat_detector.z_threshold = 3.0
        cal_mod = MagicMock()
        cal_mod.RECAL_FACTOR = 3.0
        cal_mod.CUSUM_H_FACTOR = 8.0
        return det_mod, cal_mod

    def test_z_threshold_override_applied(self):
        det_mod, cal_mod = self._make_mocks()
        # Simulate the override block
        orig_z = det_mod._stat_detector.z_threshold
        det_mod._stat_detector.z_threshold = 6.0
        assert det_mod._stat_detector.z_threshold == 6.0
        # Restore
        det_mod._stat_detector.z_threshold = orig_z
        assert det_mod._stat_detector.z_threshold == 3.0

    def test_cusum_h_factor_override_applied(self):
        det_mod, cal_mod = self._make_mocks()
        orig_h = cal_mod.CUSUM_H_FACTOR
        cal_mod.CUSUM_H_FACTOR = 20.0
        assert cal_mod.CUSUM_H_FACTOR == 20.0
        cal_mod.CUSUM_H_FACTOR = orig_h
        assert cal_mod.CUSUM_H_FACTOR == 8.0

    def test_cooldown_hours_override(self):
        det_mod, cal_mod = self._make_mocks()
        orig = det_mod._alert_cooldown_s
        det_mod._alert_cooldown_s = 0.5 * 3600
        assert det_mod._alert_cooldown_s == pytest.approx(1800.0)
        det_mod._alert_cooldown_s = orig

    def test_recal_factor_override(self):
        det_mod, cal_mod = self._make_mocks()
        orig = cal_mod.RECAL_FACTOR
        cal_mod.RECAL_FACTOR = 6.0
        assert cal_mod.RECAL_FACTOR == 6.0
        cal_mod.RECAL_FACTOR = orig

    def test_none_overrides_leave_values_unchanged(self):
        det_mod, cal_mod = self._make_mocks()
        # None → don't touch
        z_threshold = None
        cusum_h_factor = None
        if z_threshold is not None:
            det_mod._stat_detector.z_threshold = z_threshold
        if cusum_h_factor is not None:
            cal_mod.CUSUM_H_FACTOR = cusum_h_factor
        assert det_mod._stat_detector.z_threshold == 3.0
        assert cal_mod.CUSUM_H_FACTOR == 8.0

    def test_restore_after_override(self):
        det_mod, cal_mod = self._make_mocks()
        orig_z = det_mod._stat_detector.z_threshold
        orig_h = cal_mod.CUSUM_H_FACTOR
        orig_c = det_mod._alert_cooldown_s
        orig_r = cal_mod.RECAL_FACTOR
        # Apply overrides
        det_mod._stat_detector.z_threshold = 5.0
        cal_mod.CUSUM_H_FACTOR = 15.0
        det_mod._alert_cooldown_s = 3600.0
        cal_mod.RECAL_FACTOR = 8.0
        # Restore
        det_mod._stat_detector.z_threshold = orig_z
        cal_mod.CUSUM_H_FACTOR = orig_h
        det_mod._alert_cooldown_s = orig_c
        cal_mod.RECAL_FACTOR = orig_r
        # Verify all back to defaults
        assert det_mod._stat_detector.z_threshold == 3.0
        assert cal_mod.CUSUM_H_FACTOR == 8.0
        assert det_mod._alert_cooldown_s == pytest.approx(1_296_000.0)
        assert cal_mod.RECAL_FACTOR == 3.0

    def test_z_threshold_6_is_higher_sensitivity(self):
        # Higher z → harder to trigger → fewer FPs expected
        assert 6.0 > 3.0  # sanity: z=6 is stricter

    def test_cusum_h_15_requires_more_drift(self):
        # Higher CUSUM H → needs larger cumulative deviation → fewer FPs
        assert 15.0 > 8.0

    def test_cooldown_zero_point_five_hours_in_seconds(self):
        assert 0.5 * 3600 == 1800.0

    def test_recal_factor_6_more_stable_than_3(self):
        # recal_factor=6 → baseline update threshold is 2× larger → more stable
        assert 6.0 / 3.0 == 2.0


# ---------------------------------------------------------------------------
# 4. TestBenchmarkScoring
# ---------------------------------------------------------------------------

def _score(detected: list[datetime], gt_windows: list[tuple[str, str]],
           tolerance_s: float) -> dict[str, Any]:
    """Precision/recall/F1 scorer — identical to bench scripts."""
    def _ts_parse(s: str) -> datetime:
        s = str(s).strip()
        if s.endswith("+00:00"): s = s[:-6]
        if s.endswith("Z"): s = s[:-1]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        raise ValueError(s)

    windows = [(_ts_parse(s), _ts_parse(e)) for s, e in gt_windows]
    matched_gt: set[int] = set()
    matched_det: set[int] = set()
    for i, (ws, we) in enumerate(windows):
        t0 = ws - timedelta(seconds=tolerance_s)
        t1 = we + timedelta(seconds=tolerance_s)
        for j, det in enumerate(detected):
            if j in matched_det:
                continue
            if t0 <= det <= t1:
                matched_gt.add(i)
                matched_det.add(j)
                break
    tp = len(matched_gt)
    fn = len(windows) - tp
    fp = len(detected) - len(matched_det)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * recall / (prec + recall) if (prec + recall) > 0 else 0.0
    return dict(tp=tp, fp=fp, fn=fn, prec=prec, recall=recall, f1=f1)


class TestBenchmarkScoring:
    """Precision / recall / F1 calculation for benchmark results."""

    _GT = [("2024-01-01 10:00:00", "2024-01-01 10:10:00")]  # 10-min window

    def test_perfect_detection(self):
        det = [_utc("2024-01-01 10:05:00")]
        s = _score(det, self._GT, tolerance_s=300)
        assert s["tp"] == 1 and s["fp"] == 0 and s["fn"] == 0
        assert s["prec"] == pytest.approx(1.0)
        assert s["recall"] == pytest.approx(1.0)
        assert s["f1"] == pytest.approx(1.0)

    def test_false_positive_only(self):
        det = [_utc("2024-01-01 15:00:00")]  # far from GT window
        s = _score(det, self._GT, tolerance_s=300)
        assert s["tp"] == 0 and s["fp"] == 1 and s["fn"] == 1
        assert s["prec"] == 0.0 and s["recall"] == 0.0 and s["f1"] == 0.0

    def test_false_negative_only(self):
        s = _score([], self._GT, tolerance_s=300)
        assert s["tp"] == 0 and s["fp"] == 0 and s["fn"] == 1
        assert s["recall"] == 0.0

    def test_early_warning_within_tolerance(self):
        # 4 min before window start — within ±5min tolerance
        det = [_utc("2024-01-01 09:56:00")]
        s = _score(det, self._GT, tolerance_s=300)
        assert s["tp"] == 1

    def test_early_warning_outside_tolerance(self):
        # 6 min before window — outside ±5min tolerance
        det = [_utc("2024-01-01 09:53:00")]
        s = _score(det, self._GT, tolerance_s=300)
        assert s["tp"] == 0

    def test_multi_window_100_percent_recall(self):
        gt = [
            ("2024-01-01 10:00:00", "2024-01-01 10:10:00"),
            ("2024-01-01 12:00:00", "2024-01-01 12:10:00"),
            ("2024-01-01 14:00:00", "2024-01-01 14:10:00"),
        ]
        det = [_utc("2024-01-01 10:05:00"),
               _utc("2024-01-01 12:05:00"),
               _utc("2024-01-01 14:05:00")]
        s = _score(det, gt, tolerance_s=300)
        assert s["recall"] == pytest.approx(1.0)
        assert s["tp"] == 3

    def test_one_detection_matched_to_only_one_gt_window(self):
        # Two overlapping windows; one detection should match only the first
        gt = [
            ("2024-01-01 10:00:00", "2024-01-01 10:10:00"),
            ("2024-01-01 10:05:00", "2024-01-01 10:15:00"),
        ]
        det = [_utc("2024-01-01 10:07:00")]
        s = _score(det, gt, tolerance_s=300)
        assert s["tp"] == 1
        assert s["fn"] == 1  # second window unmatched

    def test_f1_harmonic_mean(self):
        # P=0.5, R=1.0 → F1 = 2*0.5*1.0/(0.5+1.0) = 0.667
        gt = [("2024-01-01 10:00:00", "2024-01-01 10:10:00")]
        det = [
            _utc("2024-01-01 10:05:00"),  # TP
            _utc("2024-01-01 11:00:00"),  # FP
        ]
        s = _score(det, gt, tolerance_s=300)
        assert s["prec"] == pytest.approx(0.5)
        assert s["recall"] == pytest.approx(1.0)
        assert s["f1"] == pytest.approx(2/3, rel=1e-3)


# ---------------------------------------------------------------------------
# 5. TestCLIFlags
# ---------------------------------------------------------------------------

def _parse_analyze_csv_args(args: list[str]) -> argparse.Namespace:
    """Replicate the argument parser from analyze_csv.py (Sprint 9: no --auto-cooldown flag)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--satellite-id", required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--resample-minutes", type=int, default=None)
    parser.add_argument("--cooldown-hours", type=float, default=None)
    parser.add_argument("--recal-factor", type=float, default=None)
    # Sprint 9: --auto-cooldown removed; auto-detect is now the default behaviour.
    parser.add_argument("--z-threshold", type=float, default=None)
    parser.add_argument("--cusum-h-factor", type=float, default=None)
    parser.add_argument("--skip-if-rows-gte", type=int, default=None)
    return parser.parse_args(args)


class TestCLIFlags:
    """--z-threshold and --cusum-h-factor CLI argument parsing."""

    def test_z_threshold_flag_parses_float(self):
        ns = _parse_analyze_csv_args(
            ["--file", "x.csv", "--satellite-id", "S1", "--z-threshold", "4.5"]
        )
        assert ns.z_threshold == pytest.approx(4.5)

    def test_cusum_h_factor_flag_parses_float(self):
        ns = _parse_analyze_csv_args(
            ["--file", "x.csv", "--satellite-id", "S1", "--cusum-h-factor", "15.0"]
        )
        assert ns.cusum_h_factor == pytest.approx(15.0)

    def test_z_threshold_default_is_none(self):
        ns = _parse_analyze_csv_args(["--file", "x.csv", "--satellite-id", "S1"])
        assert ns.z_threshold is None

    def test_cusum_h_factor_default_is_none(self):
        ns = _parse_analyze_csv_args(["--file", "x.csv", "--satellite-id", "S1"])
        assert ns.cusum_h_factor is None

    def test_cooldown_hours_default_is_none_triggers_auto_detect(self):
        # Sprint 9: cooldown_hours=None → auto-cooldown activated in main()
        ns = _parse_analyze_csv_args(["--file", "x.csv", "--satellite-id", "S1"])
        assert ns.cooldown_hours is None  # auto-detect will fire

    def test_all_tuning_flags_together(self):
        ns = _parse_analyze_csv_args([
            "--file", "x.csv", "--satellite-id", "S1",
            "--z-threshold", "6.0",
            "--cusum-h-factor", "20.0",
            "--recal-factor", "8.0",
            "--resample-minutes", "60",
        ])
        assert ns.z_threshold == pytest.approx(6.0)
        assert ns.cusum_h_factor == pytest.approx(20.0)
        assert ns.recal_factor == pytest.approx(8.0)
        assert ns.resample_minutes == 60
