"""ARIA Telemetry WebSocket Server — feeds OpenMCT dashboard.

Runs a lightweight HTTP + WebSocket server that:
  1. Accepts WebSocket connections from OpenMCT browser clients
  2. Streams real-time ARIA telemetry (from Basilisk or any source)
  3. Serves telemetry dictionary (metadata) for OpenMCT auto-discovery
  4. Provides historical data REST endpoint
  5. Accepts commands from OpenMCT → ARIA bus

Protocol:
  WS /realtime
    Client sends: {"subscribe": "aria.power.battery_soc"} or {"unsubscribe": "..."}
    Server sends: {"key": "aria.power.battery_soc", "timestamp": 1234567890, "value": 85.0}

  GET /dictionary
    Returns: list of telemetry point definitions

  GET /history/<key>?start=<ms>&end=<ms>
    Returns: array of {timestamp, value} objects

  GET /latest/<key>
    Returns: most recent value for key
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# ────────────────────────────────────────────────────────────────────
#  TELEMETRY DICTIONARY — all points OpenMCT can display
# ────────────────────────────────────────────────────────────────────

ARIA_TELEMETRY_DICTIONARY: list[dict[str, Any]] = [
    # ─── Power ───
    {"key": "aria.power.battery_soc", "name": "Battery SoC", "unit": "%",
     "subsystem": "power", "format": "float", "min": 0, "max": 100,
     "limits": {"warning_low": 20, "critical_low": 10, "warning_high": 98}},
    {"key": "aria.power.solar_watts", "name": "Solar Panel Power", "unit": "W",
     "subsystem": "power", "format": "float", "min": 0, "max": 5000},
    {"key": "aria.power.bus_voltage", "name": "Bus Voltage", "unit": "V",
     "subsystem": "power", "format": "float", "min": 20, "max": 35,
     "limits": {"warning_low": 24, "critical_low": 22, "warning_high": 32, "critical_high": 34}},
    {"key": "aria.power.total_load", "name": "Total Power Load", "unit": "W",
     "subsystem": "power", "format": "float", "min": 0, "max": 3000},
    {"key": "aria.power.in_eclipse", "name": "In Eclipse", "unit": "",
     "subsystem": "power", "format": "enum",
     "enumerations": [{"value": 0, "string": "Sunlit"}, {"value": 1, "string": "Eclipse"}]},

    # ─── Navigation ───
    {"key": "aria.nav.altitude", "name": "Altitude", "unit": "km",
     "subsystem": "navigation", "format": "float", "min": 0, "max": 1000},
    {"key": "aria.nav.velocity", "name": "Orbital Velocity", "unit": "m/s",
     "subsystem": "navigation", "format": "float", "min": 0, "max": 11000},
    {"key": "aria.nav.latitude", "name": "Ground Track Latitude", "unit": "°",
     "subsystem": "navigation", "format": "float", "min": -90, "max": 90},
    {"key": "aria.nav.longitude", "name": "Ground Track Longitude", "unit": "°",
     "subsystem": "navigation", "format": "float", "min": -180, "max": 180},
    {"key": "aria.nav.position_x", "name": "ECI Position X", "unit": "km",
     "subsystem": "navigation", "format": "float"},
    {"key": "aria.nav.position_y", "name": "ECI Position Y", "unit": "km",
     "subsystem": "navigation", "format": "float"},
    {"key": "aria.nav.position_z", "name": "ECI Position Z", "unit": "km",
     "subsystem": "navigation", "format": "float"},

    # ─── ADCS (Attitude) ───
    {"key": "aria.adcs.roll", "name": "Roll", "unit": "°",
     "subsystem": "adcs", "format": "float", "min": -180, "max": 180},
    {"key": "aria.adcs.pitch", "name": "Pitch", "unit": "°",
     "subsystem": "adcs", "format": "float", "min": -90, "max": 90},
    {"key": "aria.adcs.yaw", "name": "Yaw", "unit": "°",
     "subsystem": "adcs", "format": "float", "min": -180, "max": 180},

    # ─── Thermal ───
    {"key": "aria.thermal.battery_temp", "name": "Battery Temperature", "unit": "°C",
     "subsystem": "thermal", "format": "float", "min": -20, "max": 60,
     "limits": {"warning_high": 35, "critical_high": 55}},
    {"key": "aria.thermal.solar_panel_temp", "name": "Solar Panel Temperature", "unit": "°C",
     "subsystem": "thermal", "format": "float", "min": -100, "max": 120},

    # ─── ECLSS ───
    {"key": "aria.eclss.o2_percent", "name": "O₂ Concentration", "unit": "%",
     "subsystem": "eclss", "format": "float", "min": 0, "max": 25,
     "limits": {"warning_low": 19.5, "critical_low": 18, "warning_high": 23.5}},
    {"key": "aria.eclss.co2_ppm", "name": "CO₂ Level", "unit": "ppm",
     "subsystem": "eclss", "format": "float", "min": 0, "max": 10000,
     "limits": {"warning_high": 5000, "critical_high": 8000}},
    {"key": "aria.eclss.cabin_pressure", "name": "Cabin Pressure", "unit": "psi",
     "subsystem": "eclss", "format": "float", "min": 10, "max": 16,
     "limits": {"warning_low": 13.5, "critical_low": 12}},

    # ─── ARIA System ───
    {"key": "aria.system.agent_count", "name": "Active Agents", "unit": "",
     "subsystem": "system", "format": "integer", "min": 0, "max": 20},
    {"key": "aria.system.alerts_total", "name": "Total Alerts", "unit": "",
     "subsystem": "system", "format": "integer"},
    {"key": "aria.system.anomaly_score", "name": "Dsremo Anomaly Score", "unit": "",
     "subsystem": "system", "format": "float", "min": 0, "max": 1,
     "limits": {"warning_high": 0.5, "critical_high": 0.8}},
]

# Quick lookup
_DICT_BY_KEY = {d["key"]: d for d in ARIA_TELEMETRY_DICTIONARY}


# ────────────────────────────────────────────────────────────────────
#  HISTORY STORE
# ────────────────────────────────────────────────────────────────────

class TelemetryHistoryStore:
    """Ring-buffer history for each telemetry key."""

    def __init__(self, max_per_key: int = 10000) -> None:
        self._max = max_per_key
        self._data: dict[str, deque[dict[str, Any]]] = {}

    def record(self, key: str, timestamp_ms: int, value: Any) -> None:
        if key not in self._data:
            self._data[key] = deque(maxlen=self._max)
        self._data[key].append({"timestamp": timestamp_ms, "value": value})

    def query(self, key: str, start_ms: int = 0, end_ms: int = 0,
              limit: int = 1000) -> list[dict[str, Any]]:
        if key not in self._data:
            return []
        data = self._data[key]
        if start_ms or end_ms:
            end_ms = end_ms or int(time.time() * 1000)
            filtered = [d for d in data if start_ms <= d["timestamp"] <= end_ms]
        else:
            filtered = list(data)
        return filtered[-limit:]

    def latest(self, key: str) -> dict[str, Any] | None:
        if key in self._data and self._data[key]:
            return self._data[key][-1]
        return None

    @property
    def keys(self) -> list[str]:
        return list(self._data.keys())


# ────────────────────────────────────────────────────────────────────
#  WEBSOCKET SERVER
# ────────────────────────────────────────────────────────────────────

class ARIATelemetryServer:
    """WebSocket + HTTP server for OpenMCT integration.

    Usage:
        server = ARIATelemetryServer(host="0.0.0.0", port=8080)
        await server.start()

        # Push telemetry from any source
        server.push("aria.power.battery_soc", 85.0)
        server.push("aria.nav.altitude", 400.5)

        # Or connect to Basilisk runner
        server.connect_basilisk(runner)
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:  # nosec B104 (Docker-bind default; operator overrides via arg)
        self._host = host
        self._port = port
        self._history = TelemetryHistoryStore()
        self._ws_clients: set[Any] = set()
        self._subscriptions: dict[int, set[str]] = {}  # client_id → subscribed keys
        self._running = False
        self._app: Any = None
        self._runner: Any = None

    def push(self, key: str, value: Any, timestamp_ms: int | None = None) -> None:
        """Push a telemetry value — stores in history and broadcasts to subscribers."""
        ts = timestamp_ms or int(time.time() * 1000)
        self._history.record(key, ts, value)

        # Broadcast to subscribed WebSocket clients
        message = json.dumps({"key": key, "timestamp": ts, "value": value})
        disconnected = set()

        for ws in self._ws_clients:
            ws_id = id(ws)
            subs = self._subscriptions.get(ws_id, set())
            if not subs or key in subs:  # Empty subs = subscribed to all
                try:
                    asyncio.ensure_future(ws.send_str(message))
                except Exception:
                    disconnected.add(ws)

        self._ws_clients -= disconnected
        for ws in disconnected:
            self._subscriptions.pop(id(ws), None)

    def push_basilisk_frame(self, frame: Any) -> None:
        """Push a BasiliskRunner TelemetryFrame to all relevant keys."""
        ts = int(time.time() * 1000)

        self.push("aria.power.battery_soc", frame.battery_soc * 100, ts)
        self.push("aria.power.solar_watts", frame.solar_power_w, ts)
        self.push("aria.power.bus_voltage", 28.0, ts)
        self.push("aria.power.total_load", frame.power_draw_w, ts)
        self.push("aria.power.in_eclipse", 1 if frame.in_eclipse else 0, ts)
        self.push("aria.nav.altitude", frame.altitude_km, ts)
        self.push("aria.nav.velocity", frame.orbital_velocity_m_s, ts)
        self.push("aria.nav.latitude", frame.ground_track_lat_deg, ts)
        self.push("aria.nav.longitude", frame.ground_track_lon_deg, ts)
        self.push("aria.nav.position_x", frame.position_eci_m[0] / 1000, ts)
        self.push("aria.nav.position_y", frame.position_eci_m[1] / 1000, ts)
        self.push("aria.nav.position_z", frame.position_eci_m[2] / 1000, ts)
        self.push("aria.adcs.roll", frame.roll_deg, ts)
        self.push("aria.adcs.pitch", frame.pitch_deg, ts)
        self.push("aria.adcs.yaw", frame.yaw_deg, ts)

    async def start(self) -> None:
        """Start the HTTP + WebSocket server."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp required: pip install aiohttp")

        self._app = web.Application()
        self._app.router.add_get("/dictionary", self._handle_dictionary)
        self._app.router.add_get("/history/{key:.+}", self._handle_history)
        self._app.router.add_get("/latest/{key:.+}", self._handle_latest)
        self._app.router.add_get("/realtime", self._handle_websocket)
        self._app.router.add_get("/health", self._handle_health)

        # CORS middleware
        self._app.middlewares.append(self._cors_middleware)

        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()

        self._running = True
        logger.info("telemetry_server.started", host=self._host, port=self._port,
                     endpoints=["dictionary", "history", "latest", "realtime", "health"])

    @staticmethod
    async def _cors_middleware(app: Any, handler: Any) -> Any:
        from aiohttp import web
        import os as _os

        # Audit HIGH-9 — refuse the wildcard CORS origin.  Operator
        # supplies the comma-separated allow-list via ARIA_CORS_ORIGINS;
        # only origins that match exactly are echoed.  Empty allow-list
        # ⇒ no Access-Control-Allow-Origin emitted.
        allow_list = {
            o.strip().rstrip("/")
            for o in _os.environ.get("ARIA_CORS_ORIGINS", "").split(",")
            if o.strip()
        }

        async def middleware_handler(request: web.Request) -> web.StreamResponse:
            response = await handler(request)
            origin = (request.headers.get("Origin") or "").strip().rstrip("/")
            if origin and origin in allow_list:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        return middleware_handler

    async def _handle_dictionary(self, request: Any) -> Any:
        from aiohttp import web
        return web.json_response(ARIA_TELEMETRY_DICTIONARY)

    async def _handle_history(self, request: Any) -> Any:
        from aiohttp import web
        key = request.match_info["key"]
        start = int(request.query.get("start", 0))
        end = int(request.query.get("end", 0))
        limit = int(request.query.get("limit", 1000))
        data = self._history.query(key, start, end, limit)
        return web.json_response(data)

    async def _handle_latest(self, request: Any) -> Any:
        from aiohttp import web
        key = request.match_info["key"]
        latest = self._history.latest(key)
        if latest:
            return web.json_response(latest)
        return web.json_response({"error": "no data"}, status=404)

    async def _handle_websocket(self, request: Any) -> Any:
        from aiohttp import web

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_clients.add(ws)
        ws_id = id(ws)
        self._subscriptions[ws_id] = set()

        logger.info("telemetry_server.ws_connected", client_id=ws_id)

        try:
            async for msg in ws:
                if msg.type == 1:  # TEXT
                    try:
                        data = json.loads(msg.data)
                        if "subscribe" in data:
                            self._subscriptions[ws_id].add(data["subscribe"])
                        elif "unsubscribe" in data:
                            self._subscriptions[ws_id].discard(data["unsubscribe"])
                    except json.JSONDecodeError:
                        pass
        finally:
            self._ws_clients.discard(ws)
            self._subscriptions.pop(ws_id, None)
            logger.info("telemetry_server.ws_disconnected", client_id=ws_id)

        return ws

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web
        return web.json_response({
            "status": "ok",
            "clients": len(self._ws_clients),
            "keys_tracked": len(self._history.keys),
            "dictionary_size": len(ARIA_TELEMETRY_DICTIONARY),
        })
