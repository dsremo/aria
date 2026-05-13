"""Parameterized queries — the ONLY way to talk to the database.

Rules (never break these):
  1. All values go through $N placeholders. Zero string interpolation.
  2. Every public function opens its own connection via acquire().
  3. Bulk inserts use UNNEST — one round-trip for any batch size.
  4. ON CONFLICT DO NOTHING on telemetry — idempotent ingestion, retry-safe.
  5. All SELECT limits are capped server-side — callers cannot cause OOM.

Query map:
  Telemetry       — insert_telemetry, get_telemetry, get_recent_telemetry_window,
                    get_latest_values
  Satellites      — get_known_satellites, upsert_satellite_seen
  Channels        — upsert_channel_seen, get_channel_stats,
                    get_channel_config, upsert_channel_config,
                    delete_channel_config, load_all_channel_configs
  Calibration     — get_channel_calibration, upsert_channel_calibration,
                    get_all_calibrations
  Detector state  — get_detector_state, upsert_detector_state,
                    bulk_upsert_detector_states, get_all_detector_states
  Anomalies       — insert_anomaly, get_anomalies, get_anomaly_by_id,
                    get_anomaly_stats, mark_false_positive
  Incidents       — open_incident, get_open_incident, update_incident_stats,
                    link_anomaly_to_incident, close_incident, get_incidents
  Alerts          — insert_alert, get_alerts, acknowledge_alert,
                    upsert_alert_config, get_alert_config, delete_alert_config,
                    load_all_alert_configs
  API Keys        — store_api_key, verify_api_key_exists, touch_api_key
  Rollups         — get_hourly_stats (uses telemetry_hourly cagg if available)
"""

from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from aria.dsremo.core.models import Anomaly, TelemetryPoint
from aria.dsremo.core.tenant import get_tenant
from aria.dsremo.db.connection import acquire, get_pool

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

async def insert_telemetry(points: list[TelemetryPoint]) -> int:
    """Bulk-insert telemetry via UNNEST.

    One SQL statement regardless of batch size — 10-100x faster than
    executemany for large payloads (ESA: 500 points → 1 round-trip vs 500).

    ON CONFLICT DO NOTHING: exact duplicate (same tenant + sat + parameter + timestamp)
    is silently discarded, making ingestion idempotent on retransmission.
    """
    if not points:
        return 0

    tenant = get_tenant()
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO telemetry
                (tenant_id, satellite_id, timestamp, subsystem, parameter, value, unit, quality)
            SELECT * FROM UNNEST(
                $1::text[],
                $2::text[],
                $3::timestamptz[],
                $4::text[],
                $5::text[],
                $6::float8[],
                $7::text[],
                $8::float4[]
            )
            ON CONFLICT (tenant_id, satellite_id, parameter, timestamp) DO NOTHING
            """,
            [tenant]        * len(points),
            [p.satellite_id for p in points],
            [p.timestamp    for p in points],
            [p.subsystem    for p in points],
            [p.parameter    for p in points],
            [p.value        for p in points],
            [p.unit         for p in points],
            [p.quality      for p in points],
        )
    return len(points)


async def get_telemetry(
    satellite_id: str,
    parameter: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Query telemetry with optional filters. Hard-capped at 10 000 rows."""
    # Build conditions list cleanly — no f-string SQL, no injection risk.
    conditions: list[str] = ["satellite_id = $1"]
    params: list[Any] = [satellite_id]

    if parameter is not None:
        params.append(parameter)
        conditions.append(f"parameter = ${len(params)}")

    if since is not None:
        params.append(since)
        conditions.append(f"timestamp >= ${len(params)}")

    if until is not None:
        params.append(until)
        conditions.append(f"timestamp <= ${len(params)}")

    params.append(min(limit, 10_000))
    limit_ph = f"${len(params)}"

    where = " AND ".join(conditions)
    sql = (
        f"SELECT satellite_id, timestamp, subsystem, parameter, value, unit, quality "  # nosec B608 (column names are literal; values bound via ?)
        f"FROM telemetry WHERE {where} "
        f"ORDER BY timestamp DESC LIMIT {limit_ph}"
    )

    async with acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def get_recent_telemetry_window(
    satellite_id: str,
    parameter: str,
    window_size: int = 300,
) -> list[dict]:
    """N most-recent points for one parameter, ascending order.

    Detectors require oldest-first (ascending) so values[0] is the oldest
    and values[-1] is the current point.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT timestamp, value, quality
            FROM (
                SELECT timestamp, value, quality
                FROM telemetry
                WHERE satellite_id = $1 AND parameter = $2
                ORDER BY timestamp DESC
                LIMIT $3
            ) sub
            ORDER BY timestamp ASC
            """,
            satellite_id, parameter, window_size,
        )
    return [dict(r) for r in rows]


async def get_telemetry_batch_ordered(
    satellite_id: str,
    parameter: str,
    after_ts: "datetime | None" = None,
    limit: int = 10_000,
) -> list[dict]:
    """Chronologically ordered telemetry for one parameter, with pagination.

    Used by the bulk analysis pipeline to replay all stored data through the
    detection pipeline without going through the REST API.  Callers should
    call repeatedly, passing the last returned timestamp as after_ts, until
    an empty list is returned.

    Returns oldest-first (ascending) so the detection loop sees time correctly.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT timestamp, value, subsystem, quality
            FROM telemetry
            WHERE satellite_id = $1 AND parameter = $2
              AND ($3::timestamptz IS NULL OR timestamp > $3)
            ORDER BY timestamp ASC
            LIMIT $4
            """,
            satellite_id, parameter, after_ts, limit,
        )
    return [dict(r) for r in rows]


async def get_latest_values(satellite_id: str) -> list[dict]:
    """Most-recent value for every parameter of a satellite.

    DISTINCT ON is PostgreSQL-specific but extremely efficient with the
    idx_telemetry_param_time index (satellite_id, parameter, timestamp DESC).
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (parameter)
                satellite_id, timestamp, subsystem, parameter, value, unit, quality
            FROM telemetry
            WHERE satellite_id = $1
            ORDER BY parameter, timestamp DESC
            """,
            satellite_id,
        )
    return [dict(r) for r in rows]


async def get_telemetry_stats() -> dict:
    """Aggregate telemetry statistics for the dashboard.

    All counts are tenant-scoped via RLS so each tenant sees only their data.

    Returns:
        total_telemetry_points: Total rows for the current tenant.
        points_last_hour:       Exact count of rows inserted in the past hour.
        active_satellites:      Number of distinct satellites for this tenant.
    """
    async with acquire() as conn:
        # Tenant-scoped total (RLS filters to current tenant).
        total = await conn.fetchval("SELECT COUNT(*) FROM telemetry")
        # Exact count for the last hour (bounded, always fast).
        last_hour = await conn.fetchval(
            "SELECT COUNT(*) FROM telemetry"
            " WHERE timestamp >= NOW() - INTERVAL '1 hour'"
        )
        active_sats = await conn.fetchval(
            "SELECT COUNT(DISTINCT satellite_id) FROM satellites"
        )
    return {
        "total_telemetry_points": int(total     or 0),
        "points_last_hour":       int(last_hour or 0),
        "active_satellites":      int(active_sats or 0),
    }


async def get_anomaly_count() -> int:
    """Total anomaly count across all satellites."""
    async with acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM anomalies")
    return int(cnt or 0)


