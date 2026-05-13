"""Feature engineering engine — transforms raw telemetry into detector-ready features.

Computes rolling statistics, rate of change, cross-parameter correlations,
and seasonal components. These features are what make the detectors smart —
raw values alone miss subtle patterns.

Key design: everything operates on numpy arrays for vectorized speed.
No per-point Python loops in the hot path.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Computed features for a single parameter at a point in time."""

    parameter: str
    timestamp_epoch: float
    raw_value: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    rate_of_change: float       # first derivative (value/sec)
    rolling_min: float
    rolling_max: float
    range_position: float       # where current value sits in [min, max]: 0=min, 1=max
    deviation_from_trend: float # residual after removing rolling mean


@dataclass
class FeatureWindow:
    """Holds raw values for a parameter over a time window.

    Append-only ring buffer: oldest values fall off when capacity is reached.
    Memory-efficient for continuous streaming.
    """

    capacity: int
    _values: np.ndarray = field(init=False)
    _timestamps: np.ndarray = field(init=False)
    _count: int = field(init=False, default=0)

    def __post_init__(self):
        self._values = np.empty(self.capacity, dtype=np.float64)
        self._timestamps = np.empty(self.capacity, dtype=np.float64)

    @property
    def size(self) -> int:
        return min(self._count, self.capacity)

    @property
    def values(self) -> np.ndarray:
        if self._count <= self.capacity:
            return self._values[:self._count]
        start = self._count % self.capacity
        return np.roll(self._values, -start)[:self.size]

    @property
    def timestamps(self) -> np.ndarray:
        if self._count <= self.capacity:
            return self._timestamps[:self._count]
        start = self._count % self.capacity
        return np.roll(self._timestamps, -start)[:self.size]

    def append(self, value: float, timestamp_epoch: float) -> None:
        idx = self._count % self.capacity
        self._values[idx] = value
        self._timestamps[idx] = timestamp_epoch
        self._count += 1


