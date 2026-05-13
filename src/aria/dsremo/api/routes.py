"""API routes — the public contract of the Dsremo engine.

Every route is thin: validate → delegate → respond.
Business logic lives in domain modules, never in route handlers.
"""

from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from aria.dsremo.api.dependencies import get_current_user, require_admin, require_operator, require_viewer

from aria.dsremo import __version__
from aria.dsremo.api.schemas import (
    AnalyzeResult,
    AnomalyOut,
    CsvUploadResult,
    FeedbackIn,
    HealthResponse,
    IngestResponse,
    InjectRequest,
    SimulateRequest,
    TelemetryBatchIn,
    TelemetryIn,
    TelemetryOut,
)
from aria.dsremo.db import queries
from aria.dsremo.detection.detector import run_detection_cycle
from aria.dsremo.detection.sensor_health import apply_sensor_corrections
from aria.dsremo.core.plan_limits import get_limits
from aria.dsremo.ingest.adapter import AdapterError, adapt_batch, adapt_single

logger = structlog.get_logger()
router = APIRouter()


async def _trigger_detection(satellite_ids: "set[str] | str") -> None:
    """Run the detection pipeline for one or more satellites, swallowing errors.

    Extraction point: all ingest paths (batch, single, simulator) share this
    pattern — store telemetry, then trigger detection per unique satellite.
    Errors are logged as warnings rather than propagated so that ingest success
    is not gated on detection availability.
    """
    ids = {satellite_ids} if isinstance(satellite_ids, str) else satellite_ids
    for sat_id in ids:
        try:
            await run_detection_cycle(sat_id)
        except Exception as exc:
            logger.warning("detection_cycle_error", satellite=sat_id, error=str(exc))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", tags=["system"])
async def get_stats(_user: dict = Depends(get_current_user)) -> dict:
    """Aggregate telemetry and anomaly counts for the dashboard."""
    stats = await queries.get_telemetry_stats()
    stats["total_anomalies"]         = await queries.get_anomaly_count()
    stats["anomaly_severity_counts"] = await queries.get_anomaly_severity_counts()
    return stats


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check(request: Request) -> HealthResponse:
    """System health check — always accessible without auth."""
    db_ok = True
    try:
        from aria.dsremo.db.connection import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        db_ok = False

    uptime = time.monotonic() - getattr(request.app.state, "start_time", time.monotonic())
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        version=__version__,
        db_connected=db_ok,
        uptime_seconds=round(uptime, 1),
    )


# ---------------------------------------------------------------------------
# Telemetry Ingestion
# ---------------------------------------------------------------------------

@router.post("/telemetry", response_model=IngestResponse, tags=["telemetry"])
async def ingest_telemetry(body: TelemetryBatchIn, _user: dict = Depends(require_operator)) -> IngestResponse:
    """Ingest a batch of telemetry points.

    Partial success: valid points are stored, invalid ones reported as errors.
    """
    raw_dicts = [p.model_dump() for p in body.points]
    valid_points, errors = adapt_batch(raw_dicts)

    # V3-M1: apply sensor health corrections (gain/offset/TID drift) before
    # storing. Unknown channels pass through unchanged; known channels receive
    # corrected value + tier-adjusted quality.
    valid_points = apply_sensor_corrections(valid_points)

    if valid_points:
        try:
            await queries.insert_telemetry(valid_points)
        except Exception as e:
            logger.error("telemetry_insert_failed", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to store telemetry")

    await _trigger_detection({p.satellite_id for p in valid_points})

    return IngestResponse(
        accepted=len(valid_points),
        rejected=len(errors),
        errors=errors[:10],  # cap error detail to prevent response bloat
    )


@router.post("/telemetry/single", response_model=IngestResponse, tags=["telemetry"])
async def ingest_single(body: TelemetryIn, _user: dict = Depends(require_operator)) -> IngestResponse:
    """Convenience endpoint for a single telemetry point."""
    try:
        point = adapt_single(body.model_dump())
    except AdapterError as e:
        return IngestResponse(accepted=0, rejected=1, errors=[{"error": str(e)}])

    # V3-M1: apply sensor health corrections before storing.
    corrected = apply_sensor_corrections([point])
    await queries.insert_telemetry(corrected)
    await _trigger_detection(point.satellite_id)
    return IngestResponse(accepted=1, rejected=0)


_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # hard ceiling regardless of plan (100 MB)


@router.post("/telemetry/upload", response_model=CsvUploadResult, tags=["telemetry"])
async def upload_telemetry_csv(
    satellite_id: str = Form(..., min_length=1, max_length=128),
    subsystem: str = Form(default="unknown", max_length=32),
    timestamp_col: str = Form(default="timestamp", max_length=64),
    resample_minutes: int = Form(default=1, ge=1, le=1440),
    file: UploadFile = File(..., description="Wide-format CSV: timestamp + parameter columns"),
    _user: dict = Depends(require_operator),
) -> CsvUploadResult:
    """Upload a wide-format CSV file and bulk-load it into Dsremo.

    CSV format::

        timestamp,param1,param2,...
        2024-01-01T00:00:00Z,1.2,3.4,...

    All non-timestamp columns are treated as telemetry parameters.
    Channels already having ≥ 50 000 rows are skipped (idempotent re-uploads).
    Upload size limit is enforced per plan tier.  Returns per-channel row counts.
    """
    raw = await file.read()

    # Enforce plan upload size limit
    limits = get_limits(_user.get("plan"))
    plan_max = limits.upload_bytes if limits.upload_bytes > 0 else _MAX_UPLOAD_BYTES
    effective_max = min(plan_max, _MAX_UPLOAD_BYTES)
    if len(raw) > effective_max:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large for your plan ({_user.get('plan', 'free')!r}): "
                f"{len(raw):,} bytes (plan limit {effective_max:,} bytes). "
                "Upgrade to Pro for 100 MB uploads."
            ),
        )

    try:
        from aria.dsremo.ingest.csv_connector import CSVConnector
        connector = CSVConnector(
            source=io.BytesIO(raw),
            satellite_id=satellite_id,
            subsystem=subsystem,
            timestamp_col=timestamp_col,
        )
        totals = await connector.bulk_load_to_db(
            resample_minutes=resample_minutes,
            skip_if_rows_gte=50_000,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("csv_upload_failed", satellite=satellite_id, error=str(exc))
        raise HTTPException(status_code=500, detail="CSV processing failed — check server logs")

    channels_skipped = sum(1 for v in totals.values() if v >= 50_000)
    return CsvUploadResult(
        satellite_id=satellite_id,
        channels_loaded=len(totals),
        channels_skipped=channels_skipped,
        total_rows_inserted=sum(totals.values()),
        rows_per_channel=totals,
        source_name=connector.source_name,
    )


@router.get("/telemetry/{satellite_id}", tags=["telemetry"])
async def get_telemetry(
    satellite_id: str,
    parameter: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=10_000),
    _user: dict = Depends(require_viewer),
) -> list[TelemetryOut]:
    """Query historical telemetry for a satellite."""
    rows = await queries.get_telemetry(
        satellite_id=satellite_id,
        parameter=parameter,
        since=since,
        until=until,
        limit=limit,
    )
    return [TelemetryOut(**r) for r in rows]