async def get_anomaly_severity_counts() -> dict[str, int]:
    """Count anomalies by severity across all satellites."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT severity, COUNT(*) AS cnt FROM anomalies GROUP BY severity"
        )
    return {r["severity"]: int(r["cnt"]) for r in rows}


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------

async def upsert_satellite_seen(satellite_id: str, ts: datetime) -> None:
    """Register satellite on first telemetry; update last_telemetry_at thereafter."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO satellites (tenant_id, satellite_id, first_telemetry_at, last_telemetry_at)
            VALUES ($1, $2, $3, $3)
            ON CONFLICT (tenant_id, satellite_id) DO UPDATE
                SET last_telemetry_at = EXCLUDED.last_telemetry_at
                WHERE satellites.last_telemetry_at IS NULL
                   OR satellites.last_telemetry_at < EXCLUDED.last_telemetry_at
            """,
            get_tenant(), satellite_id, ts,
        )


async def get_known_satellites() -> list[str]:
    """All satellite IDs that have ever sent telemetry."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT satellite_id FROM satellites ORDER BY satellite_id"
        )
    return [r["satellite_id"] for r in rows]


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------

async def upsert_channel_seen(
    satellite_id: str,
    parameter: str,
    subsystem: str,
    unit: str,
    point_count: int = 1,
) -> None:
    """Register a channel on first sight; bump total_points and last_seen_at."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO channel_registry
                (tenant_id, satellite_id, parameter, subsystem, unit, total_points)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (tenant_id, satellite_id, parameter) DO UPDATE
                SET last_seen_at = NOW(),
                    total_points = channel_registry.total_points + EXCLUDED.total_points,
                    subsystem    = EXCLUDED.subsystem,
                    unit         = EXCLUDED.unit
            """,
            get_tenant(), satellite_id, parameter, subsystem, unit, point_count,
        )


async def get_channel_stats(satellite_id: str | None = None) -> list[dict]:
    """Summary stats for every channel. Used by dashboard and /channels API.

    When satellite_id is None, returns channels for all satellites (RLS-scoped
    to the current tenant). Includes per-channel config overrides via LEFT JOIN
    so callers can compute effective thresholds without a second query.
    """
    _ORDER_SAT  = "cr.satellite_id, cr.subsystem, cr.parameter"
    _ORDER_CHAN = "cr.subsystem, cr.parameter"
    _SELECT = """
        SELECT
            cr.satellite_id,
            cr.parameter,
            cr.subsystem,
            cr.unit,
            cr.total_points,
            cr.first_seen_at,
            cr.last_seen_at,
            cc.state           AS calibration_state,
            cc.ref_mean,
            cc.ref_std,
            cc.ref_sample_count,
            cfg.z_threshold,
            cfg.cusum_h,
            cfg.cusum_k,
            cfg.ewma_lambda,
            cfg.ewma_sigma_mult,
            cfg.min_confidence,
            cfg.alert_cooldown_s,
            cfg.updated_at     AS config_updated_at
        FROM channel_registry cr
        LEFT JOIN channel_calibration cc
               ON cc.satellite_id = cr.satellite_id
              AND cc.parameter    = cr.parameter
        LEFT JOIN channel_config cfg
               ON cfg.satellite_id = cr.satellite_id
              AND cfg.parameter    = cr.parameter
    """
    async with acquire() as conn:
        if satellite_id is not None:
            rows = await conn.fetch(
                _SELECT + f" WHERE cr.satellite_id = $1 ORDER BY {_ORDER_CHAN}",
                satellite_id,
            )
        else:
            rows = await conn.fetch(_SELECT + f" ORDER BY {_ORDER_SAT}")
    return [dict(r) for r in rows]


async def get_channel_config(satellite_id: str, parameter: str) -> dict | None:
    """Return channel_config override row for one channel, or None if not set."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT z_threshold, cusum_h, cusum_k, ewma_lambda, ewma_sigma_mult,
                   min_confidence, alert_cooldown_s, variance_z_threshold, updated_at
            FROM channel_config
            WHERE satellite_id = $1 AND parameter = $2
            """,
            satellite_id, parameter,
        )
    return dict(row) if row else None


async def upsert_channel_config(
    satellite_id: str,
    parameter: str,
    *,
    z_threshold: float | None = None,
    cusum_h: float | None = None,
    cusum_k: float | None = None,
    ewma_lambda: float | None = None,
    ewma_sigma_mult: float | None = None,
    min_confidence: float | None = None,
    alert_cooldown_s: int | None = None,
    variance_z_threshold: float | None = None,
    hard_limit_high: float | None = None,
    hard_limit_low: float | None = None,
    velocity_threshold: float | None = None,
) -> dict:
    """Insert or partially update per-channel threshold overrides.

    COALESCE on each column: passing None keeps the existing DB value, so
    callers can update a single field without touching the others.
    To remove all overrides use delete_channel_config().
    Returns the full updated row.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO channel_config
                (tenant_id, satellite_id, parameter,
                 z_threshold, cusum_h, cusum_k,
                 ewma_lambda, ewma_sigma_mult,
                 min_confidence, alert_cooldown_s, variance_z_threshold,
                 hard_limit_high, hard_limit_low, velocity_threshold,
                 updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            ON CONFLICT (tenant_id, satellite_id, parameter) DO UPDATE
                SET z_threshold           = COALESCE(EXCLUDED.z_threshold,           channel_config.z_threshold),
                    cusum_h               = COALESCE(EXCLUDED.cusum_h,               channel_config.cusum_h),
                    cusum_k               = COALESCE(EXCLUDED.cusum_k,               channel_config.cusum_k),
                    ewma_lambda           = COALESCE(EXCLUDED.ewma_lambda,           channel_config.ewma_lambda),
                    ewma_sigma_mult       = COALESCE(EXCLUDED.ewma_sigma_mult,       channel_config.ewma_sigma_mult),
                    min_confidence        = COALESCE(EXCLUDED.min_confidence,        channel_config.min_confidence),
                    alert_cooldown_s      = COALESCE(EXCLUDED.alert_cooldown_s,      channel_config.alert_cooldown_s),
                    variance_z_threshold  = COALESCE(EXCLUDED.variance_z_threshold,  channel_config.variance_z_threshold),
                    hard_limit_high       = COALESCE(EXCLUDED.hard_limit_high,       channel_config.hard_limit_high),
                    hard_limit_low        = COALESCE(EXCLUDED.hard_limit_low,        channel_config.hard_limit_low),
                    velocity_threshold    = COALESCE(EXCLUDED.velocity_threshold,    channel_config.velocity_threshold),
                    updated_at            = NOW()
            RETURNING z_threshold, cusum_h, cusum_k, ewma_lambda, ewma_sigma_mult,
                      min_confidence, alert_cooldown_s, variance_z_threshold,
                      hard_limit_high, hard_limit_low, velocity_threshold, updated_at
            """,
            get_tenant(), satellite_id, parameter,
            z_threshold, cusum_h, cusum_k,
            ewma_lambda, ewma_sigma_mult,
            min_confidence, alert_cooldown_s, variance_z_threshold,
            hard_limit_high, hard_limit_low, velocity_threshold,
        )
    return dict(row)


async def delete_channel_config(satellite_id: str, parameter: str) -> bool:
    """Remove all per-channel overrides (revert to global defaults).

    Returns True if a row existed and was deleted.
    """
    async with acquire() as conn:
        result = await conn.execute(
            "DELETE FROM channel_config WHERE satellite_id = $1 AND parameter = $2",
            satellite_id, parameter,
        )
    return result == "DELETE 1"