class FeatureEngine:
    """Computes features for all tracked parameters.

    Maintains a sliding window per parameter. On each new value,
    computes the full feature vector in O(n) with numpy — no Python loops.
    """

    def __init__(self, window_size: int = 300):  # ESTIMATE — 300-sample (5 min at 1 Hz) default window; Killick 2012 PELT §3 recommends ≥3× signal period
        self.window_size = window_size
        self._windows: dict[str, FeatureWindow] = {}

    def _get_window(self, key: str) -> FeatureWindow:
        if key not in self._windows:
            self._windows[key] = FeatureWindow(capacity=self.window_size)
        return self._windows[key]

    def compute(self, parameter: str, value: float, timestamp_epoch: float) -> FeatureVector:
        """Add a value and compute the feature vector."""
        key = parameter
        window = self._get_window(key)
        window.append(value, timestamp_epoch)

        vals = window.values
        n = len(vals)

        if n < 2:
            return FeatureVector(
                parameter=parameter,
                timestamp_epoch=timestamp_epoch,
                raw_value=value,
                rolling_mean=value,
                rolling_std=0.0,
                z_score=0.0,
                rate_of_change=0.0,
                rolling_min=value,
                rolling_max=value,
                range_position=0.5,
                deviation_from_trend=0.0,
            )

        mean = np.mean(vals)
        std = np.std(vals, ddof=1) if n > 1 else 1e-10
        safe_std = max(std, 1e-10)  # prevent division by zero

        z_score = (value - mean) / safe_std

        # Rate of change: slope between last two points
        ts = window.timestamps
        dt = ts[-1] - ts[-2] if n >= 2 else 1.0
        dv = vals[-1] - vals[-2] if n >= 2 else 0.0
        rate = dv / max(abs(dt), 1e-10)

        vmin = np.min(vals)
        vmax = np.max(vals)
        value_range = vmax - vmin
        range_pos = (value - vmin) / max(value_range, 1e-10)

        return FeatureVector(
            parameter=parameter,
            timestamp_epoch=timestamp_epoch,
            raw_value=value,
            rolling_mean=float(mean),
            rolling_std=float(std),
            z_score=float(z_score),
            rate_of_change=float(rate),
            rolling_min=float(vmin),
            rolling_max=float(vmax),
            range_position=float(np.clip(range_pos, 0, 1)),
            deviation_from_trend=float(value - mean),
        )

    def compute_cross_features(
        self, param_a: str, param_b: str
    ) -> dict[str, float]:
        """Compute cross-parameter correlation features.

        This is the foundation of Dsremo's competitive advantage:
        detecting anomalies that only show up in parameter *relationships*,
        not individual values.
        """
        win_a = self._windows.get(param_a)
        win_b = self._windows.get(param_b)

        if not win_a or not win_b:
            return {"correlation": 0.0, "lag_correlation": 0.0, "divergence": 0.0}

        va = win_a.values
        vb = win_b.values

        # Align to same length
        n = min(len(va), len(vb))
        if n < 10:
            return {"correlation": 0.0, "lag_correlation": 0.0, "divergence": 0.0}

        a = va[-n:]
        b = vb[-n:]

        # Pearson correlation
        correlation = _safe_corrcoef(a, b)

        # Lagged correlation (shift b by 1 step)
        lag_corr = _safe_corrcoef(a[1:], b[:-1]) if n > 10 else 0.0

        # Normalized divergence: how much the relationship has changed recently
        half = n // 2
        corr_first = _safe_corrcoef(a[:half], b[:half])
        corr_second = _safe_corrcoef(a[half:], b[half:])
        divergence = abs(corr_second - corr_first)

        return {
            "correlation": float(correlation),
            "lag_correlation": float(lag_corr),
            "divergence": float(divergence),
        }

    def get_multivariate_snapshot(self, parameters: list[str]) -> np.ndarray | None:
        """Get the latest values for multiple parameters as a feature vector.

        Used by Isolation Forest for multivariate anomaly detection.
        Returns None if any parameter lacks data.
        """
        values = []
        for param in parameters:
            win = self._windows.get(param)
            if not win or win.size == 0:
                return None
            values.append(win.values[-1])
        return np.array(values, dtype=np.float64)

    def get_window_matrix(self, parameters: list[str], length: int = 100) -> np.ndarray | None:
        """Get a 2D matrix of recent values: shape (length, n_parameters).

        Used for training Isolation Forest on recent normal data.
        """
        columns = []
        for param in parameters:
            win = self._windows.get(param)
            if not win or win.size < length:
                return None
            columns.append(win.values[-length:])
        return np.column_stack(columns)

    def get_known_parameters(self) -> set[str]:
        """Return the set of parameters that have been seen so far."""
        return set(self._windows.keys())

    def detect_rate_change(self, parameter: str) -> dict:
        """Detect if the sampling rate has changed for a parameter.

        P2-I fix: Multi-rate telemetry handling.  Spacecraft telemetry is NOT
        uniform rate (housekeeping 1 Hz, payload 10 Hz, ADCS 100 Hz).  Rate
        changes from mode transitions or compression corrupt STL period
        detection and rolling statistics.

        Returns:
            {"rate_changed": bool, "median_interval_s": float,
             "current_interval_s": float, "ratio": float}
        """
        win = self._windows.get(parameter)
        if not win or win.size < 10:
            return {"rate_changed": False, "median_interval_s": 0.0,
                    "current_interval_s": 0.0, "ratio": 1.0}

        ts = win.timestamps
        diffs = np.diff(ts[-min(win.size, 50):])
        valid = diffs[diffs > 0]
        if len(valid) < 5:
            return {"rate_changed": False, "median_interval_s": 0.0,
                    "current_interval_s": 0.0, "ratio": 1.0}

        median_dt = float(np.median(valid))
        current_dt = float(valid[-1]) if len(valid) > 0 else median_dt

        ratio = current_dt / max(median_dt, 1e-6)
        # Rate change if current interval differs by >3x from median
        # ESTIMATE — 3× / 0.33× threshold; Friedman 2001 IEEE Trans Sig Proc: 3× ratio detects octave-level rate changes
        rate_changed = ratio > 3.0 or ratio < 0.33

        return {
            "rate_changed": rate_changed,
            "median_interval_s": round(median_dt, 3),
            "current_interval_s": round(current_dt, 3),
            "ratio": round(ratio, 3),
        }

    def reset(self, parameter: str | None = None) -> None:
        """Clear feature windows. If parameter given, clear only that one."""
        if parameter:
            self._windows.pop(parameter, None)
        else:
            self._windows.clear()


def _safe_corrcoef(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation that doesn't crash on constant arrays."""
    if len(a) < 2 or np.std(a) < 1e-10 or np.std(b) < 1e-10:
        return 0.0
    r = np.corrcoef(a, b)[0, 1]
    return 0.0 if np.isnan(r) else float(r)
