"""V3-M3: Warm-standby sensor switchover detection.

Spacecraft with redundant sensors (primary/backup gyro, redundant thermistors)
switch to the backup unit when the primary degrades.  The switchover creates an
instantaneous step change indistinguishable from a level-shift anomaly.  CUSUM
and EWMA fire immediately on switchover — generating false alerts at exactly
the moment the ground team is already managing a failure.

This module detects switchover events from two complementary signals:

  1. **Metadata path** — explicit ``sensor_unit_id`` change in the telemetry
     packet.  Authoritative when ground stations forward unit IDs.
  2. **Statistical path** (sensor-fusion audit S-11) — fast fallback for
     pipelines whose ground feeds do NOT carry ``sensor_unit_id``.  A
     sample-vs-running-mean step exceeding ``stat_step_sigma_threshold``
     standard deviations and aligned with a running-variance change of at
     least ``stat_var_ratio_threshold`` is treated as a probable
     switchover.  This catches CSV / SatNOGS / Influx ingest paths where
     unit IDs were never plumbed through.

Reference: NASA-HDBK-1002 §3.4.1: sensor anomaly response — unit isolation
           and switchover detection.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import structlog

logger = structlog.get_logger()


# Statistical detector window (S-11). 30 samples ≈ a 30-second window at
# 1 Hz, long enough for a stable running mean/std but short enough that
# the running statistics adapt to a real switchover within seconds.
DEFAULT_STAT_WINDOW = 30           # samples — empirically tuned to 30 s @ 1 Hz

# 5σ step threshold — set above CUSUM's typical 4σ alarm so genuine
# anomalies are NOT classified as switchovers.  NASA-HDBK-1002 §3.4.1
# specifies "sustained, step-shaped" as the switchover signature.
DEFAULT_STEP_SIGMA_THRESHOLD = 5.0  # σ — NASA-HDBK-1002 §3.4.1

# Step in mean must coincide with a noticeable variance change too —
# otherwise a sustained drift would be mis-classified as switchover.
DEFAULT_VAR_RATIO_THRESHOLD = 2.0   # post/pre running-σ² — heuristic


@dataclass
class _ChannelStats:
    """Running first/second moments for the statistical fallback."""
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=DEFAULT_STAT_WINDOW))

    def mean(self) -> float:
        if not self.samples:
            return 0.0
        return sum(self.samples) / len(self.samples)

    def std(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        mean_v = self.mean()
        var = sum((sample - mean_v) ** 2 for sample in self.samples) / (len(self.samples) - 1)
        return var ** 0.5


class SensorSwitchoverDetector:
    """Detects sensor unit switchovers and generates suppression events.

    Tracks the latest sensor_unit_id per (satellite_id, parameter).
    When a unit change is detected, returns a suppression request
    (channel key, suppress_for_n_samples).
    """

    def __init__(
        self,
        suppress_samples: int = 10,
        stat_window: int = DEFAULT_STAT_WINDOW,
        stat_step_sigma_threshold: float = DEFAULT_STEP_SIGMA_THRESHOLD,
        stat_var_ratio_threshold: float = DEFAULT_VAR_RATIO_THRESHOLD,
    ) -> None:
        self._suppress_samples = suppress_samples
        self._stat_window = stat_window
        self._stat_step_sigma_threshold = stat_step_sigma_threshold
        self._stat_var_ratio_threshold = stat_var_ratio_threshold
        # (satellite_id, parameter) → last sensor_unit_id
        self._unit_ids: dict[tuple[str, str], str] = {}
        # (satellite_id, parameter) → remaining suppression count
        self._suppression_remaining: dict[tuple[str, str], int] = {}
        # (satellite_id, parameter) → running stats for S-11 fallback
        self._stats: dict[tuple[str, str], _ChannelStats] = {}

    def update(
        self,
        satellite_id: str,
        parameter: str,
        sensor_unit_id: str | None = None,
        value: float | None = None,
    ) -> dict | None:
        """Process a telemetry point.

        Returns a dict with suppression info on switchover detection,
        else ``None``.  Either ``sensor_unit_id`` (metadata path) or
        ``value`` (statistical fallback, S-11) MUST be supplied for the
        detector to do useful work.
        """
        key = (satellite_id, parameter)

        # Metadata path — same behaviour as before.
        if sensor_unit_id is not None:
            prev = self._unit_ids.get(key)
            self._unit_ids[key] = sensor_unit_id
            if prev is not None and prev != sensor_unit_id:
                self._suppression_remaining[key] = self._suppress_samples
                logger.info(
                    "sensor_switchover_detected",
                    satellite=satellite_id,
                    parameter=parameter,
                    old_unit=prev,
                    new_unit=sensor_unit_id,
                    suppress_samples=self._suppress_samples,
                    detector="metadata",
                )
                return {
                    "event": "switchover",
                    "old_unit": prev,
                    "new_unit": sensor_unit_id,
                    "suppress_samples": self._suppress_samples,
                    "detector": "metadata",
                }

        # Statistical fallback — only fires when value is supplied.
        if value is not None:
            return self._statistical_check(satellite_id, parameter, float(value))

        return None

    def _statistical_check(
        self,
        satellite_id: str,
        parameter: str,
        value: float,
    ) -> dict | None:
        """Step-change detector for pipelines without sensor_unit_id (S-11)."""
        key = (satellite_id, parameter)
        stats = self._stats.get(key)
        if stats is None:
            stats = _ChannelStats(
                samples=deque(maxlen=self._stat_window),
            )
            self._stats[key] = stats

        # Need a stable baseline before evaluating a step.
        if len(stats.samples) < self._stat_window:
            stats.samples.append(value)
            return None

        # Snapshot pre-update stats; then reseed with the new sample.
        pre_mean = stats.mean()
        pre_std = stats.std()
        # Skip when pre-window is essentially constant — divisor would
        # be near-zero and any new sample would look like a step.
        if pre_std < 1e-12:
            stats.samples.append(value)
            return None

        step_sigma = abs(value - pre_mean) / pre_std

        # Build a one-sample-shifted window to estimate post-step variance.
        post_samples = list(stats.samples)[1:] + [value]
        post_mean = sum(post_samples) / len(post_samples)
        post_var = (
            sum((sample - post_mean) ** 2 for sample in post_samples)
            / (len(post_samples) - 1)
        )
        var_ratio = post_var / max(pre_std ** 2, 1e-12)

        stats.samples.append(value)

        if (step_sigma >= self._stat_step_sigma_threshold
                and var_ratio >= self._stat_var_ratio_threshold):
            self._suppression_remaining[key] = self._suppress_samples
            logger.info(
                "sensor_switchover_detected",
                satellite=satellite_id,
                parameter=parameter,
                step_sigma=round(step_sigma, 2),
                var_ratio=round(var_ratio, 2),
                suppress_samples=self._suppress_samples,
                detector="statistical",
            )
            return {
                "event": "switchover",
                "step_sigma": step_sigma,
                "var_ratio": var_ratio,
                "suppress_samples": self._suppress_samples,
                "detector": "statistical",
            }
        return None

    def is_suppressed(self, satellite_id: str, parameter: str) -> bool:
        """Check if a channel is in post-switchover suppression window."""
        key = (satellite_id, parameter)
        remaining = self._suppression_remaining.get(key, 0)
        if remaining > 0:
            self._suppression_remaining[key] = remaining - 1
            return True
        return False

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id:
            keys = [k for k in self._unit_ids if k[0] == satellite_id]
            for k in keys:
                self._unit_ids.pop(k, None)
                self._suppression_remaining.pop(k, None)
                self._stats.pop(k, None)
            stat_keys = [k for k in self._stats if k[0] == satellite_id]
            for k in stat_keys:
                self._stats.pop(k, None)
        else:
            self._unit_ids.clear()
            self._suppression_remaining.clear()
            self._stats.clear()