async def load_all_channel_configs(satellite_id: str | None = None) -> list[dict]:
    """Load channel_config rows for the in-memory detector cache.

    Uses the raw pool directly (not acquire()) to bypass RLS and see all
    tenants' configs — same pattern as load_api_key_map().
    Called at server startup and after any PUT/DELETE to refresh the cache.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tenant_id, satellite_id, parameter,
                   z_threshold, cusum_h, cusum_k,
                   ewma_lambda, ewma_sigma_mult,
                   min_confidence, alert_cooldown_s, variance_z_threshold
            FROM channel_config
            WHERE $1::text IS NULL OR satellite_id = $1
            """,
            satellite_id,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Per-channel calibration (CUSUM / EWMA reference distribution)
# ---------------------------------------------------------------------------

async def get_channel_calibration(
    satellite_id: str, parameter: str
) -> dict | None:
    """Load calibration state for one channel."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT state, ref_mean, ref_std, ref_sample_count, calibrated_at
            FROM channel_calibration
            WHERE satellite_id = $1 AND parameter = $2
            """,
            satellite_id, parameter,
        )
    return dict(row) if row else None


async def upsert_channel_calibration(
    satellite_id: str,
    parameter: str,
    state: str,
    ref_mean: float | None,
    ref_std: float | None,
    ref_sample_count: int,
) -> None:
    """Persist calibration state.  Overwrites previous state for the channel."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO channel_calibration
                (tenant_id, satellite_id, parameter, state, ref_mean, ref_std,
                 ref_sample_count, calibrated_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7,
                    CASE WHEN $4 = 'calibrated' THEN NOW() ELSE NULL END,
                    NOW())
            ON CONFLICT (tenant_id, satellite_id, parameter) DO UPDATE
                SET state            = EXCLUDED.state,
                    ref_mean         = EXCLUDED.ref_mean,
                    ref_std          = EXCLUDED.ref_std,
                    ref_sample_count = EXCLUDED.ref_sample_count,
                    calibrated_at    = EXCLUDED.calibrated_at,
                    updated_at       = NOW()
            """,
            get_tenant(), satellite_id, parameter, state, ref_mean, ref_std, ref_sample_count,
        )


async def get_all_calibrations(satellite_id: str) -> dict[str, dict]:
    """Load calibration for all channels of a satellite in one query.

    Called at startup to warm the in-memory calibration cache so the
    detectors don't need individual DB lookups on the first ingestion cycle.
    Returns: { parameter: { state, ref_mean, ref_std, ref_sample_count } }
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT parameter, state, ref_mean, ref_std, ref_sample_count
            FROM channel_calibration
            WHERE satellite_id = $1
            """,
            satellite_id,
        )
    return {r["parameter"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Detector accumulator state (CUSUM / EWMA — survive restarts)
# ---------------------------------------------------------------------------

async def get_detector_state(
    satellite_id: str, parameter: str, detector_name: str
) -> dict | None:
    """Load accumulator state for one (channel, detector) pair."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT state_data, last_updated_at
            FROM detector_state
            WHERE satellite_id = $1 AND parameter = $2 AND detector_name = $3
            """,
            satellite_id, parameter, detector_name,
        )
    return dict(row) if row else None


async def upsert_detector_state(
    satellite_id: str,
    parameter: str,
    detector_name: str,
    state_data: dict,
) -> None:
    """Persist accumulator state for one (channel, detector) pair."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO detector_state
                (tenant_id, satellite_id, parameter, detector_name, state_data, last_updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
            ON CONFLICT (tenant_id, satellite_id, parameter, detector_name) DO UPDATE
                SET state_data      = EXCLUDED.state_data,
                    last_updated_at = NOW()
            """,
            get_tenant(), satellite_id, parameter, detector_name, json.dumps(state_data),
        )


async def bulk_upsert_detector_states(
    states: list[dict[str, Any]],
) -> None:
    """Batch-persist accumulator states in one round-trip.

    Expected shape of each dict:
        { satellite_id, parameter, detector_name, state_data: dict }

    Called during the flush cycle (every N detections) and at shutdown
    to persist all in-memory accumulators.
    """
    if not states:
        return

    tenant = get_tenant()
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO detector_state
                (tenant_id, satellite_id, parameter, detector_name, state_data, last_updated_at)
            SELECT t, s, p, d, data::jsonb, NOW()
            FROM UNNEST($1::text[], $2::text[], $3::text[], $4::text[], $5::text[])
                AS u(t, s, p, d, data)
            ON CONFLICT (tenant_id, satellite_id, parameter, detector_name) DO UPDATE
                SET state_data      = EXCLUDED.state_data,
                    last_updated_at = NOW()
            """,
            [tenant]                        * len(states),
            [s["satellite_id"]              for s in states],
            [s["parameter"]                 for s in states],
            [s["detector_name"]             for s in states],
            [json.dumps(s["state_data"])    for s in states],
        )


async def get_all_detector_states(
    satellite_id: str, detector_name: str
) -> dict[str, dict]:
    """Load all accumulator states for one detector across all channels.

    Called at startup to warm the in-memory state so detection can resume
    seamlessly after a restart.
    Returns: { parameter: state_data_dict }
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT parameter, state_data
            FROM detector_state
            WHERE satellite_id = $1 AND detector_name = $2
            """,
            satellite_id, detector_name,
        )
    return {r["parameter"]: dict(r["state_data"]) for r in rows}


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

async def insert_anomaly(anomaly: Anomaly) -> str:
    """Insert one anomaly record. Returns the anomaly ID."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO anomalies
                (tenant_id, id, satellite_id, timestamp, subsystem, parameter, value,
                 severity, confidence, detectors_triggered, explanation,
                 root_cause_group, contributing_params, stl_residual)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14)
            ON CONFLICT (tenant_id, satellite_id, parameter, timestamp) DO NOTHING
            """,
            get_tenant(),
            anomaly.id,
            anomaly.satellite_id,
            anomaly.timestamp,
            anomaly.subsystem,
            anomaly.parameter,
            anomaly.value,
            anomaly.severity.value,
            anomaly.confidence,
            list(anomaly.detectors_triggered),
            anomaly.explanation,
            anomaly.root_cause_group,
            json.dumps(anomaly.contributing_params),
            getattr(anomaly, "stl_residual", None),
        )
    return anomaly.id


async def get_anomalies(
    satellite_id: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    include_false_positives: bool = False,
    ml_only: bool | None = None,
) -> list[dict]:
    """Query anomalies with optional filters and cursor-based pagination.

    Pagination model (newest-first):
      - Initial load: no cursor → returns newest `limit` rows.
      - Infinite scroll older: before=<oldest_loaded_timestamp> → next page.
      - Poll for new: since=<newest_loaded_timestamp> → any rows added since.
      - Date range filter: date_from / date_to (inclusive).
    """
    conditions: list[str] = []
    params: list[Any] = []

    if not include_false_positives:
        conditions.append("false_positive = FALSE")

    if satellite_id is not None:
        params.append(satellite_id)
        conditions.append(f"satellite_id = ${len(params)}")

    if severity is not None:
        params.append(severity)
        conditions.append(f"severity = ${len(params)}")

    # `since` = poll for NEW rows (timestamp >= boundary)
    if since is not None:
        params.append(since)
        conditions.append(f"timestamp >= ${len(params)}")

    # `before` = infinite-scroll cursor for OLDER rows (timestamp < boundary)
    if before is not None:
        params.append(before)
        conditions.append(f"timestamp < ${len(params)}")

    # Explicit date-range filter (from dashboard date pickers)
    if date_from is not None:
        params.append(date_from)
        conditions.append(f"timestamp >= ${len(params)}")

    if date_to is not None:
        params.append(date_to)
        conditions.append(f"timestamp <= ${len(params)}")

    # ml_only: True → only ML-detector-only detections (lstm/tcn, no stats)
    if ml_only is True:
        conditions.append(
            "(detectors_triggered <@ ARRAY['lstm','tcn']::TEXT[] "
            "AND array_length(detectors_triggered, 1) > 0)"
        )
    elif ml_only is False:
        conditions.append(
            "NOT (detectors_triggered <@ ARRAY['lstm','tcn']::TEXT[] "
            "AND array_length(detectors_triggered, 1) > 0)"
        )

    params.append(min(limit, 500))
    limit_ph = f"${len(params)}"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT id, satellite_id, timestamp, subsystem, parameter, value, "  # nosec B608 (column names are literal; values bound via ?)
        f"severity, confidence, detectors_triggered, explanation, "
        f"root_cause_group, contributing_params, incident_id, "
        f"reviewed, false_positive, stl_residual, created_at "
        f"FROM anomalies {where} "
        f"ORDER BY timestamp DESC LIMIT {limit_ph}"
    )

    async with acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def get_anomaly_by_id(anomaly_id: str) -> dict | None:
    """Full detail for one anomaly."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM anomalies WHERE id = $1",
            anomaly_id,
        )
    return dict(row) if row else None


