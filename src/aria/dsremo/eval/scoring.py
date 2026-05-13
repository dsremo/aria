"""Benchmark scoring utilities — event-level precision/recall/F1.

Used by benchmark scripts and test suites to evaluate anomaly detection
quality against ground-truth labeled datasets (OPS-SAT, CATS, SKAB, NAB).

All functions are pure (no DB, no I/O) and stdlib-only (no new deps).

Typical usage:
    from aria.dsremo.eval.scoring import cluster_events, score, ScoringResult

    # Cluster raw detections into events (merge nearby alarms)
    events = cluster_events(detected_timestamps, gap_s=600)

    # Score against ground-truth windows
    result = score(detected_timestamps, ground_truth_windows, window_s=1800)
    print(f"P={result.precision:.1%}  R={result.recall:.1%}  F1={result.f1:.1%}")
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ScoringResult:
    """Immutable event-level scoring summary."""

    tp: int            # ground-truth windows correctly detected
    fp: int            # detected events with no matching GT window
    fn: int            # ground-truth windows that were missed

    precision: float   # tp / (tp + fp), NaN-safe (0.0 when no detections)
    recall: float      # tp / (tp + fn), NaN-safe (0.0 when no GT windows)
    f1: float          # harmonic mean of precision and recall

    event_count: int   # total ground-truth windows
    detected_count: int  # total detected events (after clustering)


def cluster_events(
    timestamps: list[datetime],
    gap_s: float = 3600.0,
) -> list[list[datetime]]:
    """Group detected timestamps into events using gap-based clustering.

    Any two consecutive detections separated by ≤ gap_s seconds belong to
    the same event. Returns a list of clusters; each cluster is a list of
    datetime objects that form one logical event.

    Algorithm: O(n) linear scan on pre-sorted timestamps. Timestamps need
    not be pre-sorted — this function sorts them internally.

    Args:
        timestamps: Raw detection timestamps (may be unsorted, may be empty).
        gap_s:      Maximum inter-detection gap within one event (seconds).
                    Default 3600 s = 1 hour (suitable for hourly satellite data).
                    Use ~600 s for 1-Hz industrial/spacecraft data.

    Returns:
        List of clusters, ordered by first timestamp in each cluster.
        Empty list if timestamps is empty.

    Examples:
        >>> from datetime import datetime, timedelta
        >>> t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        >>> ts = [t0, t0 + timedelta(minutes=5), t0 + timedelta(hours=2)]
        >>> events = cluster_events(ts, gap_s=600)
        >>> len(events)   # two events: {t0, t0+5min} and {t0+2h}
        2
    """
    if not timestamps:
        return []

    sorted_ts = sorted(timestamps)
    clusters: list[list[datetime]] = [[sorted_ts[0]]]

    for ts in sorted_ts[1:]:
        prev = clusters[-1][-1]
        gap = (ts - prev).total_seconds()
        if gap <= gap_s:
            clusters[-1].append(ts)
        else:
            clusters.append([ts])

    return clusters


def score(
    detected: list[datetime],
    ground_truth: list[tuple[datetime, datetime]],
    window_s: float = 1800.0,
    gap_s: float = 3600.0,
) -> ScoringResult:
    """Compute event-level precision/recall/F1 with ±window_s tolerance.

    Matching strategy:
    1. Cluster detected timestamps into events via cluster_events(gap_s).
    2. For each GT window [start, end], a TP is counted if at least one
       detected event representative falls within window_s seconds of either
       the window start or window end.  The representative is the *earliest*
       timestamp in the cluster (i.e. the first alarm).
    3. GT windows with no matching detected event → FN.
    4. Detected events with no matching GT window → FP.

    Complexity: O(n log m) using bisect — no nested loops.

    Args:
        detected:     Raw detection timestamps (may be unsorted, may be empty).
        ground_truth: List of (start, end) datetime pairs marking anomaly
                      windows.  May overlap.  May be empty.
        window_s:     Tolerance in seconds: a detection is considered to
                      "match" a GT window if it falls within window_s of
                      the window's start or end (or within the window itself).
                      Default 1800 s = 30 minutes.
        gap_s:        Passed to cluster_events() to merge nearby detections.

    Returns:
        ScoringResult with tp, fp, fn, precision, recall, f1, counts.
    """
    n_gt = len(ground_truth)
    if not detected:
        return ScoringResult(
            tp=0, fp=0, fn=n_gt,
            precision=0.0, recall=0.0, f1=0.0,
            event_count=n_gt, detected_count=0,
        )

    # Cluster detections → one representative per event (earliest timestamp).
    clusters = cluster_events(detected, gap_s=gap_s)
    representatives: list[float] = [_epoch(c[0]) for c in clusters]
    n_detected = len(clusters)

    if not ground_truth:
        return ScoringResult(
            tp=0, fp=n_detected, fn=0,
            precision=0.0, recall=1.0, f1=0.0,
            event_count=0, detected_count=n_detected,
        )

    # For each GT window, check if any representative falls within it (±window_s).
    gt_matched = [False] * n_gt
    event_matched = [False] * n_detected

    # Sort representatives for bisect-based lookups.
    sorted_reps = sorted(representatives)
    sorted_rep_indices = sorted(range(n_detected), key=lambda i: representatives[i])

    for gt_idx, (gt_start, gt_end) in enumerate(ground_truth):
        gs = _epoch(gt_start)
        ge = _epoch(gt_end)
        lo = gs - window_s
        hi = ge + window_s

        # Binary search: find representatives in [lo, hi]
        left  = bisect.bisect_left(sorted_reps, lo)
        right = bisect.bisect_right(sorted_reps, hi)

        if left < right:
            gt_matched[gt_idx] = True
            # Mark all matching representatives as used.
            for i in range(left, right):
                event_matched[sorted_rep_indices[i]] = True

    tp = sum(gt_matched)
    fn = n_gt - tp
    fp = n_detected - sum(event_matched)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (
        2.0 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return ScoringResult(
        tp=tp, fp=fp, fn=fn,
        precision=precision, recall=recall, f1=f1,
        event_count=n_gt, detected_count=n_detected,
    )


def _epoch(dt: datetime) -> float:
    """Convert datetime to UTC epoch seconds. Handles naive and tz-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()
