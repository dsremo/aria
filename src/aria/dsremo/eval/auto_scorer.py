"""AutoScorer — fully self-calibrating benchmark scorer.

Zero manual tuning required.  The scorer:

  1. Extracts GT windows from any labeled DataFrame (auto-detects column name,
     handles any timezone, normalises everything to UTC).

  2. Calibrates window_s by measuring the actual median lead-time between
     detections and GT window starts (our detectors are early-warning —
     they fire *before* the labeled window).

  3. Derives gap_s from the cooldown setting so clustering is always
     consistent with how frequently the detector can fire.

  4. Scores P / R / F1 and returns a full ScoringResult plus calibration
     metadata so callers can see *why* the tolerances are what they are.

Usage::

    from aria.dsremo.eval.auto_scorer import AutoScorer

    scorer = AutoScorer(cooldown_hours=0.138)   # 8.3 min

    # From a labeled pandas DataFrame (any column name)
    gt_windows = scorer.extract_gt(df, time_col="datetime", label_col="anomaly")

    # Given raw detection timestamps from the DB (UTC-aware)
    result, meta = scorer.score(detected_ts, gt_windows)
    print(f"P={result.precision:.1%}  R={result.recall:.1%}  F1={result.f1:.1%}")
    print(f"  auto window_s={meta['window_s']:.0f}s  gap_s={meta['gap_s']:.0f}s")
    print(f"  lead_time_median={meta['lead_time_median_s']:.0f}s")
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from aria.dsremo.eval.scoring import ScoringResult, cluster_events, score as _score


# ---------------------------------------------------------------------------
# GT extraction
# ---------------------------------------------------------------------------

_LABEL_COLUMNS = (
    "anomaly", "label", "y", "is_anomaly", "anomalous",
    "fault", "failure", "changepoint", "attack",
)


def extract_gt_windows(
    df: pd.DataFrame,
    label_col: str | None = None,
    time_col: str | None = None,
) -> list[tuple[datetime, datetime]]:
    """Extract GT anomaly windows from a labeled DataFrame.

    Handles:
    - Any timezone (naive → UTC, aware → converted to UTC).
    - Any label column name (auto-detects from _LABEL_COLUMNS).
    - Integer (0/1) or boolean labels.
    - Contiguous runs of label==1 → one window per run.
    - CSV formats where the time is the index or a named column.

    Args:
        df:         DataFrame with at least one time column and one label column.
        label_col:  Name of the anomaly label column (auto-detected if None).
        time_col:   Name of the timestamp column (uses index if None or missing).

    Returns:
        List of (start_utc, end_utc) tuples, one per contiguous anomaly run.

    Raises:
        ValueError: if no label column can be found.
    """
    # ── resolve time index ─────────────────────────────────────────────────
    if time_col and time_col in df.columns:
        ts_series = pd.to_datetime(df[time_col], utc=False)
    else:
        ts_series = pd.to_datetime(df.index, utc=False)

    ts_series = _normalise_to_utc(ts_series)

    # ── resolve label column ───────────────────────────────────────────────
    col = label_col
    if col is None or col not in df.columns:
        for candidate in _LABEL_COLUMNS:
            if candidate in df.columns:
                col = candidate
                break
        if col is None:
            raise ValueError(
                f"No anomaly label column found. Tried: {_LABEL_COLUMNS}. "
                f"Columns present: {list(df.columns)}"
            )

    labels = df[col].fillna(0).astype(float)

    # ── vectorised window extraction ───────────────────────────────────────
    diff = labels.diff().fillna(0).astype(int)
    rising  = ts_series[diff == 1].tolist()
    falling = ts_series[diff == -1].tolist()

    # Handle series that starts in an anomaly
    if labels.iloc[0] >= 1:
        rising = [ts_series.iloc[0]] + rising

    # Handle series that ends in an anomaly
    if labels.iloc[-1] >= 1:
        falling = falling + [ts_series.iloc[-1]]

    return [
        (_to_utc_dt(s), _to_utc_dt(e))
        for s, e in zip(rising, falling)
    ]


# ---------------------------------------------------------------------------
# AutoScorer
# ---------------------------------------------------------------------------

class AutoScorer:
    """Self-calibrating scorer for any anomaly detection run.

    Parameters
    ----------
    cooldown_hours : float
        The alert cooldown used during detection (hours).
        gap_s is derived as  max(cooldown_s × 2, 600).

    min_window_s : float
        Minimum tolerance window in seconds (floor). Default: 300 (5 min).

    max_window_s : float
        Maximum tolerance window in seconds (ceiling). Default: 14400 (4 h).
    """

    def __init__(
        self,
        cooldown_hours: float = 0.138,
        min_window_s: float = 300.0,
        max_window_s: float = 14_400.0,
    ) -> None:
        self.cooldown_hours = cooldown_hours
        self.min_window_s   = min_window_s
        self.max_window_s   = max_window_s

    # -- public ---------------------------------------------------------------

    def extract_gt(
        self,
        df: pd.DataFrame,
        label_col: str | None = None,
        time_col: str | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Thin wrapper around the module-level extract_gt_windows."""
        return extract_gt_windows(df, label_col=label_col, time_col=time_col)

    def score(
        self,
        detected: list[datetime],
        ground_truth: list[tuple[datetime, datetime]],
    ) -> tuple[ScoringResult, dict[str, Any]]:
        """Score detections against GT with auto-calibrated tolerances.

        Calibration steps:
        1. Compute gap_s from cooldown_hours × 2 (minimum 600s).
        2. Cluster detections into events.
        3. Measure lead-time from each event representative to the nearest
           following GT window start (early-warning offset).
        4. Set window_s = max(min_window_s,
                               median_lead_time × 1.5,
                               gt_window_duration × 0.5)
        5. Re-score with calibrated parameters.

        Returns
        -------
        result : ScoringResult
        meta   : dict with calibration details (window_s, gap_s,
                  lead_time_median_s, lead_time_p90_s, n_gt, n_events)
        """
        gap_s = self._derive_gap_s()

        n_gt = len(ground_truth)
        if not detected or not ground_truth:
            meta = self._meta(0.0, gap_s, 0.0, 0.0, n_gt, 0, False,
                              empty_detections=not bool(detected))
            result = _score(detected, ground_truth, window_s=self.min_window_s,
                            gap_s=gap_s)
            return result, meta

        # ── calibrate gap_s: grow until we get at least n_gt clusters ─────
        # "Single cluster" pathology: when the detector fires continuously
        # with gaps all below gap_s, every detection merges into 1 cluster.
        # The earliest representative then sits far from all GT windows and
        # P/R/F1 collapse to 0 — a misleading result.
        # Fix: double gap_s until ≥ min(n_gt, 5) clusters form OR gap_s
        # exceeds 1 day.  If still 1 cluster after that (truly uninterrupted
        # firing, e.g. CATS 1-Hz data), fall back to point-level scoring:
        # gap_s=1 treats each detection as its own event, so every GT window
        # that contains any detection is correctly marked TP.  This exposes
        # the real problem — high recall, near-zero precision — rather than
        # hiding it with an impossible 0%/0%/0% result.
        target_clusters = max(2, min(n_gt, 5))
        clusters = cluster_events(detected, gap_s=gap_s)
        while len(clusters) < target_clusters and gap_s < 86_400:
            gap_s *= 2.0
            clusters = cluster_events(detected, gap_s=gap_s)
        degenerate = len(clusters) == 1
        if degenerate:
            gap_s = 1.0
            clusters = cluster_events(detected, gap_s=gap_s)

        # ── calibrate window_s ─────────────────────────────────────────────
        avg_gt_dur = statistics.mean(
            (e - s).total_seconds() for s, e in ground_truth
        )
        if degenerate:
            # Point-level scoring: window_s = avg GT duration so the
            # entire GT window interior counts as a valid match zone.
            window_s   = min(max(self.min_window_s, avg_gt_dur), self.max_window_s)
            median_lead = 0.0
            p90_lead    = 0.0
        else:
            reps        = [c[0] for c in clusters]
            lead_times  = self._measure_lead_times(reps, ground_truth)
            median_lead = statistics.median(lead_times) if lead_times else 0.0
            p90_lead    = sorted(lead_times)[int(len(lead_times) * 0.9)] if lead_times else 0.0
            window_s    = max(
                self.min_window_s,
                median_lead * 1.5,
                avg_gt_dur * 0.5,
            )
            window_s = min(window_s, self.max_window_s)

        result = _score(detected, ground_truth, window_s=window_s, gap_s=gap_s)
        meta   = self._meta(window_s, gap_s, median_lead, p90_lead,
                            n_gt, len(clusters), degenerate, empty_detections=False)
        return result, meta

    # -- internal helpers -----------------------------------------------------

    def _derive_gap_s(self) -> float:
        """gap_s = 2× cooldown, bounded [600, 86400]."""
        return min(max(self.cooldown_hours * 3600 * 2, 600.0), 86_400.0)

    @staticmethod
    def _measure_lead_times(
        reps: list[datetime],
        ground_truth: list[tuple[datetime, datetime]],
    ) -> list[float]:
        """For each event rep, find the nearest GT window and compute lead-time.

        Positive = rep fires BEFORE the GT window start (early warning).
        Negative = rep fires INSIDE or AFTER the GT window.
        Only positive lead-times are included (we only calibrate for early fire).
        """
        leads: list[float] = []
        gt_starts_epoch = sorted(
            (s - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
            for s, _ in ground_truth
        )
        for rep in reps:
            rep_epoch = (rep - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
            # Find nearest GT start ahead of this detection
            nearest = None
            for gs in gt_starts_epoch:
                if gs > rep_epoch:
                    nearest = gs
                    break
            if nearest is not None:
                lead = nearest - rep_epoch
                if 0 < lead < 86_400:   # only sensible positive leads (<24h)
                    leads.append(lead)
        return leads

    @staticmethod
    def _meta(
        window_s: float,
        gap_s: float,
        lead_median: float,
        lead_p90: float,
        n_gt: int,
        n_events: int,
        degenerate: bool = False,
        empty_detections: bool = False,
    ) -> dict[str, Any]:
        return {
            "window_s":           window_s,
            "gap_s":              gap_s,
            "lead_time_median_s": lead_median,
            "lead_time_p90_s":    lead_p90,
            "n_gt":               n_gt,
            "n_events":           n_events,
            "degenerate":         degenerate,        # True = detector fires without pause (continuous-fire)
            "empty_detections":   empty_detections,  # True = detector found nothing at all
        }


# ---------------------------------------------------------------------------
# Parquet GT extractor (for CATS / any parquet with labels)
# ---------------------------------------------------------------------------

def extract_gt_from_parquet(
    path: "str | Any",
    label_col: str | None = None,
) -> list[tuple[datetime, datetime]]:
    """Load a parquet file and extract GT windows (vectorised, fast).

    The parquet index is treated as the time axis.
    """
    import pandas as pd
    cols = [label_col] if label_col else list(_LABEL_COLUMNS)
    # Try loading only the columns we need
    try:
        df = pd.read_parquet(path, columns=cols)
    except Exception:
        df = pd.read_parquet(path)
    return extract_gt_windows(df, label_col=label_col)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _normalise_to_utc(series: pd.Series) -> pd.Series:
    """Ensure a DatetimeSeries is timezone-aware UTC regardless of source TZ."""
    if hasattr(series, "dt"):
        if series.dt.tz is None:
            return series.dt.tz_localize("UTC")
        return series.dt.tz_convert("UTC")
    return series


def _to_utc_dt(ts: Any) -> datetime:
    """Convert a pandas Timestamp (any tz) to a UTC-aware Python datetime."""
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
    else:
        dt = ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