async def get_anomaly_stats(satellite_id: str) -> dict:
    """Aggregate counts for the dashboard summary panel.

    Single query with conditional aggregation — avoids 4 separate round-trips.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)
                    FILTER (WHERE false_positive = FALSE)
                    AS total,
                COUNT(*)
                    FILTER (WHERE severity = 'critical'
                              AND reviewed = FALSE
                              AND false_positive = FALSE)
                    AS open_critical,
                COUNT(*)
                    FILTER (WHERE severity = 'warning'
                              AND reviewed = FALSE
                              AND false_positive = FALSE)
                    AS open_warning,
                COUNT(*)
                    FILTER (WHERE severity = 'watch'
                              AND reviewed = FALSE
                              AND false_positive = FALSE)
                    AS open_watch,
                COUNT(*)
                    FILTER (WHERE timestamp > NOW() - INTERVAL '24 hours'
                              AND false_positive = FALSE)
                    AS last_24h,
                COUNT(*)
                    FILTER (WHERE timestamp > NOW() - INTERVAL '1 hour'
                              AND false_positive = FALSE)
                    AS last_hour,
                MAX(confidence)
                    FILTER (WHERE false_positive = FALSE)
                    AS peak_confidence,
                MAX(timestamp)
                    FILTER (WHERE false_positive = FALSE)
                    AS latest_at
            FROM anomalies
            WHERE satellite_id = $1
            """,
            satellite_id,
        )
    return dict(row) if row else {}


async def mark_false_positive(anomaly_id: str) -> bool:
    """Flag an anomaly as a false positive. Returns True if found."""
    return await update_anomaly_review(anomaly_id, false_positive=True)


async def update_anomaly_review(anomaly_id: str, *, false_positive: bool) -> bool:
    """Set reviewed=True and false_positive verdict on an anomaly.

    Returns True if the anomaly was found and updated, False otherwise.
    """
    async with acquire() as conn:
        result = await conn.execute(
            """
            UPDATE anomalies
               SET reviewed = TRUE, false_positive = $2
             WHERE id = $1
            """,
            anomaly_id,
            false_positive,
        )
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

async def open_incident(
    satellite_id: str,
    subsystem: str,
    severity: str,
    title: str,
    first_anomaly_at: datetime,
) -> str:
    """Create a new incident. Returns the UUID as a string."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO incidents
                (tenant_id, satellite_id, subsystem, severity, title,
                 first_anomaly_at, last_anomaly_at)
            VALUES ($1, $2, $3, $4, $5, $6, $6)
            RETURNING id::text
            """,
            get_tenant(), satellite_id, subsystem, severity, title, first_anomaly_at,
        )
    return row["id"]


async def get_open_incident(
    satellite_id: str,
    subsystem: str,
    window_minutes: int = 10,
) -> dict | None:
    """Find an open incident for a subsystem within the correlation window.

    Used to group anomalies that arrive close together in time into one
    incident rather than generating N separate incidents.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, severity, anomaly_count, last_anomaly_at
            FROM incidents
            WHERE satellite_id = $1
              AND subsystem     = $2
              AND status        = 'open'
              AND last_anomaly_at > NOW() - ($3 * INTERVAL '1 minute')
            ORDER BY last_anomaly_at DESC
            LIMIT 1
            """,
            satellite_id, subsystem, window_minutes,
        )
    return dict(row) if row else None


async def update_incident_stats(
    incident_id: str,
    severity: str,
    last_anomaly_at: datetime,
) -> None:
    """Bump anomaly count and update severity + last-seen timestamp."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE incidents
               SET anomaly_count  = anomaly_count + 1,
                   last_anomaly_at = $2,
                   severity = CASE
                       WHEN $3 = 'critical' THEN 'critical'
                       WHEN $3 = 'warning' AND severity != 'critical' THEN 'warning'
                       ELSE severity
                   END
             WHERE id = $1::uuid
            """,
            incident_id, last_anomaly_at, severity,
        )


async def link_anomaly_to_incident(anomaly_id: str, incident_id: str) -> None:
    """Associate an anomaly with an incident."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE anomalies SET incident_id = $1::uuid WHERE id = $2",
            incident_id, anomaly_id,
        )


async def upsert_incident(incident: "Incident") -> None:  # type: ignore[name-defined]
    """Insert or update an incident from IncidentGrouper state.

    Uses the incident's hex id as the primary key.  On conflict, updates all
    mutable fields (severity, confidence, channels, last_anomaly_at, etc.).
    Called after every anomaly that belongs to the incident.
    """
    from aria.dsremo.core.models import Incident  # noqa: PLC0415
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO incidents
                (id, tenant_id, satellite_id, severity, status,
                 confidence, channels, root_cause_summary,
                 anomaly_count, first_anomaly_at, last_anomaly_at, closed_at)
            VALUES
                ($1::uuid, $2, $3, $4, $5,
                 $6, $7, $8,
                 $9, $10, $11, $12)
            ON CONFLICT (id) DO UPDATE SET
                severity         = EXCLUDED.severity,
                status           = EXCLUDED.status,
                confidence       = EXCLUDED.confidence,
                channels         = EXCLUDED.channels,
                root_cause_summary = EXCLUDED.root_cause_summary,
                anomaly_count    = EXCLUDED.anomaly_count,
                last_anomaly_at  = EXCLUDED.last_anomaly_at,
                closed_at        = EXCLUDED.closed_at
            """,
            incident.id,
            get_tenant(),
            incident.satellite_id,
            incident.severity.value,
            incident.status,
            incident.confidence,
            list(incident.channels),
            incident.root_cause_summary,
            incident.anomaly_count,
            incident.first_anomaly_at,
            incident.last_anomaly_at,
            incident.closed_at,
        )


async def get_incidents_v2(
    satellite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query incidents with confidence + channels columns (Sprint 17+)."""
    conditions: list[str] = []
    params: list = []

    if satellite_id is not None:
        params.append(satellite_id)
        conditions.append(f"satellite_id = ${len(params)}")

    if status is not None:
        params.append(status)
        conditions.append(f"status = ${len(params)}")

    params.append(min(limit, 500))
    limit_ph = f"${len(params)}"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT id::text, satellite_id, severity, status, confidence, channels, "  # nosec B608 (column names are literal; values bound via ?)
        f"root_cause_summary, anomaly_count, first_anomaly_at, last_anomaly_at, "
        f"closed_at, created_at "
        f"FROM incidents {where} "
        f"ORDER BY last_anomaly_at DESC LIMIT {limit_ph}"
    )

    async with acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def update_incident_status(incident_id: str, status: str) -> bool:
    """Set incident status (resolved / false_positive). Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            """
            UPDATE incidents
               SET status    = $2,
                   closed_at = CASE WHEN $2 IN ('resolved','false_positive')
                                    THEN NOW() ELSE closed_at END
             WHERE id = $1::uuid
            """,
            incident_id, status,
        )
    return result == "UPDATE 1"


async def get_subsystem_health(satellite_id: str) -> list[dict]:
    """Return health score per subsystem for a satellite (Sprint 18).

    Health = 1.0 − (channels_with_open_incidents / total_channels_in_subsystem)
    Uses channel_registry.subsystem for grouping + incidents.channels[] for
    the anomalous channel set.  Returns [] if satellite has no registered channels.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH open_chans AS (
                SELECT UNNEST(channels) AS parameter
                  FROM incidents
                 WHERE satellite_id = $1
                   AND status = 'open'
            ),
            chan_sub AS (
                SELECT parameter, COALESCE(subsystem, 'unknown') AS subsystem
                  FROM channel_registry
                 WHERE satellite_id = $1
            ),
            totals AS (
                SELECT subsystem, COUNT(*) AS total
                  FROM chan_sub
                 GROUP BY subsystem
            ),
            anomalous AS (
                SELECT cs.subsystem, COUNT(DISTINCT oc.parameter) AS bad
                  FROM open_chans oc
                  JOIN chan_sub cs USING (parameter)
                 GROUP BY cs.subsystem
            )
            SELECT t.subsystem,
                   t.total::INT                                              AS total_channels,
                   COALESCE(a.bad, 0)::INT                                  AS anomalous_channels,
                   1.0 - COALESCE(a.bad, 0)::REAL / t.total::REAL          AS health
              FROM totals t
              LEFT JOIN anomalous a USING (subsystem)
             ORDER BY health ASC
            """,
            satellite_id,
        )
    return [dict(r) for r in rows]


async def close_incident(incident_id: str) -> None:
    """Mark an incident as closed."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE incidents
               SET status    = 'closed',
                   closed_at = NOW()
             WHERE id = $1::uuid
            """,
            incident_id,
        )


