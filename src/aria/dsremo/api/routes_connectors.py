"""Connector routes — pull telemetry from YAMCS and InfluxDB on demand.

Each endpoint accepts connection parameters, fetches data from the external
source via the existing connector modules, bulk-inserts into the DB, and
runs anomaly detection — identical pipeline to the CSV upload + analyze flow.

These endpoints let operators trigger pulls from the dashboard UI or via
scheduled cron jobs (e.g. curl every 5 min for continuous near-real-time).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException

from aria.dsremo.api.dependencies import require_operator
from aria.dsremo.api.schemas import ConnectorResult, InfluxDBConnectRequest, YAMCSConnectRequest
from aria.dsremo.db import queries
from aria.dsremo.ingest.bulk_loader import run_bulk_detection

logger = structlog.get_logger()
connectors_router = APIRouter()


def _parse_iso_dt(s: str | None, field: str) -> datetime | None:
    """Parse an optional ISO-8601 string to a timezone-aware datetime.

    Raises HTTP 422 with a clear message on invalid input.
    Returns None when s is None (caller uses its own default).
    """
    if s is None:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field}: {s!r}. Use ISO-8601 format (e.g. 2024-01-01T00:00:00Z).",
        )


@connectors_router.post(
    "/connectors/yamcs",
    response_model=ConnectorResult,
    tags=["connectors"],
)
async def pull_yamcs(
    body: YAMCSConnectRequest,
    _user: dict = Depends(require_operator),
) -> ConnectorResult:
    """Pull archived telemetry from a YAMCS server and run anomaly detection.

    Fetches the specified parameters for the given time range, inserts them
    into the DB (idempotent — channels already at 50 K rows are skipped),
    then runs the full 6-detector pipeline over all stored channels.

    For continuous ingestion: call this endpoint periodically (e.g. via cron
    or a scheduled task) with overlapping time windows to catch new data.
    """
    from aria.dsremo.ingest.yamcs_connector import YAMCSConnector

    start_dt = _parse_iso_dt(body.start, "start time")
    stop_dt  = _parse_iso_dt(body.stop,  "stop time")

    connector = YAMCSConnector(
        base_url=body.yamcs_url,
        instance=body.instance,
        parameters=body.parameters,
        satellite_id=body.satellite_id,
        start=start_dt,
        stop=stop_dt,
        api_key=body.api_key,
        subsystem=body.subsystem,
    )

    t0 = time.monotonic()
    try:
        totals = await connector.bulk_load_to_db(resample_minutes=body.resample_minutes)
    except Exception as exc:
        logger.error("yamcs_pull_failed", satellite=body.satellite_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"YAMCS connection failed: {exc}",
        )

    results = await _detect(body.satellite_id)
    elapsed = round(time.monotonic() - t0, 2)

    return ConnectorResult(
        satellite_id=body.satellite_id,
        source=connector.source_name,
        channels_loaded=len(totals),
        total_rows_inserted=sum(totals.values()),
        total_anomalies=sum(len(a) for a in results.values()),
        elapsed_s=elapsed,
    )


@connectors_router.post(
    "/connectors/influxdb",
    response_model=ConnectorResult,
    tags=["connectors"],
)
async def pull_influxdb(
    body: InfluxDBConnectRequest,
    _user: dict = Depends(require_operator),
) -> ConnectorResult:
    """Pull telemetry from InfluxDB v2 and run anomaly detection.

    Runs a Flux query for each field, inserts results into the DB, then
    runs the full 6-detector pipeline over all stored channels.

    For continuous ingestion: schedule this endpoint to run every N minutes
    with `start='-Nm'` (e.g. `start='-10m'`) to process only new data.
    """
    from aria.dsremo.ingest.influxdb_connector import InfluxDBConnector

    connector = InfluxDBConnector(
        base_url=body.influxdb_url,
        org=body.org,
        bucket=body.bucket,
        token=body.token,
        measurement=body.measurement,
        fields=body.fields,
        satellite_id=body.satellite_id,
        start=body.start,
        stop=body.stop,
        subsystem=body.subsystem,
    )

    t0 = time.monotonic()
    try:
        totals = await connector.bulk_load_to_db(resample_minutes=body.resample_minutes)
    except Exception as exc:
        logger.error("influxdb_pull_failed", satellite=body.satellite_id, error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"InfluxDB connection failed: {exc}",
        )

    results = await _detect(body.satellite_id)
    elapsed = round(time.monotonic() - t0, 2)

    return ConnectorResult(
        satellite_id=body.satellite_id,
        source=connector.source_name,
        channels_loaded=len(totals),
        total_rows_inserted=sum(totals.values()),
        total_anomalies=sum(len(a) for a in results.values()),
        elapsed_s=elapsed,
    )


async def _detect(satellite_id: str) -> dict:
    """Run bulk detection over all channels for a satellite. Returns results dict."""
    channel_rows = await queries.get_channel_stats(satellite_id)
    if not channel_rows:
        return {}
    parameters = [r["parameter"] for r in channel_rows]
    subsystem_map = {r["parameter"]: r["subsystem"] for r in channel_rows}
    try:
        return await run_bulk_detection(satellite_id, parameters, subsystem_map)
    except Exception as exc:
        logger.error("connector_detection_failed", satellite=satellite_id, error=str(exc))
        return {}
