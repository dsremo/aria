"""OpenMCT Telemetry Bridge for ARIA.

Streams ARIA telemetry data to NASA's Open Mission Control Technologies
(OpenMCT) web-based mission control interface via WebSocket and REST endpoints.

OpenMCT expects:
  1. A **dictionary** endpoint listing available telemetry points (their IDs,
     display names, units, ranges, and value types).
  2. A **history** endpoint returning past telemetry values for a given point
     and time range.
  3. A **realtime** WebSocket that pushes new values as they arrive.

This bridge:
  - Subscribes to all ``aria.sensor.*`` topics on the ARIA message bus
  - Flattens nested payloads into individual telemetry points
  - Maintains a rolling history buffer (configurable depth)
  - Serves the dictionary and history via an aiohttp REST server
  - Pushes realtime updates over WebSocket to connected OpenMCT clients

References:
  - https://github.com/nasa/openmct
  - https://github.com/nasa/openmct-tutorial (telemetry server example)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenMCTConfig:
    """Configuration for the OpenMCT bridge."""
    host: str = "0.0.0.0"  # nosec B104 (OpenMCT dev bridge; production confined to localhost)
    port: int = 8082
    history_depth: int = 50_000       # Max data points per telemetry key
    dictionary_namespace: str = "aria"
    spacecraft_name: str = "ARIA Spacecraft"


# ---------------------------------------------------------------------------
# Telemetry point definition (OpenMCT dictionary format)
# ---------------------------------------------------------------------------

@dataclass
class TelemetryPoint:
    """A single telemetry point that OpenMCT can subscribe to."""
    key: str               # Unique ID, e.g. "aria.power.total_power_w"
    name: str              # Human-readable name
    units: str = ""
    value_type: str = "float"  # float, int, bool, string, enum
    min_value: float | None = None
    max_value: float | None = None
    hints: dict[str, Any] = field(default_factory=dict)

    def to_openmct_dict(self) -> dict[str, Any]:
        """Serialize to OpenMCT dictionary format."""
        result: dict[str, Any] = {
            "key": self.key,
            "name": self.name,
            "values": [
                {
                    "key": "utc",
                    "source": "timestamp",
                    "name": "Timestamp",
                    "format": "utc",
                    "hints": {"domain": 1},
                },
                {
                    "key": "value",
                    "name": self.name,
                    "units": self.units,
                    "format": self.value_type,
                    "hints": {"range": 1},
                },
            ],
        }
        if self.min_value is not None:
            result["values"][1]["min"] = self.min_value
        if self.max_value is not None:
            result["values"][1]["max"] = self.max_value
        return result


# ---------------------------------------------------------------------------
# Default telemetry dictionary
# ---------------------------------------------------------------------------

def _build_default_dictionary() -> list[TelemetryPoint]:
    """Build the default set of telemetry points from ARIA topics."""
    return [
        # Navigation / Attitude
        TelemetryPoint("aria.nav.quaternion_qw", "Attitude Qw", "", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.quaternion_qx", "Attitude Qx", "", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.quaternion_qy", "Attitude Qy", "", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.quaternion_qz", "Attitude Qz", "", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.angular_velocity_mag", "Angular Velocity Magnitude", "rad/s", "float", 0.0, 1.0),
        TelemetryPoint("aria.nav.omega_x", "Angular Velocity X", "rad/s", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.omega_y", "Angular Velocity Y", "rad/s", "float", -1.0, 1.0),
        TelemetryPoint("aria.nav.omega_z", "Angular Velocity Z", "rad/s", "float", -1.0, 1.0),
        # Orbit
        TelemetryPoint("aria.nav.altitude_km", "Altitude", "km", "float", 0.0, 2000.0),
        TelemetryPoint("aria.nav.true_anomaly_deg", "True Anomaly", "deg", "float", 0.0, 360.0),
        TelemetryPoint("aria.nav.inclination_deg", "Inclination", "deg", "float", 0.0, 180.0),
        TelemetryPoint("aria.nav.semi_major_axis_km", "Semi-Major Axis", "km", "float"),
        # Power
        TelemetryPoint("aria.power.total_power_w", "Total Solar Power", "W", "float", 0.0, 5000.0),
        TelemetryPoint("aria.power.panel_0_w", "Solar Panel 1 Power", "W", "float", 0.0, 2500.0),
        TelemetryPoint("aria.power.panel_1_w", "Solar Panel 2 Power", "W", "float", 0.0, 2500.0),
        TelemetryPoint("aria.power.battery_soc", "Battery State of Charge", "%", "float", 0.0, 100.0),
        TelemetryPoint("aria.power.eclipse", "In Eclipse", "", "bool"),
        TelemetryPoint("aria.power.sun_angle_deg", "Sun Angle", "deg", "float", 0.0, 360.0),
        # Thermal
        TelemetryPoint("aria.thermal.solar_panel_1_k", "Solar Panel 1 Temp", "K", "float", 50.0, 400.0),
        TelemetryPoint("aria.thermal.solar_panel_2_k", "Solar Panel 2 Temp", "K", "float", 50.0, 400.0),
        TelemetryPoint("aria.thermal.battery_pack_k", "Battery Pack Temp", "K", "float", 250.0, 330.0),
        TelemetryPoint("aria.thermal.payload_bay_k", "Payload Bay Temp", "K", "float", 250.0, 330.0),
        TelemetryPoint("aria.thermal.rw_cluster_k", "RW Cluster Temp", "K", "float", 250.0, 350.0),
        TelemetryPoint("aria.thermal.star_tracker_k", "Star Tracker Temp", "K", "float", 250.0, 320.0),
        TelemetryPoint("aria.thermal.prop_tank_k", "Propellant Tank Temp", "K", "float", 250.0, 330.0),
        TelemetryPoint("aria.thermal.avionics_bay_k", "Avionics Bay Temp", "K", "float", 270.0, 340.0),
        # Propulsion / Actuators
        TelemetryPoint("aria.prop.rw_0_rpm", "Reaction Wheel 1 Speed", "RPM", "float", -6000.0, 6000.0),
        TelemetryPoint("aria.prop.rw_1_rpm", "Reaction Wheel 2 Speed", "RPM", "float", -6000.0, 6000.0),
        TelemetryPoint("aria.prop.rw_2_rpm", "Reaction Wheel 3 Speed", "RPM", "float", -6000.0, 6000.0),
        TelemetryPoint("aria.prop.rw_3_rpm", "Reaction Wheel 4 Speed", "RPM", "float", -6000.0, 6000.0),
        # Sensors
        TelemetryPoint("aria.sensor_health.star_tracker_valid", "Star Tracker Valid", "", "bool"),
        TelemetryPoint("aria.sensor_health.sun_sensor_valid", "Sun Sensor Valid", "", "bool"),
    ]


# ---------------------------------------------------------------------------
# Telemetry history buffer
# ---------------------------------------------------------------------------

@dataclass
class TelemetryDatum:
    """A single telemetry data point with timestamp."""
    timestamp_ms: int  # Unix milliseconds
    value: Any


class TelemetryHistoryStore:
    """Rolling buffer of telemetry data per key."""

    def __init__(self, max_depth: int = 50_000) -> None:
        self._max_depth = max_depth
        self._data: dict[str, list[TelemetryDatum]] = {}

    def record(self, key: str, value: Any, timestamp_ms: int | None = None) -> None:
        """Record a data point."""
        ts = timestamp_ms or int(time.time() * 1000)
        if key not in self._data:
            self._data[key] = []
        buf = self._data[key]
        buf.append(TelemetryDatum(timestamp_ms=ts, value=value))
        if len(buf) > self._max_depth:
            # Trim oldest 10% to avoid frequent trimming
            trim = self._max_depth // 10
            self._data[key] = buf[trim:]

    def query(
        self,
        key: str,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query history for a telemetry key within a time range."""
        buf = self._data.get(key, [])
        results: list[dict[str, Any]] = []
        for datum in buf:
            if start_ms is not None and datum.timestamp_ms < start_ms:
                continue
            if end_ms is not None and datum.timestamp_ms > end_ms:
                continue
            results.append({
                "id": key,
                "timestamp": datum.timestamp_ms,
                "value": datum.value,
            })
            if len(results) >= limit:
                break
        return results

    def latest(self, key: str) -> dict[str, Any] | None:
        """Get the most recent value for a key."""
        buf = self._data.get(key, [])
        if not buf:
            return None
        d = buf[-1]
        return {"id": key, "timestamp": d.timestamp_ms, "value": d.value}

    @property
    def keys(self) -> list[str]:
        return list(self._data.keys())

    @property
    def total_points(self) -> int:
        return sum(len(v) for v in self._data.values())