async def get_incidents(
    satellite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query incidents with optional satellite + status filter."""
    conditions: list[str] = []
    params: list[Any] = []

    if satellite_id is not None:
        params.append(satellite_id)
        conditions.append(f"satellite_id = ${len(params)}")

    if status is not None:
        params.append(status)
        conditions.append(f"status = ${len(params)}")

    params.append(min(limit, 500))
    limit_ph = f"${len(params)}"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT id::text, satellite_id, subsystem, severity, status, title, "  # nosec B608 (column names are literal; values bound via ?)
        f"root_cause_summary, anomaly_count, first_anomaly_at, last_anomaly_at, "
        f"acknowledged_at, closed_at, created_at "
        f"FROM incidents {where} "
        f"ORDER BY last_anomaly_at DESC LIMIT {limit_ph}"
    )

    async with acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

async def insert_alert(anomaly: "Anomaly") -> str:
    """Persist a dispatched alert. Returns the alert id.

    BUG FIX: Previously alerts were dispatched (webhook/email) but never stored.
    This ensures the alerts table is populated for the history endpoint.
    """
    alert_id = str(_uuid.uuid4())
    title = f"[{anomaly.severity.value.upper()}] {anomaly.satellite_id} — {anomaly.parameter}"
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO alerts (id, tenant_id, anomaly_id, satellite_id, severity, "
            "title, message, dispatched_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            alert_id, get_tenant(), anomaly.id, anomaly.satellite_id,
            anomaly.severity.value, title, anomaly.explanation,
        )
    return alert_id


async def get_alerts(
    satellite_id: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query alert dispatch records, joined with anomaly details."""
    conditions: list[str] = []
    params: list[Any] = []

    if satellite_id is not None:
        params.append(satellite_id)
        conditions.append(f"al.satellite_id = ${len(params)}")

    if severity is not None:
        params.append(severity)
        conditions.append(f"al.severity = ${len(params)}")

    if since is not None:
        params.append(since)
        conditions.append(f"al.dispatched_at >= ${len(params)}")

    if acknowledged is not None:
        params.append(acknowledged)
        conditions.append(f"al.acknowledged = ${len(params)}")

    params.append(min(limit, 1000))
    limit_ph = f"${len(params)}"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = (
        f"SELECT al.id, al.satellite_id, al.severity, al.acknowledged, "  # nosec B608 (column names are literal; values bound via ?)
        f"al.dispatched_at, al.title, al.message, "
        f"an.subsystem, an.parameter, an.value, an.confidence, "
        f"an.timestamp AS anomaly_timestamp, an.explanation "
        f"FROM alerts al "
        f"LEFT JOIN anomalies an ON an.id = al.anomaly_id "
        f"{where} "
        f"ORDER BY al.dispatched_at DESC LIMIT {limit_ph}"
    )

    async with acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def acknowledge_alert(alert_id: str) -> bool:
    """Mark alert as acknowledged. Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE alerts SET acknowledged = TRUE WHERE id = $1 AND acknowledged = FALSE",
            alert_id,
        )
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# Alert configs (per-tenant delivery settings)
# ---------------------------------------------------------------------------

async def upsert_alert_config(
    tenant_id: str,
    *,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    email_to: list[str] | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    min_severity: str | None = None,
    dedup_window_s: int | None = None,
    escalation_delay_s: int | None = None,
    enabled: bool | None = None,
) -> dict:
    """Insert or partial-update per-tenant alert config.

    COALESCE pattern: only non-None fields overwrite existing values.
    Omitted fields retain their current DB value.
    """
    _FIELDS = (
        "webhook_url", "webhook_secret", "email_to", "smtp_host", "smtp_port",
        "smtp_user", "smtp_password", "min_severity", "dedup_window_s",
        "escalation_delay_s", "enabled",
    )
    new_vals = (
        webhook_url, webhook_secret, email_to, smtp_host, smtp_port,
        smtp_user, smtp_password, min_severity, dedup_window_s,
        escalation_delay_s, enabled,
    )

    # Build SET clause with COALESCE for partial update.
    # Qualify the fallback with the table name to avoid
    # "ambiguous column reference" inside ON CONFLICT DO UPDATE SET.
    set_parts = [
        f"{f} = COALESCE(${i + 2}, alert_configs.{f})"
        for i, f in enumerate(_FIELDS)
    ]
    set_parts.append(f"updated_at = NOW()")

    # INSERT defaults: COALESCE NOT NULL columns with their schema defaults so
    # that an INSERT with all-NULL optional fields doesn't violate the constraint.
    # (Explicitly listing a column with NULL bypasses the DB DEFAULT expression.)
    _NOT_NULL_DEFAULTS: dict[str, str] = {
        "min_severity":       "'warning'",
        "dedup_window_s":     "300",
        "escalation_delay_s": "600",
        "enabled":            "TRUE",
    }
    insert_phs: list[str] = []
    for i, f in enumerate(_FIELDS):
        ph = f"${i + 2}"
        if f in _NOT_NULL_DEFAULTS:
            ph = f"COALESCE({ph}, {_NOT_NULL_DEFAULTS[f]})"
        insert_phs.append(ph)
    insert_cols = ", ".join(["tenant_id"] + list(_FIELDS))
    insert_placeholders = ", ".join(["$1"] + insert_phs)

    sql = (
        f"INSERT INTO alert_configs ({insert_cols}) "  # nosec B608 (column names are literal; values bound via ?)
        f"VALUES ({insert_placeholders}) "
        f"ON CONFLICT (tenant_id) DO UPDATE SET "
        + ", ".join(set_parts) +
        " RETURNING *"
    )

    async with acquire() as conn:
        row = await conn.fetchrow(sql, tenant_id, *new_vals)
    return dict(row)


async def get_alert_config(tenant_id: str | None = None) -> dict | None:
    """Return alert_configs row for the given tenant, or None if not set.

    Uses RLS-scoped acquire() — tenant_id defaults to current tenant context.
    Pass tenant_id explicitly only when bypassing RLS (e.g. startup load).
    """
    if tenant_id is not None:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM alert_configs WHERE tenant_id = $1", tenant_id
            )
    else:
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM alert_configs WHERE tenant_id = $1", get_tenant()
            )
    return dict(row) if row else None


async def delete_alert_config(tenant_id: str) -> bool:
    """Remove alert config for a tenant. Returns True if row existed."""
    async with acquire() as conn:
        result = await conn.execute(
            "DELETE FROM alert_configs WHERE tenant_id = $1", tenant_id
        )
    return result == "DELETE 1"


async def load_all_alert_configs() -> list[dict]:
    """Load all alert_config rows without RLS filter.

    Uses direct pool connection (bypasses RLS) — same pattern as load_api_key_map().
    Called at startup to populate AlertService class-level config cache.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM alert_configs WHERE enabled = TRUE")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

async def load_api_key_map() -> dict[str, str]:
    """Load all active api_key hashes → tenant_id for the in-memory auth cache.

    Uses the raw pool directly (not acquire()) so it bypasses RLS.
    api_keys has ENABLE-only RLS — the table owner (dsremo user) sees all
    rows across all tenants without needing app.tenant_id set.

    Called once at server startup by the lifespan function in app.py.
    The result is passed to ApiKeyMiddleware which uses it for every request.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key_hash, tenant_id FROM api_keys WHERE active = TRUE"
        )
    return {r["key_hash"]: r["tenant_id"] for r in rows}


async def store_api_key(key_hash: str, label: str) -> None:
    """Persist a hashed API key. Plain-text key is never stored."""
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO api_keys (tenant_id, key_hash, label) VALUES ($1, $2, $3) "
            "ON CONFLICT (key_hash) DO NOTHING",
            get_tenant(), key_hash, label,
        )


async def verify_api_key_exists(key_hash: str) -> bool:
    """Return True if the hash matches an active key."""
    async with acquire() as conn:
        result = await conn.fetchval(
            "SELECT active FROM api_keys WHERE key_hash = $1",
            key_hash,
        )
    return result is True


async def touch_api_key(key_hash: str) -> None:
    """Update last_used_at for audit trail. Best-effort — no failure on miss."""
    try:
        async with acquire() as conn:
            await conn.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = $1",
                key_hash,
            )
    except Exception as exc:
        logger.warning("api_key_touch_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Rollup queries (telemetry_hourly cagg or raw fallback)
# ---------------------------------------------------------------------------

async def get_hourly_stats(
    satellite_id: str,
    parameter: str,
    since: datetime,
) -> list[dict]:
    """Per-hour aggregates for dashboard trend charts.

    Uses the telemetry_hourly continuous aggregate when TimescaleDB is
    available; falls back to a plain GROUP BY on raw telemetry otherwise.
    Both return the same columns: hour, avg_value, min_value, max_value,
    stddev_value, sample_count.
    """
    async with acquire() as conn:
        # Check if the cagg exists.
        has_cagg: bool = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews
                WHERE matviewname = 'telemetry_hourly'
            )
            """
        )

        if has_cagg:
            rows = await conn.fetch(
                """
                SELECT hour, avg_value, min_value, max_value,
                       stddev_value, sample_count
                FROM telemetry_hourly
                WHERE satellite_id = $1
                  AND parameter    = $2
                  AND hour         >= $3
                ORDER BY hour ASC
                """,
                satellite_id, parameter, since,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    date_trunc('hour', timestamp)  AS hour,
                    AVG(value)    AS avg_value,
                    MIN(value)    AS min_value,
                    MAX(value)    AS max_value,
                    STDDEV(value) AS stddev_value,
                    COUNT(*)      AS sample_count
                FROM telemetry
                WHERE satellite_id = $1
                  AND parameter    = $2
                  AND timestamp    >= $3
                GROUP BY date_trunc('hour', timestamp)
                ORDER BY hour ASC
                """,
                satellite_id, parameter, since,
            )

    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def get_user_by_google_id(google_id: str) -> dict | None:
    """Look up a user by Google subject ID — bypasses RLS (no tenant context yet).

    Used at OAuth callback time before we know which tenant the user belongs to.
    Returns full row including tenant_id so the caller can set tenant context.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Use the security-definer function (v20 migration) so the lookup runs
        # without tenant context — google_id is globally unique across all tenants.
        row = await conn.fetchrow(
            "SELECT * FROM find_user_by_google_id($1)",
            google_id,
        )
    return dict(row) if row else None


async def upsert_google_user(
    google_id: str,
    email: str,
    display_name: str,
    avatar_url: str,
    tenant_id: str,
    role: str = "admin",
    plan: str = "free",
) -> dict:
    """Insert or update a Google OAuth user — bypasses RLS.

    On first Google login: creates the user row.
    On subsequent logins: refreshes display_name and avatar_url.
    Returns the user row including tenant_id and plan.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Set tenant context so the FORCE RLS policy allows the INSERT/UPDATE.
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, false)", tenant_id
        )
        row = await conn.fetchrow(
            """
            INSERT INTO users (tenant_id, email, google_id, display_name, avatar_url, role, plan)
            VALUES ($1, $2, $3, $4, $5, $6::user_role, $7)
            ON CONFLICT (google_id) WHERE google_id IS NOT NULL DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    avatar_url   = EXCLUDED.avatar_url,
                    last_login   = NOW()
            RETURNING id::text, tenant_id, email, role::text, active,
                      COALESCE(display_name, '') AS display_name,
                      COALESCE(avatar_url, '')   AS avatar_url,
                      COALESCE(plan, 'free')     AS plan
            """,
            tenant_id, email, google_id, display_name, avatar_url, role, plan,
        )
    return dict(row)


async def create_tenant(tenant_id: str, name: str, plan: str = "free") -> None:
    """Create a new tenant — used when a Google user signs up for the first time."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tenants (id, name, plan)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO NOTHING
            """,
            tenant_id, name, plan,
        )


async def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email within the current tenant (RLS-scoped)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, tenant_id, email, password_hash, role::text, active,
                   created_at, last_login,
                   COALESCE(display_name, '') AS display_name,
                   COALESCE(phone, '') AS phone
            FROM users
            WHERE email = $1 AND active = TRUE
            """,
            email,
        )
    return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    """Look up a user by UUID within the current tenant (RLS-scoped)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, tenant_id, email, role::text, active, created_at, last_login,
                   COALESCE(display_name, '') AS display_name,
                   COALESCE(phone, '') AS phone
            FROM users
            WHERE id = $1::uuid
            """,
            user_id,
        )
    return dict(row) if row else None


