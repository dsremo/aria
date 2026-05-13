"""V3-V5: Telemetry-gap tracker — annotates anomalies that follow a gap.

Problem (from V3 audit V-5)
---------------------------
When telemetry has an AOS/LOS gap (~80 min for LEO) and a naive imputation
path fills it with interpolated values, the detectors see a smooth "no
anomaly" zone inside the gap window.  An anomaly that actually began during
the gap and persisted into post-gap data has its onset attributed to
*after* the gap rather than during it.  For operator context, it matters
whether an alarm is (a) a clean fault onset observable in recent telemetry
or (b) post-gap evidence that something changed while we were offline.

Solution
--------
V3-V1 (mTAN) already prevents the detector itself from being fooled by
interpolated regions: gap tokens are masked from reconstruction loss.
What V-5 adds is an operator-visible *explanation suffix*: when an alarm
fires within `lookback_s` seconds of a detected gap, the explanation is
enriched with "preceded by X s telemetry gap at Y UTC" so the operator
knows the onset time is uncertain.

Implementation
--------------
`GapTracker.record_gap(key, gap_start, gap_end)` stores the most recent
gap per channel.  `describe_recent_gap(key, anomaly_epoch, lookback_s)`
returns a short human-readable phrase or None.  Callers plug the phrase
into `Anomaly.explanation` or the alert payload.

No DB persistence is required — gap context is only useful for a short
window after the gap ends (hours, not days), which fits an in-memory LRU.

Reference
---------
CCSDS 135.0-B-1 (2015), §4.3: telemetry gap semantics during AOS/LOS.
Moritz & Bartz-Beielstein (2017), R Journal 9(1):207-218 §3: imputation
    effects on downstream analysis.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone


# Cap on tracked channels to bound memory (channels rarely exceed ~10_000
# per mission — 10× that still fits in a few megabytes).
_MAX_TRACKED_CHANNELS: int = 100_000   # ESTIMATE — LRU cap, single-satellite

# Default lookback when deciding whether a gap counts as "recent" for an
# anomaly's explanation.  6 hours is sufficient for most LEO missions'
# worst-case AOS/LOS cycle (~90 min × a few orbits) without being so long
# that stale gap context misleads the operator.
DEFAULT_GAP_LOOKBACK_S: float = 6.0 * 3600.0   # ESTIMATE — 6 h lookback for gap context


@dataclass(frozen=True, slots=True)
class GapRecord:
    """One telemetry gap for a channel."""

    gap_start_epoch: float   # last timestamp BEFORE the gap
    gap_end_epoch:   float   # first timestamp AFTER the gap

    @property
    def gap_duration_s(self) -> float:
        return max(0.0, self.gap_end_epoch - self.gap_start_epoch)


class GapTracker:
    """LRU-capped per-channel store of the most recent telemetry gap.

    Usage (detection path)::
        tracker.record_gap(key, gap_start_epoch, gap_end_epoch)
        phrase = tracker.describe_recent_gap(key, anomaly_epoch)
        if phrase is not None:
            anomaly.explanation += f" ({phrase})"
    """

    def __init__(self, max_channels: int = _MAX_TRACKED_CHANNELS) -> None:
        self._max = int(max_channels)
        self._last_gap: OrderedDict[str, GapRecord] = OrderedDict()

    def record_gap(self, key: str, gap_start_epoch: float, gap_end_epoch: float) -> None:
        """Record the most recent gap for a channel.  Older gaps are overwritten.

        Callers determine what qualifies as a gap — typical thresholds are
        3×Δt_nominal (matching V-1 mTAN gap-token insertion).
        """
        if gap_end_epoch < gap_start_epoch:
            # Defensive: refuse to store a non-physical record.
            return
        self._last_gap[key] = GapRecord(
            gap_start_epoch=float(gap_start_epoch),
            gap_end_epoch=float(gap_end_epoch),
        )
        # Touch-and-move for LRU semantics.
        self._last_gap.move_to_end(key)
        while len(self._last_gap) > self._max:
            self._last_gap.popitem(last=False)

    def get(self, key: str) -> GapRecord | None:
        return self._last_gap.get(key)

    def describe_recent_gap(
        self,
        key: str,
        anomaly_epoch: float | None = None,
        lookback_s: float = DEFAULT_GAP_LOOKBACK_S,
    ) -> str | None:
        """Return a short phrase describing a gap that preceded the anomaly,
        or None when no relevant gap is tracked.

        The phrase format: "preceded by N.N-min telemetry gap ending YYYY-MM-DD HH:MM UTC".
        Only gaps whose end was within `lookback_s` of the anomaly are reported.
        """
        rec = self._last_gap.get(key)
        if rec is None:
            return None
        now = anomaly_epoch if anomaly_epoch is not None else datetime.now(timezone.utc).timestamp()
        if now < rec.gap_end_epoch:
            return None
        if (now - rec.gap_end_epoch) > lookback_s:
            return None
        minutes = rec.gap_duration_s / 60.0
        end_utc = datetime.fromtimestamp(rec.gap_end_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"preceded by {minutes:.1f}-min telemetry gap ending {end_utc}"

    def clear(self) -> None:
        self._last_gap.clear()

    def __len__(self) -> int:
        return len(self._last_gap)


# ── Process-wide singleton ────────────────────────────────────────────────── #

_tracker: GapTracker | None = None


def get_tracker() -> GapTracker:
    global _tracker
    if _tracker is None:
        _tracker = GapTracker()
    return _tracker


def reset_tracker() -> None:
    global _tracker
    _tracker = None


def record_gaps_from_timestamps(
    key: str,
    timestamps: "list[float]",
    dt_nominal_s: float,
    gap_threshold_mult: float = 3.0,
    tracker: GapTracker | None = None,
) -> int:
    """Scan a timestamp sequence and record the single most-recent gap.

    Convenience wrapper for the detection loop: call this with the same
    timestamps passed to V-1's mTAN encoder and the same GAP_THRESHOLD,
    and gap context flows into alerts for free.  Returns the number of
    gaps detected in the sequence (0 or 1; only the latest is retained).
    """
    if len(timestamps) < 2 or dt_nominal_s <= 0.0:
        return 0
    mon = tracker if tracker is not None else get_tracker()
    threshold = gap_threshold_mult * dt_nominal_s
    latest_start: float | None = None
    latest_end:   float | None = None
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        if dt > threshold:
            latest_start = float(timestamps[i - 1])
            latest_end   = float(timestamps[i])
    if latest_start is not None and latest_end is not None:
        mon.record_gap(key, latest_start, latest_end)
        return 1
    return 0