# ---------------------------------------------------------------------------
# ARIA bus -> flat telemetry extraction
# ---------------------------------------------------------------------------

def _flatten_aria_message(message: Message) -> dict[str, Any]:
    """Convert an ARIA sensor message into flat telemetry key-value pairs.

    Maps bus topic + payload fields to OpenMCT telemetry point keys.
    """
    topic = message.topic
    payload = message.payload
    flat: dict[str, Any] = {}

    if topic == "aria.sensor.navigation.attitude":
        q = payload.get("quaternion", [0, 0, 0, 1])
        flat["aria.nav.quaternion_qx"] = q[0] if len(q) > 0 else 0
        flat["aria.nav.quaternion_qy"] = q[1] if len(q) > 1 else 0
        flat["aria.nav.quaternion_qz"] = q[2] if len(q) > 2 else 0
        flat["aria.nav.quaternion_qw"] = q[3] if len(q) > 3 else 1
        omega = payload.get("angular_velocity_rad_s", [0, 0, 0])
        flat["aria.nav.omega_x"] = omega[0] if len(omega) > 0 else 0
        flat["aria.nav.omega_y"] = omega[1] if len(omega) > 1 else 0
        flat["aria.nav.omega_z"] = omega[2] if len(omega) > 2 else 0
        flat["aria.nav.angular_velocity_mag"] = payload.get(
            "angular_velocity_magnitude_rad_s", 0
        )

    elif topic == "aria.sensor.navigation.orbit":
        flat["aria.nav.altitude_km"] = payload.get("altitude_km", 0)
        flat["aria.nav.true_anomaly_deg"] = payload.get("true_anomaly_deg", 0)
        flat["aria.nav.inclination_deg"] = payload.get("inclination_deg", 0)
        sma = payload.get("semi_major_axis_m", 0)
        flat["aria.nav.semi_major_axis_km"] = sma / 1000.0 if sma else 0

    elif topic == "aria.sensor.power.solar_panels":
        flat["aria.power.total_power_w"] = payload.get("total_power_w", 0)
        panels = payload.get("panel_power_w", [])
        for i, p in enumerate(panels):
            flat[f"aria.power.panel_{i}_w"] = p
        flat["aria.power.eclipse"] = payload.get("eclipse", False)
        flat["aria.power.sun_angle_deg"] = payload.get("sun_angle_deg", 0)

    elif topic == "aria.sensor.power.battery":
        soc = payload.get("state_of_charge", 0)
        flat["aria.power.battery_soc"] = soc * 100.0  # Convert to percentage

    elif topic == "aria.sensor.power.eclipse":
        flat["aria.power.eclipse"] = payload.get("in_eclipse", False)
        flat["aria.power.sun_angle_deg"] = payload.get("sun_angle_deg", 0)

    elif topic == "aria.sensor.thermal.nodes":
        temps = payload.get("node_temps_k", [])
        names = payload.get("node_names", [])
        thermal_key_map = {
            "solar_panel_1": "aria.thermal.solar_panel_1_k",
            "solar_panel_2": "aria.thermal.solar_panel_2_k",
            "battery_pack": "aria.thermal.battery_pack_k",
            "payload_bay": "aria.thermal.payload_bay_k",
            "reaction_wheel_cluster": "aria.thermal.rw_cluster_k",
            "star_tracker": "aria.thermal.star_tracker_k",
            "propellant_tank": "aria.thermal.prop_tank_k",
            "avionics_bay": "aria.thermal.avionics_bay_k",
        }
        for i, temp in enumerate(temps):
            name = names[i] if i < len(names) else f"node_{i}"
            key = thermal_key_map.get(name, f"aria.thermal.{name}_k")
            flat[key] = temp

    elif topic == "aria.sensor.propulsion.reaction_wheels":
        speeds = payload.get("speeds_rpm", [])
        for i, spd in enumerate(speeds):
            flat[f"aria.prop.rw_{i}_rpm"] = spd

    elif topic == "aria.sensor.navigation.sensors":
        flat["aria.sensor_health.star_tracker_valid"] = payload.get(
            "star_tracker_valid", True
        )
        flat["aria.sensor_health.sun_sensor_valid"] = payload.get(
            "sun_sensor_valid", True
        )

    return flat