async def create_user(
    email: str,
    password_hash: str,
    role: str,
    display_name: str = "",
    phone: str = "",
) -> dict:
    """Insert a new user. tenant_id comes from the current ContextVar.

    Returns the new user row (id, email, role, tenant_id, created_at).
    Raises asyncpg.UniqueViolationError if email already exists in this tenant.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (tenant_id, email, password_hash, role, display_name, phone)
            VALUES ($1, $2, $3, $4::user_role, $5, $6)
            RETURNING id::text, tenant_id, email, role::text, active, created_at,
                      COALESCE(display_name, '') AS display_name,
                      COALESCE(phone, '') AS phone
            """,
            get_tenant(), email, password_hash, role, display_name, phone,
        )
    return dict(row)


async def update_last_login(user_id: str) -> None:
    """Record the current time as last_login for the given user."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE id = $1::uuid",
            user_id,
        )


async def list_users(limit: int = 100) -> list[dict]:
    """List all users within the current tenant (RLS-scoped)."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text, email, role::text, active, created_at, last_login,
                   COALESCE(display_name, '') AS display_name,
                   COALESCE(phone, '') AS phone
            FROM users
            ORDER BY created_at DESC
            LIMIT $1
            """,
            min(limit, 1000),
        )
    return [dict(r) for r in rows]


async def deactivate_user(email: str) -> bool:
    """Deactivate a user by email within the current tenant. Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET active = FALSE WHERE email = $1 AND active = TRUE",
            email,
        )
    return result == "UPDATE 1"


async def deactivate_user_by_id(user_id: str) -> bool:
    """Deactivate a user by UUID within the current tenant. Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET active = FALSE WHERE id = $1::uuid AND active = TRUE",
            user_id,
        )
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# Refresh Tokens
# ---------------------------------------------------------------------------

async def store_refresh_token(
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Persist a hashed refresh token. Plain token is never stored."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO refresh_tokens (user_id, tenant_id, token_hash, expires_at)
            VALUES ($1::uuid, $2, $3, $4)
            ON CONFLICT (token_hash) DO NOTHING
            """,
            user_id, get_tenant(), token_hash, expires_at,
        )


async def get_refresh_token(token_hash: str) -> dict | None:
    """Load a refresh token row by hash (RLS-scoped to current tenant)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, user_id::text, tenant_id, expires_at, revoked
            FROM refresh_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )
    return dict(row) if row else None


async def revoke_refresh_token(token_hash: str) -> None:
    """Mark a specific refresh token as revoked (logout)."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
            token_hash,
        )


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (password reset, account deactivation)."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1::uuid",
            user_id,
        )


# ---------------------------------------------------------------------------
# User management (RLS-scoped — acquire())
# ---------------------------------------------------------------------------

async def update_user_role(user_id: str, new_role: str) -> bool:
    """Change the role of a user within the current tenant. Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET role = $1::user_role WHERE id = $2::uuid AND active = TRUE",
            new_role, user_id,
        )
    return result == "UPDATE 1"


async def reactivate_user(user_id: str) -> bool:
    """Re-enable a previously deactivated user. Returns True if found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET active = TRUE WHERE id = $1::uuid AND active = FALSE",
            user_id,
        )
    return result == "UPDATE 1"


async def update_user_password(user_id: str, new_hash: str) -> bool:
    """Replace the password hash for a user. Returns True if user was found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2::uuid",
            new_hash, user_id,
        )
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# API key management (RLS-scoped — acquire())
# ---------------------------------------------------------------------------

async def list_api_keys_for_tenant() -> list[dict]:
    """List all API keys for the current tenant (hash_prefix, not full hash)."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT label,
                   SUBSTRING(key_hash, 1, 16) AS hash_prefix,
                   created_at,
                   last_used_at,
                   active
            FROM api_keys
            ORDER BY created_at DESC
            """,
        )
    return [dict(r) for r in rows]


async def revoke_api_key_by_prefix(prefix: str) -> bool:
    """Deactivate keys whose hash starts with the given prefix. Returns True if any found."""
    async with acquire() as conn:
        result = await conn.execute(
            "UPDATE api_keys SET active = FALSE WHERE key_hash LIKE $1 || '%' AND active = TRUE",
            prefix,
        )
    return result != "UPDATE 0"


# ---------------------------------------------------------------------------
# Tenant CRUD (pool direct — tenants has no RLS)
# ---------------------------------------------------------------------------

async def list_tenants() -> list[dict]:
    """List all tenants (dsremo admin access — bypasses RLS via direct pool)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, plan, active, created_at FROM tenants ORDER BY created_at ASC"
        )
    return [dict(r) for r in rows]


async def get_tenant_by_id(tenant_id: str) -> dict | None:
    """Fetch a single tenant by ID (direct pool — no RLS on tenants table)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, plan, active, created_at, settings FROM tenants WHERE id = $1",
            tenant_id,
        )
    return dict(row) if row else None


async def create_tenant(tenant_id: str, name: str, plan: str = "free") -> dict:
    """Insert a new tenant. Raises asyncpg.UniqueViolationError on duplicate id."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tenants (id, name, plan)
            VALUES ($1, $2, $3)
            RETURNING id, name, plan, active, created_at
            """,
            tenant_id, name, plan,
        )
    return dict(row)


async def update_tenant(
    tenant_id: str,
    name: str | None = None,
    active: bool | None = None,
) -> bool:
    """Patch a tenant's name and/or active flag. Returns True if found."""
    updates: list[str] = []
    params: list = []

    if name is not None:
        params.append(name)
        updates.append(f"name = ${len(params)}")
    if active is not None:
        params.append(active)
        updates.append(f"active = ${len(params)}")

    if not updates:
        return False

    params.append(tenant_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            f"UPDATE tenants SET {', '.join(updates)} WHERE id = ${len(params)}",  # nosec B608 (column names are literal; values bound via ?)
            *params,
        )
    return result == "UPDATE 1"


# ---------------------------------------------------------------------------
# Dsremo users (pool direct — no RLS on dsremo_users)
# ---------------------------------------------------------------------------

async def get_dsremo_user_by_email(email: str) -> dict | None:
    """Look up a dsremo user by email (direct pool, no RLS)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text, email, password_hash, role::text, active, created_at, last_login
            FROM dsremo_users
            WHERE email = $1
            """,
            email,
        )
    return dict(row) if row else None


async def create_dsremo_user(email: str, password_hash: str, role: str) -> dict:
    """Insert a new Dsremo internal user.

    Raises asyncpg.UniqueViolationError if email already exists.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dsremo_users (email, password_hash, role)
            VALUES ($1, $2, $3::dsremo_role)
            RETURNING id::text, email, role::text, active, created_at
            """,
            email, password_hash, role,
        )
    return dict(row)


async def update_dsremo_last_login(user_id: str) -> None:
    """Record the current time as last_login for a dsremo user."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE dsremo_users SET last_login = NOW() WHERE id = $1::uuid",
            user_id,
        )


async def list_dsremo_users() -> list[dict]:
    """List all dsremo internal users (direct pool, no RLS)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id::text, email, role::text, active, created_at, last_login "
            "FROM dsremo_users ORDER BY created_at ASC"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Dsremo refresh tokens (pool direct — no RLS)
# ---------------------------------------------------------------------------

async def store_dsremo_refresh_token(
    user_id: str,
    token_hash: str,
    expires_at: datetime,
) -> None:
    """Persist a hashed dsremo refresh token."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO dsremo_refresh_tokens (user_id, token_hash, expires_at)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT (token_hash) DO NOTHING
            """,
            user_id, token_hash, expires_at,
        )


