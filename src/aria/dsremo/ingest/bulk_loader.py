"""Generic bulk loader — direct DB insert + streaming detection.

Used by both the ESA and SatNOGS analysis scripts so that all
pipeline mechanics live in one place, not scattered across scripts.

Responsibilities
----------------
bulk_insert_channel()
    Takes a pandas Series (DatetimeIndex, float values) and writes it
    directly to PostgreSQL via UNNEST batch inserts, bypassing the REST
    API entirely.  Same throughput as analyze_esa_full used to embed
    inline — now reusable by any data source.

run_bulk_detection()
    Iterates a list of parameters and calls analyze_channel_history()
    for each, with a tqdm progress bar and live timing output.  Flushes
    CUSUM/EWMA/calibration states to DB at the end.

check_channel_row_count()
    Fast helper: returns the current row count for a (satellite, parameter)
    pair so callers can decide whether to skip re-loading.

print_detection_report()
    Shared console report: total anomalies, severity breakdown, subsystem
    breakdown, top-20 by confidence, per-channel summary.  Both ESA and
    SatNOGS scripts call this so the output format is consistent.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import timezone

import numpy as np
import pandas as pd
import structlog
from tqdm import tqdm

# Sensor-fusion audit S-18: ``run_bulk_detection`` mutates module-level
# globals on aria.dsremo.detection.detector / .calibration to scope its
# parameter overrides.  Two concurrent invocations would race on those
# writes and corrupt each other's settings.  This lock serialises the
# function so each call has exclusive ownership of the shared globals
# during its lifetime.
_RUN_BULK_DETECTION_LOCK = threading.Lock()

from aria.dsremo.core.models import Anomaly, TelemetryPoint
from aria.dsremo.db import connection as db_connection
from aria.dsremo.db import queries
from aria.dsremo.detection.detector import (
    analyze_channel_history,
    flush_all_states,
    save_channel_models,
)
from aria.dsremo.ingest.utils import prepare_series, validated_satellite_id

logger = structlog.get_logger()

# Default batch size for UNNEST inserts — 10 K rows per round-trip keeps
# memory bounded while amortising per-call overhead.
DEFAULT_INSERT_BATCH: int = 10_000

# Skip re-loading a channel that already has this many rows.
# Prevents duplicate inserts on re-runs (idempotent).
SKIP_IF_ROWS_GTE: int = 50_000


# ---------------------------------------------------------------------------
# Row count helper
# ---------------------------------------------------------------------------

async def check_channel_row_count(satellite_id: str, parameter: str) -> int:
    """Return current telemetry row count for (satellite_id, parameter)."""
    async with db_connection.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM telemetry"
            " WHERE satellite_id = $1 AND parameter = $2",
            satellite_id, parameter,
        )
    return int(cnt or 0)


# ---------------------------------------------------------------------------
# Bulk insert
# ---------------------------------------------------------------------------

async def bulk_insert_channel(
    satellite_id: str,
    channel_name: str,
    subsystem: str,
    unit: str,
    series: pd.Series,
    batch_size: int = DEFAULT_INSERT_BATCH,
    quality: float = 1.0,
    progress_cb: object | None = None,
) -> int:
    """Insert a time-series channel directly to DB via UNNEST.

    Args:
        satellite_id:  Unique satellite identifier.
        channel_name:  Parameter name (e.g. "channel_22", "frame_length").
        subsystem:     Subsystem label ("eps", "comms", etc.).
        unit:          Physical unit string (may be empty).
        series:        pandas Series with DatetimeIndex (tz-aware) and float
                       values.  NaN values are silently dropped.
        batch_size:    Rows per UNNEST call.  Tune for memory vs latency.
        quality:       Data quality flag written to every row (0.0–1.0).
        progress_cb:   Optional callable(n_inserted_so_far: int) for progress.

    Returns:
        Total rows accepted by the DB (may be less than len(series) if some
        timestamps were duplicates and hit the ON CONFLICT DO NOTHING guard).
    """
    accepted = 0
    dropped_nan = 0      # S-8/S-17 — count silent drops for observability
    buf: list[TelemetryPoint] = []
    total = len(series)

    for ts, val in series.items():
        if pd.isna(val):
            dropped_nan += 1
            continue

        # Ensure timezone-aware datetime for PostgreSQL timestamptz.
        ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if hasattr(ts_dt, "tzinfo") and ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)

        buf.append(TelemetryPoint(
            satellite_id=satellite_id,
            timestamp=ts_dt,
            subsystem=subsystem,
            parameter=channel_name,
            value=float(val),
            unit=unit,
            quality=quality,
        ))

        if len(buf) >= batch_size:
            await queries.insert_telemetry(buf)
            accepted += len(buf)
            if progress_cb:
                progress_cb(accepted)
            buf = []

    if buf:
        await queries.insert_telemetry(buf)
        accepted += len(buf)
        if progress_cb:
            progress_cb(accepted)

    # S-8/S-17: warn when silent NaN drop rate exceeds 1%.  Below the
    # threshold we still log at debug level so a slow-rising corruption
    # rate is visible in time-windowed dashboards.
    if total > 0 and dropped_nan / total > 0.01:
        logger.warning(
            "bulk_insert_high_nan_drop",
            satellite=satellite_id,
            param=channel_name,
            accepted=accepted,
            dropped_nan=dropped_nan,
            total=total,
            ratio=round(dropped_nan / total, 4),
        )
    elif dropped_nan:
        logger.debug(
            "bulk_insert_nan_drop",
            satellite=satellite_id,
            param=channel_name,
            dropped_nan=dropped_nan,
            total=total,
        )

    return accepted


# ---------------------------------------------------------------------------
# Bulk detection
# ---------------------------------------------------------------------------

_SKIP_ML_THRESHOLD = 999_999_999  # unreachably large min_train → ML never trains


async def run_bulk_detection(
    satellite_id: str,
    parameters: list[str],
    subsystem_map: dict[str, str],
    batch_size: int = 600,
    cooldown_hours: float | None = None,
    recal_factor: float | None = None,
    z_threshold: float | None = None,
    cusum_h_factor: float | None = None,
    lstm_epochs: int | None = None,
    tcn_epochs: int | None = None,
    retrain_interval: int | None = None,
    max_rows_per_channel: int | None = None,
) -> dict[str, list[Anomaly]]:
    """Run streaming anomaly detection over all stored channels.

    Fetches data from the DB in chronological order for each parameter
    and feeds it through the full 10-detector pipeline via
    analyze_channel_history().  Flushes accumulated CUSUM/EWMA state
    to DB when all channels have been processed.

    Args:
        satellite_id:         Satellite whose telemetry to analyse.
        parameters:           Ordered list of channel/parameter names.
        subsystem_map:        Maps parameter → subsystem label for anomaly records.
        batch_size:           DB fetch page size (600 = one full STL window).
        cooldown_hours:       Override alert cooldown (hours). None = use config value.
        recal_factor:         Override CUSUM recalibration sensitivity. None = use config.
        z_threshold:          Override z-score threshold. None = use config (default 3.0).
        cusum_h_factor:       Override CUSUM decision threshold multiplier. None = use config.
        lstm_epochs:          Override GRU training epochs. 0 = disable GRU entirely (fast).
                              None = use config (default 30). Useful for benchmark runs.
        tcn_epochs:           Override TCN training epochs. 0 = disable TCN entirely (fast).
                              None = use config (default 40). Useful for benchmark runs.
        retrain_interval:     Override how often ML models retrain (samples between retrains).
                              None = use config (default 500). Higher = faster but less adaptive.
        max_rows_per_channel: Hard cap on rows processed per channel. Prevents OOM on
                              continuous-fire datasets (e.g. CATS-2 5M rows/channel).
                              None = process all rows.

    Returns:
        Dict mapping each parameter name to its list of detected Anomaly objects.
    """
    import aria.dsremo.detection.detector as _det_mod
    import aria.dsremo.detection.calibration as _cal_mod

    # S-18: prevent concurrent invocations from racing on the
    # module-level globals below.  Acquire-on-entry; release-on-exit.
    if not _RUN_BULK_DETECTION_LOCK.acquire(blocking=False):
        logger.warning(
            "run_bulk_detection_lock_busy",
            satellite=satellite_id,
            hint=("another bulk-detection run is in progress; "
                  "this call will block until it completes"),
        )
        _RUN_BULK_DETECTION_LOCK.acquire()

    # Capture originals for guaranteed restore (even on exception).
    _orig_cooldown      = _det_mod._alert_cooldown_s
    _orig_recal         = _cal_mod.RECAL_FACTOR
    _orig_z             = _det_mod._stat_detector.z_threshold
    _orig_cusum_h       = _cal_mod.CUSUM_H_FACTOR
    _orig_lstm_epochs   = _det_mod._lstm_epochs
    _orig_lstm_min      = _det_mod._lstm_min_train
    _orig_tcn_epochs    = _det_mod._tcn_epochs
    _orig_tcn_min       = _det_mod._tcn_min_train
    _orig_lstm_retrain  = _det_mod._lstm_retrain_interval
    _orig_tcn_retrain   = _det_mod._tcn_retrain_interval

    if cooldown_hours is not None:
        _det_mod._alert_cooldown_s = cooldown_hours * 3600.0
        _det_mod._last_anomaly_ts.clear()   # reset per-channel timers on cooldown change
    if recal_factor is not None:
        _cal_mod.RECAL_FACTOR = recal_factor
    if z_threshold is not None:
        _det_mod._stat_detector.z_threshold = z_threshold
    if cusum_h_factor is not None:
        _cal_mod.CUSUM_H_FACTOR = cusum_h_factor
    if lstm_epochs is not None:
        _det_mod._lstm_epochs = lstm_epochs
        if lstm_epochs == 0:
            _det_mod._lstm_min_train = _SKIP_ML_THRESHOLD  # never reaches training threshold
        _det_mod._lstm_models.clear()   # drop stale instances so new ones use new epochs
    if tcn_epochs is not None:
        _det_mod._tcn_epochs = tcn_epochs
        if tcn_epochs == 0:
            _det_mod._tcn_min_train = _SKIP_ML_THRESHOLD
        _det_mod._tcn_models.clear()
    if retrain_interval is not None:
        _det_mod._lstm_retrain_interval = retrain_interval
        _det_mod._tcn_retrain_interval  = retrain_interval
        _det_mod._lstm_models.clear()
        _det_mod._tcn_models.clear()

    results: dict[str, list[Anomaly]] = {}

    try:
        for param in tqdm(parameters, desc="Detecting", unit="ch"):
            subsystem = subsystem_map.get(param, "")

            cnt = await check_channel_row_count(satellite_id, param)

            if not cnt:
                tqdm.write(f"  SKIP {param} — no data in DB")
                continue

            t0 = time.monotonic()
            display_cnt = int(min(cnt, max_rows_per_channel) if max_rows_per_channel else cnt)
            with tqdm(total=display_cnt, desc=f"  {param}", unit="pt", leave=False) as pbar:
                anomalies = await analyze_channel_history(
                    satellite_id=satellite_id,
                    parameter=param,
                    subsystem=subsystem,
                    batch_size=batch_size,
                    max_rows=max_rows_per_channel,
                    progress_cb=lambda n, last=[0], p=pbar: (
                        p.update(n - last[0]),
                        last.__setitem__(0, n),
                    ),
                )

            elapsed = time.monotonic() - t0
            if anomalies:
                tqdm.write(
                    f"  {param}: {int(cnt):>7,} pts, {len(anomalies)} anomalies"
                    f"  [{elapsed:.1f}s]"
                )
            results[param] = anomalies

            # Persist ML model checkpoints for warm-start on the next run.
            save_channel_models(satellite_id, param)

        # Persist CUSUM/EWMA/calibration states to DB.
        await flush_all_states()

    finally:
        try:
            # Always restore original settings — even if an exception interrupts detection.
            _det_mod._alert_cooldown_s          = _orig_cooldown
            _cal_mod.RECAL_FACTOR               = _orig_recal
            _det_mod._stat_detector.z_threshold = _orig_z
            _cal_mod.CUSUM_H_FACTOR             = _orig_cusum_h
            _det_mod._lstm_epochs               = _orig_lstm_epochs
            _det_mod._lstm_min_train            = _orig_lstm_min
            _det_mod._tcn_epochs                = _orig_tcn_epochs
            _det_mod._tcn_min_train             = _orig_tcn_min
            _det_mod._lstm_retrain_interval     = _orig_lstm_retrain
            _det_mod._tcn_retrain_interval      = _orig_tcn_retrain
            _det_mod._lstm_models.clear()   # drop run-scoped ML models (may have used different epochs)
            _det_mod._tcn_models.clear()
        finally:
            # S-18: always release the lock, even if the restore itself raises.
            _RUN_BULK_DETECTION_LOCK.release()

    return results


# ---------------------------------------------------------------------------
# Shared report printer
# ---------------------------------------------------------------------------

def print_detection_report(
    results: dict[str, list[Anomaly]],
    title: str = "ANOMALY DETECTION RESULTS",
    ground_truth_note: str = "",
) -> None:
    """Print a formatted anomaly detection report to stdout.

    Args:
        results:             Output of run_bulk_detection().
        title:               Header line for the report.
        ground_truth_note:   Optional footer note about ground truth comparison.
    """
    all_anomalies = [a for anoms in results.values() for a in anoms]

    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)
    print(f"\nTotal anomalies found:  {len(all_anomalies)}")

    if not all_anomalies:
        print("\n  No anomalies detected above threshold.")
        print("  Possible causes:")
        print("    • Channels still in warm-up (need 200 samples)")
        print("    • Thresholds too conservative — lower watch threshold in dsremo.yaml")
        print("    • Dataset is predominantly nominal (expected for real telemetry)")
        if ground_truth_note:
            print(f"\n{ground_truth_note}")
        return

    # Sort by confidence descending.
    all_anomalies.sort(key=lambda a: a.confidence, reverse=True)

    # Severity breakdown.
    sev_counts = Counter(a.severity.value for a in all_anomalies)
    print("\nBy severity:")
    for sev in ("critical", "warning", "watch", "nominal"):
        c = sev_counts.get(sev, 0)
        if c:
            print(f"  {sev:8s}: {c}")

    # Subsystem breakdown.
    sub_groups: dict[str, list[Anomaly]] = {}
    for a in all_anomalies:
        sub_groups.setdefault(a.subsystem, []).append(a)
    print("\nBy subsystem:")
    for sub, anoms in sorted(sub_groups.items(), key=lambda x: -len(x[1])):
        print(f"  {sub:8s}: {len(anoms)} anomalies")

    # Top-20 table.
    top_n = min(20, len(all_anomalies))
    print(f"\nTop {top_n} by confidence:")
    print(f"  {'Channel':<14} {'Severity':<10} {'Conf':>6} "
          f"{'Detectors':<35} {'Timestamp'}")
    print("  " + "-" * 90)
    for a in all_anomalies[:top_n]:
        dets = "+".join(a.detectors_triggered) if a.detectors_triggered else "none"
        ts   = str(a.timestamp)[:19]
        print(f"  {a.parameter:<14} {a.severity.value:<10} {a.confidence:>6.3f} "
              f"{dets:<35} {ts}")

    # Per-channel breakdown.
    print("\nPer-channel anomaly counts (channels with detections only):")
    ch_anom = {ch: anoms for ch, anoms in results.items() if anoms}
    for ch, anoms in sorted(ch_anom.items(), key=lambda x: -len(x[1])):
        timestamps = sorted(str(a.timestamp)[:10] for a in anoms)
        t_range = (
            f"{timestamps[0]} → {timestamps[-1]}"
            if len(timestamps) > 1
            else timestamps[0]
        )
        top = max(anoms, key=lambda a: a.confidence)
        print(
            f"  {ch:<20} {len(anoms):>4} anomalies"
            f"  [{top.severity.value}/{top.confidence:.2f}]  {t_range}"
        )

    if ground_truth_note:
        print("\n" + "=" * 65)
        print(ground_truth_note)
    print("=" * 65)


# ---------------------------------------------------------------------------
# DRY channel loader — shared by YAMCS, InfluxDB, and future HTTP connectors
# ---------------------------------------------------------------------------

async def load_channels_from_series(
    satellite_id: str,
    channels: dict[str, pd.Series],
    *,
    subsystem_map: dict[str, str] | None = None,
    unit_map: dict[str, str] | None = None,
    resample_minutes: int = 1,
    skip_if_rows_gte: int = 50_000,
    source_name: str = "unknown",
) -> dict[str, int]:
    """Bulk-insert a dict of pre-fetched time-series channels into the DB.

    Encapsulates the per-channel pipeline that all HTTP connectors share:
      1. Validate satellite_id and resample_minutes.
      2. For each channel: prepare series (UTC + resample + drop NaN).
      3. Skip channels that already have >= skip_if_rows_gte rows.
      4. Register satellite + channel (upsert_satellite_seen / upsert_channel_seen).
      5. Bulk-insert via bulk_insert_channel (UNNEST batches, idempotent).

    Args:
        satellite_id:    Dsremo satellite identifier (must be non-empty).
        channels:        {parameter_name: pandas.Series(DatetimeIndex, float)}.
        subsystem_map:   Optional {parameter → subsystem label}. Defaults to source_name.
        unit_map:        Optional {parameter → unit string}.
        resample_minutes: Resampling interval (>= 1).
        skip_if_rows_gte: Skip a channel that already has this many rows.
        source_name:     Label stored in logs for traceability.

    Returns:
        {parameter: rows_inserted} for each processed channel.
        Skipped channels include their existing row count.
    """
    satellite_id = validated_satellite_id(satellite_id)
    if resample_minutes < 1:
        raise ValueError(f"resample_minutes must be >= 1, got {resample_minutes!r}")

    _subsystem_map = subsystem_map or {}
    _unit_map = unit_map or {}
    totals: dict[str, int] = {}

    for param, raw_series in channels.items():
        subsystem = _subsystem_map.get(param, source_name)
        unit = _unit_map.get(param, "")

        try:
            series = prepare_series(raw_series, resample_minutes)
        except Exception as exc:
            logger.warning(
                "load_channels_series_prep_failed",
                satellite_id=satellite_id,
                param=param,
                error=str(exc),
            )
            continue

        if series.empty:
            logger.warning(
                "load_channels_series_empty",
                satellite_id=satellite_id,
                param=param,
                source=source_name,
            )
            continue

        existing = await check_channel_row_count(satellite_id, param)
        if skip_if_rows_gte > 0 and existing >= skip_if_rows_gte:
            logger.info(
                "load_channels_skipped",
                satellite_id=satellite_id,
                param=param,
                existing_rows=existing,
            )
            totals[param] = existing
            continue

        await queries.upsert_satellite_seen(
            satellite_id, series.index[0].to_pydatetime()
        )
        await queries.upsert_channel_seen(satellite_id, param, subsystem, unit)

        inserted = await bulk_insert_channel(
            satellite_id=satellite_id,
            channel_name=param,
            subsystem=subsystem,
            unit=unit,
            series=series,
        )
        totals[param] = inserted

        logger.info(
            "load_channels_inserted",
            satellite_id=satellite_id,
            param=param,
            rows=inserted,
            source=source_name,
        )

    return totals