# ---------------------------------------------------------------------------
# WebSocket / HTTP server
# ---------------------------------------------------------------------------

class OpenMCTServer:
    """HTTP + WebSocket server for OpenMCT telemetry integration.

    Endpoints:
      GET /dictionary              — full telemetry dictionary
      GET /history/<key>?start=&end=&limit=  — historical data
      GET /latest/<key>            — most recent value
      WS  /realtime                — WebSocket for live updates

    Requires aiohttp. Falls back to a stub if not available.
    """

    def __init__(
        self,
        config: OpenMCTConfig,
        dictionary: list[TelemetryPoint],
        history_store: TelemetryHistoryStore,
    ) -> None:
        self._config = config
        self._dictionary = dictionary
        self._dict_by_key = {p.key: p for p in dictionary}
        self._history = history_store
        self._ws_clients: list[Any] = []  # aiohttp WebSocketResponse objects
        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None

    async def start(self) -> None:
        """Start the HTTP/WebSocket server."""
        try:
            from aiohttp import web  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "openmct_server.aiohttp_not_installed",
                msg="Install aiohttp to serve OpenMCT endpoints. "
                    "WebSocket push and history queries are still available "
                    "programmatically via the OpenMCTBridge API.",
            )
            return

        # Wiring audit Pass 4 (F13.8) — refuse to bind to all
        # interfaces in production. The default ``host="0.0.0.0"``
        # would expose the OpenMCT WebSocket + history HTTP to the
        # world; the docstring on OpenMCTConfig says "production
        # confined to localhost" but no gate enforces it. Pattern
        # matches Pass 1 F13.x production refuse-to-start.
        import os as _os
        if (
            _os.environ.get("ARIA_ENVIRONMENT", "development") == "production"
            and self._config.host == "0.0.0.0"
        ):
            logger.critical(
                "openmct_server.production_bind_all_interfaces_refused",
                host=self._config.host,
                impact="default 0.0.0.0 bind would expose telemetry WS / "
                       "history HTTP to the world; refusing to start",
                fix="set OpenMCTConfig.host=127.0.0.1 or supply an "
                    "explicit private interface",
            )
            raise RuntimeError(
                "OpenMCTServer refuses host=0.0.0.0 in production "
                "(set OpenMCTConfig.host explicitly)"
            )

        self._app = web.Application()
        self._app.router.add_get("/dictionary", self._handle_dictionary)
        self._app.router.add_get("/history/{key:.+}", self._handle_history)
        self._app.router.add_get("/latest/{key:.+}", self._handle_latest)
        self._app.router.add_get("/realtime", self._handle_websocket)
        self._app.router.add_get("/health", self._handle_health)

        # Audit HIGH-9 — exact-origin CORS for OpenMCT on a different
        # port.  Operator supplies the allow-list via ARIA_CORS_ORIGINS;
        # the wildcard ``*`` is no longer emitted.
        from aiohttp import web_middlewares  # noqa: F401
        import os as _os

        allow_list = {
            o.strip().rstrip("/")
            for o in _os.environ.get("ARIA_CORS_ORIGINS", "").split(",")
            if o.strip()
        }

        @web.middleware
        async def cors_middleware(
            request: web.Request,
            handler: Any,
        ) -> web.StreamResponse:
            origin = (request.headers.get("Origin") or "").strip().rstrip("/")
            if request.method == "OPTIONS":
                resp = web.Response()
            else:
                resp = await handler(request)
            if origin and origin in allow_list:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Vary"] = "Origin"
                resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp

        self._app.middlewares.append(cors_middleware)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner, self._config.host, self._config.port
        )
        await self._site.start()
        logger.info(
            "openmct_server.started",
            host=self._config.host,
            port=self._config.port,
        )

    async def stop(self) -> None:
        """Stop the HTTP/WebSocket server."""
        # Close WebSocket connections
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        logger.info("openmct_server.stopped")

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Push a telemetry datum to all connected WebSocket clients."""
        if not self._ws_clients:
            return

        payload = json.dumps(data)
        dead: list[Any] = []
        for ws in self._ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._ws_clients.remove(ws)

    # --- HTTP handlers ---

    async def _handle_dictionary(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import-not-found]

        dictionary = {
            "name": self._config.spacecraft_name,
            "key": self._config.dictionary_namespace,
            "measurements": [
                p.to_openmct_dict() for p in self._dictionary
            ],
        }
        return web.json_response(dictionary)

    async def _handle_history(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import-not-found]

        key = request.match_info["key"]
        start_ms = request.query.get("start")
        end_ms = request.query.get("end")
        limit = int(request.query.get("limit", 1000))

        start = int(start_ms) if start_ms else None
        end = int(end_ms) if end_ms else None

        data = self._history.query(key, start_ms=start, end_ms=end, limit=limit)
        return web.json_response(data)

    async def _handle_latest(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import-not-found]

        key = request.match_info["key"]
        datum = self._history.latest(key)
        if datum is None:
            return web.json_response(
                {"error": f"No data for key: {key}"}, status=404
            )
        return web.json_response(datum)

    async def _handle_websocket(self, request: Any) -> Any:
        from aiohttp import web, WSMsgType  # type: ignore[import-not-found]

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_clients.append(ws)
        logger.info("openmct_server.ws_client_connected", total=len(self._ws_clients))

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # OpenMCT may send subscription requests
                    try:
                        data = json.loads(msg.data)
                        logger.debug("openmct_server.ws_message", data=data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)
            logger.info(
                "openmct_server.ws_client_disconnected",
                total=len(self._ws_clients),
            )

        return ws

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import-not-found]

        return web.json_response({
            "status": "ok",
            "ws_clients": len(self._ws_clients),
            "telemetry_points": len(self._dictionary),
            "history_points": self._history.total_points,
        })


# ---------------------------------------------------------------------------
# Main OpenMCT Bridge
# ---------------------------------------------------------------------------

class OpenMCTBridge:
    """Streams ARIA telemetry to OpenMCT via WebSocket and REST.

    Usage::

        bus = MessageBus()
        bridge = OpenMCTBridge(bus, OpenMCTConfig(port=8082))
        await bridge.start()
        # OpenMCT connects to ws://localhost:8082/realtime
        # and fetches http://localhost:8082/dictionary
        await bridge.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        config: OpenMCTConfig | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or OpenMCTConfig()
        self._dictionary = _build_default_dictionary()
        self._history = TelemetryHistoryStore(max_depth=self._config.history_depth)
        self._server = OpenMCTServer(self._config, self._dictionary, self._history)
        self._running = False

        # Stats
        self._messages_ingested: int = 0
        self._points_recorded: int = 0

    @property
    def history_store(self) -> TelemetryHistoryStore:
        """Direct access to the history store for programmatic queries."""
        return self._history

    @property
    def dictionary(self) -> list[TelemetryPoint]:
        """The telemetry dictionary."""
        return list(self._dictionary)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "messages_ingested": self._messages_ingested,
            "points_recorded": self._points_recorded,
            "history_total_points": self._history.total_points,
            "telemetry_keys": len(self._dictionary),
        }

    def add_telemetry_point(self, point: TelemetryPoint) -> None:
        """Register an additional telemetry point in the dictionary."""
        self._dictionary.append(point)

    async def start(self) -> None:
        """Start the OpenMCT bridge: subscribe to bus + start HTTP server."""
        if self._running:
            logger.warning("openmct_bridge.already_running")
            return

        logger.info("openmct_bridge.starting", port=self._config.port)

        # Subscribe to all sensor topics
        self._bus.subscribe("aria.sensor.*", self._on_aria_message)

        # Start HTTP/WS server
        await self._server.start()

        self._running = True
        logger.info("openmct_bridge.started")

    async def stop(self) -> None:
        """Stop the bridge and server."""
        if not self._running:
            return

        self._running = False
        self._bus.unsubscribe("aria.sensor.*", self._on_aria_message)
        await self._server.stop()
        logger.info("openmct_bridge.stopped", stats=self.stats)

    async def _on_aria_message(self, message: Message) -> None:
        """Process an ARIA bus message: flatten, store, and broadcast."""
        self._messages_ingested += 1
        timestamp_ms = int(time.time() * 1000)

        flat = _flatten_aria_message(message)
        for key, value in flat.items():
            self._history.record(key, value, timestamp_ms)
            self._points_recorded += 1

            # Push to WebSocket clients
            await self._server.broadcast({
                "id": key,
                "timestamp": timestamp_ms,
                "value": value,
            })