async def get_dsremo_refresh_token(token_hash: str) -> dict | None:
    """Look up a dsremo refresh token by hash (with user info joined)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT srt.id::text, srt.user_id::text, srt.expires_at, srt.revoked,
                   su.role::text AS role, su.email, su.active
            FROM dsremo_refresh_tokens srt
            JOIN dsremo_users su ON su.id = srt.user_id
            WHERE srt.token_hash = $1
            """,
            token_hash,
        )
    return dict(row) if row else None


async def revoke_dsremo_refresh_token(token_hash: str) -> None:
    """Mark a dsremo refresh token as revoked."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE dsremo_refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
            token_hash,
        )


async def revoke_all_dsremo_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a dsremo user."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE dsremo_refresh_tokens SET revoked = TRUE WHERE user_id = $1::uuid",
            user_id,
        )


# ── Suppression persistence (P1-H) ──────────────────────────────────────────

async def upsert_suppression(
    tenant_id: str, satellite_id: str, parameter: str,
    until_epoch: float, reason: str = "",
) -> None:
    """Persist a suppression window to DB (survives server restarts)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO suppressions (tenant_id, satellite_id, parameter, until_epoch, reason)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (tenant_id, satellite_id, parameter)
            DO UPDATE SET until_epoch = $4, reason = $5
            """,
            tenant_id, satellite_id, parameter, until_epoch, reason,
        )


async def delete_suppression(
    tenant_id: str, satellite_id: str, parameter: str,
) -> bool:
    """Remove a suppression window. Returns True if one existed."""
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM suppressions WHERE tenant_id = $1 AND satellite_id = $2 AND parameter = $3",
            tenant_id, satellite_id, parameter,
        )
        return result.split()[-1] != "0"


async def load_active_suppressions(tenant_id: str | None = None) -> list[dict]:
    """Load all non-expired suppressions from DB. Called at startup."""
    import time  # noqa: PLC0415
    pool = get_pool()
    now = time.time()
    async with pool.acquire() as conn:
        if tenant_id:
            rows = await conn.fetch(
                "SELECT tenant_id, satellite_id, parameter, until_epoch, reason "
                "FROM suppressions WHERE tenant_id = $1 AND until_epoch > $2",
                tenant_id, now,
            )
        else:
            rows = await conn.fetch(
                "SELECT tenant_id, satellite_id, parameter, until_epoch, reason "
                "FROM suppressions WHERE until_epoch > $1",
                now,
            )
        return [dict(r) for r in rows]


# ── Detection audit trail (P1-D) ────────────────────────────────────────────

async def insert_detection_audit(
    satellite_id: str,
    parameter: str,
    timestamp: "datetime",
    detector_scores: dict,
    ensemble_confidence: float,
    severity: str,
    calibration_state: dict | None = None,
    stl_method: str = "",
) -> None:
    """Store an immutable audit record of a detection decision.

    Records individual detector scores, ensemble output, calibration state,
    and STL method at the time of detection for full decision traceability.
    """
    import json  # noqa: PLC0415
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO detection_audit
                (satellite_id, parameter, timestamp, detector_scores,
                 ensemble_confidence, severity, calibration_state, stl_method)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb, $8)
            """,
            satellite_id, parameter, timestamp,
            json.dumps(detector_scores),
            ensemble_confidence, severity,
            json.dumps(calibration_state) if calibration_state else None,
            stl_method,
        )


# ---------------------------------------------------------------------------
# Mission Config (V3-F4) — per-(tenant, satellite) launch + design life
# ---------------------------------------------------------------------------

async def upsert_mission_config(
    satellite_id: str,
    launch_epoch: float,
    design_life_days: int,
) -> dict:
    """Set launch_epoch + design_life_days for a satellite (V3-F4)."""
    if design_life_days <= 0:
        raise ValueError(f"design_life_days must be positive, got {design_life_days!r}")
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mission_config
                (tenant_id, satellite_id, launch_epoch, design_life_days, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (tenant_id, satellite_id) DO UPDATE
                SET launch_epoch     = EXCLUDED.launch_epoch,
                    design_life_days = EXCLUDED.design_life_days,
                    updated_at       = NOW()
            RETURNING satellite_id, launch_epoch, design_life_days, updated_at
            """,
            get_tenant(), satellite_id, launch_epoch, design_life_days,
        )
    return dict(row)


async def get_mission_config(satellite_id: str) -> dict | None:
    """Return {launch_epoch, design_life_days, updated_at} or None (V3-F4)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT satellite_id, launch_epoch, design_life_days, updated_at
            FROM mission_config
            WHERE tenant_id = $1 AND satellite_id = $2
            """,
            get_tenant(), satellite_id,
        )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Calibration hot (V3-B3) — hot sufficient-statistics table
# ---------------------------------------------------------------------------

async def upsert_calibration_hot(
    satellite_id: str,
    parameter: str,
    running_sum: float,
    running_sumsq: float,
    sample_count: int,
    last_value: float | None = None,
    last_value_epoch: float | None = None,
) -> dict:
    """Update the hot sufficient statistics for a channel (V3-B3).

    Writes only the typed DOUBLE PRECISION columns — no JSONB rewrite.
    Returns the updated row so callers can verify.
    """
    if sample_count < 0:
        raise ValueError(f"sample_count must be ≥ 0, got {sample_count!r}")
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO calibration_hot
                (tenant_id, satellite_id, parameter,
                 running_sum, running_sumsq, sample_count,
                 last_value, last_value_epoch, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (tenant_id, satellite_id, parameter) DO UPDATE
                SET running_sum      = EXCLUDED.running_sum,
                    running_sumsq    = EXCLUDED.running_sumsq,
                    sample_count     = EXCLUDED.sample_count,
                    last_value       = EXCLUDED.last_value,
                    last_value_epoch = EXCLUDED.last_value_epoch,
                    updated_at       = NOW()
            RETURNING satellite_id, parameter, running_sum, running_sumsq,
                      sample_count, last_value, last_value_epoch, updated_at
            """,
            get_tenant(), satellite_id, parameter,
            running_sum, running_sumsq, sample_count,
            last_value, last_value_epoch,
        )
    return dict(row)


async def get_calibration_hot(
    satellite_id: str,
    parameter: str,
) -> dict | None:
    """Read the hot sufficient-stats row (V3-B3). Returns None if absent."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT satellite_id, parameter, running_sum, running_sumsq,
                   sample_count, last_value, last_value_epoch, updated_at
            FROM calibration_hot
            WHERE tenant_id = $1 AND satellite_id = $2 AND parameter = $3
            """,
            get_tenant(), satellite_id, parameter,
        )
    return dict(row) if row else None


async def upsert_calibration_cold(
    satellite_id: str,
    parameter: str,
    cold_params: dict,
) -> None:
    """Update the cold JSONB sidecar on channel_calibration (V3-B3)."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE channel_calibration
               SET cold_params = $4::jsonb,
                   updated_at  = NOW()
             WHERE tenant_id = $1 AND satellite_id = $2 AND parameter = $3
            """,
            get_tenant(), satellite_id, parameter, json.dumps(cold_params),
        )


async def get_calibration_cold(
    satellite_id: str,
    parameter: str,
) -> dict | None:
    """Read the cold JSONB sidecar (V3-B3). Returns None if absent."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cold_params
            FROM channel_calibration
            WHERE tenant_id = $1 AND satellite_id = $2 AND parameter = $3
            """,
            get_tenant(), satellite_id, parameter,
        )
    if row is None or row["cold_params"] is None:
        return None
    raw = row["cold_params"]
    return raw if isinstance(raw, dict) else json.loads(raw)

