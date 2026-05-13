"""ARIA integration routes — adapter endpoints for the ARIA central AI.

ARIA uses a channel_id format (e.g., "eps.battery.soc_percent") that maps
to Dsremo's subsystem+parameter convention. These routes accept ARIA's
format and translate internally.

Routes:
  POST /ingest           — Single telemetry ingest (ARIA format: channel_id)
  POST /ingest/batch     — Batch telemetry ingest (ARIA format)
  GET  /channels/{channel_id}/health  — Channel health summary
  GET  /channels/{channel_id}/score   — Real-time anomaly score
  WS   /ws/alerts        — ARIA-compatible WebSocket (alias for /ws/live)

These complement the existing routes.py endpoints. ARIA's tools call these
directly; the standard dashboard routes remain unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from aria.dsremo.api.dependencies import require_viewer
from aria.dsremo.db import queries
from aria.dsremo.detection.detector import run_detection_cycle

logger = structlog.get_logger()
aria_router = APIRouter(tags=["aria"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class AriaIngestRequest(BaseModel):
    """ARIA single-point ingest — uses channel_id format."""
    satellite_id: str = Field(..., min_length=1)
    channel_id: str = Field(..., min_length=1, description="e.g. eps.battery.soc_percent")
    value: float
    timestamp: str | None = None


class AriaIngestResponse(BaseModel):
    anomaly_score: float = 0.0
    detectors_triggered: list[str] = []
    channel_id: str = ""
    ingested: bool = True


class AriaBatchReading(BaseModel):
    satellite_id: str = "sat-01"
    channel_id: str
    value: float
    timestamp: str | None = None


class AriaBatchRequest(BaseModel):
    readings: list[AriaBatchReading] = Field(..., min_length=1, max_length=500)


class AriaBatchResult(BaseModel):
    channel_id: str
    anomaly_score: float = 0.0
    detectors_triggered: list[str] = []


class AriaBatchResponse(BaseModel):
    results: list[AriaBatchResult]
    count: int


class AriaChannelHealth(BaseModel):
    channel_id: str
    status: str = "NOMINAL"
    anomaly_rate_24h: float = 0.0
    data_quality: float = 1.0
    last_value: float | None = None
    last_timestamp: str | None = None


class AriaAnomalyScore(BaseModel):
    channel_id: str
    anomaly_score: float = 0.0
    detectors: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Channel ID → subsystem + parameter decomposition
# ---------------------------------------------------------------------------

def _decompose_channel(channel_id: str) -> tuple[str, str]:
    """Split channel_id into (subsystem, parameter).

    "eps.battery.soc_percent" → ("eps", "battery.soc_percent")
    """
    parts = channel_id.split(".", 1)
    return (parts[0], parts[1]) if len(parts) > 1 else (channel_id, "")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@aria_router.post("/ingest", response_model=AriaIngestResponse)
async def aria_ingest_single(req: AriaIngestRequest):
    """Ingest a single telemetry point using ARIA's channel_id format.

    Translates channel_id to subsystem+parameter and stores in Dsremo.
    Returns the anomaly score from the 12-detector ensemble.
    """
    subsystem, parameter = _decompose_channel(req.channel_id)
    ts = req.timestamp or datetime.now(timezone.utc).isoformat()

    try:
        await queries.insert_telemetry(
            satellite_id=req.satellite_id,
            timestamp=ts,
            subsystem=subsystem,
            parameter=parameter,
            value=req.value,
        )
    except Exception as exc:
        logger.warning("aria_ingest.db_error", error=str(exc), channel=req.channel_id)

    # Trigger detection
    score = 0.0
    triggered: list[str] = []
    try:
        result = await run_detection_cycle(req.satellite_id)
        if result:
            score = getattr(result, "ensemble_score", 0.0)
            triggered = getattr(result, "detectors_triggered", [])
    except Exception as exc:
        logger.warning("aria_ingest.detection_error", error=str(exc))

    return AriaIngestResponse(
        anomaly_score=score,
        detectors_triggered=triggered,
        channel_id=req.channel_id,
        ingested=True,
    )


@aria_router.post("/ingest/batch", response_model=AriaBatchResponse)
async def aria_ingest_batch(req: AriaBatchRequest):
    """Batch ingest telemetry using ARIA's channel_id format.

    Returns per-channel anomaly scores.
    """
    results: list[AriaBatchResult] = []
    satellite_ids: set[str] = set()

    for reading in req.readings:
        subsystem, parameter = _decompose_channel(reading.channel_id)
        ts = reading.timestamp or datetime.now(timezone.utc).isoformat()

        try:
            await queries.insert_telemetry(
                satellite_id=reading.satellite_id,
                timestamp=ts,
                subsystem=subsystem,
                parameter=parameter,
                value=reading.value,
            )
            satellite_ids.add(reading.satellite_id)
        except Exception as exc:
            logger.warning("aria_batch.db_error", error=str(exc), channel=reading.channel_id)

        results.append(AriaBatchResult(channel_id=reading.channel_id))

    # Run detection for all affected satellites
    for sat_id in satellite_ids:
        try:
            await run_detection_cycle(sat_id)
        except Exception as exc:
            logger.warning("aria_batch.detection_error", error=str(exc), satellite=sat_id)

    return AriaBatchResponse(results=results, count=len(results))


@aria_router.get("/channels/{channel_id}/health", response_model=AriaChannelHealth)
async def aria_channel_health(channel_id: str):
    """Get health summary for a specific channel (ARIA format)."""
    subsystem, parameter = _decompose_channel(channel_id)

    try:
        stats = await queries.get_channel_stats(subsystem=subsystem, parameter=parameter)
        if stats:
            return AriaChannelHealth(
                channel_id=channel_id,
                status="NOMINAL" if stats.get("anomaly_rate", 0) < 0.05 else "DEGRADED",
                anomaly_rate_24h=stats.get("anomaly_rate", 0.0),
                data_quality=stats.get("quality", 1.0),
                last_value=stats.get("last_value"),
            )
    except Exception:
        pass

    return AriaChannelHealth(channel_id=channel_id)


@aria_router.get("/channels/{channel_id}/score", response_model=AriaAnomalyScore)
async def aria_anomaly_score(channel_id: str):
    """Get current real-time anomaly score for a channel (ARIA format)."""
    subsystem, parameter = _decompose_channel(channel_id)

    try:
        score_data = await queries.get_latest_score(subsystem=subsystem, parameter=parameter)
        if score_data:
            return AriaAnomalyScore(
                channel_id=channel_id,
                anomaly_score=score_data.get("ensemble_score", 0.0),
                detectors=score_data.get("detector_scores", {}),
            )
    except Exception:
        pass

    return AriaAnomalyScore(channel_id=channel_id)


# WebSocket alias for ARIA — same as /ws/live but at /ws/alerts
@aria_router.websocket("/ws/alerts")
async def aria_websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for ARIA — alias for /ws/live."""
    from aria.dsremo.api.websocket import _clients

    await websocket.accept()
    _clients.add(websocket)
    logger.info("aria_ws_connected", total=len(_clients))

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)
