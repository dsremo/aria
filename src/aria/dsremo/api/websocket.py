"""WebSocket endpoint — live anomaly stream to dashboard.

Clients connect, receive real-time anomaly events as JSON.
No polling needed. Efficient for the dashboard's live view.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()
ws_router = APIRouter()

# Connected clients — managed per-process (good enough for single-server)
_clients: set[WebSocket] = set()


@ws_router.websocket("/ws/live")
async def live_anomaly_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time anomaly notifications."""
    await websocket.accept()
    _clients.add(websocket)
    logger.info("ws_client_connected", total=len(_clients))

    try:
        # Keep connection alive, listen for pings
        while True:
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(websocket)
        logger.info("ws_client_disconnected", total=len(_clients))


async def broadcast_anomaly(anomaly_data: dict[str, Any]) -> None:
    """Push an anomaly event to all connected WebSocket clients.

    Called by the detection pipeline when a new anomaly is confirmed.
    Failed sends are silently dropped — dashboard will catch up on reconnect.
    """
    if not _clients:
        return

    payload = json.dumps({
        "type": "anomaly",
        "data": _serialize(anomaly_data),
        "server_time": datetime.now(timezone.utc).isoformat(),
    })

    disconnected: set[WebSocket] = set()
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)

    _clients.difference_update(disconnected)


async def broadcast_telemetry_summary(summary: dict[str, Any]) -> None:
    """Push periodic telemetry summary to dashboard (every N seconds)."""
    if not _clients:
        return

    payload = json.dumps({
        "type": "telemetry_summary",
        "data": _serialize(summary),
        "server_time": datetime.now(timezone.utc).isoformat(),
    })

    disconnected: set[WebSocket] = set()
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)

    _clients.difference_update(disconnected)


def _serialize(obj: Any) -> Any:
    """Make objects JSON-safe."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj
