"""Shared ingest utilities — timezone handling, series preparation, validation, retry.

All connectors (CSVConnector, SatNOGSFetcher, ESADataLoader, …) use these
helpers to ensure consistent behaviour without duplicating code.

Data-frequency utilities (usable by all analyze_* scripts):
    detect_data_frequency()   — peek at a CSV file and return the median
                                inter-sample interval in seconds.
    adaptive_cooldown_hours() — convert a sampling interval to a proportional
                                alert cooldown.  Formula: max(5 min, 500×interval),
                                capped at 72 h.  Scales automatically from
                                1-second SCADA data (≈8 min) to 1-hour satellite
                                telemetry (72 h cap).
    smart_cooldown_hours()    — scan raw CSV z-scores to find natural anomaly
                                burst spacing and set cooldown proportionally.
                                Falls back to None when signal is insufficient.
"""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import Any, Callable, Coroutine, TypeVar

import httpx
import pandas as pd
import structlog

logger = structlog.get_logger()

_T = TypeVar("_T")


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (httpx.TransportError,),
) -> Callable[[Callable[..., Coroutine[Any, Any, _T]]], Callable[..., Coroutine[Any, Any, _T]]]:
    """Decorator: retry an async function on specified exceptions with exponential backoff.

    Args:
        max_attempts: Total attempts before re-raising (default 3).
        base_delay:   Initial delay in seconds; doubles each attempt (1s, 2s, 4s, …).
        exceptions:   Exception types to catch and retry (default: httpx.TransportError).

    Usage:
        @retry_with_backoff(max_attempts=3)
        async def fetch_page(self, url: str) -> bytes:
            ...
    """
    def decorator(
        func: Callable[..., Coroutine[Any, Any, _T]]
    ) -> Callable[..., Coroutine[Any, Any, _T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> _T:
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts - 1:
                        raise
                    wait = base_delay * (2 ** attempt)
                    logger.warning(
                        "retry_backoff",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        retry_in=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)
            raise RuntimeError("retry_with_backoff: unreachable")  # pragma: no cover
        return wrapper
    return decorator


def ensure_utc_series(
    series: pd.Series,
    *,
    assume_naive_tz: str = "UTC",
) -> pd.Series:
    """Return series with a UTC-aware DatetimeIndex.

    If the index is already tz-aware this is a no-op (no copy).

    Sensor-fusion audit S-9: naive indices used to be silently labelled
    ``"UTC"``.  Many ground-station feeds emit local-time strings
    without a TZ — silently labelling them UTC stored events at the
    wrong offset (9 h for JAXA TKSC, 3 h for ESA Kourou) and broke
    every cross-channel correlation downstream.

    The default ``assume_naive_tz="UTC"`` preserves historical CSV
    pipelines, but a structured warning is emitted on every naive
    input so operators can flip the default.  Passing any other IANA
    name (e.g. ``"Asia/Tokyo"``) localises to that zone and then
    converts to UTC.
    """
    if series.index.tz is not None:
        return series

    series = series.copy()
    tz_label = assume_naive_tz.upper() if assume_naive_tz else "UTC"
    if tz_label == "UTC":
        logger.warning(
            "naive_timestamps_assumed_utc",
            n_rows=len(series),
            hint=("naive DatetimeIndex was relabelled UTC; pass "
                  "assume_naive_tz=<IANA-zone> if data is local time"),
        )
        series.index = series.index.tz_localize("UTC")
    else:
        series.index = (
            series.index.tz_localize(assume_naive_tz).tz_convert("UTC")
        )
    return series


def prepare_series(
    series: pd.Series,
    resample_minutes: int = 1,
    *,
    assume_naive_tz: str = "UTC",
) -> pd.Series:
    """Normalize timezone, optionally resample to coarser resolution, drop NaN.

    Pipeline:
        1. Localize naive index → ``assume_naive_tz`` then convert UTC.
           ``"UTC"`` is the default to preserve historical CSV-pipeline
           behaviour, but callers handling ground-local feeds SHOULD
           pass the actual ground TZ so timestamps are converted, not
           silently relabelled.  A structured warning fires on every
           naive index (sensor-fusion audit S-9).
        2. Resample via median if resample_minutes > 1
        3. Drop NaN rows

    Always returns a new Series; never mutates the input.
    """
    series = ensure_utc_series(series, assume_naive_tz=assume_naive_tz)
    if resample_minutes > 1:
        series = series.resample(f"{resample_minutes}min").median()
    return series.dropna()


def validated_resample(minutes: int) -> int:
    """Return `minutes` unchanged, or raise ValueError if < 1."""
    if minutes < 1:
        raise ValueError(f"resample_minutes must be >= 1, got {minutes!r}")
    return minutes


def validated_satellite_id(sid: str) -> str:
    """Strip whitespace and return the satellite ID, or raise ValueError if empty."""
    sid = sid.strip() if isinstance(sid, str) else ""
    if not sid:
        raise ValueError("satellite_id must not be empty")
    return sid


# ── Data-frequency helpers (shared by all analyze_* scripts) ─────────────────

def detect_data_frequency(
    file_path: Path,
    timestamp_col: str = "timestamp",
) -> float:
    """Return median inter-sample interval in seconds by peeking at the first 200 rows.

    Used to scale the alert cooldown to the data frequency before running
    anomaly detection — avoids the foot-gun of applying a 72-hour cooldown
    to 1-second SCADA data (which would suppress all multi-window events).

    Handles both comma and semicolon CSV delimiters (auto-detected from the
    first 500 bytes of the file).

    Args:
        file_path:     Path to a wide-format CSV (timestamp + parameter columns).
        timestamp_col: Name of the timestamp column (default "timestamp").

    Returns:
        Median inter-sample interval in seconds (float).
        Falls back to 3600.0 (1-hour assumption) on any error or if fewer
        than 2 rows are present.
    """
    try:
        text_peek = file_path.read_text(errors="replace")[:500]
        sep = ";" if ";" in text_peek else ","
        df = pd.read_csv(file_path, sep=sep, nrows=200)
        if timestamp_col not in df.columns:
            return 3600.0
        ts = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce").dropna().sort_values()
        if len(ts) < 2:
            return 3600.0
        diffs = ts.diff().dropna().dt.total_seconds()
        return float(diffs.median())
    except Exception:
        return 3600.0


def adaptive_cooldown_hours(median_interval_s: float) -> float:
    """Compute alert cooldown (hours) proportional to data frequency.

    Formula: cooldown = max(5 minutes, 500 × median_interval_s), capped at 72 h.

    Scaling examples:
        1-second SCADA/industrial data  → 500 s  ≈  8.3 min
        5-minute monitoring data        → 2500 s ≈ 41.7 min
        1-hour satellite telemetry      → 500 h  → capped at 72 h

    The 500× multiplier ensures the cooldown spans many data-frequency
    "periods", so a brief anomaly is not immediately followed by another
    false positive on the receding edge.

    Args:
        median_interval_s: Median inter-sample interval in seconds (from
                           detect_data_frequency()).  Must be ≥ 0.

    Returns:
        Cooldown in hours (float), in the range [0.0833, 72.0].
    """
    cooldown_s = max(300.0, 500.0 * max(0.0, median_interval_s))
    cooldown_s = min(cooldown_s, 72.0 * 3600.0)   # cap at 72 h
    return cooldown_s / 3600.0


def smart_cooldown_hours(
    file_path: Path,
    timestamp_col: str = "timestamp",
    z_threshold: float = 2.0,
    min_bursts: int = 5,
    cooldown_fraction: float = 0.5,
) -> float | None:
    """Estimate optimal cooldown by scanning raw value bursts in the CSV.

    Scans the whole file, computes rolling z-scores per channel, finds
    "proto-alarm" bursts (samples where any channel exceeds z_threshold),
    clusters them, measures the median gap between burst starts, and returns
    cooldown = gap × cooldown_fraction.

    This answers the question "how far apart are anomaly events?" using only
    the raw signal — no GT, no ML, no DB required.

    Returns None (caller should fall back to adaptive_cooldown_hours) when:
      - The file cannot be read
      - Fewer than min_bursts burst clusters are found (not enough signal)
      - The data is too uniform to trigger any z-score alarms

    Args:
        file_path:         Wide-format CSV with timestamp + value columns.
        timestamp_col:     Name of the timestamp column.
        z_threshold:       Rolling z-score threshold for proto-alarm detection.
        min_bursts:        Minimum burst clusters required to return an estimate.
        cooldown_fraction: Cooldown = median_burst_gap × this fraction.

    Returns:
        Estimated cooldown in hours, or None.
    """
    try:
        text_peek = file_path.read_text(errors="replace")[:500]
        sep = ";" if ";" in text_peek else ","
        df = pd.read_csv(file_path, sep=sep)

        if timestamp_col not in df.columns or len(df) < 50:
            return None

        ts = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
        median_s = float(ts.diff().dt.total_seconds().dropna().median())
        if median_s <= 0:
            return None

        # Tight burst gap: 20 data points worth of time
        burst_gap_s = max(60.0, 20.0 * median_s)

        # Build a boolean mask: True where any channel exceeds z_threshold
        value_cols = [c for c in df.columns if c != timestamp_col]
        proto_alarm = pd.Series(False, index=df.index)
        for col in value_cols:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() < 30:
                continue
            roll = s.rolling(min(100, len(s) // 4), min_periods=10)
            z = ((s - roll.mean()) / roll.std().clip(lower=1e-9)).abs()
            proto_alarm |= (z > z_threshold)

        alarm_ts = ts[proto_alarm].dropna().sort_values()
        if len(alarm_ts) < min_bursts:
            return None

        # Cluster tight alarms into bursts, collect burst start timestamps
        burst_starts: list[float] = [alarm_ts.iloc[0].timestamp()]
        for i in range(1, len(alarm_ts)):
            gap = (alarm_ts.iloc[i] - alarm_ts.iloc[i - 1]).total_seconds()
            if gap > burst_gap_s:
                burst_starts.append(alarm_ts.iloc[i].timestamp())

        if len(burst_starts) < min_bursts:
            return None

        # Median gap between consecutive burst starts
        inter_gaps = sorted(
            burst_starts[i] - burst_starts[i - 1]
            for i in range(1, len(burst_starts))
        )
        median_gap_s = inter_gaps[len(inter_gaps) // 2]

        cooldown_s = max(300.0, median_gap_s * cooldown_fraction)
        cooldown_s = min(cooldown_s, 72.0 * 3600.0)
        return cooldown_s / 3600.0

    except Exception:
        return None