# ---------------------------------------------------------------------------
# Analyze stored telemetry (on-demand detection)
# ---------------------------------------------------------------------------

@router.post("/telemetry/{satellite_id}/analyze", response_model=AnalyzeResult, tags=["telemetry"])
async def analyze_satellite(
    satellite_id: str,
    _user: dict = Depends(require_operator),
) -> AnalyzeResult:
    """Run anomaly detection over all stored telemetry for a satellite.

    Fetches every registered channel for the satellite, runs the full
    11-detector pipeline via run_bulk_detection(), and returns a summary.
    Idempotent — safe to call repeatedly; detection state is updated in DB.
    """
    import time as _time
    from aria.dsremo.ingest.bulk_loader import run_bulk_detection

    # Discover channels registered for this satellite.
    channel_rows = await queries.get_channel_stats(satellite_id)
    if not channel_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No channels found for satellite '{satellite_id}'. Upload telemetry first.",
        )

    parameters = [r["parameter"] for r in channel_rows]
    subsystem_map = {r["parameter"]: r["subsystem"] for r in channel_rows}

    t0 = _time.monotonic()
    try:
        results = await run_bulk_detection(
            satellite_id=satellite_id,
            parameters=parameters,
            subsystem_map=subsystem_map,
        )
    except Exception as e:
        logger.error("analyze_satellite_failed", satellite=satellite_id, error=str(e))
        raise HTTPException(status_code=500, detail="Detection failed — check server logs")

    elapsed = round(_time.monotonic() - t0, 2)
    anomalies_per_channel = {p: len(anoms) for p, anoms in results.items()}
    total_anomalies = sum(anomalies_per_channel.values())

    return AnalyzeResult(
        satellite_id=satellite_id,
        channels_analyzed=len(results),
        total_anomalies=total_anomalies,
        anomalies_per_channel=anomalies_per_channel,
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

@router.get("/anomalies", tags=["anomalies"])
async def list_anomalies(
    satellite_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    ml_only: bool | None = Query(default=None, description="Filter to ML-pattern-only (lstm sole detector) or stats-detected anomalies"),
    _user: dict = Depends(require_viewer),
) -> list[AnomalyOut]:
    """List anomalies. Supports cursor pagination and date-range filtering.

    Pagination:
      GET /anomalies                       → newest 200
      GET /anomalies?before=<iso-ts>       → 200 older than cursor (infinite scroll)
      GET /anomalies?since=<iso-ts>        → new rows since ts (polling)
    Date filter:
      GET /anomalies?date_from=...&date_to=... → within range
    ML filter:
      GET /anomalies?ml_only=true          → only lstm-sole detections (subtle patterns)
      GET /anomalies?ml_only=false         → only stats-detected anomalies
    """
    rows = await queries.get_anomalies(
        satellite_id=satellite_id,
        severity=severity,
        since=since,
        before=before,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        ml_only=ml_only,
    )
    return [_row_to_anomaly(r) for r in rows]


@router.get("/anomalies/{anomaly_id}", tags=["anomalies"])
async def get_anomaly(anomaly_id: str, _user: dict = Depends(require_viewer)) -> AnomalyOut:
    """Get a single anomaly with full explanation."""
    row = await queries.get_anomaly_by_id(anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return _row_to_anomaly(row)


@router.patch("/anomalies/{anomaly_id}/feedback", tags=["anomalies"])
async def submit_anomaly_feedback(
    anomaly_id: str,
    body: FeedbackIn,
    _user: dict = Depends(require_viewer),
) -> AnomalyOut:
    """Submit operator feedback (true positive / false positive) on an anomaly.

    Marks the anomaly as reviewed.  False positive anomalies are excluded from
    future GET /anomalies listings (unless include_false_positives=true).
    """
    is_fp = body.verdict == "false_positive"
    updated = await queries.update_anomaly_review(anomaly_id, false_positive=is_fp)
    if not updated:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    row = await queries.get_anomaly_by_id(anomaly_id)
    # Propagate FP verdict to in-memory detector weights (online learning).
    if is_fp and row:
        from aria.dsremo.detection.detector import record_false_positive  # noqa: PLC0415
        record_false_positive(
            satellite_id=row["satellite_id"],
            parameter=row["parameter"],
            detectors_triggered=row.get("detectors_triggered") or [],
        )
    return _row_to_anomaly(row)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------

@router.get("/satellites", tags=["satellites"])
async def list_satellites(_user: dict = Depends(require_viewer)) -> list[str]:
    """List all satellites that have sent telemetry."""
    return await queries.get_known_satellites()


# ---------------------------------------------------------------------------
# Simulator (dev/demo only)
# ---------------------------------------------------------------------------

@router.post("/simulate/start", tags=["simulator"])
async def start_simulation(body: SimulateRequest, _user: dict = Depends(require_admin)) -> dict:
    """Start generating synthetic telemetry. For demos and testing."""
    try:
        from aria.dsremo.simulate.spacecraft import SpacecraftSimulator
        sim = SpacecraftSimulator(
            satellite_id=body.satellite_id,
            rate_hz=body.rate_hz,
        )
        # Run simulation in background task
        import asyncio
        asyncio.create_task(
            _run_simulation(sim, body.duration_seconds)
        )
        return {
            "status": "started",
            "satellite_id": body.satellite_id,
            "duration_seconds": body.duration_seconds,
            "rate_hz": body.rate_hz,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/simulate/inject", tags=["simulator"])
async def inject_fault(body: InjectRequest, _user: dict = Depends(require_admin)) -> dict:
    """Inject a fault into running simulation. For testing anomaly detection."""
    return {
        "status": "injected",
        "fault_type": body.fault_type,
        "subsystem": body.subsystem,
        "parameter": body.parameter,
        "intensity": body.intensity,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run_simulation(sim, duration_seconds: int) -> None:
    """Background task that feeds simulated telemetry into the pipeline."""
    import asyncio
    end_time = time.monotonic() + duration_seconds
    while time.monotonic() < end_time:
        try:
            points = sim.generate_tick()
            await queries.insert_telemetry(points)
            await _trigger_detection({p.satellite_id for p in points})
        except Exception as e:
            logger.warning("simulation_tick_error", error=str(e))
        await asyncio.sleep(1.0 / sim.rate_hz)


def _row_to_anomaly(row: dict) -> AnomalyOut:
    """Convert a DB row dict to an AnomalyOut schema."""
    import json
    contributing = row.get("contributing_params", "{}")
    if isinstance(contributing, str):
        contributing = json.loads(contributing)
    detectors = row.get("detectors_triggered", [])
    if isinstance(detectors, str):
        detectors = json.loads(detectors)
    detectors = list(detectors)
    # ml_only: only ML detectors (lstm/tcn) fired — statistics missed it
    _ML_DETECTORS = {"lstm", "tcn"}
    ml_only = bool(detectors) and set(detectors).issubset(_ML_DETECTORS)
    return AnomalyOut(
        id=row["id"],
        satellite_id=row["satellite_id"],
        timestamp=row["timestamp"],
        subsystem=row["subsystem"],
        parameter=row["parameter"],
        value=row["value"],
        severity=row["severity"],
        confidence=row["confidence"],
        detectors_triggered=detectors,
        explanation=row.get("explanation", ""),
        root_cause_group=row.get("root_cause_group"),
        contributing_params=contributing,
        reviewed=bool(row.get("reviewed", False)),
        false_positive=bool(row.get("false_positive", False)),
        ml_only=ml_only,
    )
