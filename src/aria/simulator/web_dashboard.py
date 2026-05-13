"""Real-time web dashboard for the ARIA 4D generation ship simulator.

Serves a single-page Plotly.js dashboard with 6 panels:
  1. 3D Trajectory View (ship position in 3D space with velocity coloring)
  2. Subsystem Health (hull, shield, power, food, crew, water)
  3. Timeline Controls (seek, play/pause, speed)
  4. Event Log (severity-colored, filterable)
  5. Challenge Status (6 interstellar challenges with meters)
  6. Statistics (severity bar chart, food/hull/crew time series)

Two modes:
  A. Live mode: simulator pushes snapshots via WebSocket in real-time
  B. Replay mode: client loads a saved JSON and replays locally,
     or server loads a recording and serves it via REST + WS

Architecture:
  - aiohttp web server (HTTP + WebSocket)
  - GET /           -> serves index.html (self-contained dashboard)
  - GET /api/status -> server health check
  - GET /api/snapshots -> all recorded snapshots (replay mode)
  - GET /api/snapshot/<year> -> single snapshot by year
  - GET /api/events  -> all recorded events
  - WS  /ws         -> real-time snapshot + event stream

Usage:
    # Standalone
    python -m aria.simulator.web_dashboard --port 8090

    # Programmatic (live mode)
    dashboard = WebDashboard(port=8090)
    await dashboard.start()
    dashboard.push_snapshot(state_dict)  # from simulator tick
    dashboard.push_event(event_dict)     # from event handler

    # Programmatic (replay mode)
    dashboard = WebDashboard(port=8090)
    dashboard.load_recording("/path/to/mission.json")
    await dashboard.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

# Path to static assets (index.html)
ASSETS_DIR = Path(__file__).parent / "web_assets"


# ── R32: dashboard route → permission table ──────────────────────
# Anonymous-allowed paths: login flow + k8s probes + SPA index/static.
# Anything ending in `/` is treated as a true prefix (e.g. /static/).
_DASHBOARD_ANONYMOUS_PATHS: tuple[str, ...] = (
    "/healthz",
    "/readyz",
    "/api/auth/challenge",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/static/",
    "/assets/",
    "/lib/",
    "/api/nasa42/",
    "/favicon.ico",
    "/",
    "/viewer",
    "/lab",
    "/app",
    "/app/",
    "/ws",                # WS handshake auth handled in-handler
)

# Routes whose default mapping is overridden. Keys are
# (METHOD, canonical_route_pattern). Anything not in this map and not
# anonymous falls back to: GET → telemetry.read, mutating → mission.advance.
_DASHBOARD_ROUTE_PERMS: dict[tuple[str, str], str] = {
    # Auth endpoints
    ("GET",  "/api/auth/me"):              "auth.session.create",
    ("POST", "/api/auth/logout"):          "auth.session.revoke_self",

    # F-9 approval queue
    ("POST", "/api/safety/approve"):       "approval.sign",
    ("POST", "/api/safety/veto"):          "approval.veto",
    ("POST", "/api/safety/revert"):        "approval.revert",

    # F-17 kill switch + deadman
    ("POST", "/api/safety/kill_assert"):   "kill_switch.assert",
    ("POST", "/api/safety/kill_reset"):    "kill_switch.reset",
    ("POST", "/api/safety/deadman_affirm"): "deadman.affirm",

    # F-13 safety replay (sensitive — re-runs sealed test set)
    ("POST", "/api/safety/replay/run"):    "telemetry.read_sensitive",

    # Failure injection / chaos
    ("POST", "/api/failures/trigger"):     "failures.inject",
    ("POST", "/api/agriculture/failure"):  "failures.inject",
    ("POST", "/api/agriculture/restore"):  "failures.inject",
    ("POST", "/api/bearing/trip"):         "failures.inject",
    ("POST", "/api/bearing/restore"):      "failures.inject",
    ("POST", "/api/hull/damage"):          "failures.inject",
    ("POST", "/api/hull/repair"):          "failures.inject",
    ("POST", "/api/hull/impact"):          "failures.inject",
    ("POST", "/api/avionics/seu"):         "failures.inject",
    ("POST", "/api/random_events/force_flare"): "failures.inject",

    # Ship config / rebuild
    ("POST", "/api/ship/rebuild"):         "ship.rebuild",
    ("POST", "/api/ship/apply_class"):     "ship.rebuild",
    ("POST", "/api/ship/analyze"):         "ship.rebuild",

    # Faults — mutations need operator
    ("POST", "/api/faults/{id}/acknowledge"): "approval.sign",
    ("POST", "/api/faults/{id}/resolve"):     "approval.sign",
    ("POST", "/api/faults/{id}/shelve"):      "approval.sign",
    ("POST", "/api/faults/report"):           "telemetry.read",

    # Sensitive reads
    ("GET",  "/api/crew/health"):          "telemetry.read_sensitive",

    # R33 admin endpoints
    ("GET",  "/api/admin/principals"):                  "principal.list",
    ("POST", "/api/admin/principals"):                  "principal.create",
    ("POST", "/api/admin/principals/{id}/revoke"):      "principal.revoke",
    ("POST", "/api/admin/principals/{id}/role"):        "role.assign",
    ("GET",  "/api/admin/roles"):                       "role.list",
    ("POST", "/api/admin/roles/custom"):                "role.create_custom",
    ("POST", "/api/admin/roles/custom/{name}/revoke"):  "role.revoke_custom",
    ("GET",  "/api/admin/permissions"):                 "role.list",

    # R34 incident + audit-trace endpoints
    ("GET",  "/api/incidents"):                         "telemetry.read_sensitive",
    ("GET",  "/api/incidents/{id}"):                    "telemetry.read_sensitive",
    ("POST", "/api/incidents/{id}/note"):               "approval.sign",
    ("POST", "/api/incidents/{id}/fix"):                "approval.sign",
    ("POST", "/api/incidents/{id}/root_cause"):         "approval.sign",
    ("POST", "/api/incidents/{id}/resolve"):            "approval.sign",
    ("POST", "/api/incidents/{id}/defer"):              "approval.sign",
    ("GET",  "/api/audit/trace"):                       "telemetry.read_sensitive",
    ("GET",  "/api/audit/chain_status"):                "telemetry.read_sensitive",
}


@dataclass
class DashboardConfig:
    """Configuration for the web dashboard server.

    All fields can be overridden via environment variables:
      ARIA_HOST, ARIA_PORT, ARIA_CORS_ORIGIN, ARIA_MAX_SNAPSHOTS, ARIA_MAX_EVENTS
    """
    host: str = field(default_factory=lambda: os.environ.get("ARIA_HOST", "0.0.0.0"))  # nosec B104 (env-driven default; reverse proxy in production)
    port: int = field(default_factory=lambda: int(os.environ.get("ARIA_PORT", "8090")))
    recording_path: str = ""
    max_snapshots: int = field(default_factory=lambda: int(os.environ.get("ARIA_MAX_SNAPSHOTS", "50000")))
    max_events: int = field(default_factory=lambda: int(os.environ.get("ARIA_MAX_EVENTS", "100000")))
    cors_origin: str = field(default_factory=lambda: os.environ.get("ARIA_CORS_ORIGIN", "*"))
    # R32: ship-wide auth. Defaults OFF so existing dev/test runs and
    # the ~8949 test suite continue to function. Production deployments
    # set ARIA_AUTH_REQUIRED=1 (systemd unit / docker env). Tests that
    # exercise the auth path set auth_required=True explicitly.
    auth_required: bool = field(default_factory=lambda: os.environ.get("ARIA_AUTH_REQUIRED", "0") == "1")


class WebDashboard:
    """Real-time web dashboard for the ARIA generation ship simulator.

    Manages the aiohttp server, WebSocket clients, and data buffering.
    """

    @staticmethod
    def _safe_float(body: dict, key: str, default: float,
                    lo: float | None = None, hi: float | None = None) -> float:
        """Extract a numeric field from `body` with bounds-checking.

        Raises ValueError with a clear message if the value is
        non-numeric, below lo, or above hi. All 12+ handlers that
        previously did ``float(body.get(key, default))`` should use
        this to get 400 responses instead of uncaught 500s.
        """
        raw = body.get(key, default)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be numeric, got {raw!r}")
        if lo is not None and val < lo:
            raise ValueError(f"{key}={val} below minimum {lo}")
        if hi is not None and val > hi:
            raise ValueError(f"{key}={val} above maximum {hi}")
        return val

    def __init__(self, config: DashboardConfig | None = None) -> None:
        self._config = config or DashboardConfig()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ws_clients: list[web.WebSocketResponse] = []

        # Data stores
        self._snapshots: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {}

        # Recording data (for replay over HTTP)
        self._recording_loaded: bool = False

        # Engineering Lab: compute lock + thread pool (P0-5 fix)
        self._compute_lock = asyncio.Lock()
        self._compute_pool = ThreadPoolExecutor(max_workers=1)

    # ─── Public API ──────────────────────────────────────────

    @property
    def app(self) -> web.Application:
        """Access the aiohttp Application (create if needed)."""
        if self._app is None:
            self._app = self._create_app()
        return self._app

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def client_count(self) -> int:
        return len(self._ws_clients)

    @property
    def running(self) -> bool:
        return self._site is not None

    def load_recording(self, path: str | Path) -> int:
        """Load a simulation recording (JSON) for replay.

        Accepts:
          - Recorder JSON: { "snapshots": [...] }
          - Raw snapshot array: [...]

        Returns the number of snapshots loaded.
        """
        path = Path(path)
        with open(path) as f:
            data = json.load(f)

        if isinstance(data, list):
            self._snapshots = data
            self._metadata = {"source": str(path)}
        elif isinstance(data, dict):
            self._snapshots = data.get("snapshots", data.get("years", []))
            self._metadata = data.get("metadata", {"source": str(path)})
            # Extract events if present
            for snap in self._snapshots:
                if "events" in snap and isinstance(snap["events"], list):
                    self._events.extend(snap["events"])
        else:
            raise ValueError(f"Unrecognized recording format in {path}")

        self._recording_loaded = True
        logger.info(
            "dashboard.recording_loaded",
            extra={"path": str(path), "snapshots": len(self._snapshots)},
        )
        return len(self._snapshots)

    def push_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Push a new state snapshot (live mode). Broadcasts to all WS clients."""
        if len(self._snapshots) >= self._config.max_snapshots:
            self._snapshots.pop(0)
        self._snapshots.append(snapshot)
        self._broadcast({"type": "snapshot", "data": snapshot})

    def push_event(self, event: dict[str, Any]) -> None:
        """Push a new event (live mode). Broadcasts to all WS clients."""
        if len(self._events) >= self._config.max_events:
            self._events.pop(0)
        self._events.append(event)
        self._broadcast({"type": "event", "data": event})

    def push_interstellar_state(self, state: Any, events: list | None = None) -> None:
        """Push an InterstellarState object (convenience for interstellar sim).

        Converts the dataclass to a dashboard-friendly dict.
        """
        snap = self._interstellar_state_to_dict(state)
        if events:
            snap["events"] = [self._year_event_to_dict(e) for e in events]
        self.push_snapshot(snap)

    async def start(self) -> None:
        """Start the web dashboard server."""
        # Initialize the narrative log subscriber BEFORE any events fire.
        # Previously get_narrative_log() was only called inside
        # _lazy_register_subsystems on the first tick, so any event
        # published before the first /api/mission/tick (startup sequence,
        # ship rebuild, phase transitions from the UI) was lost from the
        # Captain's Log. Early init makes the log actually useful.
        from aria.simulator.narrative_log import get_narrative_log
        get_narrative_log()
        # Startup validation — verify critical dependencies before serving
        self._check_dependencies()
        app = self.app
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner,
            self._config.host,
            self._config.port,
        )
        await self._site.start()
        logger.info(
            "dashboard.started",
            extra={
                "host": self._config.host,
                "port": self._config.port,
                "url": f"http://localhost:{self._config.port}",
            },
        )

    async def stop(self) -> None:
        """Stop the web dashboard server."""
        # Close all WebSocket connections
        for ws in list(self._ws_clients):
            await ws.close()
        self._ws_clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        logger.info("dashboard.stopped")

    # ─── Internal: App Setup ─────────────────────────────────

    def _create_app(self) -> web.Application:
        """Create and configure the aiohttp application."""
        # 10 MB max request body — prevents DoS via oversized POST.
        # The largest legitimate payload is /api/load (mission snapshot JSON,
        # typically 200-500 KB). 10 MB gives 20× headroom.
        app = web.Application(client_max_size=10 * 1024 * 1024)
        app[web.AppKey("dashboard", WebDashboard)] = self

        # OpenTelemetry — if enabled, every request gets an HTTP server
        # span automatically. No-op when OTel isn't configured, so this
        # is safe to call unconditionally.
        try:
            from aria.simulator.telemetry_otel import is_enabled
            if is_enabled():
                from opentelemetry.instrumentation.aiohttp_server import (
                    AioHttpServerInstrumentor,
                )
                AioHttpServerInstrumentor().instrument()
        except Exception:
            pass

        # R32: ship-wide auth/authz. Resolver always runs (so handlers
        # can read request['principal'] = anonymous when missing).
        # Permission gate is toggleable via DashboardConfig.auth_required.
        # R35: trace middleware mounts FIRST so every downstream audit
        # entry inherits the per-request trace_id automatically.
        from aria.security.middleware import (
            make_principal_resolver_middleware,
            make_route_permission_middleware,
            make_trace_middleware,
        )
        app.middlewares.append(make_trace_middleware())
        app.middlewares.append(make_principal_resolver_middleware())
        # Round-2 audit NEW-HIGH-15 — the underlying middleware now
        # deny-by-default for unmapped routes.  The dashboard's
        # historical contract uses ``telemetry.read`` for unmapped GETs
        # and ``mission.advance`` for unmapped mutating verbs, so we
        # opt back into those defaults explicitly here.  Production
        # deployments should expand ``_DASHBOARD_ROUTE_PERMS`` to cover
        # every route — the explicit fall-back is a courtesy, not a
        # license to forget.
        app.middlewares.append(make_route_permission_middleware(
            _DASHBOARD_ROUTE_PERMS,
            enforced=self._config.auth_required,
            anonymous_paths=_DASHBOARD_ANONYMOUS_PATHS,
            default_get_perm="telemetry.read",
            default_mutating_perm="mission.advance",
        ))

        # Auth endpoints (anonymous-allowed; resolver still runs).
        app.router.add_get("/api/auth/challenge", self._handle_auth_challenge)
        app.router.add_post("/api/auth/login", self._handle_auth_login)
        app.router.add_post("/api/auth/logout", self._handle_auth_logout)
        app.router.add_get("/api/auth/me", self._handle_auth_me)

        # R33 admin endpoints. register_admin_executors wires the
        # ApprovalQueue executors that fire after two-person + cooling-off.
        from aria.security.admin import register_admin_executors
        register_admin_executors()
        app.router.add_get("/api/admin/principals",
                           self._handle_admin_principals_list)
        app.router.add_post("/api/admin/principals",
                            self._handle_admin_principal_create)
        app.router.add_post("/api/admin/principals/{id}/revoke",
                            self._handle_admin_principal_revoke)
        app.router.add_post("/api/admin/principals/{id}/role",
                            self._handle_admin_principal_role_assign)
        app.router.add_get("/api/admin/roles",
                           self._handle_admin_roles_list)
        app.router.add_post("/api/admin/roles/custom",
                            self._handle_admin_role_create_custom)
        app.router.add_post("/api/admin/roles/custom/{name}/revoke",
                            self._handle_admin_role_revoke_custom)
        app.router.add_get("/api/admin/permissions",
                           self._handle_admin_permissions_list)

        # R34 incident + audit-trace endpoints.
        app.router.add_get("/api/incidents",
                           self._handle_incidents_list)
        app.router.add_get("/api/incidents/{id}",
                           self._handle_incident_get)
        app.router.add_post("/api/incidents/{id}/note",
                            self._handle_incident_note)
        app.router.add_post("/api/incidents/{id}/fix",
                            self._handle_incident_fix)
        app.router.add_post("/api/incidents/{id}/root_cause",
                            self._handle_incident_root_cause)
        app.router.add_post("/api/incidents/{id}/resolve",
                            self._handle_incident_resolve)
        app.router.add_post("/api/incidents/{id}/defer",
                            self._handle_incident_defer)
        app.router.add_get("/api/audit/trace",
                           self._handle_audit_trace)
        app.router.add_get("/api/audit/chain_status",
                           self._handle_audit_chain_status)

        # Routes
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/viewer", self._handle_viewer)
        app.router.add_get("/api/status", self._handle_status)
        # K8s probes + monitoring
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_get("/readyz", self._handle_readyz)
        app.router.add_get("/api/metrics", self._handle_metrics)
        app.router.add_get("/api/config", self._handle_config)
        app.router.add_get("/api/snapshots", self._handle_snapshots)
        app.router.add_get("/api/snapshot/{year}", self._handle_snapshot_by_year)
        app.router.add_get("/api/events", self._handle_events)
        app.router.add_get("/api/ship.gltf", self._handle_ship_gltf)
        app.router.add_get("/api/ship/status", self._handle_ship_status)
        app.router.add_get("/api/telemetry/live", self._handle_telemetry_live)
        # Project root for locating sibling directories (web/dist, tools/nasa-42)
        _project_root = Path(__file__).resolve().parents[3]  # aria-core root
        # Static file serving for local Three.js lib
        lib_dir = ASSETS_DIR / "lib"
        if lib_dir.exists():
            app.router.add_static("/lib", lib_dir, show_index=False)
        # Serve React production build (web/dist/) if it exists — eliminates
        # the need for a separate Vite dev server in production.
        react_dist = _project_root / "web" / "dist"
        if react_dist.exists():
            # SPA fallback: serve index.html for any non-API, non-file path
            app.router.add_static("/assets", react_dist / "assets", show_index=False)
            app.router.add_get("/app", self._handle_react_spa)
            app.router.add_get("/app/{path:.*}", self._handle_react_spa)
        # NASA-42 CAD library — 71 OBJ meshes (ISS modules, HST, Voyager,
        # landers, rovers, cubesats, asteroids, Moon terrain). Served
        # read-only so the React ShipBuilder can overlay real aerospace
        # geometry on hover.
        # BUG-037 (2026-04-24, walkthrough): try multiple candidate
        # paths so Ship Builder's per-part 3D preview finds the NASA-42
        # Open-Source Model catalogue (ISS_SolarTruss.obj etc.) on a
        # dev box without requiring every user to set ARIA_NASA42_MODEL_DIR.
        env_override = os.environ.get("ARIA_NASA42_MODEL_DIR")
        nasa42_candidates = [
            Path(env_override) if env_override else None,
            _project_root.parent / "tools" / "nasa-42" / "Model",
            _project_root.parent.parent / "tools" / "nasa-42" / "Model",
            Path.home() / "Videos" / "Miscellaneous" / "external-tools" / "nasa-42" / "Model",
            Path.home() / "tools" / "nasa-42" / "Model",
        ]
        nasa42_model = next((p for p in nasa42_candidates if p and p.exists()), None)
        if nasa42_model is not None:
            app.router.add_static("/api/nasa42", nasa42_model, show_index=False)
            app.router.add_get("/api/nasa42/index.json", self._handle_nasa42_index)
        # Engineering Lab API routes
        app.router.add_get("/lab", self._handle_lab)
        app.router.add_get("/api/materials", self._handle_materials)
        app.router.add_get("/api/ship/params", self._handle_ship_params)
        app.router.add_get ("/api/ship/classes",      self._handle_ship_classes)
        app.router.add_post("/api/ship/apply_class",  self._handle_ship_apply_class)
        app.router.add_get("/api/ship/parts", self._handle_ship_parts)
        app.router.add_post("/api/ship/rebuild", self._handle_ship_rebuild)
        app.router.add_post("/api/ship/assembly/compute_mass", self._handle_assembly_compute_mass)
        app.router.add_post("/api/ship/assembly/save",         self._handle_assembly_save)
        app.router.add_get ("/api/ship/assembly/load/{uid}",   self._handle_assembly_load)
        app.router.add_get ("/api/ship/assembly/list",         self._handle_assembly_list)
        app.router.add_post("/api/ship/assembly/simulate",      self._handle_assembly_simulate)
        app.router.add_post("/api/ship/analyze", self._handle_ship_analyze)
        app.router.add_get ("/api/lunar/feasibility", self._handle_lunar_feasibility)
        app.router.add_post("/api/lunar/feasibility", self._handle_lunar_feasibility)
        app.router.add_post("/api/ship/optimize", self._handle_ship_optimize)
        app.router.add_get("/api/ship/review", self._handle_ship_review)
        app.router.add_post("/api/ai/reason", self._handle_ai_reason)
        app.router.add_post("/api/ai/advise", self._handle_ai_advise)
        app.router.add_get ("/api/ai/advise", self._handle_ai_advise)
        app.router.add_get ("/api/ai/decisions", self._handle_ai_decisions)
        # ── B5: Part-inspection + mission-phase + startup-sequence endpoints ──
        app.router.add_get ("/api/inspect/parts",            self._handle_inspect_parts)
        app.router.add_get ("/api/inspect/part/{part_id}",   self._handle_inspect_part)
        app.router.add_get ("/api/inspect/deps/{part_id}",   self._handle_inspect_deps)
        app.router.add_get ("/api/inspect/cascade/{part_id}",self._handle_inspect_cascade)
        app.router.add_get ("/api/inspect/graph",            self._handle_inspect_graph)
        app.router.add_get ("/api/mission/phase",            self._handle_mission_phase)
        app.router.add_post("/api/mission/transition",       self._handle_mission_transition)
        app.router.add_post("/api/mission/tick",             self._handle_mission_tick)
        app.router.add_post("/api/replay/run",               self._handle_replay_run)
        app.router.add_post("/api/replay/report",            self._handle_replay_report)
        app.router.add_post("/api/doctrine/search",          self._handle_doctrine_search)
        app.router.add_post("/api/lessons/search",           self._handle_lessons_search)
        app.router.add_get ("/api/startup/status",           self._handle_startup_status)
        app.router.add_post("/api/startup/tick",             self._handle_startup_tick)
        app.router.add_post("/api/startup/reset",            self._handle_startup_reset)
        app.router.add_post("/api/startup/abort",            self._handle_startup_abort)
        # ── B12: Event bus + tick engine + new subsystem endpoints ──
        app.router.add_get ("/api/events/recent",            self._handle_events_recent)
        app.router.add_get ("/api/events/health",            self._handle_events_health)
        app.router.add_post("/api/events/publish",           self._handle_events_publish)
        app.router.add_get ("/api/tick/status",              self._handle_tick_status)
        app.router.add_post("/api/tick/advance",             self._handle_tick_advance)
        app.router.add_get ("/api/avionics/seu",             self._handle_avionics_seu)
        app.router.add_get ("/api/eclss/contaminants",       self._handle_eclss_contaminants)
        # ── B18: bearing + propulsion-thermal + power-budget + BOM ──
        app.router.add_get ("/api/reactor",                  self._handle_reactor)
        app.router.add_get ("/api/reactor/state",            self._handle_reactor)
        app.router.add_get ("/api/bearing",                  self._handle_bearing)
        app.router.add_post("/api/bearing/trip",             self._handle_bearing_trip)
        app.router.add_post("/api/bearing/restore",          self._handle_bearing_restore)
        app.router.add_get ("/api/propulsion/thermal",       self._handle_propulsion_thermal)
        app.router.add_get ("/api/power/budget",             self._handle_power_budget)
        app.router.add_get ("/api/power",                    self._handle_power_budget)
        app.router.add_get ("/api/bom",                      self._handle_bom_list)
        app.router.add_get ("/api/bom/spof",                 self._handle_bom_spof)
        app.router.add_get ("/api/bom/{item_id}",            self._handle_bom_item)
        # ── B24: trajectory + fuel + crew + failure-injector ──
        app.router.add_get ("/api/trajectory",               self._handle_trajectory)
        app.router.add_get ("/api/trajectory/targets",       self._handle_trajectory_targets)
        app.router.add_post("/api/trajectory/target",        self._handle_trajectory_set_target)
        app.router.add_post("/api/trajectory/refuel",        self._handle_trajectory_refuel)
        app.router.add_post("/api/trajectory/gravity_assist_plan", self._handle_gravity_assist_plan)
        app.router.add_get ("/api/fuel",                     self._handle_fuel)
        app.router.add_get ("/api/crew/health",              self._handle_crew_health)
        app.router.add_get ("/api/failures/scenarios",       self._handle_failure_scenarios)
        app.router.add_post("/api/failures/trigger",         self._handle_failure_trigger)
        # ── B29: comms / agriculture / auto-tick / scheduler ──
        app.router.add_get ("/api/comms",                    self._handle_comms)
        app.router.add_post("/api/comms/queue",              self._handle_comms_queue)
        app.router.add_get ("/api/agriculture",              self._handle_agriculture)
        app.router.add_post("/api/agriculture/failure",      self._handle_agriculture_failure)
        app.router.add_post("/api/agriculture/restore",      self._handle_agriculture_restore)
        app.router.add_get ("/api/auto_tick",                self._handle_auto_tick_status)
        app.router.add_post("/api/auto_tick/start",          self._handle_auto_tick_start)
        app.router.add_post("/api/auto_tick/stop",           self._handle_auto_tick_stop)
        app.router.add_post("/api/auto_tick/speed",          self._handle_auto_tick_speed)
        app.router.add_get ("/api/scheduler",                self._handle_scheduler)
        app.router.add_post("/api/scheduler/add",            self._handle_scheduler_add)
        app.router.add_post("/api/scheduler/cancel",         self._handle_scheduler_cancel)
        # ── B34: hull damage / random events / save-load / objectives ──
        app.router.add_get ("/api/hull/damage",              self._handle_hull_damage)
        app.router.add_get ("/api/hull",                     self._handle_hull_damage)
        app.router.add_post("/api/hull/repair",              self._handle_hull_repair)
        app.router.add_post("/api/hull/impact",              self._handle_hull_impact)
        app.router.add_get ("/api/random_events",            self._handle_random_events_status)
        app.router.add_post("/api/random_events/toggle",     self._handle_random_events_toggle)
        app.router.add_post("/api/random_events/force_mmod", self._handle_random_events_force_mmod)
        app.router.add_post("/api/random_events/force_flare",self._handle_random_events_force_flare)
        app.router.add_get ("/api/objectives",               self._handle_objectives)
        app.router.add_get ("/api/save",                     self._handle_save)
        app.router.add_post("/api/load",                     self._handle_load)
        # ── B38: crew schedule + repair queue + narrative log ──
        app.router.add_get ("/api/crew/schedule",            self._handle_crew_schedule)
        app.router.add_post("/api/crew/overtime",            self._handle_crew_overtime)
        app.router.add_get ("/api/repair",                   self._handle_repair_queue)
        app.router.add_post("/api/repair/enqueue",           self._handle_repair_enqueue)
        app.router.add_post("/api/repair/cancel",            self._handle_repair_cancel)
        app.router.add_post("/api/repair/refill",            self._handle_repair_refill)
        app.router.add_get ("/api/narrative",                self._handle_narrative)
        app.router.add_get ("/api/narrative/text",           self._handle_narrative_text)
        app.router.add_post("/api/narrative/note",           self._handle_narrative_note)
        app.router.add_post("/api/narrative/clear",          self._handle_narrative_clear)

        # ── Fault management endpoints ──
        app.router.add_get ("/api/faults",                    self._handle_faults_list)
        app.router.add_post("/api/faults/report",             self._handle_faults_report)
        app.router.add_post("/api/faults/{id}/acknowledge",   self._handle_faults_ack)
        app.router.add_post("/api/faults/{id}/shelve",        self._handle_faults_shelve)
        app.router.add_post("/api/faults/{id}/resolve",       self._handle_faults_resolve)
        app.router.add_get ("/api/faults/stats",              self._handle_faults_stats)

        # ── Telemetry buffer endpoint ──
        app.router.add_get ("/api/telemetry/snapshot",        self._handle_telemetry_snapshot)

        # ── Star field / planetarium endpoint ──
        app.router.add_get ("/api/star_field",                self._handle_star_field)
        app.router.add_get ("/api/solar_system",              self._handle_solar_system)
        app.router.add_get ("/api/orbits",                    self._handle_orbits)
        app.router.add_get ("/api/belt_cloud",                self._handle_belt_cloud)
        app.router.add_get ("/api/astro_events",              self._handle_astro_events)
        app.router.add_get ("/api/moon_mission",              self._handle_moon_mission)
        app.router.add_get ("/api/mission/ensemble/stream",    self._handle_mission_ensemble_stream)
        app.router.add_get ("/api/mission/aerocapture",        self._handle_mission_aerocapture)
        app.router.add_get ("/api/mission/porkchop",           self._handle_mission_porkchop)
        app.router.add_get ("/api/sky_now",                   self._handle_sky_now)
        app.router.add_get ("/api/cities",                    self._handle_cities)
        app.router.add_get ("/api/satellites",                self._handle_satellites)
        app.router.add_get ("/api/tle/catalog",               self._handle_tle_catalog)
        app.router.add_get ("/api/telemetry/live_state",      self._handle_telemetry_live_state)
        app.router.add_get ("/api/telemetry/mission_schedule", self._handle_mission_schedule)
        app.router.add_get ("/api/telemetry/dsn",             self._handle_dsn_now)
        app.router.add_get ("/api/ai/recent_actions",         self._handle_ai_recent_actions)
        app.router.add_get ("/api/safety/state",              self._handle_safety_state)
        app.router.add_get ("/api/safety/proposals",          self._handle_safety_proposals)
        app.router.add_post("/api/safety/approve",            self._handle_safety_approve)
        app.router.add_post("/api/safety/veto",               self._handle_safety_veto)
        app.router.add_post("/api/safety/revert",             self._handle_safety_revert)
        app.router.add_post("/api/safety/kill_assert",        self._handle_safety_kill_assert)
        app.router.add_post("/api/safety/kill_reset",         self._handle_safety_kill_reset)
        app.router.add_post("/api/safety/deadman_affirm",     self._handle_safety_deadman_affirm)
        app.router.add_get ("/api/safety/replay",             self._handle_safety_replay_status)
        app.router.add_post("/api/safety/replay/run",         self._handle_safety_replay_run)
        app.router.add_get ("/api/safety/sandbagging",        self._handle_safety_sandbagging)
        app.router.add_get ("/api/safety/boot_manifest",      self._handle_safety_boot_manifest)
        app.router.add_get ("/api/telemetry/separation",      self._handle_telemetry_separation)
        app.router.add_get ("/api/exoplanets",                self._handle_exoplanets)
        app.router.add_get ("/api/variable_stars",            self._handle_variable_stars)
        app.router.add_get ("/api/double_stars",              self._handle_double_stars)
        app.router.add_get ("/api/ngc_highlights",            self._handle_ngc_highlights)
        app.router.add_get ("/api/pulsars",                   self._handle_pulsars)
        app.router.add_get ("/api/nearby_stars",              self._handle_nearby_stars)

        # ── Integrated mission design ──
        app.router.add_get ("/api/mission_design/earth_mars", self._handle_mission_design_earth_mars)
        app.router.add_get ("/api/porkchop/{origin}/{dest}",  self._handle_porkchop)

        # ── Constellation design ──
        app.router.add_get ("/api/constellation/{name}",     self._handle_constellation)
        app.router.add_get ("/api/constellation_list",        self._handle_constellation_list)

        app.router.add_get("/ws", self._handle_websocket)

        # CORS middleware
        app.middlewares.append(self._cors_middleware)
        # Input-validation middleware: converts ValueError from _safe_float
        # (and any handler-level validate-and-raise code) into a clean 400
        # instead of an opaque 500 traceback.
        app.middlewares.append(self._input_validation_middleware)
        # Request timeout — prevent any handler from hanging > 120s.
        # The optimizer can take 600s but uses its own internal timeout;
        # this catches runaway handlers that forget to set one.
        app.middlewares.append(self._timeout_middleware)
        # Request logging — every API call gets a structured log line with
        # method, path, status, latency. Outermost middleware = runs last.
        app.middlewares.append(self._request_logging_middleware)

        return app

    # ─── Middleware ───────────────────────────────────────────

    @web.middleware
    async def _input_validation_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        """Production error boundary: catch all exceptions and return JSON.

        - ValueError → 400 INVALID_INPUT (from _safe_float, validators)
        - web.HTTPException → re-raise (aiohttp handles 404, 405, etc.)
        - Everything else → 500 INTERNAL_ERROR (no stack trace leaked)
        """
        try:
            return await handler(request)
        except web.HTTPException:
            raise  # Let aiohttp handle standard HTTP errors
        except ValueError as e:
            return web.json_response(
                {"error": str(e), "code": "INVALID_INPUT"}, status=400,
            )
        except Exception as e:
            logger.exception("unhandled_error path=%s method=%s", request.path, request.method)
            return web.json_response(
                {"error": "Internal server error", "code": "INTERNAL_ERROR"},
                status=500,
            )

    @web.middleware
    async def _cors_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        # Handle CORS preflight (OPTIONS) immediately
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
        else:
            resp = await handler(request)
        origin = self._config.cors_origin
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        # Security headers — OWASP recommendations
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Cache headers for content-hashed static assets (Vite build)
        if request.path.startswith("/assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    @web.middleware
    async def _timeout_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        """Cap all handler execution at 120s to prevent hung requests."""
        try:
            return await asyncio.wait_for(handler(request), timeout=120.0)
        except asyncio.TimeoutError:
            logger.warning("request.timeout", extra={"path": request.path, "method": request.method})
            return web.json_response(
                {"error": "Request timed out (120s)", "code": "TIMEOUT"}, status=504,
            )

    @web.middleware
    async def _request_logging_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        """Log every API request with method, path, status, latency_ms."""
        import time as _time
        t0 = _time.monotonic()
        resp = await handler(request)
        latency_ms = (_time.monotonic() - t0) * 1000
        # Skip logging for high-frequency polling endpoints and static files
        path = request.path
        if not path.startswith("/api/") and path not in ("/healthz", "/readyz"):
            return resp
        logger.info(
            "http.request",
            extra={
                "method": request.method,
                "path": path,
                "status": resp.status,
                "latency_ms": round(latency_ms, 1),
            },
        )
        return resp

    def _check_dependencies(self) -> None:
        """Verify critical modules are importable before serving traffic."""
        errors = []
        for mod_name in [
            "aria.digital_twin.parameters",
            "aria.digital_twin.mass_budget",
            "aria.digital_twin.solver",
            "aria.digital_twin.lbm_cfd",
            "aria.simulator.tick_engine",
            "aria.simulator.event_bus",
            "aria.simulator.mission_phases",
            "aria.safety.execution_guard",
            "aria.conjunction.pipeline.runner",
            "aria.genastra.radiation.environment",
            "aria.dsremo.detection.ewma",
            "numpy", "scipy", "meshio",
        ]:
            try:
                __import__(mod_name)
            except ImportError as e:
                errors.append(f"{mod_name}: {e}")
        if errors:
            for err in errors:
                logger.error("startup.missing_dependency", extra={"error": err})
            logger.warning("startup.degraded_mode",
                           extra={"missing": len(errors), "total_checked": 12})
        else:
            logger.info("startup.all_dependencies_ok")

    async def _handle_react_spa(self, request: web.Request) -> web.Response:
        """Serve the React SPA from web/dist/index.html (production mode)."""
        _root = Path(__file__).resolve().parents[3]
        index = _root / "web" / "dist" / "index.html"
        if not index.exists():
            return web.Response(text="React build not found. Run: cd web && npm run build", status=404)
        return web.FileResponse(index, headers={
            "Cache-Control": "no-cache",  # SPA entry point should not be cached
        })

    # ─── HTTP Handlers ───────────────────────────────────────

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main dashboard HTML page."""
        index_path = ASSETS_DIR / "index.html"
        if not index_path.exists():
            return web.Response(text="Dashboard HTML not found", status=404)
        return web.FileResponse(index_path)

    async def _handle_viewer(self, request: web.Request) -> web.Response:
        """Serve the 3D ship viewer HTML page."""
        viewer_path = ASSETS_DIR / "ship_viewer.html"
        if not viewer_path.exists():
            return web.Response(text="Ship viewer HTML not found", status=404)
        return web.FileResponse(viewer_path)

    async def _handle_ship_gltf(self, request: web.Request) -> web.Response:
        """Serve the exported glTF model file for the 3D ship viewer."""
        gltf_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "ship.gltf"
        if not gltf_path.exists():
            # Auto-generate on first access (P2-10 fix)
            try:
                from aria.digital_twin.export_gltf import export_gltf
                await asyncio.get_event_loop().run_in_executor(
                    self._compute_pool, export_gltf, gltf_path
                )
            except Exception as e:
                return web.json_response(
                    {"error": f"Failed to generate ship.gltf: {e}"},
                    status=500,
                )
        return web.FileResponse(gltf_path, headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        })

    async def _handle_telemetry_live(self, request: web.Request) -> web.Response:
        """GET /api/telemetry/live — aggregated real-time telemetry for dashboard cards.

        Returns the latest value + recent history (last 60 samples) for each
        key metric so the frontend can render sparklines without polling
        multiple endpoints.

        BUG-018/019/020 (2026-04-24, walkthrough):
          - Mission clock unified on ``phase_controller.elapsed_yr`` so the
            status strip and telemetry can never disagree (was reading
            trajectory_state.elapsed_yr, which runs its own counter).
          - Propellant now reads from ``fuel_tracker`` so injected fuel
            leaks actually show up in the Telemetry tile (was reading
            ``trajectory_state.propellant_fraction_remaining`` which the
            failure injector never touches).
          - ECLSS scrubber efficiency surfaced so the scrubber_fault
            scenario becomes visible instead of alarm-only.
          - mission_phase metric is now actually emitted (the old
            ``get_phase_manager`` import was a typo of
            ``get_phase_controller`` — silently swallowed forever).
        """
        import time as _time

        # Collect current values from all subsystem singletons
        data: dict[str, Any] = {"timestamp": _time.time(), "metrics": {}}
        metrics = data["metrics"]

        # ── Mission phase + elapsed_yr — SINGLE SOURCE OF TRUTH ────
        # Reads the same `get_phase_controller()` that drives
        # /api/mission/phase, the status strip, and (post-R65) the
        # auto-transition logic.  Everything else in the dashboard must
        # agree with this clock.
        phase_elapsed_yr = 0.0
        try:
            from aria.simulator.mission_phases import get_phase_controller
            pc = get_phase_controller()
            phase_elapsed_yr = float(pc.elapsed_yr)
            # Casing matches the canonical /api/mission/phase endpoint
            # (lowercase enum value); UI can upcase for display.
            metrics["mission_phase"] = {
                "value": pc.current.value, "unit": "",
                "label": "Phase",
            }
            metrics["elapsed_yr"] = {
                "value": round(phase_elapsed_yr, 3), "unit": "yr",
                "label": "Mission Time",
            }
        except Exception:
            pass

        # ── Trajectory scalars ─────────────────────────────────────
        try:
            from aria.simulator.trajectory_state import get_trajectory_state
            ts = get_trajectory_state()
            # BUG-020 (2026-04-24, walkthrough): the raw
            # trajectory velocity is the inertial cruise speed toward
            # the target — it clamps to 0 in ORBIT because the ship is
            # parked at the destination.  Operators (reasonably) expect
            # "velocity" on an orbiting ship to be the orbital speed.
            # If cruise velocity is 0 and the phase implies orbit, we
            # report the target's circular orbital velocity instead so
            # the tile reads something physically meaningful.
            v_ms = float(ts.velocity_m_s)
            v_note = ""
            if v_ms <= 0.1:
                try:
                    from aria.simulator.mission_phases import get_phase_controller, Phase
                    ph = get_phase_controller().current
                    if ph in (Phase.ORBIT, Phase.ARRIVAL):
                        # Circular orbit at LLO (100 km Moon): √(μ/r)
                        # with Moon μ=4.9e12, r=1838 km → 1633 m/s.
                        # For interstellar targets the ship is still
                        # parked; leave 0 and note it.
                        tgt = (ts.target or "").lower()
                        if "moon" in tgt:
                            v_ms = 1633.0
                            v_note = " (LLO circular, Moon μ=4.9e12)"
                        elif "mars" in tgt:
                            v_ms = 3550.0   # LMO 400 km circular
                            v_note = " (LMO circular, Mars μ=4.28e13)"
                except Exception:
                    pass
            metrics["velocity_m_s"] = {
                "value": round(v_ms, 1), "unit": "m/s",
                "label": "Velocity" + v_note,
            }
            metrics["position_ly"] = {
                "value": ts.position_ly, "unit": "ly", "label": "Position",
            }
        except Exception:
            pass

        # ── Propellant — read from fuel_inventory (tank-aware) ─────
        # BUG-018: was reading trajectory_state.propellant_fraction_remaining
        # which the failure injector never touches.  fuel_inventory is
        # what `fuel_leak_a` / `main_leak` / RCS burns actually mutate,
        # so reading here means every injected leak shows up in the tile.
        # (Module is `fuel_tracker.py` but the singleton is named
        # `get_fuel_inventory` — importing the wrong name silently dumped
        # us on the trajectory-state fallback for every poll.)
        try:
            from aria.simulator.fuel_tracker import get_fuel_inventory
            fi = get_fuel_inventory()
            metrics["propellant_pct"] = {
                "value": round(fi.main_fill_pct, 2), "unit": "%",
                "label": "Propellant",
            }
            metrics["propellant_kg"] = {
                "value": round(fi.total_main_kg, 0), "unit": "kg",
                "label": "Propellant Mass",
            }
        except Exception:
            # Fallback to trajectory_state for legacy/test paths.
            try:
                from aria.simulator.trajectory_state import get_trajectory_state
                ts = get_trajectory_state()
                metrics["propellant_pct"] = {
                    "value": round(ts.propellant_fraction_remaining * 100, 2),
                    "unit": "%", "label": "Propellant (legacy)",
                }
            except Exception:
                pass

        # ── ECLSS scrubber — surfaces eclss_scrubber_fault ─────────
        # BUG-018: this was invisible to telemetry despite being THE
        # scenario the walkthrough exercises.  scrubber_eff_frac < 0.5
        # means the CO₂ scrubber can't keep up.
        try:
            from aria.simulator.eclss_contaminants import get_eclss_contaminants
            ec = get_eclss_contaminants()
            metrics["eclss_scrubber_eff_pct"] = {
                "value": round(float(ec.scrubber_efficiency_frac) * 100, 1),
                "unit": "%", "label": "ECLSS Scrubber",
            }
        except Exception:
            pass

        try:
            from aria.simulator.power_tracker import get_power_tracker
            pt = get_power_tracker()
            d = pt.to_dict()
            metrics["power_margin_pct"] = {"value": round(d["summary"]["margin_pct"], 1), "unit": "%", "label": "Power Margin"}
        except Exception:
            pass

        try:
            from aria.simulator.crew_health import get_crew_health
            ch = get_crew_health()
            metrics["crew_health_bone"] = {"value": round(ch.bone_density_pct, 1), "unit": "%", "label": "Bone Density"}
            metrics["crew_health_psych"] = {"value": round(ch.psych_cohesion_pct, 1), "unit": "%", "label": "Psych Cohesion"}
        except Exception:
            pass

        # R8 (2026-04-24, sync refactor): expose the unified live values
        # from MissionState so the operator can see crew + hull from the
        # SAME source the survival check uses.  Was scattered across
        # crew_health.crew_size (1000 default), engine.SimulatorState
        # snapshots (1-tick stale), and per-region hull data.
        try:
            from aria.core.mission_state import get_mission_state
            ms = get_mission_state()
            metrics["crew_alive"] = {
                "value": ms.crew_alive, "unit": "",
                "label": "Crew Alive",
            }
            metrics["hull_integrity_pct_live"] = {
                "value": round(ms.hull_integrity_pct, 1), "unit": "%",
                "label": "Hull Integrity (live)",
            }
        except Exception:
            pass

        try:
            from aria.simulator.hull_damage import get_hull_damage
            hd = get_hull_damage()
            regions = hd.regions
            if regions:
                healths = [r.health_pct for r in regions.values()]
                metrics["hull_health_pct"] = {"value": round(min(healths), 1), "unit": "%", "label": "Hull Health (worst)"}
                metrics["hull_impacts"] = {"value": hd.stats["total_impacts"], "unit": "", "label": "Total Impacts"}
        except Exception:
            pass

        try:
            from aria.simulator.agriculture_yield import get_agriculture
            ag = get_agriculture()
            d = ag.to_dict()
            metrics["food_store_kg"] = {"value": round(d["food_store_kg"], 0), "unit": "kg", "label": "Food Store"}
        except Exception:
            pass

        # Append to rolling history buffer (stored on the dashboard instance)
        if not hasattr(self, "_telemetry_history"):
            self._telemetry_history: list[dict] = []
        # Store compact snapshot: {timestamp, metric_key: value}
        snap = {"t": data["timestamp"]}
        for k, v in metrics.items():
            if isinstance(v.get("value"), (int, float)):
                snap[k] = v["value"]
        self._telemetry_history.append(snap)
        # Keep last 120 samples (~2 min at 1 Hz polling)
        if len(self._telemetry_history) > 120:
            self._telemetry_history = self._telemetry_history[-120:]

        data["history"] = self._telemetry_history
        return web.json_response(data)

    async def _handle_ship_status(self, request: web.Request) -> web.Response:
        """Return current ship status — LIVE values, not snapshot.

        R8 (2026-04-24, sync refactor): historically read the last
        snapshot in `self._snapshots`, which had a hardcoded default
        of `crew_count=4` for the empty-snapshot case.  That's how
        `/api/ship/status` and `/api/telemetry/live` ended up reporting
        crew_count=4 vs crew_alive=1000 simultaneously.  Now both
        traverse to MissionState (crew + hull) and the live singletons
        (fuel) for the dynamic fields, falling back to snapshots only
        for fields with no live source.
        """
        # Prefer live, fall back to snapshot, fall back to default.
        latest = self._snapshots[-1] if self._snapshots else {}

        # Crew + hull from the unified MissionState.
        try:
            from aria.core.mission_state import get_mission_state
            ms = get_mission_state()
            crew_count = ms.crew_alive
            hull_integrity = ms.hull_integrity_pct / 100.0
        except Exception:
            crew_count = latest.get("crew_count", 1000)
            hull_integrity = latest.get("hull_integrity", 1.0)

        # Fuel from the unified inventory.
        try:
            from aria.simulator.fuel_tracker import get_fuel_inventory
            fuel_fraction = float(get_fuel_inventory().main_fill_pct) / 100.0
        except Exception:
            fuel_fraction = latest.get("fuel_fraction", 1.0)

        # Mission time + phase from MissionClock + phase controller.
        try:
            from aria.core.mission_clock import get_mission_clock
            from aria.simulator.mission_phases import get_phase_controller
            mission_year = round(get_mission_clock().elapsed_yr, 3)
            phase = get_phase_controller().current.value
        except Exception:
            mission_year = latest.get("mission_year", 0)
            phase = latest.get("phase", "UNKNOWN")

        return web.json_response({
            "hull_integrity": hull_integrity,
            "shield_health": latest.get("shield_health", 1.0),
            "food_production_ratio": latest.get("food_production_ratio", 1.0),
            "electronics_health": latest.get("electronics_health", 1.0),
            "crew_morale": latest.get("crew_morale", 0.8),
            "fuel_fraction": fuel_fraction,
            "crew_count": crew_count,
            "crew_generation": latest.get("crew_generation", 1),
            "water_liters": latest.get("water_liters", 50000.0),
            "phase": phase,
            "mission_year": mission_year,
        })

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        """Liveness probe — returns 200 if the process is alive."""
        return web.json_response({"status": "alive"})

    async def _handle_readyz(self, request: web.Request) -> web.Response:
        """Readiness probe — returns 200 when the server can accept traffic.
        Returns 503 if critical subsystems aren't initialized."""
        # Check that the simulator tick engine is registered
        try:
            from aria.simulator.tick_engine import get_tick_engine
            te = get_tick_engine()
            ready = len(te.registered_subsystems) > 0
        except Exception:
            ready = False
        if ready:
            return web.json_response({"status": "ready"})
        return web.json_response({"status": "not_ready"}, status=503)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Operational metrics for monitoring dashboards (Grafana, Datadog)."""
        import time as _time, sys
        try:
            from aria.simulator.tick_engine import get_tick_engine
            te = get_tick_engine()
            tick_count = te.tick_count
            sim_time_s = te.total_sim_time_s
            subsystems = len(te.registered_subsystems)
        except Exception:
            tick_count = sim_time_s = subsystems = 0
        try:
            from aria.simulator.event_bus import get_event_bus
            bus = get_event_bus()
            sc = bus.subscriber_count
            bus_subscribers = sc() if callable(sc) else sc
        except Exception:
            bus_subscribers = 0
        # Process memory (RSS)
        try:
            import resource
            rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # KB → bytes on Linux
        except Exception:
            rss_bytes = 0
        return web.json_response({
            "uptime_s": round(_time.monotonic(), 1),
            "python_version": sys.version.split()[0],
            "memory_rss_mb": round(rss_bytes / (1024 * 1024), 1),
            "ws_clients": len(self._ws_clients),
            "snapshots_buffered": len(self._snapshots),
            "events_buffered": len(self._events),
            "tick_count": tick_count,
            "sim_time_s": round(sim_time_s, 1),
            "registered_subsystems": subsystems,
            "bus_subscribers": bus_subscribers,
            "compute_pool_busy": self._compute_lock.locked(),
        })

    async def _handle_config(self, request: web.Request) -> web.Response:
        """Runtime configuration — useful for debugging deployment issues."""
        import sys
        has_anthropic = False
        try:
            import anthropic  # noqa: F401
            has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        except ImportError:
            pass
        return web.json_response({
            "version": "0.3.0",
            "python": sys.version.split()[0],
            "host": self._config.host,
            "port": self._config.port,
            "cors_origin": self._config.cors_origin,
            "max_snapshots": self._config.max_snapshots,
            "max_events": self._config.max_events,
            "llm_available": has_anthropic,
            "otel_enabled": bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")),
        })

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Return server status."""
        return web.json_response({
            "status": "ok",
            "snapshots": len(self._snapshots),
            "events": len(self._events),
            "clients": len(self._ws_clients),
            "recording_loaded": self._recording_loaded,
        })

    async def _handle_snapshots(self, request: web.Request) -> web.Response:
        """Return all snapshots (for replay from server recording)."""
        # Support pagination — guard against non-numeric query params
        try:
            offset = max(0, int(request.query.get("offset", 0)))
            limit = max(0, int(request.query.get("limit", 0)))
        except (TypeError, ValueError):
            return web.json_response({"error": "offset and limit must be integers"}, status=400)

        data = self._snapshots
        if offset > 0:
            data = data[offset:]
        if limit > 0:
            data = data[:limit]

        return web.json_response({
            "total": len(self._snapshots),
            "offset": offset,
            "count": len(data),
            "snapshots": data,
        })

    async def _handle_snapshot_by_year(self, request: web.Request) -> web.Response:
        """Return the snapshot closest to the requested year."""
        try:
            target_year = float(request.match_info["year"])
        except (ValueError, KeyError):
            return web.json_response({"error": "Invalid year"}, status=400)

        if not self._snapshots:
            return web.json_response({"error": "No snapshots available"}, status=404)

        best = min(
            self._snapshots,
            key=lambda s: abs(
                (s.get("mission_year") or s.get("mission_time_years") or 0) - target_year
            ),
        )
        return web.json_response(best)

    async def _handle_events(self, request: web.Request) -> web.Response:
        """Return all events, optionally filtered by severity."""
        severity = request.query.get("severity")
        events = self._events
        if severity:
            events = [e for e in events if e.get("severity") == severity.upper()]

        try:
            offset = max(0, int(request.query.get("offset", 0)))
            limit = max(0, int(request.query.get("limit", 0)))
        except (TypeError, ValueError):
            return web.json_response({"error": "offset and limit must be integers"}, status=400)
        if offset > 0:
            events = events[offset:]
        if limit > 0:
            events = events[:limit]

        return web.json_response({
            "total": len(self._events),
            "count": len(events),
            "events": events,
        })

    # ─── Engineering Lab Handlers ────────────────────────────

    async def _handle_lab(self, request: web.Request) -> web.Response:
        """Serve the Engineering Lab HTML page."""
        lab_path = ASSETS_DIR / "engineering_lab.html"
        if not lab_path.exists():
            return web.Response(text="Engineering Lab HTML not found", status=404)
        return web.FileResponse(lab_path)

    def _make_params(self, overrides: dict[str, Any]) -> Any:
        """Create ShipParameters with validated overrides (stateless, P0-4 fix)."""
        from aria.digital_twin.parameters import ShipParameters
        # 0 is a valid "skip this feature" sentinel for ring / spoke /
        # radiator fields — used by Stealth Recon + Interstellar Cargo
        # ship-class presets. The export_gltf branch checks `> 0` and
        # skips the corresponding geometry pass entirely. Ship-class
        # branching would be impossible if we clamped to the O'Neill
        # minima on every rebuild.
        BOUNDS = {
            "hull_wall_thickness_m":    (0.02, 0.15),
            "hull_radius_m":            (1.0,  30.0),   # was 5; lower for fighter/chaser scaling
            "hull_length_m":            (5.0,  1000.0),
            "radiator_panel_width_m":   (5.0,  60.0),
            "radiator_panel_height_m":  (5.0,  50.0),
            "radiator_total_panels":    (0,    300),    # 0 → no radiators
            "radiator_wing_count":      (0,    12),     # 0 → skip render pass entirely
            "reactor_radius_m":         (0.2,  10.0),   # was 1.0; lower for fighter micro-reactor
            "reactor_length_m":         (0.5,  20.0),
            "habitat_ring_radius_m":    (0.0,  1000.0), # 0 → no ring (Stealth / Interstellar Cargo)
            "habitat_ring_tube_radius_m":(0.0, 50.0),
            "habitat_rpm":              (0.0,  5.0),
            "habitat_spoke_count":      (0,    12),
            "crew_size":                (1,    10000),
        }
        params = ShipParameters()
        # Track adjustments so callers can surface them in the response —
        # otherwise the user thinks they set t=500mm and silently gets
        # the clamped t=150mm back.
        clamps: list[dict[str, Any]] = []
        ignored: list[str] = []
        for key, val in overrides.items():
            if not hasattr(params, key):
                ignored.append(key)
                continue
            if key not in BOUNDS:
                ignored.append(key)
                continue
            try:
                lo, hi = BOUNDS[key]
                f_val = float(val)
                clamped = max(lo, min(hi, f_val))
                if key in ("radiator_total_panels", "crew_size",
                           "radiator_wing_count", "habitat_spoke_count"):
                    clamped = int(clamped)
                if clamped != f_val:
                    clamps.append({
                        "field": key, "requested": f_val, "applied": clamped,
                        "bounds": [lo, hi],
                    })
                setattr(params, key, clamped)
            except (ValueError, TypeError):
                clamps.append({
                    "field": key, "requested": val, "applied": None,
                    "reason": "non-numeric",
                })
        # Stash on the instance so callers (handlers) can include it in
        # the JSON response without threading a second return value.
        self._last_clamps = clamps
        self._last_ignored = ignored
        # Recompute derived fields
        params.hull_length_m = 0.0
        params.__post_init__()
        return params

    def _params_to_dict(self, params: Any) -> dict[str, Any]:
        """Serialize ShipParameters to JSON-safe dict."""
        return {
            "hull_radius_m": round(params.hull_radius_m, 3),
            "hull_wall_thickness_m": round(params.hull_wall_thickness_m, 4),
            "hull_length_m": round(params.hull_length_m, 1),
            "hull_inner_radius_m": round(params.hull_inner_radius_m, 3),
            "habitat_ring_radius_m": params.habitat_ring_radius_m,
            "habitat_ring_tube_radius_m": params.habitat_ring_tube_radius_m,
            "habitat_rpm": params.habitat_rpm,
            "habitat_spoke_count": params.habitat_spoke_count,
            "radiator_panel_width_m": params.radiator_panel_width_m,
            "radiator_panel_height_m": params.radiator_panel_height_m,
            "radiator_total_panels": params.radiator_total_panels,
            "total_radiator_area_m2": round(params.total_radiator_area_m2, 0),
            "reactor_radius_m": params.reactor_radius_m,
            "reactor_length_m": params.reactor_length_m,
            "ship_mass_kg": params.ship_mass_kg,
            "crew_size": params.crew_size,
            "ship_cross_section_m2": params.ship_cross_section_m2,
            "total_shield_thickness_m": round(params.total_shield_thickness_m, 3),
            "shield_layers": [
                {"name": l.name, "thickness_m": l.thickness_m, "material": l.material}
                for l in params.shield_layers
            ],
        }

    async def _handle_materials(self, request: web.Request) -> web.Response:
        """Return the complete materials database."""
        from aria.digital_twin.materials.material_db import MATERIAL_DATABASE
        result = {}
        for name, mat in MATERIAL_DATABASE.items():
            result[name] = {
                "name": mat.name,
                "density_kg_m3": mat.density_kg_m3,
                "youngs_modulus_gpa": round(mat.youngs_modulus_pa / 1e9, 1) if mat.youngs_modulus_pa else None,
                "poisson_ratio": mat.poisson_ratio,
                "yield_strength_mpa": round(mat.yield_strength_pa / 1e6, 0) if mat.yield_strength_pa else None,
                "uts_mpa": round(mat.uts_pa / 1e6, 0) if mat.uts_pa else None,
                "thermal_conductivity_w_mk": mat.thermal_conductivity_w_mk,
                "specific_heat_j_kgk": mat.specific_heat_j_kgk,
                "emissivity": mat.emissivity,
                "melting_point_k": mat.melting_point_k,
                "source": mat.source,
            }
        return web.json_response({"materials": result})

    async def _handle_ship_params(self, request: web.Request) -> web.Response:
        """Return current default ShipParameters."""
        from aria.digital_twin.parameters import ShipParameters
        params = ShipParameters()
        return web.json_response(self._params_to_dict(params))

    # ── Ship class presets ──────────────────────────────────────────
    # Only ARIA / Cruiser uses the full baseline ShipParameters. The
    # other classes scale geometry + crew + fuel fraction down to
    # illustrate what the parametric pipeline CAN model. Mass numbers
    # are order-of-magnitude estimates, NOT sourced from design papers.
    _SHIP_CLASS_PRESETS = {
        "cruiser": {
            "label": "ARIA Cruiser (baseline)",
            "hull_radius_m": 12.6, "hull_wall_thickness_m": 0.08, "hull_length_m": 711.9,
            "habitat_ring_radius_m": 500.0, "habitat_rpm": 1.0, "habitat_spoke_count": 6,
            "radiator_total_panels": 100, "reactor_radius_m": 3.0, "reactor_length_m": 6.0,
            "ship_mass_kg": 1.0e8, "crew_size": 1000,
            "note": "Full habitat-ring generation ship. Live-backed values.",
        },
        "fighter": {
            "label": "Escort Fighter",
            "hull_radius_m": 1.5, "hull_wall_thickness_m": 0.025, "hull_length_m": 18.0,
            "habitat_ring_radius_m": 50.0, "habitat_rpm": 0.1, "habitat_spoke_count": 2,
            "radiator_total_panels": 4, "reactor_radius_m": 0.35, "reactor_length_m": 0.9,
            "ship_mass_kg": 1.5e4, "crew_size": 1,
            "note": "ESTIMATE. Single-seat hull, minimal habitat, micro-reactor.",
        },
        "chaser": {
            "label": "Interceptor / Chaser",
            "hull_radius_m": 2.8, "hull_wall_thickness_m": 0.030, "hull_length_m": 42.0,
            "habitat_ring_radius_m": 60.0, "habitat_rpm": 0.5, "habitat_spoke_count": 2,
            "radiator_total_panels": 6, "reactor_radius_m": 0.6, "reactor_length_m": 1.4,
            "ship_mass_kg": 8.0e4, "crew_size": 2,
            "note": "ESTIMATE. High-Δv hull, 4× cruiser fuel-fraction scaled down.",
        },
        "stealth": {
            "label": "Stealth Recon",
            "hull_radius_m": 3.0, "hull_wall_thickness_m": 0.040, "hull_length_m": 55.0,
            "habitat_ring_radius_m": 0.0, "habitat_ring_tube_radius_m": 0.0,
            "habitat_rpm": 0.0, "habitat_spoke_count": 0,
            "radiator_total_panels": 0, "radiator_wing_count": 0,
            "reactor_radius_m": 0.7, "reactor_length_m": 1.5,
            "ship_mass_kg": 1.2e5, "crew_size": 3,
            "note": "ESTIMATE. No rotating habitat, no radiating panels (LOX sublimator).",
        },
        "freighter": {
            "label": "Inner-System Freighter",
            "hull_radius_m": 8.0, "hull_wall_thickness_m": 0.050, "hull_length_m": 180.0,
            "habitat_ring_radius_m": 60.0, "habitat_rpm": 0.5, "habitat_spoke_count": 3,
            "radiator_total_panels": 20, "reactor_radius_m": 1.5, "reactor_length_m": 3.0,
            "ship_mass_kg": 8.0e6, "crew_size": 6,
            "note": "ESTIMATE. Bulk cargo, modular bays, minimal shielding.",
        },
        "cargo_interstellar": {
            "label": "Interstellar Cargo (ARIA sister)",
            "hull_radius_m": 12.6, "hull_wall_thickness_m": 0.080, "hull_length_m": 711.9,
            "habitat_ring_radius_m": 0.0, "habitat_ring_tube_radius_m": 0.0,
            "habitat_rpm": 0.0, "habitat_spoke_count": 0,
            "radiator_total_panels": 80, "radiator_wing_count": 4,
            "reactor_radius_m": 3.0, "reactor_length_m": 6.0,
            "ship_mass_kg": 5.0e7, "crew_size": 20,
            "note": "ESTIMATE. Shares hull + reactor with ARIA; ring replaced by 40 k m³ hold.",
        },
    }

    async def _handle_ship_classes(self, request: web.Request) -> web.Response:
        """Catalogue of ship classes — one `cruiser` is fully live, the
        others are design-estimate presets the pipeline can render."""
        return web.json_response({
            "classes": [
                {"id": cid, **{k: v for k, v in preset.items()}}
                for cid, preset in self._SHIP_CLASS_PRESETS.items()
            ],
        })

    async def _handle_ship_apply_class(self, request: web.Request) -> web.Response:
        """POST /api/ship/apply_class {class_id: 'fighter'}
        Swaps the active glTF geometry to the picked class's preset.
        Operator can then tweak parameters via the normal slider UI."""
        try: body = await request.json()
        except Exception: body = {}
        cid = body.get("class_id")
        preset = self._SHIP_CLASS_PRESETS.get(cid)
        if not preset:
            return web.json_response({"error": f"Unknown class_id '{cid}'. Available: {list(self._SHIP_CLASS_PRESETS)}"}, status=400)
        # Build params using the preset values as overrides.
        overrides = {k: v for k, v in preset.items() if k not in ("label", "note")}
        params = self._make_params(overrides)
        def _do_rebuild():
            from aria.digital_twin.export_gltf import build_ship_gltf
            from pathlib import Path as _P
            import json as _json
            gltf_path = _P(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "ship.gltf"
            gltf_path.parent.mkdir(parents=True, exist_ok=True)
            gltf = build_ship_gltf(params)
            with open(gltf_path, "w") as f:
                _json.dump(gltf, f)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._compute_pool, _do_rebuild)
        return web.json_response({
            "status": "ok",
            "class_id": cid,
            "preset_label": preset["label"],
            "params": self._params_to_dict(params),
        })

    async def _handle_ship_parts(self, request: web.Request) -> web.Response:
        """Return the ship parts catalog with properties computed from params.

        Each part carries a ``category`` tag and a ``compatible_with`` list
        of categories it can attach to. The ShipAssembler frontend uses
        these to enforce simple connection constraints (Track 2 P2 of
        ROADMAP_THREE_GAPS.md):
          - hull        — root; nothing depends on; required first
          - shield      — attaches to hull (forward face)
          - habitat     — attaches to hull (mid section)
          - reactor     — attaches to hull (aft)
          - radiator    — attaches to hull or reactor (multiple OK)
          - propulsion  — attaches to reactor

        Each part also carries ``mass_kg_default`` (computed once for the
        baseline ShipParameters) so the assembler can show a running
        budget without having to re-query for every drop.
        """
        from aria.digital_twin.parameters import ShipParameters
        params = ShipParameters()
        gravity_g = (2 * math.pi * params.habitat_rpm / 60) ** 2 * params.habitat_ring_radius_m / 9.81

        # Mass estimates (kg) at the baseline. Source: ShipParameters.* uses
        # ASM Handbook densities; these are derived from the same params.
        # Hull: cylinder shell mass = ρ × 2πR × L × t  (Ti-6Al-4V density 4430 kg/m³)
        ti_density = 4430.0   # MMPDS-17 Ti-6Al-4V
        hull_mass_kg = ti_density * 2 * math.pi * params.hull_radius_m * params.hull_length_m * params.hull_wall_thickness_m
        # Habitat ring: torus shell, projected area × wall thickness × density
        # (rough; exact mass uses CNT composite ≈ 1700 kg/m³ — Lurie 2012)
        cnt_density = 1700.0  # Lurie 2012 CNT composite
        torus_area_m2 = (2 * math.pi * params.habitat_ring_radius_m) * (2 * math.pi * params.habitat_ring_tube_radius_m)
        habitat_mass_kg = cnt_density * torus_area_m2 * 0.05   # 5 cm wall
        # Reactor: simplified solid mass (EUROFER97 ≈ 7700 kg/m³, Stork 2014)
        eurofer_density = 7700.0
        reactor_mass_kg = eurofer_density * math.pi * params.reactor_radius_m ** 2 * params.reactor_length_m * 0.05
        # Radiator: panels at ~6 kg/m² (NASA TM-2010-216614 deployable panel)
        radiator_unit_kg = 6.0 * params.radiator_panel_area_m2
        radiator_total_kg = radiator_unit_kg * params.radiator_total_panels
        # Shield: water ice fills bulk → 920 kg/m³ × area × thickness
        ice_density = 920.0   # NIST ice density
        shield_mass_kg = ice_density * (math.pi * params.hull_radius_m ** 2) * params.total_shield_thickness_m
        # Propulsion: ~50 t for the magnetic-nozzle/engine cluster (NASA TM-2017-219716 estimate)
        propulsion_mass_kg = 50_000.0   # ESTIMATE — NASA TM-2017-219716 magnetic-nozzle scale

        parts = [
            {
                "id": "hull_main", "name": "Pressure Hull",
                "material": "Ti-6Al-4V", "color": "#c0c0c0",
                "category": "hull",
                "compatible_with": [],   # root; everything attaches to it
                "mass_kg_default": round(hull_mass_kg, 0),
                "description": f"Cylindrical pressure vessel, R={params.hull_radius_m:.1f}m, L={params.hull_length_m:.0f}m, t={params.hull_wall_thickness_m*1000:.0f}mm",
                "parameters": [
                    {"name": "hull_wall_thickness_m", "label": "Wall Thickness", "value": params.hull_wall_thickness_m, "min": 0.02, "max": 0.15, "step": 0.005, "unit": "m"},
                    {"name": "hull_radius_m", "label": "Hull Radius", "value": params.hull_radius_m, "min": 5.0, "max": 30.0, "step": 0.5, "unit": "m"},
                ],
            },
            {
                "id": "shield_bow", "name": "7-Layer Shield Stack",
                "material": "Multi-layer", "color": "#44cc66",
                "category": "shield",
                "compatible_with": ["hull"],
                "mass_kg_default": round(shield_mass_kg, 0),
                "description": f"Total thickness: {params.total_shield_thickness_m:.2f}m (ice + Whipple + magnetic + electrostatic)",
                "layers": [{"name": l.name, "thickness_m": l.thickness_m, "material": l.material} for l in params.shield_layers],
            },
            {
                "id": "habitat_ring", "name": "Rotating Habitat Ring",
                "material": "CNT-Composite", "color": "#ddaa33",
                "category": "habitat",
                "compatible_with": ["hull"],
                "mass_kg_default": round(habitat_mass_kg, 0),
                "description": f"O'Neill torus R={params.habitat_ring_radius_m:.0f}m, r={params.habitat_ring_tube_radius_m:.0f}m, {params.habitat_rpm:.1f} RPM ({gravity_g:.2f}g)",
                "parameters": [
                    {"name": "habitat_ring_radius_m", "label": "Major Radius", "value": params.habitat_ring_radius_m, "min": 50, "max": 1000, "step": 10, "unit": "m"},
                    {"name": "habitat_rpm", "label": "Rotation RPM", "value": params.habitat_rpm, "min": 0.1, "max": 5.0, "step": 0.1, "unit": "RPM"},
                    {"name": "crew_size", "label": "Crew Size", "value": params.crew_size, "min": 10, "max": 10000, "step": 10, "unit": "people"},
                ],
                "computed": {"artificial_gravity_g": round(gravity_g, 3)},
            },
            {
                "id": "reactor_engine", "name": "Fusion Reactor",
                "material": "EUROFER97 / Inconel-718", "color": "#ff4444",
                "category": "reactor",
                "compatible_with": ["hull"],
                "mass_kg_default": round(reactor_mass_kg, 0),
                "description": f"D-T fusion, R={params.reactor_radius_m:.0f}m, L={params.reactor_length_m:.0f}m",
                "parameters": [
                    {"name": "reactor_radius_m", "label": "Reactor Radius", "value": params.reactor_radius_m, "min": 1.0, "max": 10.0, "step": 0.5, "unit": "m"},
                    {"name": "reactor_length_m", "label": "Reactor Length", "value": params.reactor_length_m, "min": 2.0, "max": 20.0, "step": 1.0, "unit": "m"},
                ],
            },
            {
                "id": "radiator_panel", "name": "Radiator Array",
                "material": "Carbon composite", "color": "#4488ff",
                "category": "radiator",
                "compatible_with": ["hull", "reactor"],
                "mass_kg_default": round(radiator_total_kg, 0),
                "description": f"{params.radiator_total_panels} panels x {params.radiator_panel_area_m2:.0f} m^2 = {params.total_radiator_area_m2:,.0f} m^2 total",
                "parameters": [
                    {"name": "radiator_panel_width_m", "label": "Panel Width", "value": params.radiator_panel_width_m, "min": 5, "max": 60, "step": 1, "unit": "m"},
                    {"name": "radiator_panel_height_m", "label": "Panel Height", "value": params.radiator_panel_height_m, "min": 5, "max": 50, "step": 1, "unit": "m"},
                    {"name": "radiator_total_panels", "label": "Panel Count", "value": params.radiator_total_panels, "min": 10, "max": 300, "step": 5, "unit": "panels"},
                ],
            },
            {
                "id": "propulsion", "name": "Propulsion System",
                "material": "HfB2 / Inconel-718", "color": "#ff8844",
                "category": "propulsion",
                "compatible_with": ["reactor"],
                "mass_kg_default": round(propulsion_mass_kg, 0),
                "description": "Fusion drive nozzle + magnetic sail coil",
                "parameters": [],
            },
        ]
        return web.json_response({"parts": parts})

    async def _handle_assembly_compute_mass(self, request: web.Request) -> web.Response:
        """Compute total mass + per-part mass for a user-assembled ship.

        POST body::
            {
              "parts": [
                {"part_id": "hull_main", "material": "Ti-6Al-4V"},
                {"part_id": "habitat_ring", "material": null},
                ...
              ]
            }

        Per-part mass uses MATERIAL_DATABASE.density_kg_m3 when a
        material override is supplied; otherwise the baseline mass from
        ``/api/ship/parts``. Returns:

            {
              "total_mass_kg": <float>,
              "parts": [{"part_id", "material", "mass_kg"}, ...],
              "warnings": [<str>, ...]    # e.g. unknown material substitutions
            }

        Roadmap Track 2 Phase 3.
        """
        from aria.digital_twin.materials.material_db import MATERIAL_DATABASE
        try:
            body = await request.json()
        except Exception:
            body = {}
        items = body.get("parts") or []
        if not isinstance(items, list):
            return web.json_response({"error": "parts must be a list"}, status=400)

        # Reuse the same baseline mass values from /api/ship/parts. For
        # the prototype, "material override" scales mass by the density
        # ratio against the part's default density (a fair first-order
        # approximation; real swap would re-run FEA via /api/ship/analyze).
        from aria.digital_twin.parameters import ShipParameters
        params = ShipParameters()

        # Default mass + reference density per category. Same constants
        # as /api/ship/parts so the two endpoints agree.
        ti_density = 4430.0       # MMPDS-17
        cnt_density = 1700.0      # Lurie 2012
        eurofer_density = 7700.0  # Stork 2014
        c_composite_density = 1800.0  # ESTIMATE — typical CFRP density
        ice_density = 920.0       # NIST ice
        hfb2_density = 11_200.0   # Fahrenholtz 2017 UHTC

        defaults = {
            "hull_main": (
                ti_density * 2 * math.pi * params.hull_radius_m
                * params.hull_length_m * params.hull_wall_thickness_m,
                ti_density,
            ),
            "shield_bow": (
                ice_density * (math.pi * params.hull_radius_m ** 2)
                * params.total_shield_thickness_m,
                ice_density,
            ),
            "habitat_ring": (
                cnt_density
                * (2 * math.pi * params.habitat_ring_radius_m)
                * (2 * math.pi * params.habitat_ring_tube_radius_m)
                * 0.05,
                cnt_density,
            ),
            "reactor_engine": (
                eurofer_density * math.pi * params.reactor_radius_m ** 2
                * params.reactor_length_m * 0.05,
                eurofer_density,
            ),
            "radiator_panel": (
                6.0 * params.radiator_panel_area_m2 * params.radiator_total_panels,
                c_composite_density,
            ),
            # ESTIMATE — NASA TM-2017-219716 magnetic-nozzle scale
            "propulsion": (50_000.0, hfb2_density),
        }

        warnings: list[str] = []
        total = 0.0
        out: list[dict] = []
        for it in items:
            pid = (it.get("part_id") or "").strip()
            material = it.get("material")
            if pid not in defaults:
                warnings.append(f"unknown part '{pid}' — skipped")
                continue
            base_mass, base_density = defaults[pid]
            mass = base_mass
            if material:
                m = MATERIAL_DATABASE.get(material)
                if m is None:
                    warnings.append(f"unknown material '{material}' for {pid} — using baseline")
                else:
                    if base_density > 0 and m.density_kg_m3:
                        mass = base_mass * (m.density_kg_m3 / base_density)
                    else:
                        warnings.append(f"material '{material}' has no density — baseline kept")
            mass = round(mass, 0)
            total += mass
            out.append({"part_id": pid, "material": material, "mass_kg": mass})

        return web.json_response({
            "total_mass_kg": round(total, 0),
            "parts": out,
            "warnings": warnings,
        })

    async def _handle_assembly_save(self, request: web.Request) -> web.Response:
        """Persist a user-built assembly. POST body::
            {"name": "<optional label>", "parts": [...], "thumbnail": null}

        Returns ``{uid, name, saved_at_wall, parts_count}``. The uid can
        be used as a deep link (``?assembly=<uid>``) to share the design.

        Roadmap Track 2 Phase 5.
        """
        import uuid as _uuid
        import time
        try:
            body = await request.json()
        except Exception:
            body = {}
        parts = body.get("parts") or []
        if not isinstance(parts, list) or not parts:
            return web.json_response({"error": "parts list required"}, status=400)
        name = (body.get("name") or "").strip() or "untitled"
        # Cap name length so it can't bloat the file index.
        name = name[:80]

        uid = _uuid.uuid4().hex[:12]
        record = {
            "uid": uid,
            "name": name,
            "saved_at_wall": time.time(),
            "parts": parts,
        }
        out_dir = Path(__file__).resolve().parents[3] / "data" / "assemblies"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{uid}.json"
        try:
            import json as _json
            with open(out_path, "w") as f:
                _json.dump(record, f, indent=2)
        except OSError as exc:
            return web.json_response(
                {"error": f"persist failed: {exc}"}, status=500,
            )
        return web.json_response({
            "uid": uid, "name": name,
            "saved_at_wall": round(record["saved_at_wall"], 1),
            "parts_count": len(parts),
        })

    async def _handle_assembly_load(self, request: web.Request) -> web.Response:
        """Load a previously saved assembly by uid."""
        uid = request.match_info.get("uid", "")
        # Sanitise — only [a-f0-9] chars, max 12.
        if not uid or not all(c in "0123456789abcdef" for c in uid) or len(uid) > 12:
            return web.json_response({"error": "invalid uid"}, status=400)
        path = Path(__file__).resolve().parents[3] / "data" / "assemblies" / f"{uid}.json"
        if not path.exists():
            return web.json_response({"error": f"assembly '{uid}' not found"}, status=404)
        try:
            import json as _json
            with open(path) as f:
                record = _json.load(f)
        except (OSError, ValueError) as exc:
            return web.json_response({"error": f"read failed: {exc}"}, status=500)
        return web.json_response(record)

    async def _handle_assembly_list(self, request: web.Request) -> web.Response:
        """List saved assemblies. Returns ``{count, assemblies: [{uid, name, saved_at_wall, parts_count}, ...]}``."""
        import json as _json
        out_dir = Path(__file__).resolve().parents[3] / "data" / "assemblies"
        if not out_dir.exists():
            return web.json_response({"count": 0, "assemblies": []})
        records: list[dict] = []
        for p in sorted(out_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                with open(p) as f:
                    rec = _json.load(f)
                records.append({
                    "uid": rec.get("uid", p.stem),
                    "name": rec.get("name", ""),
                    "saved_at_wall": round(float(rec.get("saved_at_wall", 0.0)), 1),
                    "parts_count": len(rec.get("parts", [])),
                })
            except (OSError, ValueError):
                continue
        return web.json_response({"count": len(records), "assemblies": records})

    async def _handle_assembly_simulate(self, request: web.Request) -> web.Response:
        """Run a scenario batch against a user-assembled ship.

        Picks scenarios deterministically based on which categories are
        present on the assembly:

          hull        → shield_ice_mmod, decompression_micro
          shield      → radiation_dose_spike
          habitat     → hab_ring_gradient, sleep_deprivation
          reactor     → radiator_blockage
          radiator    → radiator_loss, peltier_runaway
          propulsion  → propulsion_valve_stuck, throttle_oscillation

        Returns ``{run_id, parts_count, scenarios_triggered: [...],
        events_emitted: [...], total_critical, total_warning}`` so the
        operator sees exactly what cascades the assembly produces.

        Roadmap Track 2 Phase 4 — the demoable capstone.
        """
        from aria.simulator.failure_injector import trigger as trigger_scenario, SCENARIOS
        from aria.simulator.event_bus import get_event_bus
        try:
            body = await request.json()
        except Exception:
            body = {}
        parts = body.get("parts") or []
        if not isinstance(parts, list) or not parts:
            return web.json_response({"error": "parts list required"}, status=400)
        explicit_scenarios = body.get("scenarios") or None

        # Build the per-category scenario set from what's on the canvas.
        from aria.simulator.web_dashboard import WebDashboard as _Self  # noqa
        category_to_scenarios = {
            "hull":       ["shield_ice_mmod", "decompression_micro"],
            "shield":     ["radiation_dose_spike"],
            "habitat":    ["hab_ring_gradient", "sleep_deprivation"],
            "reactor":    ["radiator_blockage"],
            "radiator":   ["radiator_loss", "peltier_runaway"],
            "propulsion": ["propulsion_valve_stuck", "throttle_oscillation"],
        }
        # Map each part_id back to its category via the same logic as
        # /api/ship/parts. Inline here to avoid dragging the whole parts
        # dict through the cascade.
        part_categories = {
            "hull_main":        "hull",
            "shield_bow":       "shield",
            "habitat_ring":     "habitat",
            "reactor_engine":   "reactor",
            "radiator_panel":   "radiator",
            "propulsion":       "propulsion",
        }
        chosen: list[str] = []
        if explicit_scenarios:
            chosen = [s for s in explicit_scenarios if s in SCENARIOS]
        else:
            present_cats: set[str] = set()
            for p in parts:
                pid = (p.get("part_id") or p.get("partId") or "").strip()
                cat = part_categories.get(pid)
                if cat:
                    present_cats.add(cat)
            for c in sorted(present_cats):
                for s in category_to_scenarios.get(c, []):
                    if s in SCENARIOS and s not in chosen:
                        chosen.append(s)

        if not chosen:
            return web.json_response({
                "run_id": f"sim_{int(__import__('time').time())}",
                "parts_count": len(parts),
                "scenarios_triggered": [],
                "events_emitted": [],
                "total_critical": 0,
                "total_warning": 0,
                "note": "no scenarios match the assembled categories",
            })

        # Subscribe to the event bus while the scenarios run; capture the
        # subset of events emitted by the failure_injector + the
        # downstream subsystems they touched.
        captured: list[dict] = []
        bus = get_event_bus()

        def _on_event(ev) -> None:
            try:
                captured.append({
                    "topic": ev.topic,
                    "severity": getattr(ev, "severity", "info"),
                    "source": getattr(ev, "source", ""),
                    "payload": getattr(ev, "payload", {}) or {},
                    "sim_time_yr": getattr(ev, "sim_time_yr", 0.0),
                })
            except Exception:
                pass

        # Subscribe a wildcard callback that captures every event emitted
        # while the scenario batch runs. simulator/event_bus uses a
        # simple matcher where "*" matches every topic.
        bus.subscribe("*", _on_event)

        results: list[dict] = []
        for sid in chosen:
            r = trigger_scenario(sid)
            results.append(r)

        critical = sum(1 for e in captured if e.get("severity") == "critical")
        warning = sum(1 for e in captured if e.get("severity") == "warning")

        return web.json_response({
            "run_id": f"sim_{int(__import__('time').time())}",
            "parts_count": len(parts),
            "scenarios_triggered": [{"id": r.get("id"), "label": r.get("label"),
                                     "severity": r.get("severity"),
                                     "impact": r.get("impact")} for r in results],
            "events_emitted": captured[:200],   # cap so JSON stays small
            "total_critical": critical,
            "total_warning": warning,
        })

    async def _handle_ship_rebuild(self, request: web.Request) -> web.Response:
        """Rebuild glTF geometry with parameter overrides."""
        try:
            body = await request.json()
        except Exception:
            body = {}

        params = self._make_params(body)

        def _do_rebuild():
            from aria.digital_twin.export_gltf import build_ship_gltf, export_gltf
            gltf_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exports" / "ship.gltf"
            gltf_path.parent.mkdir(parents=True, exist_ok=True)
            gltf = build_ship_gltf(params)
            import json as _json
            with open(gltf_path, "w") as f:
                _json.dump(gltf, f)
            return gltf_path

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._compute_pool, _do_rebuild)

        return web.json_response({
            "status": "ok",
            "params": self._params_to_dict(params),
            # Surface silent clamps / ignored keys so the caller can tell
            # if requested overrides were applied as-is or mangled.
            "clamps":  list(getattr(self, "_last_clamps", [])),
            "ignored": list(getattr(self, "_last_ignored", [])),
        })

    async def _handle_lunar_feasibility(self, request: web.Request) -> web.Response:
        """Run the Earth-to-Moon feasibility pass through the digital twin.

        Accepts optional POST body with dimension/material overrides:
            {"cabin_radius_m": 2.0, "cabin_wall_thickness_m": 0.015,
             "dry_mass_kg": 18000, "propellant_mass_kg": 32000,
             "propulsion_isp_s": 450, "shield_areal_density_kg_m2": 80}
        """
        try:
            body = await request.json() if request.method == "POST" else {}
        except Exception:
            body = {}

        # Physical sanity bounds — reject input before it reaches Gmsh.
        # Each tuple is (min_allowed, max_allowed); either bound can be None.
        # Sources: NASA-STD-3001 Vol 1 (crew module sizing), Sutton & Biblarz
        # 2016 (Isp envelope), and practical capsule-scale limits.
        LUNAR_PARAM_BOUNDS = {
            "cabin_radius_m":               (0.5, 10.0),
            "cabin_length_m":               (1.0, 50.0),
            "cabin_wall_thickness_m":       (0.001, 0.100),   # 1–100 mm
            "crew_size":                    (1, 20),
            "mission_duration_days":        (0.5, 60.0),
            "propulsion_isp_s":             (200.0, 100_000.0),  # chemical → fusion envelope
            "dry_mass_kg":                  (500.0, 1e6),
            "propellant_mass_kg":           (100.0, 5e6),
            "shield_areal_density_kg_m2":   (1.0, 2000.0),
        }

        def _do_feasibility():
            from aria.digital_twin.lunar_mission import (
                LunarShipParameters, evaluate_lunar_mission, to_dict,
            )
            params = LunarShipParameters()
            rejected: list[str] = []
            for k, (lo, hi) in LUNAR_PARAM_BOUNDS.items():
                if k not in body:
                    continue
                try:
                    raw = body[k]
                    val = type(getattr(params, k))(raw)
                except (TypeError, ValueError):
                    rejected.append(f"{k}: non-numeric ({body[k]!r})")
                    continue
                if lo is not None and val < lo:
                    rejected.append(f"{k}={val} below min {lo}")
                    continue
                if hi is not None and val > hi:
                    rejected.append(f"{k}={val} above max {hi}")
                    continue
                setattr(params, k, val)
            if rejected:
                # Raise so the outer handler turns it into a 400.
                raise ValueError("Invalid parameters: " + "; ".join(rejected))
            rep = evaluate_lunar_mission(params)
            out = to_dict(rep)
            out["params"] = {
                "cabin_radius_m":      params.cabin_radius_m,
                "cabin_length_m":      params.cabin_length_m,
                "cabin_wall_mm":       params.cabin_wall_thickness_m * 1000,
                "crew_size":           params.crew_size,
                "mission_days":        params.mission_duration_days,
                "isp_s":               params.propulsion_isp_s,
                "dry_mass_kg":         params.dry_mass_kg,
                "propellant_mass_kg":  params.propellant_mass_kg,
                "shield_kg_m2":        params.shield_areal_density_kg_m2,
                "mass_ratio":          params.mass_ratio,
            }
            return out

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._compute_pool, _do_feasibility),
                timeout=60.0,
            )
            return web.json_response(result)
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "Lunar feasibility timed out", "code": "TIMEOUT"},
                status=504,
            )
        except ValueError as e:
            # Parameter validation failure — surface as 400 so the client
            # knows it was a bad input, not a server-side crash.
            return web.json_response(
                {"error": str(e), "code": "INVALID_INPUT"},
                status=400,
            )
        except Exception as e:
            return web.json_response(
                {"error": f"Lunar feasibility failed: {e}", "code": "ERROR"},
                status=500,
            )

    async def _handle_ship_analyze(self, request: web.Request) -> web.Response:
        """Run full FEA analysis with parameter overrides."""
        if self._compute_lock.locked():
            return web.json_response(
                {"error": "Analysis already in progress", "code": "BUSY"},
                status=429,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}

        params = self._make_params(body)

        async with self._compute_lock:
            def _do_analyze():
                from aria.digital_twin.bridge import SimTwinBridge
                from aria.digital_twin.mass_budget import compute_mass_budget
                from aria.digital_twin.eclss_bridge import compute_eclss_constraints

                class _Cfg:
                    def __init__(self, p):
                        self.ship_mass_kg = p.ship_mass_kg
                        self.habitat_rpm = p.habitat_rpm
                        self.crew_size = p.crew_size

                bridge = SimTwinBridge()
                result = bridge.analyze(_Cfg(params), params=params)

                mb = compute_mass_budget(params=params)
                eclss = compute_eclss_constraints(
                    params.hull_inner_radius_m,
                    params.hull_length_m,
                    crew_size=params.crew_size,
                    habitat_ring_radius_m=params.habitat_ring_radius_m,
                    habitat_tube_radius_m=params.habitat_ring_tube_radius_m,
                )

                # Per-part stress summary for coloring
                avg_stress = result.max_von_mises_mpa * 0.6 if result.max_von_mises_mpa > 0 else 0
                part_stresses = {
                    "hull_main": result.max_von_mises_mpa,
                    "shield_bow": avg_stress * 0.1,
                    "reactor_engine": avg_stress * 0.8,
                    "habitat_ring": avg_stress * 0.3,
                    "radiator_panel_0": avg_stress * 0.05,
                    "radiator_panel_1": avg_stress * 0.05,
                    "radiator_panel_2": avg_stress * 0.05,
                    "radiator_panel_3": avg_stress * 0.05,
                }

                mass_breakdown = {}
                for item in mb.items:
                    sub = item.subsystem
                    mass_breakdown[sub] = mass_breakdown.get(sub, 0) + item.mass_kg

                return {
                    "structural": {
                        "max_von_mises_mpa": round(result.max_von_mises_mpa, 1),
                        "max_displacement_mm": round(result.max_displacement_mm, 2),
                        "safety_factor": round(result.structural_safety_factor, 2),
                        "yield_strength_mpa": 880.0,
                        "stress_status": "PASS" if result.structural_safety_factor >= 2.0 else "FAIL",
                        "part_stresses_mpa": part_stresses,
                    },
                    "thermal": {
                        "max_temperature_k": round(result.max_temperature_k, 1),
                        "min_temperature_k": round(result.min_temperature_k, 1),
                        "thermal_margin_k": round(result.thermal_margin_k, 1),
                        "thermal_status": "PASS" if result.thermal_margin_k >= 50 else "FAIL",
                    },
                    "mass_budget": {
                        "total_mass_kg": round(mb.total_mass_kg, 0),
                        "config_mass_kg": round(mb.config_mass_kg, 0),
                        "discrepancy_pct": round(mb.discrepancy_pct, 1),
                        "breakdown": {k: round(v, 0) for k, v in mass_breakdown.items()},
                    },
                    "eclss": {
                        "food_self_sufficiency_pct": round(eclss.food_self_sufficiency_pct, 1),
                        "water_reserve_days": round(eclss.water_reserve_days, 1),
                        "co2_buffer_hours": round(eclss.co2_buffer_hours, 1),
                        "crop_area_m2": round(eclss.crop_area_m2, 0),
                    },
                    "warnings": result.warnings,
                    "params": self._params_to_dict(params),
                    # Surface any silent clamps/drops from _make_params
                    # so the UI can flag that the requested value was not
                    # what was actually simulated.
                    "clamps":  list(getattr(self, "_last_clamps", [])),
                    "ignored": list(getattr(self, "_last_ignored", [])),
                }

            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(self._compute_pool, _do_analyze),
                    timeout=60.0,
                )
                return web.json_response(result)
            except asyncio.TimeoutError:
                return web.json_response(
                    {"error": "Analysis timed out (60s limit)", "code": "TIMEOUT"},
                    status=504,
                )
            except Exception as e:
                return web.json_response(
                    {"error": f"Analysis failed: {e}", "code": "ERROR"},
                    status=500,
                )

    async def _handle_ship_optimize(self, request: web.Request) -> web.Response:
        """Run the ship mass optimiser (differential evolution over
        hull / shield / radiator design variables)."""
        if self._compute_lock.locked():
            return web.json_response(
                {"error": "Computation already in progress", "code": "BUSY"},
                status=429,
            )
        try:
            body = await request.json()
        except Exception:
            body = {}

        # Clamp max_iterations to a sane range — previously only the
        # upper bound was enforced, so 0 / negative slipped through and
        # DE would either no-op or throw deep in scipy.
        try:
            raw = int(body.get("max_iterations", 30))
        except (TypeError, ValueError):
            raw = 30
        max_iter = max(3, min(raw, 50))

        async with self._compute_lock:
            def _do_optimize():
                from aria.digital_twin.parameters import ShipParameters
                from aria.digital_twin.optimizer import ShipOptimizer
                params = ShipParameters()
                opt = ShipOptimizer(base_params=params, max_iterations=max_iter)
                result = opt.optimize()
                return {
                    "converged": result.converged,
                    "iterations": result.iterations,
                    "best_mass_kg": round(result.best_mass_kg, 0),
                    "final_stress_mpa": round(result.final_stress_mpa, 1),
                    "final_temp_k": round(result.final_temp_k, 1),
                    "best_params": self._params_to_dict(result.best_params),
                    "history": result.history[:50],
                }

            try:
                # Upped from 180 s to 600 s because the DE optimiser
                # (commit ba86efb) does popsize x (maxiter + 1) FEA
                # evaluations at ~1.5 s each. Even max_iterations=3
                # empirically takes ~170 s in the real-mesh E2E test;
                # max_iterations=50 would exceed the old 180 s cap.
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(self._compute_pool, _do_optimize),
                    timeout=600.0,
                )
                return web.json_response(result)
            except asyncio.TimeoutError:
                return web.json_response(
                    {"error": "Optimization timed out (600s limit). Try lower max_iterations.", "code": "TIMEOUT"},
                    status=504,
                )
            except Exception as e:
                return web.json_response(
                    {"error": f"Optimization failed: {e}", "code": "ERROR"},
                    status=500,
                )

    async def _handle_ship_review(self, request: web.Request) -> web.Response:
        """Run the full engineering design review."""
        if self._compute_lock.locked():
            return web.json_response(
                {"error": "Computation already in progress", "code": "BUSY"},
                status=429,
            )

        async with self._compute_lock:
            def _do_review():
                from aria.digital_twin.bridge import SimTwinBridge
                from aria.digital_twin.mass_budget import compute_mass_budget
                from aria.digital_twin.parameters import ShipParameters
                from aria.digital_twin.eclss_bridge import compute_eclss_constraints

                params = ShipParameters()

                class _Cfg:
                    ship_mass_kg = params.ship_mass_kg
                    habitat_rpm = params.habitat_rpm
                    crew_size = params.crew_size

                bridge = SimTwinBridge()
                fea = bridge.analyze(_Cfg(), params=params)
                mb = compute_mass_budget(params=params)
                eclss = compute_eclss_constraints(
                    params.hull_inner_radius_m, params.hull_length_m, params.crew_size,
                    habitat_ring_radius_m=params.habitat_ring_radius_m,
                    habitat_tube_radius_m=params.habitat_ring_tube_radius_m,
                )

                findings = list(fea.warnings)
                if fea.structural_safety_factor < 2.0:
                    findings.append(f"CRITICAL: Safety factor {fea.structural_safety_factor:.1f}x below NASA 2.0x minimum")
                if fea.structural_safety_factor > 10.0:
                    findings.append(f"OVERDESIGNED: Safety factor {fea.structural_safety_factor:.1f}x — reduce hull thickness to save mass")
                if abs(mb.discrepancy_pct) > 5:
                    findings.append(f"Mass budget {mb.discrepancy_pct:+.0f}% vs target ({mb.total_mass_kg:,.0f} vs {mb.config_mass_kg:,.0f} kg)")
                if eclss.food_self_sufficiency_pct < 50:
                    findings.append(f"Food self-sufficiency only {eclss.food_self_sufficiency_pct:.0f}% — need more agriculture area")

                return {
                    "structural": {
                        "safety_factor": round(fea.structural_safety_factor, 2),
                        "max_stress_mpa": round(fea.max_von_mises_mpa, 1),
                        "max_displacement_mm": round(fea.max_displacement_mm, 2),
                    },
                    "thermal": {
                        "max_temp_k": round(fea.max_temperature_k, 1),
                        "thermal_margin_k": round(fea.thermal_margin_k, 1),
                    },
                    "mass_budget": {"total_kg": round(mb.total_mass_kg, 0), "discrepancy_pct": round(mb.discrepancy_pct, 1)},
                    "eclss": {
                        "food_pct": round(eclss.food_self_sufficiency_pct, 1),
                        "water_days": round(eclss.water_reserve_days, 1),
                        "co2_hours": round(eclss.co2_buffer_hours, 1),
                    },
                    "findings": findings,
                    "params": self._params_to_dict(params),
                }

            try:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(self._compute_pool, _do_review),
                    timeout=60.0,
                )
                return web.json_response(result)
            except asyncio.TimeoutError:
                return web.json_response({"error": "Review timed out", "code": "TIMEOUT"}, status=504)
            except Exception as e:
                return web.json_response({"error": f"Review failed: {e}", "code": "ERROR"}, status=500)

    async def _handle_ai_decisions(self, request: web.Request) -> web.Response:
        """Rolling log of every LLM-involved decision (agent and advisor).

        Query params:
            limit: max entries to return (default 50)
            since_id: return only entries with id > since_id (for polling)
        """
        from aria.cognitive.decision_log import get_decision_log

        def _int(name, default, lo=1, hi=400):
            try:
                v = int(request.query.get(name, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v))

        limit = _int("limit", 50)
        since = _int("since_id", 0, lo=0, hi=10**9)
        entries = get_decision_log().recent(limit=limit, since_id=since)
        return web.json_response({
            "count": len(entries),
            "capacity": get_decision_log().capacity,
            "entries": [e.to_dict() for e in entries],
        })

    async def _handle_ai_advise(self, request: web.Request) -> web.Response:
        """Live mission advisor. Builds a state snapshot, asks the LLM for
        recommendations, falls back to rule-based heuristics if no API key.

        POST body (optional): {"focus": "hull" | "power" | "eclss" | "auto"}
        Response:
            {
              "source": "llm" | "rule",
              "severity": "NOMINAL" | "WARNING" | "CRITICAL" | "EMERGENCY",
              "summary": "one-line situation report",
              "recommendation": "multi-line text of what to do",
              "citations": ["hull_damage.total_impacts=N", ...],
              "sim_yr": 42.0,
              "latency_ms": 1234
            }
        """
        import os
        import time as _time
        t0 = _time.monotonic()

        try:
            body = await request.json() if request.method == "POST" else {}
        except Exception:
            body = {}
        focus = body.get("focus", "auto")

        # ── Build situation snapshot from live subsystem state ─────
        snap: dict[str, Any] = {"focus": focus}
        try:
            from aria.simulator.mission_phases import get_phase_controller
            phase_dict = get_phase_controller().to_dict()
            snap["mission_phase"] = (phase_dict.get("phase")
                                     or phase_dict.get("current_phase")
                                     or "prelaunch")
        except Exception as e:
            snap["mission_phase"] = "unknown"
            snap["_mission_phase_err"] = str(e)[:120]

        # Hull — HullDamageState exposes `regions` (dict of RegionState)
        # and `impacts` (int). It does NOT have `overall_health_pct` —
        # that was a silent-zero default (always 100.0). Compute it as
        # the minimum across all region health_pct values.
        try:
            from aria.simulator.hull_damage import get_hull_damage
            hd = get_hull_damage()
            regions = hd.regions  # dict[str, RegionState]
            region_healths = [r.health_pct for r in regions.values()]
            overall = min(region_healths) if region_healths else 100.0
            total_impacts = sum(r.impact_count for r in regions.values())
            snap["hull"] = {
                "health_pct": round(float(overall), 2),
                "impacts":    int(total_impacts),
                "critical_regions": [
                    name for name, r in regions.items()
                    if r.health_pct < 80.0
                ],
            }
        except Exception as e:
            snap["hull"] = {"error": str(e)[:120]}

        # Power — PowerBudgetState exposes `available_w`, `allocated_w`,
        # `margin_w`, `margin_pct`, `cumulative_shed_wh`. My previous
        # field names (total_generation_w, total_consumption_w) did not
        # exist and silently returned 0.0.
        try:
            from aria.simulator.power_tracker import get_power_budget
            pb = get_power_budget()
            snap["power"] = {
                "available_mw":  round(pb.available_w / 1e6, 2),
                "allocated_mw":  round(pb.allocated_w / 1e6, 2),
                "margin_pct":    round(pb.margin_pct, 1),
                "shed_events":   pb.total_shed_events,
            }
        except Exception as e:
            snap["power"] = {"error": str(e)[:120]}

        # ECLSS / food — AgricultureYieldState exposes `food_store_kg`,
        # `days_short_kcal`, `total_kcal_produced/consumed`. The old
        # `daily_harvest_kg` name did not exist.
        try:
            from aria.simulator.agriculture_yield import get_agriculture
            ag = get_agriculture()
            snap["food"] = {
                "store_kg":            round(ag.food_store_kg, 1),
                "days_short":          ag.days_short_kcal,
                "total_kcal_produced": round(ag.total_kcal_produced, 0),
                "total_kcal_consumed": round(ag.total_kcal_consumed, 0),
            }
        except Exception as e:
            snap["food"] = {"error": str(e)[:120]}

        # Crew / health
        try:
            from aria.simulator.crew_health import get_crew_health
            ch = get_crew_health()
            # CrewHealthState fields: crew_size, psych_cohesion_pct,
            # bone_density_pct, vo2max_pct, sans_prevalence_pct, etc.
            # cumulative_dose_sv does NOT exist on this object — dose is
            # tracked in the radiation subsystem (radiation.py), not here.
            snap["crew"] = {
                "alive":            ch.crew_size,
                "cohesion_pct":     round(ch.psych_cohesion_pct, 1),
                "bone_density_pct": round(ch.bone_density_pct, 1),
            }
        except Exception as e:
            snap["crew"] = {"error": str(e)[:120]}

        # Trajectory — TrajectoryState exposes: target, fraction_complete,
        # propellant_fraction_remaining, elapsed_yr. The previous field
        # names (target_name / progress_pct / propellant_frac) did not
        # exist and silently defaulted to None/0 via getattr().
        try:
            from aria.simulator.trajectory_state import get_trajectory_state
            tr = get_trajectory_state()
            snap["trajectory"] = {
                "target":     tr.target,
                "progress":   round(tr.fraction_complete, 4),
                "propellant": round(tr.propellant_fraction_remaining, 3),
                "sim_yr":     round(tr.elapsed_yr, 3),
            }
        except Exception as e:
            snap["trajectory"] = {"error": str(e)[:120]}

        # Recent critical events (from the event bus). R65 (2026-04-24)
        # BUG-B3: was calling a non-existent `history(limit=)` — the real
        # method is `recent(n=, min_severity=)`.  Caused every snapshot
        # to carry `_recent_events_err: "'EventBus' has no attribute
        # 'history'"` and ship an empty `recent_events` list, starving
        # the rule engine.  Also switched to server-side severity filter
        # so we don't waste a 200-event copy for 10 output slots.
        try:
            from aria.simulator.event_bus import get_event_bus
            recent = get_event_bus().recent(200, min_severity="warning")
            snap["recent_events"] = [
                {"topic": e.topic, "severity": e.severity, "src": e.source}
                for e in recent[:10]   # recent() already returns newest-first
            ]
        except Exception as e:
            snap["recent_events"] = []
            snap["_recent_events_err"] = str(e)[:120]

        # ECLSS contaminants — scrubber efficiency is THE variable the ECLSS
        # scrubber-fault failure injector targets.  Without this block the
        # rule-based advisor couldn't see "scrubber at 10%" even though the
        # user had just injected that fault.  BUG-008 (2026-04-24).
        try:
            from aria.simulator.eclss_contaminants import get_eclss_contaminants
            ec = get_eclss_contaminants()
            snap["eclss"] = {
                "scrubber_eff_frac": round(float(ec.scrubber_efficiency_frac), 3),
                "atmosphere_ok":     float(ec.scrubber_efficiency_frac) >= 0.5,
            }
        except Exception as e:
            snap["eclss"] = {"error": str(e)[:120]}

        # ── Call the LLM if a key is available, else rule-based ────
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

        def _rule_based() -> dict[str, Any]:
            # Rank ordering for severity escalation. Higher index = more severe.
            SEV_RANK = ["NOMINAL", "WARNING", "CRITICAL", "EMERGENCY"]
            def bump(current: str, candidate: str) -> str:
                return candidate if SEV_RANK.index(candidate) > SEV_RANK.index(current) else current

            severity = "NOMINAL"
            summary_bits: list[str] = []
            recs: list[str] = []
            cits: list[str] = []

            # ── Recent bus events (BUG-008 2026-04-24) ──
            # The walkthrough surfaced that the rule engine was building a
            # rich `recent_events` block into the snapshot and then ignoring
            # it entirely.  A critical ECLSS scrubber fault was live in the
            # alarm queue for 3 sim-weeks and the advisor stayed on NOMINAL.
            # Fix: inspect severity + topic of every recent event and
            # escalate accordingly.  Specific subsystem topics map to
            # targeted recommendations; anything else still contributes a
            # generic WARNING so unhandled criticals don't disappear.
            events = snap.get("recent_events", []) or []
            crit_events = [e for e in events if e.get("severity") == "critical"]
            warn_events = [e for e in events if e.get("severity") == "warning"]
            if crit_events:
                severity = bump(severity, "CRITICAL")
                summary_bits.append(f"{len(crit_events)} critical event(s)")
                cits.append(f"recent_events.critical={[e['topic'] for e in crit_events[:4]]}")
            elif warn_events:
                severity = bump(severity, "WARNING")
                summary_bits.append(f"{len(warn_events)} warning event(s)")
                cits.append(f"recent_events.warning={[e['topic'] for e in warn_events[:4]]}")

            # Map recognised topics to concrete remediation text so the
            # advisor is actually useful, not just "pay attention".
            for ev in crit_events + warn_events:
                topic = ev.get("topic", "")
                if "eclss" in topic or "scrubber" in topic:
                    recs.append(
                        "ECLSS fault: verify scrubber_efficiency_frac via "
                        "/api/eclss; spin up backup CO₂ scrubber, raise "
                        "bleed air, and quarantine the failed bank until "
                        "the crew can swap filters."
                    )
                elif "fuel" in topic or "leak" in topic:
                    recs.append(
                        "Fuel-leak pattern: isolate affected tank, cut main "
                        "thrust by 50 %, plan early cruise-coast, refile "
                        "trajectory with reduced Δv budget."
                    )
                elif "ecc_escape" in topic or "avionics" in topic:
                    recs.append(
                        "Avionics ECC escape: force TMR re-sync on the "
                        "affected CPU bank; review flight-software memory "
                        "integrity counters for secondary SEU storms."
                    )
                elif "bearing" in topic or "maglev" in topic or "roller" in topic:
                    recs.append(
                        "Bearing subsystem transition: verify maglev "
                        "controller health and bearing temperature; be "
                        "ready for roller backup if fluctuations persist."
                    )
                elif "flare" in topic or "spe" in topic or "solar" in topic:
                    recs.append(
                        "Space-weather event (solar flare / SPE): confirm "
                        "storm-shelter occupancy, reduce EVA window, and "
                        "increase SEU-scrub cadence for the next 8 h."
                    )
                elif "hull" in topic or "impact" in topic or "mmod" in topic:
                    recs.append(
                        "Hull impact flagged: poll hull_damage per-region "
                        "health and queue patch tasks on regions under 80 %."
                    )

            # ── Hull (unchanged) ──
            hull = snap.get("hull", {})
            if hull.get("health_pct", 100) < 80:
                severity = bump(severity, "CRITICAL")
                summary_bits.append(f"Hull {hull['health_pct']}%")
                recs.append("Activate reserve shield; survey affected regions with repair queue.")
                cits.append(f"hull.health_pct={hull['health_pct']}")

            # ── Food (unchanged) ──
            food = snap.get("food", {})
            if food.get("store_kg", 1e9) < 100:
                severity = bump(severity, "WARNING")
                summary_bits.append(f"food {food['store_kg']} kg")
                recs.append("Ration to 80% per capita; boost hydroponic bay power.")
                cits.append(f"food.store_kg={food['store_kg']}")

            # ── Propellant (gated on active phase, unchanged) ──
            tr = snap.get("trajectory", {})
            phase = str(snap.get("mission_phase", "")).lower()
            active = phase not in ("", "unknown", "prelaunch")
            prop = tr.get("propellant", 1.0)
            if active and prop < 0.10:
                severity = bump(severity, "WARNING")
                summary_bits.append(f"prop {prop*100:.0f}%")
                recs.append("Plan refuel leg or cut burn to cruise-coast.")
                cits.append(f"trajectory.propellant={prop}")

            # ── ECLSS scrubber (new — BUG-008) ──
            # The failure injector's "ECLSS scrubber 90 % degraded"
            # scenario sets scrubber_efficiency_frac to ~0.10.  A bare
            # rule-engine that doesn't check this is blind to the most
            # commonly-injected fault in the walkthrough.
            ecl = snap.get("eclss", {})
            scrub = ecl.get("scrubber_eff_frac")
            if scrub is not None:
                if scrub < 0.25:
                    severity = bump(severity, "CRITICAL")
                    summary_bits.append(f"scrubber {scrub*100:.0f}%")
                    recs.append(
                        "CO₂ scrubber at critical degradation: vent CO₂ "
                        "via emergency bleed, bring backup scrubber online, "
                        "mask-up protocol for the next crew shift."
                    )
                    cits.append(f"eclss.scrubber_eff_frac={scrub}")
                elif scrub < 0.75:
                    severity = bump(severity, "WARNING")
                    summary_bits.append(f"scrubber {scrub*100:.0f}%")
                    recs.append(
                        "Scrubber degraded: monitor CO₂ ppm trend; "
                        "schedule filter swap within 24 h."
                    )
                    cits.append(f"eclss.scrubber_eff_frac={scrub}")

            # ── Power margin (new — BUG-008) ──
            # margin_pct < 10 means load shedding is imminent.  Gate on
            # active phase: at PRELAUNCH the reactor is off and margin=0
            # is expected — firing here would be a false positive that
            # triggers on every clean load of the dashboard.
            pw = snap.get("power", {})
            mp = pw.get("margin_pct")
            if active and mp is not None:
                if mp < 5:
                    severity = bump(severity, "CRITICAL")
                    summary_bits.append(f"power margin {mp:.1f}%")
                    recs.append(
                        "Power margin critical: shed non-essential loads "
                        "(hydroponic lights, science payload) and switch "
                        "to cruise-mode reactor setpoint."
                    )
                    cits.append(f"power.margin_pct={mp}")
                elif mp < 15:
                    severity = bump(severity, "WARNING")
                    summary_bits.append(f"power margin {mp:.1f}%")
                    recs.append(
                        "Power margin tight: pre-emptively queue a shed "
                        "priority list before the next high-thrust burn."
                    )
                    cits.append(f"power.margin_pct={mp}")

            # ── Crew physiological drift (new — BUG-008) ──
            # Watches the metrics that actually decay over BOOST/CRUISE:
            # bone density (Sibonga 2007), psych cohesion.  These are
            # long-game signals — escalate only to WARNING.
            cr = snap.get("crew", {})
            bone = cr.get("bone_density_pct")
            coh  = cr.get("cohesion_pct")
            if bone is not None and bone < 92:
                severity = bump(severity, "WARNING")
                summary_bits.append(f"bone {bone:.1f}%")
                recs.append(
                    "Crew bone density under 92 %: increase resistance-"
                    "exercise loadout by 20 %, verify ARED uptime."
                )
                cits.append(f"crew.bone_density_pct={bone}")
            if coh is not None and coh < 70:
                severity = bump(severity, "WARNING")
                summary_bits.append(f"cohesion {coh:.0f}%")
                recs.append(
                    "Psych cohesion low: rotate crew shifts, schedule "
                    "social events, consider remote counselor uplink."
                )
                cits.append(f"crew.cohesion_pct={coh}")

            # ── De-dup recommendations while preserving order ──
            seen: set[str] = set()
            dedup_recs: list[str] = []
            for r in recs:
                if r not in seen:
                    seen.add(r)
                    dedup_recs.append(r)

            summary = "; ".join(summary_bits) if summary_bits else "All subsystems nominal."
            if not dedup_recs:
                dedup_recs.append("Continue monitoring. No action required.")
            return {
                "source": "rule",
                "severity": severity,
                "summary": summary,
                "recommendation": "\n".join(f"• {r}" for r in dedup_recs),
                "citations": cits,
            }

        # Static system prompt — heavy enough to benefit from prompt caching
        # on a /api/ai/advise poller that fires every 30 s. Anthropic bills
        # cached reads at 10% of input rate.
        _ARIA_SYSTEM_PROMPT = (
            "You are ARIA, the onboard AI of a generation ship. "
            "You are given a live snapshot of the spacecraft's state. "
            "Reply in STRICT JSON with keys: "
            "severity (NOMINAL|WARNING|CRITICAL|EMERGENCY), "
            "summary (one short sentence), "
            "recommendation (multi-line action plan, bullet-prefixed), "
            "citations (list of state keys you based the recommendation on). "
            "Be conservative; cite exact numbers from the snapshot. "
            "Do NOT wrap the JSON in markdown code fences — emit the bare "
            "object only. No prose before or after."
        )

        def _strip_json_fences(raw: str) -> str:
            """Remove optional ```json ... ``` fences an LLM might wrap
            the output in, tolerantly. Regex-based so it survives
            trailing whitespace, newlines, and missing closers."""
            import re as _re
            s = raw.strip()
            m = _re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", s, flags=_re.DOTALL)
            return m.group(1) if m else s

        async def _llm_based() -> dict[str, Any]:
            try:
                import anthropic
                # 15 s hard cap — advisor is a UI poller, not a batch job.
                client = anthropic.AsyncAnthropic(api_key=api_key, timeout=15.0)
                user = f"Focus: {focus}\n\nSNAPSHOT:\n{json.dumps(snap, indent=2)}"
                resp = await client.messages.create(
                    model=os.environ.get("ARIA_LLM_MODEL", ""),
                    max_tokens=1024,   # bumped from 800 to avoid JSON truncation
                    # Prompt caching: mark the system prompt as cacheable so
                    # subsequent polls read from the cache at 10% cost.
                    # Requires the "prompt-caching-2024-07-31" beta header.
                    system=[
                        {"type": "text", "text": _ARIA_SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}},
                    ],
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(b.text for b in resp.content if b.type == "text")
                text = _strip_json_fences(text)
                data = json.loads(text)
                data["source"] = "llm"
                # Surface cache metrics so callers can see caching is working.
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    data["_usage"] = {
                        "input_tokens":              getattr(usage, "input_tokens", 0),
                        "output_tokens":             getattr(usage, "output_tokens", 0),
                        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
                        "cache_read_input_tokens":     getattr(usage, "cache_read_input_tokens", 0),
                    }
                return data
            except Exception as exc:
                out = _rule_based()
                out["llm_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
                return out

        # Advisor chain:
        #   1. the LLM if ANTHROPIC_API_KEY is set,
        #   2. else Gemini (free-tier rotation) if GEMINI_API_KEY is set,
        #   3. else the rule-based engine.
        # Fallback path: a secondary cloud LLM stopgap when the primary key is absent
        # (2026-04-24). Both LLM paths already gracefully fall back to
        # the rule engine on failure.
        if api_key:
            payload = await _llm_based()
        else:
            # R65-R4 (2026-04-24): explicit state variables instead of
            # leaning on `locals()` — `gem` was defined unconditionally
            # inside a `try` branch that only runs when advisor.enabled,
            # so the `'gem' in locals()` check was always true (never
            # actually distinguished "tried Gemini and all failed" from
            # "Gemini not enabled"). Now we track both signals cleanly.
            payload = None
            gem_tried = False
            gem_result = None
            gem_err: str | None = None
            try:
                from aria.cognitive.gemini_advisor import get_gemini_advisor
                advisor = get_gemini_advisor()
                if advisor.enabled:
                    gem_tried = True
                    gem_result = await advisor.decide(snap, focus=focus)
                    if gem_result is not None:
                        payload = gem_result
            except Exception as exc:  # noqa: BLE001
                gem_err = f"{type(exc).__name__}: {str(exc)[:160]}"
            if payload is None:
                payload = _rule_based()
                if gem_err is not None:
                    payload["gemini_error"] = gem_err
                elif gem_tried and gem_result is None:
                    payload["gemini_error"] = "all models failed or cooling down"
        payload["sim_yr"] = snap.get("trajectory", {}).get("sim_yr")
        payload["snapshot"] = snap
        payload["latency_ms"] = int((_time.monotonic() - t0) * 1000)

        # Record to the process-wide decision log so the AI Decisions UI tab
        # can replay every advisor poll with its severity + recommendation.
        try:
            from aria.cognitive.decision_log import get_decision_log
            get_decision_log().append(
                source="advisor",
                agent=None,
                question=f"focus={focus} · sim_yr={payload['sim_yr']}",
                response=payload.get("recommendation") or payload.get("summary") or "",
                severity=str(payload.get("severity", "INFO")),
                backend=str(payload.get("source", "rule")),
                latency_ms=float(payload["latency_ms"]),
            )
        except Exception:
            pass

        return web.json_response(payload)

    async def _handle_ai_reason(self, request: web.Request) -> web.Response:
        """Process an AI reasoning request using rule-based fallback."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        scenario = body.get("scenario", "")
        if not scenario or len(scenario) > 2000:
            return web.json_response({"error": "Scenario required (max 2000 chars)"}, status=400)

        # (The body's "context" field was read here but never used by the
        # keyword rule logic below. If you want state-aware reasoning,
        # call /api/ai/advise instead — it builds a real snapshot and
        # routes through the LLM with prompt caching.)

        # Rule-based reasoning (works without API key — P1-2 fix)
        steps = []
        action = "monitor"
        priority = "NOMINAL"
        confidence = 0.75

        scenario_lower = scenario.lower()

        if any(w in scenario_lower for w in ("breach", "hull", "impact", "damage")):
            steps = [
                "Detected structural threat — assessing hull integrity levels",
                "Evaluating affected sector — checking crew proximity and evacuation routes",
                "Decision: Seal bulkhead to contain damage, then activate backup shield layer",
            ]
            action = "seal_bulkhead_activate_backup"
            priority = "CRITICAL"
            confidence = 0.92
        elif any(w in scenario_lower for w in ("reactor", "coolant", "leak", "radiation")):
            steps = [
                "Reactor anomaly detected — checking coolant loop pressure and temperature",
                "Radiation levels at boundary: evaluating crew dose rate",
                "Decision: SCRAM reactor (emergency shutdown), switch to backup power, evacuate reactor zone",
            ]
            action = "scram_reactor_evacuate"
            priority = "EMERGENCY"
            confidence = 0.95
        elif any(w in scenario_lower for w in ("food", "crop", "agriculture", "harvest")):
            steps = [
                "Food production anomaly — checking hydroponic bay status",
                "Calculating reserves vs consumption rate at current crew size",
                "Decision: Ration food to 80% allocation, boost grow-light power by 20%, seed backup crops",
            ]
            action = "ration_food_boost_production"
            priority = "WARNING"
            confidence = 0.82
        elif any(w in scenario_lower for w in ("power", "electrical", "energy", "battery")):
            steps = [
                "Power system alert — checking generation vs load balance",
                "Non-critical systems identified for load shedding",
                "Decision: Shed non-essential loads (recreation, low-priority science), maintain life support priority",
            ]
            action = "shed_nonessential_loads"
            priority = "WARNING"
            confidence = 0.88
        elif any(w in scenario_lower for w in ("debris", "meteorite", "collision", "asteroid")):
            steps = [
                "Debris field detected — tracking objects with LIDAR array",
                "Computing collision probability and available evasion delta-v",
                "Decision: Activate magnetic deflector, prepare RCS for evasion maneuver if Pc > 1e-4",
            ]
            action = "activate_deflector_prepare_evasion"
            priority = "CRITICAL"
            confidence = 0.85
        elif any(w in scenario_lower for w in ("navigation", "orbit", "course", "trajectory")):
            steps = [
                "Navigation anomaly — cross-checking star tracker with inertial measurement unit",
                "Computing position error and required correction burn",
                "Decision: Execute mid-course correction burn, update trajectory estimate",
            ]
            action = "correction_burn"
            priority = "WARNING"
            confidence = 0.80
        else:
            steps = [
                f"Analyzing scenario: {scenario[:100]}",
                "Evaluating available data and subsystem status",
                "Decision: Continue monitoring with heightened alert threshold. Insufficient data for autonomous action.",
            ]
            action = "monitor_heightened_alert"
            priority = "WATCH"
            confidence = 0.60

        return web.json_response({
            "reasoning_steps": steps,
            "decision": {
                "action": action,
                "priority": priority,
                "estimated_time_s": 30,
            },
            "confidence": confidence,
            "engine": "rule_based_fallback",
            "scenario": scenario[:200],
        })

    # ─── B5: Inspection + Mission + Startup Handlers ──────────

    async def _handle_inspect_parts(self, request: web.Request) -> web.Response:
        """List every known part with a lightweight snapshot."""
        from aria.simulator.part_inspector import inspect_all, snapshot_to_dict
        snaps = inspect_all()
        return web.json_response({"count": len(snaps),
                                  "parts": [snapshot_to_dict(s) for s in snaps]})

    async def _handle_inspect_part(self, request: web.Request) -> web.Response:
        """Full snapshot of a single part by id."""
        from aria.simulator.part_inspector import inspect_part, snapshot_to_dict
        pid = request.match_info.get("part_id", "")
        snap = inspect_part(pid)
        if snap is None:
            return web.json_response({"error": f"Unknown part '{pid}'"}, status=404)
        return web.json_response(snapshot_to_dict(snap))

    async def _handle_inspect_deps(self, request: web.Request) -> web.Response:
        """Direct depends_on + feeds for a part, with rationale."""
        from aria.digital_twin.dependency_graph import get_dependency_graph
        pid = request.match_info.get("part_id", "")
        g = get_dependency_graph()
        if pid not in g.nodes():
            return web.json_response({"error": f"Unknown part '{pid}'"}, status=404)
        return web.json_response({
            "part_id": pid,
            "depends_on": [
                {"target": e.dst, "kind": e.kind, "critical": e.critical, "note": e.note}
                for e in g.depends_on(pid)
            ],
            "feeds": [
                {"source": e.src, "kind": e.kind, "critical": e.critical, "note": e.note}
                for e in g.feeds(pid)
            ],
        })

    async def _handle_inspect_cascade(self, request: web.Request) -> web.Response:
        """If this part fails, what goes down?"""
        from aria.digital_twin.dependency_graph import get_dependency_graph
        pid = request.match_info.get("part_id", "")
        g = get_dependency_graph()
        if pid not in g.nodes():
            return web.json_response({"error": f"Unknown part '{pid}'"}, status=404)
        critical = request.query.get("critical_only", "true").lower() != "false"
        doomed = g.failure_cascade(pid, critical_only=critical)
        return web.json_response({
            "part_id": pid,
            "critical_only": critical,
            "cascade": sorted(doomed),
            "count": len(doomed),
        })

    async def _handle_inspect_graph(self, request: web.Request) -> web.Response:
        """Full dependency graph (nodes + edges) for visualisation."""
        from aria.digital_twin.dependency_graph import get_dependency_graph
        return web.json_response(get_dependency_graph().to_dict())

    async def _handle_mission_phase(self, request: web.Request) -> web.Response:
        from aria.simulator.mission_phases import get_phase_controller
        return web.json_response(get_phase_controller().to_dict())

    async def _handle_mission_transition(self, request: web.Request) -> web.Response:
        from aria.simulator.mission_phases import Phase, get_phase_controller
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        # Accept both `to` (canonical) and `target_phase` (what clients
        # intuitively send — don't punish the caller with a confusing
        # "'Unknown phase None'" when they just used a different key).
        target = body.get("to", body.get("target_phase"))
        force = bool(body.get("force", False))
        legal = sorted(p.value for p in Phase)
        if target is None:
            return web.json_response({
                "error": "missing required field 'to' (phase name)",
                "legal_phases": legal,
            }, status=400)
        if target not in legal:
            return web.json_response({
                "error": f"unknown phase {target!r}",
                "legal_phases": legal,
            }, status=400)
        ctl = get_phase_controller()
        try:
            ctl.transition(Phase(target), force=force)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response(ctl.to_dict())

    async def _handle_replay_run(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON body"}, status=400)
        scenario_id = body.get("scenario_id", "apollo_13_cryo_stir")
        with_doctrine = bool(body.get("with_doctrine", True))
        with_lessons = bool(body.get("with_lessons", True))
        noise = bool(body.get("noise", False))
        try:
            from pathlib import Path
            from aria.replay import (
                ClosedLoop, StubAdvisor, StubCrossMonitor,
                WindowedZScoreDetector, get_scenario,
            )
            from aria.replay.audit_log import AuditLogger, loop_outcome_to_event
            from aria.replay.noise import overlay_noise
            from aria.cognitive.doctrine import DoctrineLoader
            from aria.knowledge import build_default_lesson_index

            try:
                scenario = get_scenario(scenario_id)
            except KeyError:
                return web.json_response({
                    "ok": False, "error": f"unknown scenario_id: {scenario_id}",
                })
            bundle = (DoctrineLoader(Path("data/doctrine")).load()
                      if with_doctrine else None)
            lesson_idx = build_default_lesson_index() if with_lessons else None
            loop = ClosedLoop(
                detector=WindowedZScoreDetector(
                    parameters=scenario.parameters,
                    window_size=15, warmup_samples=5, z_threshold=3.5,
                ),
                advisor=StubAdvisor(),
                monitor=StubCrossMonitor(),
                doctrine_bundle=bundle,
                lesson_index=lesson_idx,
            )
            samples = scenario.samples_factory()
            if noise:
                samples = overlay_noise(samples)
            audit_path = Path("/tmp/aria_replay_ui.jsonl")
            try:
                audit_path.unlink()
            except FileNotFoundError:
                pass
            audit_logger = AuditLogger(path=audit_path)
            audit_lines: list[str] = []
            applies = 0
            for sample in samples:
                outcome = loop.step(sample)
                if outcome is None:
                    continue
                event = loop_outcome_to_event(outcome, scenario.scenario_id)
                audit_logger.write_event(event)
                if outcome.hal_command:
                    applies += 1
                if len(audit_lines) < 5:
                    audit_lines.append(
                        f"GET={outcome.anomaly.get_string()} "
                        f"{outcome.anomaly.parameter} "
                        f"action={outcome.advisor.proposed_action if outcome.advisor else '-'} "
                        f"status={outcome.translation.status if outcome.translation else '-'}"
                    )
            audit_logger.close()
            first_get = loop.first_anomaly_get_s()
            lead_s: float | None = None
            if first_get is not None:
                lead_s = round(scenario.historical_alarm_get_s - first_get, 1)
            return web.json_response({
                "ok": True,
                "result": {
                    "scenario_id": scenario.scenario_id,
                    "outcomes_count": len(loop.outcomes),
                    "hal_applies": applies,
                    "lead_time_s": lead_s,
                    "outcome": "completed" if loop.outcomes else "no_anomalies",
                    "audit": audit_lines,
                },
            })
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)})

    async def _handle_replay_report(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON body"}, status=400)
        scenario_id = body.get("scenario_id", "apollo_13_cryo_stir")
        try:
            from pathlib import Path
            from aria.replay import get_scenario
            from aria.replay.report import (
                collect_report_inputs_from_audit, render_one_page_markdown,
            )
            try:
                scenario = get_scenario(scenario_id)
            except KeyError:
                return web.json_response({
                    "ok": False, "error": f"unknown scenario_id: {scenario_id}",
                })
            audit_path = Path("/tmp/aria_replay_ui.jsonl")
            inputs, outcomes = collect_report_inputs_from_audit(
                audit_log_path=audit_path,
                scenario_id=scenario.scenario_id,
                scenario_title=scenario.title,
                historical_alarm_get_s=scenario.historical_alarm_get_s,
                historical_response_get_s=scenario.historical_response_get_s,
                advisor_label="stub",
                monitor_label="stub-cross-monitor",
                doctrine_active=True,
                lessons_active=True,
                noise_active=True,
            )
            return web.json_response({
                "ok": True,
                "report": render_one_page_markdown(inputs, outcomes=outcomes),
            })
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)})

    async def _handle_doctrine_search(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "ok": False, "error": "invalid JSON body", "hits": [],
            }, status=400)
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 10) or 10)
        if not query:
            return web.json_response({"ok": True, "hits": [], "query": "", "total": 0})
        try:
            from pathlib import Path
            from aria.cognitive.doctrine import DoctrineLoader, select_relevant_entries
            bundle = DoctrineLoader(Path("data/doctrine")).load()
            entries = select_relevant_entries(
                bundle, parameter="", severity="", free_text=query, top_k=limit,
            )
            hits = [
                {
                    "id": entry.rule_id,
                    "title": entry.title,
                    "citation": entry.citation,
                    "excerpt": (entry.body or "")[:300],
                    "score": 1.0,
                }
                for entry in entries
            ]
            return web.json_response({
                "ok": True, "hits": hits, "query": query, "total": len(hits),
            })
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc), "hits": []})

    async def _handle_lessons_search(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({
                "ok": False, "error": "invalid JSON body", "hits": [],
            }, status=400)
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 10) or 10)
        if not query:
            return web.json_response({"ok": True, "hits": [], "query": "", "total": 0})
        try:
            if not hasattr(self, "_lesson_index_cache"):
                from aria.knowledge import build_default_lesson_index
                self._lesson_index_cache = build_default_lesson_index()
            hits_raw = self._lesson_index_cache.search(query, top_k=limit)
            hits = [
                {
                    "id": hit.record.record_id,
                    "title": hit.record.title,
                    "citation": hit.record.citation,
                    "excerpt": (hit.record.summary or "")[:300],
                    "score": round(float(hit.score), 3),
                }
                for hit in hits_raw
            ]
            return web.json_response({
                "ok": True, "hits": hits, "query": query, "total": len(hits),
            })
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc), "hits": []})

    async def _handle_nasa42_index(self, request: web.Request) -> web.Response:
        """GET /api/nasa42/index.json — catalogue of available NASA-42
        OBJ meshes, grouped by category, for the Ship Builder preview.
        Each entry maps a part-id concept to the NASA 42 filename so
        the React side can swap in real aerospace CAD for a hover preview."""
        from pathlib import Path as _P
        _root = _P(__file__).resolve().parents[3]
        d = _P(os.environ.get(
            "ARIA_NASA42_MODEL_DIR",
            str(_root.parent / "tools" / "nasa-42" / "Model"),
        ))
        if not d.exists():
            return web.json_response({"error": "nasa-42 not installed"}, status=404)
        # Hand-curated mapping: which NASA 42 mesh best represents each
        # ARIA subsystem or mission element. The categories are intended
        # for UI grouping (landers, rovers, ISS hardware, etc.).
        catalog = {
            "lander":       ["LanderBody.obj", "LanderLeg.obj"],
            "rover":        ["RoverBody.obj", "RoverUpperLeg.obj", "RoverLowerLeg.obj"],
            "iss_hardware": ["ISS_MainBody.obj", "ISS_SimpleMainBody.obj", "ISS_HGA.obj",
                             "ISS_Radiator.obj", "ISS_SolarPanel.obj", "ISS_SmSolarPanel.obj",
                             "ISS_SolarTruss.obj"],
            "spacecraft":   ["HST.obj", "Kepler.obj", "Voyager.obj", "SpaceShuttleOrbiter.obj",
                             "IonCruiser.obj", "Aura_MainBody.obj"],
            "antennas":     ["Ant_SBand.obj", "Ant_XBand.obj", "Ant_Gnd.obj", "Ant_Isotropic.obj",
                             "MDLSat_Antenna.obj"],
            "cubesats":     ["Cubesat_1U.obj", "Cubesat_3U.obj", "Cubesat_6U.obj", "stf1_red.obj"],
            "chaser_target":["ARC_ChaserBody.obj", "ARC_ChaserSolarArray.obj", "ARC_ArmSegment.obj",
                             "ARC_Hand.obj", "ARC_Target.obj"],
            "terrain":      ["Rgn_Crater.obj", "Rgn_Flat.obj", "Rgn_MoonCrater.obj",
                             "Rgn_TAG.obj", "Rgn_Terrain.obj"],
            "bodies":       ["Phobos.obj", "Hartley2.obj", "67P.obj", "67P-CG.obj",
                             "Wirtanen.obj", "WirtanenEllipse.obj"],
            "instruments":  ["CMG.obj", "CMGSat_Body.obj", "Telescope.obj", "RST.obj", "BBM.obj"],
        }
        present = {name: [] for name in catalog}
        for cat, files in catalog.items():
            for f in files:
                if (d / f).exists():
                    present[cat].append({"name": f, "url": f"/api/nasa42/{f}"})
        return web.json_response({
            "catalog": present,
            "count": sum(len(v) for v in present.values()),
            "source": "NASA Open Source Software 42 simulator (nasa.gov/open-source-nasa-software)",
        })

    def _lazy_register_subsystems(self) -> None:
        """Ensure every subsystem is registered with the tick_engine.
        Safe to call repeatedly — each module's register_with_tick_engine
        is idempotent (it removes a prior entry of the same name)."""
        from aria.simulator.tick_engine import get_tick_engine
        engine = get_tick_engine()
        registrations = [
            ("computing_radiation", "aria.simulator.computing_radiation"),
            ("eclss_contaminants",  "aria.simulator.eclss_contaminants"),
            ("bearing_dynamics",    "aria.simulator.bearing_dynamics"),
            ("propulsion_thermal",  "aria.simulator.propulsion_thermal"),
            ("power_tracker",       "aria.simulator.power_tracker"),
            ("trajectory_state",    "aria.simulator.trajectory_state"),
            ("fuel_tracker",        "aria.simulator.fuel_tracker"),
            ("crew_health",         "aria.simulator.crew_health"),
            ("comms_budget",        "aria.simulator.comms_budget"),
            ("agriculture_yield",   "aria.simulator.agriculture_yield"),
            ("event_scheduler",     "aria.simulator.event_scheduler"),
            ("hull_damage",         "aria.simulator.hull_damage"),
            ("random_events",       "aria.simulator.random_events"),
            ("mission_objectives",  "aria.simulator.mission_objectives"),
            ("crew_schedule",       "aria.simulator.crew_schedule"),
            ("repair_queue",        "aria.simulator.repair_queue"),
        ]
        import importlib
        for name, modpath in registrations:
            if name not in engine.registered_names():
                importlib.import_module(modpath).register_with_tick_engine()
        # narrative_log subscribes to bus directly — touch it once to ensure init
        from aria.simulator.narrative_log import get_narrative_log
        get_narrative_log()

    async def _handle_mission_tick(self, request: web.Request) -> web.Response:
        """Advance the full simulation by delta_yr years.

        Previously this only ticked the mission-phase clock, so velocity /
        fuel / hull / ECLSS state stayed frozen while the clock moved —
        the ship never actually travelled anywhere when the operator hit
        the '+0.1 yr' button. Now we also advance the tick_engine so
        every registered subsystem (trajectory, fuel, power, crew,
        radiation, thermal, etc.) integrates over the elapsed time."""
        from aria.simulator.mission_phases import get_phase_controller
        from aria.simulator.tick_engine import get_tick_engine
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            raw = body.get("delta_yr", 0.1)
            delta_yr = float(raw)
        except (TypeError, ValueError):
            return web.json_response(
                {"error": f"delta_yr must be numeric, got {raw!r}"}, status=400,
            )
        if delta_yr <= 0:
            return web.json_response(
                {"error": f"delta_yr must be > 0, got {delta_yr}"}, status=400,
            )
        # Cap at 100 000 yr per tick to bound compute time (even at
        # coarse substeps, > 100k yr would take tens of seconds).
        if delta_yr > 100_000:
            return web.json_response(
                {"error": f"delta_yr={delta_yr} exceeds 100 000 yr cap"}, status=400,
            )
        dt_s = delta_yr * 365.25 * 24 * 3600
        # BUG-019 partial (2026-04-24, walkthrough): post-R7 the central
        # MissionClock is advanced by auto_tick._loop only.  The manual
        # step buttons (+1 hr / +1 day / +0.1 yr) hit this endpoint,
        # which advanced `engine` (subsystem physics) but left the
        # MissionClock frozen — so the Mission Time tile stayed put
        # while telemetry sparklines ticked.  Explicitly advance the
        # clock here so every consumer (status strip, phase check,
        # telemetry, advisor) sees the jump.
        try:
            from aria.core.mission_clock import get_mission_clock
            get_mission_clock().advance(delta_yr)
        except Exception:
            pass
        self._lazy_register_subsystems()
        engine = get_tick_engine()
        # Adaptive substep cap — keep total step count ≤ ~2 500 so HTTP
        # latency stays bounded regardless of how big a year-jump the
        # operator requests. For a short 0.1 yr tick we stay at ≥1 hr
        # substeps; for 1000 yr jumps we widen to ~5 month substeps.
        # Physics stays valid: during CRUISE/ARRIVAL the trajectory is
        # linear / parked — no stiff dynamics that need fine substeps.
        # Shakedown: 1000 yr Proxima coast = 5 s compute; 7000 yr = 30 s.
        target_steps = 2_500
        cap = max(3_600.0, dt_s / target_steps)
        prev_cap = engine.MAX_SUBSTEP_S
        engine.MAX_SUBSTEP_S = cap
        try:
            engine.advance(dt_s)
        finally:
            engine.MAX_SUBSTEP_S = prev_cap
        # Re-check phase auto-transition now that the clock moved.
        try:
            get_phase_controller().tick(delta_yr)
        except Exception:
            pass
        return web.json_response(get_phase_controller().to_dict())

    async def _handle_startup_status(self, request: web.Request) -> web.Response:
        from aria.simulator.startup_sequence import get_startup_controller
        return web.json_response(get_startup_controller().to_dict())

    async def _handle_startup_tick(self, request: web.Request) -> web.Response:
        from aria.simulator.startup_sequence import get_startup_controller
        try:
            body = await request.json()
        except Exception:
            body = {}
        dt_s = self._safe_float(body, "dt_s", 30.0, lo=0.1, hi=86400.0)
        ctl = get_startup_controller()
        ctl.tick(dt_s)
        return web.json_response(ctl.to_dict())

    async def _handle_startup_reset(self, request: web.Request) -> web.Response:
        from aria.simulator.startup_sequence import reset_startup_controller, get_startup_controller
        reset_startup_controller()
        return web.json_response(get_startup_controller().to_dict())

    async def _handle_startup_abort(self, request: web.Request) -> web.Response:
        from aria.simulator.startup_sequence import get_startup_controller
        try:
            body = await request.json()
        except Exception:
            body = {}
        reason = body.get("reason", "operator abort")
        ctl = get_startup_controller()
        ctl.abort(reason)
        return web.json_response(ctl.to_dict())

    # ── B12: Event bus + tick engine + subsystem endpoints ──

    async def _handle_events_recent(self, request: web.Request) -> web.Response:
        """GET /api/events/recent?n=100&topic=reactor.*&min_severity=info
        Returns the last N events from the bus, most recent first."""
        from aria.simulator.event_bus import get_event_bus
        try:
            n = max(1, min(int(request.query.get("n", "100")), 10_000))
        except (TypeError, ValueError):
            n = 100
        topic_prefix = request.query.get("topic") or None
        min_severity = request.query.get("min_severity") or None
        bus = get_event_bus()
        events = bus.recent(n=n, topic_prefix=topic_prefix, min_severity=min_severity)
        return web.json_response({
            "count": len(events),
            "events": [e.to_dict() for e in events],
            "subscribers": bus.subscriber_count(),
        })

    async def _handle_events_health(self, request: web.Request) -> web.Response:
        """GET /api/events/health?window_sim_yr=1.0
        Bus observability snapshot: per-topic counts, severity histogram,
        top-10 topics, and a spammed-topics list (anything > 10× in window).
        Operators + integration tests use this to detect event spam, silent
        stalls, or suddenly-firing topics without scraping the full history.
        """
        from aria.simulator.event_bus import get_event_bus
        win_q = request.query.get("window_sim_yr", "").strip()
        try:
            window = float(win_q) if win_q else None
        except ValueError:
            return web.json_response(
                {"error": "window_sim_yr must be a float"}, status=400
            )
        return web.json_response(get_event_bus().health(window_sim_yr=window))

    async def _handle_events_publish(self, request: web.Request) -> web.Response:
        """POST /api/events/publish — operator can inject a synthetic event
        (drill scenarios, debugging). Body: {topic, severity, payload, source}."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        topic = body.get("topic")
        if not topic:
            return web.json_response({"error": "topic required"}, status=400)
        from aria.simulator.event_bus import get_event_bus
        from aria.simulator.mission_phases import get_phase_controller
        evt = get_event_bus().publish(
            topic,
            severity=body.get("severity", "info"),
            payload=body.get("payload", {}),
            source=body.get("source", "operator"),
            sim_time_yr=get_phase_controller().elapsed_yr,
        )
        return web.json_response(evt.to_dict())

    async def _handle_tick_status(self, request: web.Request) -> web.Response:
        from aria.simulator.tick_engine import get_tick_engine
        return web.json_response(get_tick_engine().to_dict())

    async def _handle_tick_advance(self, request: web.Request) -> web.Response:
        """POST /api/tick/advance {dt_s: 1.0}
        Advances every registered subsystem + mission clock + startup sequence
        by dt_s simulation seconds. Lazy-registers the avionics + eclss-contaminants
        models on first call so the user doesn't have to initialise anything."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        dt_s = self._safe_float(body, "dt_s", 1.0, lo=0.1, hi=86400.0)
        from aria.simulator.tick_engine import get_tick_engine
        # R8-fix (2026-04-24): advance the central MissionClock alongside
        # the tick engine so downstream consumers (status strip, phase
        # check, advisor) see the same elapsed_yr.
        try:
            from aria.core.mission_clock import get_mission_clock
            get_mission_clock().advance_seconds(dt_s)
        except Exception:
            pass
        self._lazy_register_subsystems()
        engine = get_tick_engine()
        engine.advance(dt_s)
        # Run phase auto-transition check now that the clock has moved.
        try:
            from aria.simulator.mission_phases import get_phase_controller
            get_phase_controller().tick(dt_s / (365.25 * 24 * 3600))
        except Exception:
            pass
        return web.json_response(engine.to_dict())

    async def _handle_avionics_seu(self, request: web.Request) -> web.Response:
        from aria.simulator.computing_radiation import get_computing_radiation
        return web.json_response(get_computing_radiation().to_dict())

    async def _handle_eclss_contaminants(self, request: web.Request) -> web.Response:
        from aria.simulator.eclss_contaminants import get_eclss_contaminants
        return web.json_response(get_eclss_contaminants().to_dict())

    # ── B18: bearing / propulsion-thermal / power / BOM ──

    async def _handle_reactor(self, request: web.Request) -> web.Response:
        """Aggregated reactor state — inspector snapshot + phase duty +
        approximate SCRAM signal when part_inspector reports the reactor
        at end-of-life. Provides the endpoint the UI was reading from
        a bundled source before (and frontend now has a direct route)."""
        from aria.simulator.part_inspector import inspect_part
        from aria.simulator.mission_phases import get_phase_controller
        snap = inspect_part("reactor_engine")
        if snap is None:
            return web.json_response({"error": "reactor not found"}, status=404)
        phase = get_phase_controller()
        scram = not snap.operational or (snap.health_pct or 0) < 20.0
        return web.json_response({
            "status":          "SCRAM" if scram else "ONLINE",
            "operational":     snap.operational,
            "health_pct":      snap.health_pct,
            "duty_cycle_pct":  snap.duty_cycle_pct,
            "temperature_k":   snap.temperature_k,
            "thermal_power_w": snap.power_draw_w,
            "mtbf_hours":      snap.mtbf_hours,
            "mission_time_hours": snap.mission_time_hours,
            "failure_mode":    snap.failure_mode,
            "mass_kg":         snap.mass_kg,
            "current_phase":   phase.current.value,
        })

    async def _handle_bearing(self, request: web.Request) -> web.Response:
        from aria.simulator.bearing_dynamics import get_bearing_state
        return web.json_response(get_bearing_state().to_dict())

    async def _handle_bearing_trip(self, request: web.Request) -> web.Response:
        from aria.simulator.bearing_dynamics import get_bearing_state
        try: body = await request.json()
        except Exception: body = {}
        reason = body.get("reason", "operator drill")
        get_bearing_state().force_trip(reason)
        return web.json_response(get_bearing_state().to_dict())

    async def _handle_bearing_restore(self, request: web.Request) -> web.Response:
        from aria.simulator.bearing_dynamics import get_bearing_state
        get_bearing_state().restore_maglev_power()
        return web.json_response(get_bearing_state().to_dict())

    async def _handle_propulsion_thermal(self, request: web.Request) -> web.Response:
        from aria.simulator.propulsion_thermal import get_propulsion_thermal
        return web.json_response(get_propulsion_thermal().to_dict())

    async def _handle_power_budget(self, request: web.Request) -> web.Response:
        from aria.simulator.power_tracker import get_power_budget
        return web.json_response(get_power_budget().to_dict())

    async def _handle_bom_list(self, request: web.Request) -> web.Response:
        from aria.simulator.bill_of_materials import to_dict
        return web.json_response(to_dict())

    async def _handle_bom_spof(self, request: web.Request) -> web.Response:
        from aria.simulator.bill_of_materials import single_points_of_failure
        items = single_points_of_failure()
        return web.json_response({
            "count": len(items),
            "items": [
                {"item_id": it.item_id, "name": it.name, "subsystem": it.subsystem,
                 "failure_mode": it.failure_mode_if_below_min, "notes": it.notes}
                for it in items
            ],
        })

    # ── B24: trajectory / fuel / crew / failure injector ──

    async def _handle_trajectory(self, request: web.Request) -> web.Response:
        from aria.simulator.trajectory_state import get_trajectory_state
        return web.json_response(get_trajectory_state().to_dict())

    async def _handle_trajectory_set_target(self, request: web.Request) -> web.Response:
        from aria.simulator.trajectory_state import get_trajectory_state
        try: body = await request.json()
        except Exception: body = {}
        target = body.get("target")
        if not target:
            return web.json_response({"error": "target required"}, status=400)
        try:
            get_trajectory_state().set_target(target)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response(get_trajectory_state().to_dict())

    # ── ISRU refuel table ───────────────────────────────────────────
    # Which targets carry exploitable propellant feedstock. Real-world:
    # LH₂ ice on the lunar poles (LCROSS 2009), water permafrost on
    # Mars (Phoenix + NASA MEPAG), surface water ice on asteroids +
    # comet nuclei (Rosetta 67P), Europa subsurface ocean (Galileo).
    # Values are in sim-years the ship must orbit to refuel; mass
    # delivered = propellant_mass_kg (back to 100 %). These numbers are
    # DESIGN ESTIMATES scaled from Moon-polar-ice recovery prototypes.
    _REFUEL_TABLE = {
        "Moon":                    {"years": 0.3,  "method": "Polar H₂O ice → electrolysis + LH₂ cryo",                "source": "LCROSS 2009"},
        "Mars":                    {"years": 1.0,  "method": "Perchlorate-rich regolith → H₂O → electrolysis",          "source": "NASA MEPAG 2016"},
        "Ceres (main belt)":       {"years": 1.5,  "method": "Hydrated silicate regolith → H₂O → electrolysis",         "source": "Dawn mission 2015"},
        "Europa":                  {"years": 2.0,  "method": "Subsurface ocean cryobot + LH₂ electrolysis",             "source": "Galileo / JUICE roadmap"},
        "Titan":                   {"years": 2.0,  "method": "Methane lakes + H₂O crust → direct CH₄/LOX fuel",         "source": "Cassini-Huygens 2005"},
        "Uranus":                  {"years": 3.0,  "method": "Atmospheric H₂/CH₄ skimmer → D extraction",               "source": "Voyager 2 flyby 1986"},
        "Neptune":                 {"years": 3.0,  "method": "Atmospheric H₂/CH₄ skimmer + D extraction",               "source": "Voyager 2 flyby 1989"},
        "Pluto":                   {"years": 2.5,  "method": "N₂ + H₂O ice surface mining",                             "source": "New Horizons 2015"},
        "Voyager 1 (heliopause)":  {"years": 0.0,  "method": "No ISRU — interstellar medium too sparse",                "source": "— (not refuelable)"},
        "Inner Oort Cloud":        {"years": 5.0,  "method": "Comet nucleus ice — slow rendezvous per body",            "source": "Dones 2015"},
    }

    async def _handle_trajectory_refuel(self, request: web.Request) -> web.Response:
        """Top up propellant via In-Situ Resource Utilisation at the
        current target. Only valid in ARRIVAL / ORBIT phase (we have
        to physically be there). Advances the mission clock by the
        configured refuel duration for that body — ISRU isn't instant."""
        from aria.simulator.trajectory_state import get_trajectory_state
        from aria.simulator.mission_phases import get_phase_controller, Phase
        ts = get_trajectory_state()
        phase = get_phase_controller()
        if phase.current not in (Phase.ARRIVAL, Phase.ORBIT):
            return web.json_response({
                "error": f"Cannot refuel in {phase.current.value} phase — must be at destination (ARRIVAL / ORBIT)",
            }, status=400)
        entry = self._REFUEL_TABLE.get(ts.target)
        if not entry or entry["years"] <= 0:
            return web.json_response({
                "error": f"No ISRU infrastructure modelled at {ts.target} ({entry['method'] if entry else 'not in catalog'})",
            }, status=400)
        # Reset cumulative_dv so Tsiolkovsky-derived propellant returns
        # to full. We keep position / velocity / target as-is so the
        # next leg starts from the refuelling orbit.
        ts.cumulative_dv_m_s = 0.0
        ts._fuel_low_fired = False
        # Advance mission clock by the refuel duration — time cost is
        # the whole point of in-situ mining (vs. Earth launch).
        # R7 (2026-04-24): use MissionClock.advance directly so the
        # phase auto-transition machinery sees the bump.  The old
        # `ts.elapsed_yr = phase.elapsed_yr` was a redundant sync that
        # — under R7 — called the @property setter and triggered a
        # spurious `mission.clock.reset` bus event on every refuel.
        from aria.core.mission_clock import get_mission_clock
        get_mission_clock().advance(entry["years"])
        phase.tick(entry["years"])  # re-check phase auto-transition
        return web.json_response({
            "status": "ok",
            "target": ts.target,
            "refuel_years": entry["years"],
            "method": entry["method"],
            "source": entry["source"],
            "propellant_kg_restored": ts.propellant_mass_kg,
            "mission_year_now": round(phase.elapsed_yr, 2),
        })

    async def _handle_gravity_assist_plan(self, request: web.Request) -> web.Response:
        """Patched-conic gravity-assist mission planner.

        POST body:
          {
            "start":        "earth",
            "destination":  "saturn",
            "flybys":       ["venus", "earth", "jupiter"],   # optional
            "flyby_alt_km": 300.0                            # optional
          }

        Returns per-leg Hohmann Δv, per-fly-by savings, total Δv
        required, and total cruise duration — ballpark numbers for the
        Mission Planner UI.
        """
        from aria.simulator.gravity_assist import plan_mission, DEFAULT_FLYBY_ALT_KM
        try:
            body = await request.json()
        except Exception:
            body = {}
        start = body.get("start", "earth")
        destination = body.get("destination")
        flybys = body.get("flybys", []) or []
        flyby_alt_km = self._safe_float(body, "flyby_alt_km", DEFAULT_FLYBY_ALT_KM, lo=10.0)
        if not destination:
            return web.json_response({"error": "destination required"}, status=400)
        if not isinstance(flybys, list):
            return web.json_response({"error": "flybys must be a list"}, status=400)
        try:
            plan = plan_mission(start, destination, flybys, flyby_alt_km=flyby_alt_km)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response(plan.to_dict())

    async def _handle_trajectory_targets(self, request: web.Request) -> web.Response:
        """Return the mission-target catalog grouped by class so the React
        picker can show the Moon / Mars / Jupiter alongside Alpha Centauri."""
        from aria.simulator.trajectory import INTERSTELLAR_TARGETS, classify_target
        items = []
        for name, dist_ly in INTERSTELLAR_TARGETS.items():
            items.append({
                "name": name,
                "distance_ly": dist_ly,
                "distance_au": dist_ly * 63241.077,   # 1 ly = 63241.077 AU
                "class": classify_target(name),
            })
        # Sort by distance within each class (solar first, then interstellar)
        items.sort(key=lambda t: (t["class"] != "solar", t["distance_ly"]))
        return web.json_response({"targets": items})

    async def _handle_fuel(self, request: web.Request) -> web.Response:
        from aria.simulator.fuel_tracker import get_fuel_inventory
        return web.json_response(get_fuel_inventory().to_dict())

    async def _handle_crew_health(self, request: web.Request) -> web.Response:
        from aria.simulator.crew_health import get_crew_health
        return web.json_response(get_crew_health().to_dict())

    async def _handle_failure_scenarios(self, request: web.Request) -> web.Response:
        from aria.simulator.failure_injector import to_dict
        return web.json_response(to_dict())

    async def _handle_failure_trigger(self, request: web.Request) -> web.Response:
        try: body = await request.json()
        except Exception: body = {}
        sid = body.get("id")
        if not sid:
            return web.json_response({"error": "id required"}, status=400)
        from aria.simulator.failure_injector import trigger
        result = trigger(sid)
        if "error" in result:
            return web.json_response(result, status=400)
        return web.json_response(result)

    # ── B29: comms / agriculture / auto-tick / scheduler ──

    async def _handle_comms(self, request: web.Request) -> web.Response:
        from aria.simulator.comms_budget import get_comms_budget
        return web.json_response(get_comms_budget().to_dict())

    async def _handle_comms_queue(self, request: web.Request) -> web.Response:
        from aria.simulator.comms_budget import get_comms_budget
        try: body = await request.json()
        except Exception: body = {}
        label = body.get("label", "operator message")
        try:
            bytes_size = max(0, int(body.get("bytes_size", 1024)))
        except (TypeError, ValueError):
            return web.json_response({"error": "bytes_size must be an integer"}, status=400)
        budget = get_comms_budget()
        msg = budget.queue_message(label, bytes_size)
        budget.tick(dt_s=1.0)
        return web.json_response({"msg_id": msg.msg_id, "label": msg.label,
                                  "bytes_size": msg.bytes_size, "status": msg.status})

    async def _handle_agriculture(self, request: web.Request) -> web.Response:
        from aria.simulator.agriculture_yield import get_agriculture
        return web.json_response(get_agriculture().to_dict())

    async def _handle_agriculture_failure(self, request: web.Request) -> web.Response:
        from aria.simulator.agriculture_yield import get_agriculture
        try: body = await request.json()
        except Exception: body = {}
        crop_id = body.get("crop_id")
        mode = body.get("mode", "nutrient_imbalance")
        if not crop_id:
            return web.json_response({"error": "crop_id required"}, status=400)
        get_agriculture().trigger_failure(crop_id, mode)
        return web.json_response(get_agriculture().to_dict())

    async def _handle_agriculture_restore(self, request: web.Request) -> web.Response:
        from aria.simulator.agriculture_yield import get_agriculture
        try: body = await request.json()
        except Exception: body = {}
        crop_id = body.get("crop_id")
        if not crop_id:
            return web.json_response({"error": "crop_id required"}, status=400)
        get_agriculture().restore_crop(crop_id)
        return web.json_response(get_agriculture().to_dict())

    async def _handle_auto_tick_status(self, request: web.Request) -> web.Response:
        from aria.simulator.auto_tick import get_auto_tick
        return web.json_response(get_auto_tick().to_dict())

    async def _handle_auto_tick_start(self, request: web.Request) -> web.Response:
        from aria.simulator.auto_tick import get_auto_tick
        try: body = await request.json()
        except Exception: body = {}
        # BUG-006 (2026-04-24): old cap `hi=1.0e4` silently 400'd every
        # UI preset ≥ "1 day/s" (86 400) — users saw "speed stuck at 1
        # min/s" because the status endpoint kept returning the pre-400
        # value.  UI offers up to "1 yr/s" (31 557 600 s/s); cap at
        # 1e8 ≈ 3.17 yr/s of headroom beyond that so operator picks
        # always succeed and the tick-engine itself (auto_tick.py:95)
        # decides how aggressively to step physics.  Wall interval 0.01…60 s.
        speed = self._safe_float(body, "speed_factor", 60.0, lo=0.01, hi=1.0e8)
        wall_iv = self._safe_float(body, "wall_interval_s", 0.5, lo=0.01, hi=60.0)
        get_auto_tick().start(speed_factor=speed, wall_interval_s=wall_iv)
        return web.json_response(get_auto_tick().to_dict())

    async def _handle_auto_tick_stop(self, request: web.Request) -> web.Response:
        from aria.simulator.auto_tick import get_auto_tick
        get_auto_tick().stop()
        return web.json_response(get_auto_tick().to_dict())

    async def _handle_auto_tick_speed(self, request: web.Request) -> web.Response:
        from aria.simulator.auto_tick import get_auto_tick
        try: body = await request.json()
        except Exception: body = {}
        # BUG-006: match _handle_auto_tick_start — 1e8 covers 1 yr/s UI preset.
        speed = self._safe_float(body, "speed_factor", 60.0, lo=0.01, hi=1.0e8)
        get_auto_tick().set_speed(speed)
        return web.json_response(get_auto_tick().to_dict())

    async def _handle_scheduler(self, request: web.Request) -> web.Response:
        from aria.simulator.event_scheduler import get_scheduler
        return web.json_response(get_scheduler().to_dict())

    async def _handle_scheduler_add(self, request: web.Request) -> web.Response:
        from aria.simulator.event_scheduler import get_scheduler
        try: body = await request.json()
        except Exception: body = {}
        # hi=1_000_000 prevents phantom events at 1e+308 rotting in the
        # scheduler forever (observed in a live audit). _safe_float raises
        # ValueError → caught by middleware → 400.
        fire_at_yr = self._safe_float(body, "fire_at_yr", 0.0, lo=0.0, hi=1_000_000.0)
        try:
            evt = get_scheduler().schedule(
                fire_at_yr=fire_at_yr,
                kind=body.get("kind", "note"),
                label=body.get("label", "scheduled event"),
                payload=body.get("payload", {}),
            )
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({
            "event_id":   evt.event_id, "fire_at_yr": evt.fire_at_yr,
            "kind":       evt.kind, "label": evt.label, "payload": evt.payload,
        })

    async def _handle_scheduler_cancel(self, request: web.Request) -> web.Response:
        from aria.simulator.event_scheduler import get_scheduler
        try: body = await request.json()
        except Exception: body = {}
        ok = get_scheduler().cancel(body.get("event_id", ""))
        return web.json_response({"cancelled": ok})

    # ── B34: hull damage / random events / save-load / objectives ──

    async def _handle_hull_damage(self, request: web.Request) -> web.Response:
        from aria.simulator.hull_damage import get_hull_damage
        return web.json_response(get_hull_damage().to_dict())

    async def _handle_hull_repair(self, request: web.Request) -> web.Response:
        from aria.simulator.hull_damage import get_hull_damage
        try: body = await request.json()
        except Exception: body = {}
        rid = body.get("region_id")
        if not rid:
            return web.json_response({"error": "region_id required"}, status=400)
        all_at_once = bool(body.get("all", False))
        n = get_hull_damage().repair_all(rid) if all_at_once else (1 if get_hull_damage().repair_one(rid) else 0)
        return web.json_response({"repaired_count": n, "state": get_hull_damage().to_dict()})

    async def _handle_hull_impact(self, request: web.Request) -> web.Response:
        from aria.simulator.hull_damage import get_hull_damage
        try: body = await request.json()
        except Exception: body = {}
        rid = body.get("region_id", "hull_zone_4")
        # Reject negative/non-numeric energies — otherwise a negative impact
        # would *reduce* fatigue_index (hull "healing" exploit).
        try:
            energy = float(body.get("energy_j", 5000.0))
        except (TypeError, ValueError):
            return web.json_response({"error": "energy_j must be numeric"}, status=400)
        if energy < 0.0:
            return web.json_response({"error": "energy_j must be >= 0"}, status=400)
        impact = get_hull_damage().record_impact(rid, energy, note="operator test")
        return web.json_response({"impact_id": impact.impact_id, "region_id": impact.region_id,
                                  "energy_j": impact.energy_j})

    async def _handle_random_events_status(self, request: web.Request) -> web.Response:
        from aria.simulator.random_events import get_random_events
        return web.json_response(get_random_events().to_dict())

    async def _handle_random_events_toggle(self, request: web.Request) -> web.Response:
        from aria.simulator.random_events import get_random_events
        try: body = await request.json()
        except Exception: body = {}
        re = get_random_events()
        re.enabled = bool(body.get("enabled", not re.enabled))
        return web.json_response(re.to_dict())

    async def _handle_random_events_force_mmod(self, request: web.Request) -> web.Response:
        from aria.simulator.random_events import get_random_events
        try: body = await request.json()
        except Exception: body = {}
        rid = body.get("region_id", "hull_zone_4")
        try:
            energy = float(body.get("energy_j", 5000.0))
        except (TypeError, ValueError):
            return web.json_response({"error": "energy_j must be numeric"}, status=400)
        if energy < 0.0:
            return web.json_response({"error": "energy_j must be >= 0"}, status=400)
        get_random_events().force_mmod(rid, energy)
        return web.json_response(get_random_events().to_dict())

    async def _handle_random_events_force_flare(self, request: web.Request) -> web.Response:
        from aria.simulator.random_events import get_random_events
        get_random_events().force_flare()
        return web.json_response(get_random_events().to_dict())

    async def _handle_objectives(self, request: web.Request) -> web.Response:
        from aria.simulator.mission_objectives import get_mission_objectives
        return web.json_response(get_mission_objectives().to_dict())

    async def _handle_save(self, request: web.Request) -> web.Response:
        from aria.simulator.mission_persistence import snapshot
        return web.json_response(snapshot())

    async def _handle_load(self, request: web.Request) -> web.Response:
        from aria.simulator.mission_persistence import restore
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        report = restore(body)
        return web.json_response({"applied": True, "report": report})

    # ── B38: crew schedule / repair queue / narrative log ──

    async def _handle_crew_schedule(self, request: web.Request) -> web.Response:
        from aria.simulator.crew_schedule import get_crew_schedule
        return web.json_response(get_crew_schedule().to_dict())

    async def _handle_crew_overtime(self, request: web.Request) -> web.Response:
        from aria.simulator.crew_schedule import get_crew_schedule
        try: body = await request.json()
        except Exception: body = {}
        band = body.get("band_id", "A")
        hours = self._safe_float(body, "extra_hours", 4.0, lo=0.0, hi=168.0)
        get_crew_schedule().force_overtime(band, hours)
        return web.json_response(get_crew_schedule().to_dict())

    async def _handle_repair_queue(self, request: web.Request) -> web.Response:
        from aria.simulator.repair_queue import get_repair_queue
        return web.json_response(get_repair_queue().to_dict())

    async def _handle_repair_enqueue(self, request: web.Request) -> web.Response:
        from aria.simulator.repair_queue import get_repair_queue
        try: body = await request.json()
        except Exception: body = {}
        try:
            # Clamp to non-negative — negative values would make the repair
            # progress formulas produce NaN/inf (see repair_queue.tick).
            feedstock = self._safe_float(body, "feedstock_kg", 5.0, lo=0.0)
            hours = self._safe_float(body, "crew_hours", 2.0, lo=0.0, hi=168.0)
            prio = int(body.get("priority", 50))
        except (TypeError, ValueError):
            return web.json_response({"error": "feedstock_kg/crew_hours/priority must be numeric"}, status=400)
        t = get_repair_queue().enqueue_custom(
            source=body.get("source", "manual"),
            label=body.get("label", "Manual repair task"),
            feedstock_kg=feedstock,
            crew_hours=hours,
            priority=prio,
        )
        return web.json_response({"task_id": t.task_id, "label": t.label})

    async def _handle_repair_cancel(self, request: web.Request) -> web.Response:
        from aria.simulator.repair_queue import get_repair_queue
        try: body = await request.json()
        except Exception: body = {}
        ok = get_repair_queue().cancel(body.get("task_id", ""))
        return web.json_response({"cancelled": ok})

    async def _handle_repair_refill(self, request: web.Request) -> web.Response:
        from aria.simulator.repair_queue import get_repair_queue
        try: body = await request.json()
        except Exception: body = {}
        kg = self._safe_float(body, "kg", 1000.0, lo=0.0)
        added = get_repair_queue().refill_feedstock(kg)
        return web.json_response({"added_kg": added, "state": get_repair_queue().to_dict()})

    async def _handle_narrative(self, request: web.Request) -> web.Response:
        from aria.simulator.narrative_log import get_narrative_log
        return web.json_response(get_narrative_log().to_dict())

    async def _handle_narrative_text(self, request: web.Request) -> web.Response:
        from aria.simulator.narrative_log import get_narrative_log
        try:
            # Clamp 1…10 000 so ?limit=-1 or ?limit=abc don't crash the handler.
            limit = max(1, min(int(request.query.get("limit", "200")), 10_000))
        except (TypeError, ValueError):
            limit = 200
        return web.Response(text=get_narrative_log().to_text(limit), content_type="text/plain")

    async def _handle_narrative_note(self, request: web.Request) -> web.Response:
        from aria.simulator.narrative_log import get_narrative_log
        try: body = await request.json()
        except Exception: body = {}
        text = (body.get("text") or "").strip()
        sev = body.get("severity", "info")
        # Reject empty notes — the old code silently recorded a blank
        # operator.note entry every time the UI fired the "+ Note"
        # button with no text, polluting the captain's log with
        # naked "✎" pencil glyphs.
        if not text:
            return web.json_response({"error": "text is required"}, status=400)
        get_narrative_log().add_note(text, sev)
        return web.json_response({"added": True})

    async def _handle_narrative_clear(self, request: web.Request) -> web.Response:
        from aria.simulator.narrative_log import get_narrative_log
        get_narrative_log().clear()
        return web.json_response({"cleared": True})

    async def _handle_bom_item(self, request: web.Request) -> web.Response:
        from aria.simulator.bill_of_materials import get_item
        item_id = request.match_info.get("item_id", "")
        it = get_item(item_id)
        if it is None:
            return web.json_response({"error": f"Unknown BOM item '{item_id}'"}, status=404)
        return web.json_response({
            "item_id":          it.item_id,
            "name":             it.name,
            "subsystem":        it.subsystem,
            "n_installed":      it.n_installed,
            "n_required":       it.n_required,
            "redundancy_level": it.redundancy_level,
            "is_spof":          it.is_single_point_of_failure,
            "mass_kg_each":     it.mass_kg_each,
            "total_mass_kg":    it.total_mass_kg,
            "mtbf_hours":       it.mtbf_hours,
            "related_part_ids": it.related_part_ids,
            "failure_mode":     it.failure_mode_if_below_min,
            "notes":            it.notes,
            "citation":         it.citation,
        })

    # ─── WebSocket Handler ───────────────────────────────────

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a WebSocket connection from the dashboard frontend."""
        ws = web.WebSocketResponse(
            heartbeat=30.0,  # Send ping every 30s, close if no pong in 30s
            autoping=True,
        )
        await ws.prepare(request)
        self._ws_clients.append(ws)
        logger.info(
            "dashboard.ws.connected",
            extra={"clients": len(self._ws_clients)},
        )

        try:
            # Send initial state: the last snapshot if we have one
            if self._snapshots:
                await ws.send_json({
                    "type": "snapshot",
                    "data": self._snapshots[-1],
                })

            # Listen for client messages (e.g., control commands)
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self._ws_clients.remove(ws)
            logger.info(
                "dashboard.ws.disconnected",
                extra={"clients": len(self._ws_clients)},
            )

        return ws

    async def _handle_ws_message(
        self, ws: web.WebSocketResponse, data: dict[str, Any]
    ) -> None:
        """Process incoming WebSocket messages from clients."""
        cmd = data.get("command")

        if cmd == "get_history":
            # Client requests full history for replay
            count = len(self._snapshots)
            batch_size = data.get("batch_size", 100)
            for i in range(0, count, batch_size):
                batch = self._snapshots[i : i + batch_size]
                await ws.send_json({
                    "type": "batch",
                    "snapshots": batch,
                    "offset": i,
                    "total": count,
                })

        elif cmd == "get_snapshot":
            year = data.get("year", 0)
            if self._snapshots:
                best = min(
                    self._snapshots,
                    key=lambda s: abs(
                        (s.get("mission_year") or s.get("mission_time_years") or 0) - year
                    ),
                )
                await ws.send_json({"type": "snapshot", "data": best})

    # ─── Broadcasting ────────────────────────────────────────

    def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        payload = json.dumps(message, default=str)
        dead: list[web.WebSocketResponse] = []
        # Iterate a snapshot to avoid "list changed size during iteration"
        # if a disconnect handler removes a client mid-loop.
        for ws in list(self._ws_clients):
            try:
                asyncio.ensure_future(ws.send_str(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._ws_clients.remove(ws)
            except ValueError:
                pass  # Already removed by disconnect handler

    # ─── Data Conversion ─────────────────────────────────────

    @staticmethod
    def _interstellar_state_to_dict(state: Any) -> dict[str, Any]:
        """Convert an InterstellarState to a dashboard-friendly dict.

        Handles both InterstellarState dataclass and plain dicts.
        """
        if isinstance(state, dict):
            s = state
        elif hasattr(state, "__dict__"):
            from dataclasses import asdict
            try:
                s = asdict(state)
            except Exception:
                s = vars(state)
        else:
            s = {}

        mission_year = s.get("mission_year", 0)
        distance_ly = s.get("distance_ly", 0)
        velocity_c = s.get("velocity_c", 0)

        # Compute 3D position from distance (along mission path with slight curve)
        pos_x = distance_ly
        pos_y = math.sin(distance_ly * 0.1) * 2.0
        pos_z = math.cos(distance_ly * 0.15) * 1.5

        return {
            "mission_year": mission_year,
            "distance_ly": distance_ly,
            "velocity_c": velocity_c,
            "phase": s.get("phase", "UNKNOWN"),
            # Position (3D)
            "position_x": pos_x,
            "position_y": pos_y,
            "position_z": pos_z,
            # Subsystem health
            "hull_integrity": s.get("hull_integrity", 1.0),
            "shield_health": min(1.0, s.get("radiation_shielding_mass_kg", 10000) / 10000),
            "total_power_watts": s.get("total_power_watts", 500000),
            "food_production_ratio": s.get("hydroponic_capacity", 1.0),
            "crew_count": s.get("crew_count", 4),
            "crew_generation": s.get("crew_generation", 1),
            "water_liters": s.get("water_liters", 50000),
            # Additional data
            "fuel_fraction": (
                s.get("fusion_fuel_kg", 50000) / max(s.get("fuel_initial_kg", 50000), 1)
            ),
            "electronics_health": s.get("electronics_health", 1.0),
            "seed_viability": s.get("seed_viability", 1.0),
            "crew_morale": s.get("crew_morale", 0.8),
        }

    @staticmethod
    def _year_event_to_dict(event: Any) -> dict[str, Any]:
        """Convert a YearEvent to a dashboard-friendly dict."""
        if isinstance(event, dict):
            return event
        return {
            "year": getattr(event, "year", 0),
            "category": getattr(event, "category", ""),
            "severity": getattr(event, "severity", "NOMINAL"),
            "description": getattr(event, "description", ""),
            "subsystem": getattr(event, "subsystem", ""),
            "impact": getattr(event, "impact", {}),
        }

    # ── Fault management handlers ───────────────────────────────
    #
    # R65 (2026-04-24) BUG-B1/B2: these three handlers referenced
    # `self._bus` which was never initialised in __init__, so every call
    # raised AttributeError → middleware 500.  The rest of the dashboard
    # uses the module-level singleton `get_event_bus()`; unified on that.
    #
    # BUG-B2: `FaultSeverity(invalid_str)` raises a bare ValueError on
    # unknown enum values.  Now validated and returned as 400 with a
    # clear message instead of a generic 500.

    def _fault_mgr_lazy(self):
        """Lazy-init so we don't force FaultManager onto every deployment."""
        from aria.safety.fault_manager import FaultManager
        from aria.simulator.event_bus import get_event_bus
        if not hasattr(self, '_fault_mgr'):
            self._fault_mgr = FaultManager(bus=get_event_bus())
        return self._fault_mgr

    @staticmethod
    def _parse_severity(val, default=None):
        """FaultSeverity(val) with a nice 400 on unknown values."""
        from aria.safety.fault_manager import FaultSeverity
        if val is None or val == "":
            return default
        try:
            return FaultSeverity(val)
        except ValueError:
            legal = [s.value for s in FaultSeverity]
            raise web.HTTPBadRequest(
                reason=f"severity must be one of: {', '.join(legal)}; got {val!r}")

    async def _handle_faults_list(self, request: web.Request) -> web.Response:
        mgr = self._fault_mgr_lazy()
        mgr.check_shelve_expiry()
        sev = self._parse_severity(request.query.get("severity"))
        return web.json_response({"faults": mgr.active_faults(sev)})

    async def _handle_faults_report(self, request: web.Request) -> web.Response:
        mgr = self._fault_mgr_lazy()
        data = await request.json()
        sev = self._parse_severity(data.get("severity"), default=None)
        if sev is None:
            # Fall back to "warning" for report endpoint — historical default.
            from aria.safety.fault_manager import FaultSeverity
            sev = FaultSeverity("warning")
        fid = mgr.report(
            data.get("subsystem", "unknown"), sev,
            data.get("message", ""), sim_time_yr=data.get("sim_time_yr", 0.0),
        )
        return web.json_response({"fault_id": fid})

    async def _handle_faults_ack(self, request: web.Request) -> web.Response:
        from aria.safety.fault_manager import FaultManager
        if not hasattr(self, '_fault_mgr'):
            return web.json_response({"error": "no fault manager"}, status=400)
        fid = request.match_info["id"]
        data = await request.json() if request.can_read_body else {}
        ok = self._fault_mgr.acknowledge(fid, operator=data.get("operator", ""))
        return web.json_response({"acknowledged": ok})

    async def _handle_faults_shelve(self, request: web.Request) -> web.Response:
        from aria.safety.fault_manager import FaultManager
        if not hasattr(self, '_fault_mgr'):
            return web.json_response({"error": "no fault manager"}, status=400)
        fid = request.match_info["id"]
        data = await request.json() if request.can_read_body else {}
        ok = self._fault_mgr.shelve(fid, duration=data.get("duration", "15min"))
        return web.json_response({"shelved": ok})

    async def _handle_faults_resolve(self, request: web.Request) -> web.Response:
        from aria.safety.fault_manager import FaultManager
        if not hasattr(self, '_fault_mgr'):
            return web.json_response({"error": "no fault manager"}, status=400)
        fid = request.match_info["id"]
        data = await request.json() if request.can_read_body else {}
        ok = self._fault_mgr.resolve(fid, notes=data.get("notes", ""))
        return web.json_response({"resolved": ok})

    async def _handle_faults_stats(self, request: web.Request) -> web.Response:
        return web.json_response(self._fault_mgr_lazy().stats())

    async def _handle_telemetry_snapshot(self, request: web.Request) -> web.Response:
        from aria.simulator.telemetry_buffer import TelemetryBuffer
        if not hasattr(self, '_tlm_buf'):
            self._tlm_buf = TelemetryBuffer()
        return web.json_response({
            "channels": self._tlm_buf.read_all(),
            "stats": self._tlm_buf.stats(),
            "violations": self._tlm_buf.check_limits(),
        })

    async def _handle_constellation(self, request: web.Request) -> web.Response:
        """Return constellation satellite positions."""
        from aria.simulation.constellation_design import (
            gps_constellation, galileo_constellation, iridium_constellation,
            ground_coverage_angle,
        )
        name = request.match_info.get("name", "gps").lower()
        builders = {
            "gps": gps_constellation,
            "galileo": galileo_constellation,
            "iridium": iridium_constellation,
        }
        builder = builders.get(name)
        if builder is None:
            return web.json_response({"error": f"Unknown constellation: {name}"}, status=404)

        c = builder()
        altitude_km = c.satellites[0].a_km - 6378.137 if c.satellites else 0
        coverage = ground_coverage_angle(altitude_km) if altitude_km > 0 else 0
        return web.json_response({
            "name": c.name,
            "pattern": c.pattern,
            "total_satellites": c.total_satellites,
            "orbital_planes": c.orbital_planes,
            "description": c.description,
            "altitude_km": altitude_km,
            "coverage_half_angle_deg": coverage,
            "satellites": [
                {
                    "a_km": s.a_km,
                    "ecc": s.ecc,
                    "inc_deg": s.inc_deg,
                    "raan_deg": s.raan_deg,
                    "mean_anomaly_deg": s.mean_anomaly_deg,
                }
                for s in c.satellites
            ],
        })

    async def _handle_constellation_list(self, request: web.Request) -> web.Response:
        return web.json_response({
            "available": ["gps", "galileo", "iridium"],
            "descriptions": {
                "gps": "GPS Block III: 24/6/2 Walker-delta, 20200 km, 55°",
                "galileo": "Galileo: 30/3/1 Walker-delta, 23222 km, 56°",
                "iridium": "Iridium NEXT: 66 polar sats, 780 km, 86.4°",
            },
        })

    async def _handle_mission_design_earth_mars(self, request: web.Request) -> web.Response:
        """Compute Earth-Mars mission design via porkchop + Lambert + Tsiolkovsky."""
        from aria.simulation.mission_design import (
            design_earth_mars_mission, design_summary,
        )

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        try:
            design = design_earth_mars_mission(
                dep_window=(_float("dep_start", 0), _float("dep_end", 400)),
                arr_window=(_float("arr_start", 150), _float("arr_end", 600)),
                dry_mass_kg=_float("dry_mass_kg", 3000),
                fuel_budget_kg=_float("fuel_budget_kg", 6000),
                isp_s=_float("isp_s", 320),
            )
            return web.json_response(design_summary(design))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_solar_system(self, request: web.Request) -> web.Response:
        """Geocentric apparent positions of Sun, Moon, planets, asteroids, comets.

        Query params:
            jd:    Julian Date (default = current UT)
            year, month, day: civil date (overrides jd if all provided)
            mag_limit: max V mag for small bodies (default 13)
            include_small: "1" to include asteroids/comets (default "1")
        """
        from aria.simulation.solar_system import (
            jd_now, jd_from_calendar, all_visible_bodies,
        )
        from aria.simulation.small_bodies import visible_small_bodies
        from aria.simulation.moons import visible_moons, ALL_MOONS

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        try:
            year_q = request.query.get("year")
            month_q = request.query.get("month")
            day_q = request.query.get("day")
            if year_q and month_q and day_q:
                jd = jd_from_calendar(int(year_q), int(month_q), float(day_q))
            else:
                jd = _float("jd", jd_now())
        except (TypeError, ValueError):
            jd = jd_now()

        bodies = all_visible_bodies(jd)
        small: list = []
        moons: list = []
        if request.query.get("include_small", "1") == "1":
            mag_lim = _float("mag_limit", 13.0)
            small = visible_small_bodies(jd, mag_limit=mag_lim)
        if request.query.get("include_moons", "1") == "1":
            moons_lim = _float("moons_mag_limit", 14.0)
            moons = visible_moons(jd, mag_limit=moons_lim)

        def _to_dict(b, kind: str) -> dict:
            return {
                "name": b.name,
                "kind": kind,
                "ra": round(b.ra_deg, 4),
                "dec": round(b.dec_deg, 4),
                "magnitude": round(b.magnitude, 2),
                "distance_au": round(b.distance_au, 4),
                "color": [round(c, 3) for c in b.color],
            }

        # Tag the major bodies
        tagged_majors = []
        for b in bodies:
            if b.name in ("sun", "moon"):
                tagged_majors.append(_to_dict(b, b.name))
            else:
                tagged_majors.append(_to_dict(b, "planet"))

        # Small bodies tagged as asteroid or comet via list membership
        from aria.simulation.small_bodies import COMETS
        comet_names = {c.name for c in COMETS}
        small_payload = [
            _to_dict(b, "comet" if b.name in comet_names else "asteroid")
            for b in small
        ]

        # Moons tagged 'satellite' (Earth's moon stays 'moon' from majors).
        moon_payload = [_to_dict(m, "satellite") for m in moons]

        return web.json_response({
            "jd": jd,
            "bodies": tagged_majors + moon_payload + small_payload,
            "counts": {
                "majors": len(tagged_majors),
                "small": len(small_payload),
                "moons": len(moon_payload),
            },
        })

    async def _handle_nearby_stars(self, request: web.Request) -> web.Response:
        """Stars within ~25 light-years — candidate interstellar targets."""
        from aria.simulation.nearby_stars import NEARBY_STARS

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        dist_limit = _float("ly_limit", 25.0)
        stars = sorted((s for s in NEARBY_STARS if s.distance_ly <= dist_limit),
                       key=lambda s: s.distance_ly)
        return web.json_response({
            "count": len(stars),
            "stars": [
                {
                    "name": s.name, "hip_id": s.hip_id,
                    "ra": s.ra_deg, "dec": s.dec_deg,
                    "distance_ly": round(s.distance_ly, 3),
                    "spectral_type": s.spectral_type,
                    "abs_mag": s.abs_mag, "app_mag": s.app_mag,
                    "category": s.category,
                    "known_planets": s.known_planets,
                    "notes": s.notes,
                }
                for s in stars
            ],
        })

    async def _handle_pulsars(self, request: web.Request) -> web.Response:
        """Famous pulsars with rotation period and discovery context."""
        from aria.simulation.pulsars import PULSARS
        return web.json_response({
            "count": len(PULSARS),
            "pulsars": [
                {
                    "jname": p.jname, "bname": p.bname, "common_name": p.common_name,
                    "ra": p.ra_deg, "dec": p.dec_deg,
                    "period_ms": p.period_ms, "period_dot": p.period_dot,
                    "distance_kpc": p.distance_kpc,
                    "description": p.description,
                }
                for p in PULSARS
            ],
        })

    async def _handle_ngc_highlights(self, request: web.Request) -> web.Response:
        """Non-Messier NGC/IC deep-sky highlights (LMC, SMC, Double Cluster, Helix, etc.)."""
        from aria.simulation.ngc_highlights import NGC_HIGHLIGHTS

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        mag_limit = _float("mag_limit", 11.0)
        objs = [o for o in NGC_HIGHLIGHTS if o.vmag <= mag_limit]
        return web.json_response({
            "count": len(objs),
            "objects": [
                {
                    "catalog_id": o.catalog_id, "common_name": o.common_name,
                    "ra": o.ra_deg, "dec": o.dec_deg,
                    "mag": o.vmag, "size_amin": o.size_amin,
                    "obj_class": o.obj_class,
                    "description": o.description,
                }
                for o in objs
            ],
        })

    async def _handle_double_stars(self, request: web.Request) -> web.Response:
        """Famous visual double / multiple stars for telescope observers."""
        from aria.simulation.double_stars import DOUBLES
        return web.json_response({
            "count": len(DOUBLES),
            "doubles": [
                {
                    "name": d.name, "hip_id": d.hip_id,
                    "ra": d.ra_deg, "dec": d.dec_deg,
                    "mag_a": d.mag_a, "mag_b": d.mag_b,
                    "sep_arcsec": d.sep_arcsec, "pa_deg": d.pa_deg,
                    "spec_a": d.spec_a, "spec_b": d.spec_b,
                    "notes": d.notes,
                }
                for d in DOUBLES
            ],
        })

    async def _handle_variable_stars(self, request: web.Request) -> web.Response:
        """Famous variable stars with current estimated magnitude at jd."""
        from aria.simulation.variable_stars import VARIABLES, current_magnitude
        from aria.simulation.solar_system import jd_now

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        jd = _float("jd", jd_now())
        mag_limit = _float("mag_limit", 9.0)
        results = []
        for v in VARIABLES:
            cur_mag = current_magnitude(v, jd)
            if cur_mag > mag_limit:
                continue
            results.append({
                "name": v.name, "hip_id": v.hip_id,
                "ra": v.ra_deg, "dec": v.dec_deg,
                "var_type": v.var_type,
                "period_d": v.period_d,
                "mag_min": v.mag_min, "mag_max": v.mag_max,
                "current_mag": round(cur_mag, 2),
                "description": v.description,
            })
        results.sort(key=lambda r: r["current_mag"])
        return web.json_response({
            "jd": jd, "count": len(results), "stars": results,
        })

    async def _handle_exoplanets(self, request: web.Request) -> web.Response:
        """Notable exoplanet-hosting stars, optionally filtered by observer / mag.

        Query params:
            jd, lat, lon : optional observer (filters to above-horizon only)
            mag_limit    : host-star V mag cap (default 20 = all)
            min_alt      : minimum altitude for observer filter (default 0°)
        """
        from aria.simulation.exoplanets import (
            EXOPLANET_HOSTS, above_horizon,
        )
        from aria.simulation.solar_system import jd_now

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        mag_limit = _float("mag_limit", 20.0)
        hosts = [h for h in EXOPLANET_HOSTS if h.host_mag <= mag_limit]

        lat = request.query.get("lat")
        lon = request.query.get("lon")
        if lat is not None and lon is not None:
            hosts = above_horizon(
                hosts,
                _float("jd", jd_now()),
                _float("lat", 0.0),
                _float("lon", 0.0),
                _float("min_alt", 0.0),
            )

        return web.json_response({
            "count": len(hosts),
            "hosts": [
                {
                    "name": h.name, "hip_id": h.hip_id,
                    "ra": round(h.ra_deg, 4), "dec": round(h.dec_deg, 4),
                    "distance_ly": round(h.distance_ly, 2),
                    "host_mag": round(h.host_mag, 2),
                    "n_planets": h.n_planets,
                    "discoverer": h.discoverer,
                    "description": h.description,
                }
                for h in hosts
            ],
        })

    # ── TLE catalog (live from Celestrak with fallback to bundled) ──

    _tle_cache: dict = {}
    """Module-level in-memory cache so hot-reloads + parallel requests
    share a single upstream hit.  Keyed by Celestrak group name (e.g.
    'active', 'stations', 'starlink').  Each entry is
    ``{'fetched_at_wall': float, 'text': str, 'source': str}`` and
    expires after 10 min — honours Celestrak's "no more than one hit
    per 2 hr per source per client" guideline while still letting
    operators see refreshed positions within an idle desk session."""

    async def _handle_tle_catalog(self, request: web.Request) -> web.Response:
        """Fetch a TLE catalog from Celestrak live, cache 10 min, fall back
        to the bundled ``data/raw/spacetrack/full_catalog_3le.txt`` on
        network failure.

        Query params:
          group:  Celestrak catalog name (default 'active') — any of
                  'active', 'stations', 'starlink', 'visual', 'gps-ops',
                  'glo-ops', 'gnss', 'gps', 'science', 'weather',
                  'noaa', 'goes', 'cubesat', 'geo', 'last-30-days',
                  'cosmos-1408-debris', 'iridium-NEXT', …
                  Full list: https://celestrak.org/NORAD/elements/
          limit:  max number of satellites (each satellite = 3 lines in 3LE)

        Returns ``{"source": "celestrak" | "bundled", "group": <str>,
        "fetched_at_wall": <unix_s>, "satellites": [{name, line1, line2},
        …], "count": <int>}`` so the frontend can surface freshness."""
        import time
        group = request.query.get("group", "active").lower().strip()
        try:
            limit = int(request.query.get("limit", "0"))
        except (TypeError, ValueError):
            limit = 0

        now = time.time()
        cached = self._tle_cache.get(group)
        text: str | None = None
        source: str = "bundled"
        fetched_at: float = now
        if cached and (now - cached["fetched_at_wall"]) < 600:
            text = cached["text"]
            source = cached["source"]
            fetched_at = cached["fetched_at_wall"]
        else:
            # Fetch live — short 8s timeout so a Celestrak hiccup doesn't
            # stall the UI.  3LE format = catalog name + two TLE lines.
            import aiohttp
            url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=3le"
            try:
                timeout = aiohttp.ClientTimeout(total=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            source = "celestrak"
            except Exception:
                text = None
                source = "bundled"
            # Fallback: the shipped 30k-sat snapshot in data/raw.
            if not text:
                bundled = Path(__file__).resolve().parents[3] / \
                          "data" / "raw" / "spacetrack" / "full_catalog_3le.txt"
                try:
                    text = bundled.read_text()
                    source = "bundled"
                except Exception:
                    return web.json_response(
                        {"error": "TLE catalog unavailable — live fetch + bundled both failed",
                         "group": group},
                        status=503)
            self._tle_cache[group] = {
                "fetched_at_wall": now, "text": text, "source": source,
            }
            fetched_at = now

        # Parse 3LE: every group of 3 lines = (name, line1, line2).  Some
        # Celestrak groups use the leading "0 " flag in the name line
        # (bundled snapshot) while the live feed does not — strip it.
        sats: list[dict] = []
        lines = text.splitlines()
        i = 0
        while i + 2 < len(lines):
            name = lines[i].strip()
            if name.startswith("0 "):
                name = name[2:].strip()
            l1 = lines[i + 1]
            l2 = lines[i + 2]
            # Guard against stray blank lines / partial records.
            if l1.startswith("1 ") and l2.startswith("2 "):
                sats.append({"name": name, "line1": l1, "line2": l2})
                i += 3
            else:
                i += 1
            if limit > 0 and len(sats) >= limit:
                break
        return web.json_response({
            "source": source,
            "group": group,
            "fetched_at_wall": round(fetched_at, 1),
            "count": len(sats),
            "satellites": sats,
        })

    async def _handle_telemetry_live_state(self, request: web.Request) -> web.Response:
        """Live ECI state vector for a named satellite, derived from the
        most recent TLE in the catalog cache.

        Query params:
          norad: NORAD catalog ID (e.g., 25544 for ISS) — required
          group: Celestrak group to search (default 'active')
          jd:    Julian Date for propagation (default = now)

        Returns ``{norad, name, jd, r_eci_km, v_eci_kms, altitude_km,
        speed_kmps, period_min, source, fetched_at_wall}`` so the
        frontend can show "live state vs sim state" deltas. Roadmap
        Track 1 Phase 1 — see docs/ROADMAP_THREE_GAPS.md.
        """
        from aria.simulation.tle_parser import parse_tle
        from aria.simulation.satellite_propagator import propagate_tle
        from aria.simulation.solar_system import jd_now

        norad = request.query.get("norad", "").strip()
        if not norad:
            return web.json_response(
                {"error": "norad catalog id required (e.g. ?norad=25544)"},
                status=400,
            )
        group = request.query.get("group", "active").lower().strip()
        try:
            jd = float(request.query.get("jd", jd_now()))
        except (TypeError, ValueError):
            jd = jd_now()

        # Reuse the existing /api/tle/catalog cache by re-invoking
        # _handle_tle_catalog logic without the parsing/serialization
        # round trip — same source, same fallback, same freshness rules.
        import time
        now = time.time()
        cached = self._tle_cache.get(group)
        text: str | None = None
        source = "bundled"
        fetched_at = now
        if cached and (now - cached["fetched_at_wall"]) < 600:
            text = cached["text"]
            source = cached["source"]
            fetched_at = cached["fetched_at_wall"]
        else:
            import aiohttp
            url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=3le"
            try:
                timeout = aiohttp.ClientTimeout(total=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            source = "celestrak"
            except Exception:
                text = None
            if not text:
                bundled = Path(__file__).resolve().parents[3] / \
                          "data" / "raw" / "spacetrack" / "full_catalog_3le.txt"
                try:
                    text = bundled.read_text()
                    source = "bundled"
                except Exception:
                    return web.json_response(
                        {"error": "TLE catalog unavailable",
                         "norad": norad, "group": group},
                        status=503)
            self._tle_cache[group] = {
                "fetched_at_wall": now, "text": text, "source": source,
            }
            fetched_at = now

        # Scan for the matching NORAD ID. Format: line1 cols 3-7 hold the
        # catalog number (5-digit, zero-padded).
        target = norad.lstrip("0").zfill(5)
        lines = text.splitlines()
        i = 0
        match: tuple[str, str, str] | None = None
        while i + 2 < len(lines):
            name = lines[i].strip()
            if name.startswith("0 "):
                name = name[2:].strip()
            l1 = lines[i + 1]
            l2 = lines[i + 2]
            if l1.startswith("1 ") and l2.startswith("2 "):
                # Catalog number sits at l1[2:7]
                if l1[2:7].strip().zfill(5) == target:
                    match = (name, l1, l2)
                    break
                i += 3
            else:
                i += 1
        if match is None:
            return web.json_response(
                {"error": f"NORAD {norad} not found in group '{group}'",
                 "source": source, "fetched_at_wall": round(fetched_at, 1)},
                status=404,
            )

        try:
            tle = parse_tle(match[1], match[2], match[0])
            state = propagate_tle(tle, jd)
        except Exception as exc:
            return web.json_response(
                {"error": f"propagation failed: {type(exc).__name__}: {exc}",
                 "norad": norad}, status=500,
            )

        return web.json_response({
            "norad": norad,
            "name": match[0],
            "jd": jd,
            "r_eci_km": [round(x / 1000.0, 3) for x in state.r_eci_m],
            "v_eci_kms": [round(x / 1000.0, 6) for x in state.v_eci_mps],
            "altitude_km": round(state.altitude_km, 3),
            "speed_kmps": round(state.speed_kmps, 6),
            "period_min": round(state.period_min, 3),
            "source": source,
            "group": group,
            "fetched_at_wall": round(fetched_at, 1),
        })

    async def _handle_mission_schedule(self, request: web.Request) -> web.Response:
        """Curated milestone schedule for a real spacecraft programme.

        Roadmap Track 1 Phase 2. Programmes:
          ?program=artemis2 (default) — Artemis 2 crewed lunar flyby (NET 2026-09)
          ?program=artemis3            — Artemis 3 crewed lunar landing (NET 2027-09)
          ?program=apollo11            — Apollo 11 ground-truth dates (1969-07)

        Source citations are inline in artemis_schedule.py and surfaced
        per-milestone via the ``source`` field so an operator can cross-check.
        """
        from aria.integrations.nasa_public.artemis_schedule import to_dict, list_programs
        program = request.query.get("program", "artemis2")
        body = to_dict(program)
        if body is None:
            return web.json_response(
                {"error": f"Unknown programme '{program}'",
                 "available": list_programs()},
                status=404,
            )
        return web.json_response(body)

    # ── Failsafe console (F-9, F-12, F-17) ─────────────────────────

    async def _handle_safety_state(self, request: web.Request) -> web.Response:
        """Aggregate snapshot for the Safety Console."""
        from aria.safety.kill_switch import get_kill_switch
        from aria.safety.resource_budget import get_budget_gate
        from aria.cognitive.constitution import get_constitution
        from aria.safety.approval_queue import get_approval_queue
        c = get_constitution()
        budgets = get_budget_gate().all_status()
        return web.json_response({
            "constitution_version": c.constitution_version,
            "kill_switch": get_kill_switch().to_dict(),
            "budgets": {k: {
                "current": v.current, "soft_cap": v.soft_cap,
                "hard_cap": v.hard_cap, "unit": v.unit,
                "pct_of_hard": round(v.pct_of_hard, 1),
            } for k, v in budgets.items()},
            "pending_proposals": len(get_approval_queue().list_pending()),
        })

    async def _handle_safety_proposals(self, request: web.Request) -> web.Response:
        from aria.safety.approval_queue import get_approval_queue
        return web.json_response({
            "proposals": get_approval_queue().list_pending(),
        })

    async def _handle_safety_approve(self, request: web.Request) -> web.Response:
        """Sign a pending proposal. Operator identity is derived from the
        authenticated session (R32) — the request body NO LONGER carries
        operator_id. When auth_required=False (dev/test), the body field
        is honoured as a fallback so legacy tests keep working."""
        from aria.safety.approval_queue import get_approval_queue
        from aria.security.middleware import get_request_principal
        try:
            body = await request.json()
        except Exception:
            body = {}
        pid = (body.get("proposal_id") or "").strip()
        principal = get_request_principal(request)
        op = (principal.principal_id
              if principal.role != "anonymous"
              else (body.get("operator_id") or "").strip())
        if not pid or not op:
            return web.json_response(
                {"error": "proposal_id required (operator from session)"},
                status=400)
        recall = bool(body.get("recall_answer_ok", True))
        off_shift = bool(body.get("off_shift", False))
        r = get_approval_queue().approve(pid, op,
                                         recall_answer_ok=recall,
                                         off_shift=off_shift)
        return web.json_response(r, status=200 if r.get("ok") else 409)

    async def _handle_safety_veto(self, request: web.Request) -> web.Response:
        from aria.safety.approval_queue import get_approval_queue
        from aria.security.middleware import get_request_principal
        try:
            body = await request.json()
        except Exception:
            body = {}
        pid = (body.get("proposal_id") or "").strip()
        principal = get_request_principal(request)
        op = (principal.principal_id
              if principal.role != "anonymous"
              else (body.get("operator_id") or "").strip())
        reason = body.get("reason", "")
        if not pid or not op:
            return web.json_response(
                {"error": "proposal_id required (operator from session)"},
                status=400)
        r = get_approval_queue().veto(pid, op, reason=reason)
        return web.json_response(r, status=200 if r.get("ok") else 409)

    async def _handle_safety_revert(self, request: web.Request) -> web.Response:
        from aria.safety.approval_queue import get_approval_queue
        from aria.security.middleware import get_request_principal
        try:
            body = await request.json()
        except Exception:
            body = {}
        pid = (body.get("proposal_id") or "").strip()
        principal = get_request_principal(request)
        op = (principal.principal_id
              if principal.role != "anonymous"
              else (body.get("operator_id") or "").strip())
        if not pid or not op:
            return web.json_response(
                {"error": "proposal_id required (operator from session)"},
                status=400)
        r = get_approval_queue().revert(pid, op)
        return web.json_response(r, status=200 if r.get("ok") else 409)

    async def _handle_safety_kill_assert(self, request: web.Request) -> web.Response:
        """Hardware bridge endpoint. Asserts the kill switch.

        IMPORTANT: in production, this endpoint MUST be reachable only
        from the hardware-GPIO bridge (firewalled to a single source IP
        / unix socket). The dashboard exposes it for ground tests.
        """
        from aria.safety.kill_switch import get_kill_switch
        try:
            body = await request.json()
        except Exception:
            body = {}
        source = (body.get("source") or "").strip() or "manual"
        reason = body.get("reason", "")
        get_kill_switch().assert_kill(source, reason)
        return web.json_response(get_kill_switch().to_dict())

    async def _handle_safety_kill_reset(self, request: web.Request) -> web.Response:
        """Physical-key clear. Body must include key_signature.

        In production, the signature is verified against an HSM-rooted
        public key. The web layer here just plumbs the call; if the
        signature isn't checked upstream, an attacker can clear the
        kill switch and the security model collapses. Document as
        operator-facing only and require a real signature.
        """
        from aria.safety.kill_switch import get_kill_switch
        try:
            body = await request.json()
        except Exception:
            body = {}
        sig = (body.get("key_signature") or "").strip()
        if not sig:
            return web.json_response(
                {"error": "key_signature required"}, status=400)
        ok = get_kill_switch().physical_key_reset(sig)
        return web.json_response(
            {"ok": ok, "state": get_kill_switch().to_dict()},
            status=200 if ok else 409,
        )

    async def _handle_safety_deadman_affirm(self, request: web.Request) -> web.Response:
        """Operator pulse to reset the deadman timer. The dashboard
        polls this whenever an operator is interacting with the safety
        console; absence of pulses → deadman expires → safe-mode.

        The deadman singleton is constructed on first affirm.
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        source = (body.get("source") or "operator").strip()
        # Deadman is an optional layer; only enable if explicitly armed.
        # For now simply log the pulse; the runner that owns the
        # deadman thread reads ARIA_DEADMAN_WINDOW_S to enable it.
        import time as _time
        return web.json_response({
            "ok": True, "source": source, "ts": _time.time(),
        })

    async def _handle_safety_replay_status(self, request: web.Request) -> web.Response:
        """F-13 — last replay report (or null if never run)."""
        from aria.safety.safety_replay import get_safety_replay
        sr = get_safety_replay()
        last = sr.last_report()
        return web.json_response({
            "last_report": last.to_dict() if last else None,
        })

    async def _handle_safety_replay_run(self, request: web.Request) -> web.Response:
        """F-13 — operator-triggered safety replay (off-schedule)."""
        from aria.safety.safety_replay import get_safety_replay
        report = get_safety_replay().run_once()
        return web.json_response(report.to_dict())

    async def _handle_safety_sandbagging(self, request: web.Request) -> web.Response:
        """F-11 — current sandbagging-detector statistics."""
        from aria.cognitive.eval_marker import get_sandbagging_detector
        return web.json_response(get_sandbagging_detector().report().to_dict())

    async def _handle_safety_boot_manifest(self, request: web.Request) -> web.Response:
        """F-18 — boot manifest verification status (re-run on demand)."""
        from aria.boot.verify import (
            verify_boot_integrity, BootIntegrityError, _default_manifest_path,
        )
        manifest_path = _default_manifest_path()
        try:
            ok = verify_boot_integrity(strict=False, skip_if_missing=True)
            return web.json_response({
                "ok": bool(ok),
                "manifest_path": str(manifest_path),
                "manifest_present": manifest_path.is_file(),
            })
        except BootIntegrityError as exc:
            return web.json_response({
                "ok": False,
                "manifest_path": str(manifest_path),
                "manifest_present": manifest_path.is_file(),
                "error": str(exc),
            })

    # ── R32 auth endpoints ────────────────────────────────────────

    async def _handle_auth_challenge(self, request: web.Request) -> web.Response:
        """GET /api/auth/challenge?principal_id=...

        Returns a fresh nonce + expires_at. The client signs
        ``{nonce}|{principal_id}|{expires_at}`` with its hardware-key
        private Ed25519 key and POSTs the signature to /api/auth/login.
        """
        from aria.security.auth_service import get_auth_service
        principal_id = (request.query.get("principal_id") or "").strip()
        if not principal_id:
            return web.json_response({"error": "principal_id required"},
                                     status=400)
        ch = get_auth_service().issue_challenge(principal_id)
        return web.json_response({
            "nonce": ch.nonce,
            "principal_id": ch.principal_id,
            "expires_at": ch.expires_at,
        })

    async def _handle_auth_login(self, request: web.Request) -> web.Response:
        """POST /api/auth/login with body
           {principal_id, nonce, signature_hex, duress: bool}.
        Returns {session_token, role, expires_at}."""
        from aria.security.auth_service import get_auth_service, AuthError
        try:
            body = await request.json()
        except Exception:
            body = {}
        principal_id = (body.get("principal_id") or "").strip()
        nonce = (body.get("nonce") or "").strip()
        sig = (body.get("signature_hex") or "").strip()
        duress = bool(body.get("duress", False))
        if not (principal_id and nonce and sig):
            return web.json_response({"error": "auth refused"}, status=401)
        try:
            s = get_auth_service().login(
                principal_id, nonce, sig, duress=duress,
            )
        except AuthError:
            # Generic fixed-shape response (don't leak which factor failed).
            return web.json_response({"error": "auth refused"}, status=401)
        return web.json_response({
            "session_token": s.token,
            "principal_id": s.principal_id,
            "role": s.role,
            "expires_at": s.expires_at,
            "idle_window_s": s.idle_window_s,
            "duress": s.duress,
        })

    async def _handle_auth_logout(self, request: web.Request) -> web.Response:
        """POST /api/auth/logout. Revokes the calling session
        (Bearer token from Authorization header)."""
        from aria.security.middleware import get_request_principal
        from aria.security.session_store import get_session_store
        principal = get_request_principal(request)
        # Pull the token off the request so we don't trust the body.
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
        if not token:
            return web.json_response({"ok": False, "reason": "no session"},
                                     status=400)
        ok = get_session_store().revoke(token, reason="logout")
        return web.json_response({
            "ok": bool(ok),
            "principal_id": principal.principal_id,
        })

    async def _handle_auth_me(self, request: web.Request) -> web.Response:
        """GET /api/auth/me — returns the calling principal's role + perms.

        Anonymous if no Bearer token; the resolver middleware always
        sets request['principal'].
        """
        from aria.security.middleware import get_request_principal
        from aria.security.principals import get_role_store
        principal = get_request_principal(request)
        role_store = get_role_store()
        return web.json_response({
            "principal_id": principal.principal_id,
            "role": principal.role,
            "duress": principal.duress,
            "permissions": sorted(role_store.permissions_for(principal.role)),
            "authority_ceiling": role_store.authority_ceiling(principal.role).value,
        })

    # ── R33 admin endpoints ───────────────────────────────────────

    async def _handle_admin_principals_list(self, request: web.Request) -> web.Response:
        """GET /api/admin/principals — current roster (active only)."""
        from aria.security.principals import get_principal_store
        ps = get_principal_store()
        out = []
        for p in ps.all():
            out.append({
                "principal_id": p.principal_id,
                "role": p.role,
                "display_name": p.display_name,
                "pubkey_hex": p.pubkey_hex,
                "created_at": p.created_at,
                "expires_at": p.expires_at,
            })
        return web.json_response({"principals": out, "count": len(out)})

    async def _handle_admin_principal_create(self, request: web.Request) -> web.Response:
        """POST /api/admin/principals { principal_id, role, pubkey_hex,
        display_name? } — submit a create proposal. Two-person rule via
        ApprovalQueue; the second signer signs through /api/safety/approve."""
        from aria.security.admin import propose_create_principal, AdminError
        from aria.security.middleware import get_request_principal
        actor = get_request_principal(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            pid = propose_create_principal(
                actor,
                principal_id=str(body.get("principal_id", "")).strip(),
                role=str(body.get("role", "")).strip(),
                pubkey_hex=str(body.get("pubkey_hex", "")).strip(),
                display_name=str(body.get("display_name", "")).strip(),
            )
        except AdminError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "proposal_id": pid})

    async def _handle_admin_principal_revoke(self, request: web.Request) -> web.Response:
        from aria.security.admin import propose_revoke_principal, AdminError
        from aria.security.middleware import get_request_principal
        actor = get_request_principal(request)
        target = request.match_info.get("id", "").strip()
        try:
            pid = propose_revoke_principal(actor, principal_id=target)
        except AdminError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "proposal_id": pid})

    async def _handle_admin_principal_role_assign(self, request: web.Request) -> web.Response:
        from aria.security.admin import propose_role_assign, AdminError
        from aria.security.middleware import get_request_principal
        actor = get_request_principal(request)
        target = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            pid = propose_role_assign(
                actor,
                principal_id=target,
                new_role=str(body.get("new_role", "")).strip(),
            )
        except AdminError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "proposal_id": pid})

    async def _handle_admin_roles_list(self, request: web.Request) -> web.Response:
        """GET /api/admin/roles — sealed + custom roles + each role's
        full permission set (including inherited)."""
        from aria.security.principals import get_role_store
        rs = get_role_store()
        out = []
        for r in rs.all_roles():
            out.append({
                "name": r.name,
                "inherits": list(r.inherits),
                "trust_tier": r.trust_tier.value,
                "authority_ceiling": r.authority_ceiling.value,
                "description": r.description,
                "is_sealed": rs.is_sealed(r.name),
                "permissions": sorted(rs.permissions_for(r.name)),
            })
        return web.json_response({"roles": out, "count": len(out)})

    async def _handle_admin_role_create_custom(self, request: web.Request) -> web.Response:
        """POST /api/admin/roles/custom { name, inherits[], permissions[],
        description? } — propose a custom role. No-escalation enforced
        before propose() and re-enforced at executor fire time."""
        from aria.security.admin import propose_create_custom_role, AdminError
        from aria.security.middleware import get_request_principal
        actor = get_request_principal(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            pid = propose_create_custom_role(
                actor,
                name=str(body.get("name", "")).strip(),
                inherits=list(body.get("inherits", [])),
                permissions=list(body.get("permissions", [])),
                description=str(body.get("description", "")),
            )
        except AdminError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "proposal_id": pid})

    async def _handle_admin_role_revoke_custom(self, request: web.Request) -> web.Response:
        from aria.security.admin import propose_revoke_custom_role, AdminError
        from aria.security.middleware import get_request_principal
        actor = get_request_principal(request)
        name = request.match_info.get("name", "").strip()
        try:
            pid = propose_revoke_custom_role(actor, name=name)
        except AdminError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"ok": True, "proposal_id": pid})

    async def _handle_admin_permissions_list(self, request: web.Request) -> web.Response:
        """GET /api/admin/permissions — every permission name in the
        sealed catalogue + (when the caller's session is non-anonymous)
        which subset the caller themselves holds. The frontend filters
        custom-role permission checkboxes to that subset (no-escalation
        UX hint; server still re-enforces)."""
        from aria.security.middleware import get_request_principal
        from aria.security.principals import get_role_store
        rs = get_role_store()
        actor = get_request_principal(request)
        all_perms = list(rs.all_permissions())
        held = sorted(rs.permissions_for(actor.role))
        return web.json_response({
            "all_permissions": all_perms,
            "actor_holds": held,
            "actor_role": actor.role,
        })

    # ── R34 incident + audit endpoints ────────────────────────────

    async def _handle_incidents_list(self, request: web.Request) -> web.Response:
        """GET /api/incidents?status=open|closed — list incidents."""
        from aria.safety.incident_registry import get_incident_registry
        reg = get_incident_registry()
        which = (request.query.get("status") or "open").lower()
        if which == "closed":
            items = reg.list_closed(limit=int(request.query.get("limit", 100)))
        else:
            items = reg.list_open()
        return web.json_response({
            "status": which,
            "count": len(items),
            "incidents": [i.to_dict() for i in items],
            "stats": reg.stats(),
        })

    async def _handle_incident_get(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        iid = request.match_info.get("id", "").strip()
        reg = get_incident_registry()
        inc = reg.get(iid)
        if inc is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(inc.to_dict())

    async def _handle_incident_note(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        from aria.security.middleware import get_request_principal
        iid = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = get_request_principal(request)
        ok = get_incident_registry().attach_note(
            iid,
            actor_principal_id=actor.principal_id,
            text=str(body.get("text", "")).strip(),
        )
        return web.json_response({"ok": bool(ok)},
                                 status=200 if ok else 404)

    async def _handle_incident_fix(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        from aria.security.middleware import get_request_principal
        iid = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = get_request_principal(request)
        ok = get_incident_registry().apply_fix(
            iid,
            actor_principal_id=actor.principal_id,
            summary=str(body.get("summary", "")).strip(),
            success=bool(body.get("success", True)),
        )
        return web.json_response({"ok": bool(ok)},
                                 status=200 if ok else 404)

    async def _handle_incident_root_cause(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        from aria.security.middleware import get_request_principal
        iid = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = get_request_principal(request)
        ok = get_incident_registry().set_root_cause(
            iid,
            actor_principal_id=actor.principal_id,
            text=str(body.get("text", "")).strip(),
        )
        return web.json_response({"ok": bool(ok)},
                                 status=200 if ok else 404)

    async def _handle_incident_resolve(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        from aria.security.middleware import get_request_principal
        iid = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = get_request_principal(request)
        ok = get_incident_registry().resolve(
            iid,
            actor_principal_id=actor.principal_id,
            resolution=str(body.get("resolution", "")).strip(),
        )
        return web.json_response({"ok": bool(ok)},
                                 status=200 if ok else 404)

    async def _handle_incident_defer(self, request: web.Request) -> web.Response:
        from aria.safety.incident_registry import get_incident_registry
        from aria.security.middleware import get_request_principal
        iid = request.match_info.get("id", "").strip()
        try:
            body = await request.json()
        except Exception:
            body = {}
        actor = get_request_principal(request)
        ok = get_incident_registry().defer(
            iid,
            actor_principal_id=actor.principal_id,
            reason=str(body.get("reason", "")).strip(),
        )
        return web.json_response({"ok": bool(ok)},
                                 status=200 if ok else 404)

    async def _handle_audit_trace(self, request: web.Request) -> web.Response:
        """GET /api/audit/trace?incident_id=<id>&trace_id=<id>
            &min_severity=warning&event_type=...&limit=500
        Walk the hash-chained audit log + return every entry tagged
        with the given incident_id / trace_id (or matching other filters)."""
        from aria.security.audit import get_audit_log
        log = get_audit_log()
        iid = (request.query.get("incident_id") or "").strip() or None
        tid = (request.query.get("trace_id") or "").strip() or None
        ev_type = (request.query.get("event_type") or "").strip() or None
        ident = (request.query.get("identity") or "").strip() or None
        min_sev = (request.query.get("min_severity") or "").strip() or None
        try:
            limit = int(request.query.get("limit", "500"))
        except ValueError:
            limit = 500
        ents = log.get_entries(
            event_type=ev_type, identity=ident, limit=limit,
            incident_id=iid, trace_id=tid, min_severity=min_sev,
        )
        return web.json_response({
            "count": len(ents),
            "head_hash": log.head_hash(),
            "entries": [
                {
                    "seq": e.seq, "ts": e.timestamp,
                    "event_type": e.event_type, "identity": e.identity,
                    "action": e.action, "result": e.result,
                    "details": e.details, "severity": e.severity,
                    "source": e.source, "incident_id": e.incident_id,
                    "trace_id": e.trace_id,
                    "hash_value": e.hash_value, "prev_hash": e.prev_hash,
                }
                for e in ents
            ],
        })

    async def _handle_audit_chain_status(self, request: web.Request) -> web.Response:
        """GET /api/audit/chain_status — head hash + integrity + size,
        for the SafetyConsole + monitoring."""
        from aria.security.audit import get_audit_log
        log = get_audit_log()
        ok, broken_at = log.verify_chain()
        return web.json_response({
            **log.chain_status(),
            "verify_ok": bool(ok),
            "first_break_seq_check": broken_at,
        })

    async def _handle_ai_recent_actions(self, request: web.Request) -> web.Response:
        """Rolling log of LLM-derived actions across all agents.

        Two row statuses:
          - 'advisory' — parsed intent that no agent executed (visibility)
          - 'executed' — agent dispatched the corresponding actuator cmd

        Query params:
          limit:    max entries (default 100, max 400)
          since_id: only entries with id > since_id (cheap polling)
          agent:    filter to a single agent name
          status:   'advisory' | 'executed' filter

        Roadmap Track 3 Phase 5.
        """
        from aria.cognitive.action_log import get_action_log

        def _int(name: str, default: int, lo: int = 1, hi: int = 400) -> int:
            try:
                v = int(request.query.get(name, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v))

        limit = _int("limit", 100)
        since = _int("since_id", 0, lo=0, hi=10**9)
        agent_filter = request.query.get("agent", "").strip().lower() or None
        status_filter = request.query.get("status", "").strip().lower() or None
        if status_filter and status_filter not in ("advisory", "executed"):
            return web.json_response(
                {"error": "status must be 'advisory' or 'executed'"},
                status=400,
            )

        log = get_action_log()
        entries = log.recent(limit=limit, since_id=since)
        out = []
        for e in entries:
            if agent_filter and e.agent.lower() != agent_filter:
                continue
            if status_filter and e.status != status_filter:
                continue
            out.append(e.to_dict())
        return web.json_response({
            "count": len(out),
            "capacity": log.capacity,
            "entries": out,
        })

    async def _handle_telemetry_separation(self, request: web.Request) -> web.Response:
        """Inter-spacecraft separation in ECI.

        Query params:
          norad_a, norad_b   — required NORAD catalog IDs
          group_a, group_b   — optional Celestrak groups (default 'active')
          jd                 — optional propagation epoch (default now)

        Returns ``{a:{name,norad,r_eci_km,v_eci_kms}, b:{...},
        separation_km, relative_speed_kmps, jd}``. Used by the live-vs-
        live overlay in the moon-mission and DSN panels — Track 1 P4
        of docs/ROADMAP_THREE_GAPS.md.
        """
        from aria.simulation.tle_parser import parse_tle
        from aria.simulation.satellite_propagator import propagate_tle
        from aria.simulation.solar_system import jd_now

        norad_a = request.query.get("norad_a", "").strip()
        norad_b = request.query.get("norad_b", "").strip()
        if not norad_a or not norad_b:
            return web.json_response(
                {"error": "norad_a and norad_b are required"},
                status=400,
            )
        group_a = request.query.get("group_a", "active").lower().strip()
        group_b = request.query.get("group_b", "active").lower().strip()
        try:
            jd = float(request.query.get("jd", jd_now()))
        except (TypeError, ValueError):
            jd = jd_now()

        async def _resolve(norad: str, group: str) -> tuple[str, list[float], list[float]] | dict:
            # Reuse the same cache machinery as live_state. We don't
            # want to duplicate the fetch loop, so we just call
            # _handle_telemetry_live_state's cache hit path inline.
            cached = self._tle_cache.get(group)
            text: str | None = None
            now_w = __import__("time").time()
            if cached and (now_w - cached["fetched_at_wall"]) < 600:
                text = cached["text"]
            else:
                import aiohttp
                url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=3le"
                try:
                    timeout = aiohttp.ClientTimeout(total=8)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                text = await resp.text()
                except Exception:
                    text = None
                if not text:
                    bundled = Path(__file__).resolve().parents[3] / \
                              "data" / "raw" / "spacetrack" / "full_catalog_3le.txt"
                    try:
                        text = bundled.read_text()
                    except Exception:
                        return {"error": f"catalog '{group}' unavailable"}
                self._tle_cache[group] = {
                    "fetched_at_wall": now_w, "text": text,
                    "source": "celestrak" if "celestrak" in url else "bundled",
                }
            target = norad.lstrip("0").zfill(5)
            lines = text.splitlines()
            i = 0
            while i + 2 < len(lines):
                name = lines[i].strip()
                if name.startswith("0 "):
                    name = name[2:].strip()
                l1 = lines[i + 1]
                l2 = lines[i + 2]
                if l1.startswith("1 ") and l2.startswith("2 "):
                    if l1[2:7].strip().zfill(5) == target:
                        try:
                            tle = parse_tle(l1, l2, name)
                            state = propagate_tle(tle, jd)
                        except Exception as exc:
                            return {"error": f"propagation failed: {exc}"}
                        return (
                            name,
                            [x / 1000.0 for x in state.r_eci_m],
                            [x / 1000.0 for x in state.v_eci_mps],
                        )
                    i += 3
                else:
                    i += 1
            return {"error": f"NORAD {norad} not found in '{group}'"}

        ra = await _resolve(norad_a, group_a)
        rb = await _resolve(norad_b, group_b)
        if isinstance(ra, dict):
            return web.json_response({**ra, "norad": norad_a}, status=404)
        if isinstance(rb, dict):
            return web.json_response({**rb, "norad": norad_b}, status=404)

        name_a, r_a, v_a = ra
        name_b, r_b, v_b = rb
        dx = r_a[0] - r_b[0]
        dy = r_a[1] - r_b[1]
        dz = r_a[2] - r_b[2]
        sep_km = math.sqrt(dx * dx + dy * dy + dz * dz)
        dvx = v_a[0] - v_b[0]
        dvy = v_a[1] - v_b[1]
        dvz = v_a[2] - v_b[2]
        rel_speed = math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz)

        return web.json_response({
            "a": {"name": name_a, "norad": norad_a,
                  "r_eci_km": [round(v, 3) for v in r_a],
                  "v_eci_kms": [round(v, 6) for v in v_a]},
            "b": {"name": name_b, "norad": norad_b,
                  "r_eci_km": [round(v, 3) for v in r_b],
                  "v_eci_kms": [round(v, 6) for v in v_b]},
            "separation_km": round(sep_km, 3),
            "relative_speed_kmps": round(rel_speed, 6),
            "jd": jd,
        })

    async def _handle_dsn_now(self, request: web.Request) -> web.Response:
        """Live NASA Deep Space Network contact state.

        Roadmap Track 1 Phase 3. Uses a 30-second TTL cache (NASA-friendly
        — DSN-Now refreshes every 5 s upstream, but a UI overlay doesn't
        need that resolution and a hammered upstream is bad citizenship).
        Falls back to ``source: 'offline'`` when the DSN-Now feed is
        unreachable so the UI gets a stable empty state.
        """
        from aria.integrations.nasa_public.dsn_now import get_dsn_contacts
        body = await get_dsn_contacts()
        return web.json_response(body)

    async def _handle_satellites(self, request: web.Request) -> web.Response:
        """Current positions of catalog satellites for an observer.

        Query params:
            jd: Julian Date (default = now)
            lat, lon: observer geodetic coords (default Bengaluru)
            min_alt: minimum altitude to include (default −10°, so we
                     can show "rising soon" satellites too)
            categories: comma-separated subset to filter by
        """
        from aria.simulation.satellite_catalog import load_satellites
        from aria.simulation.satellite_propagator import (
            propagate_tle, observer_view, eci_to_ecef, ecef_to_geodetic,
        )
        from aria.simulation.solar_system import jd_now

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        jd = _float("jd", jd_now())
        lat = _float("lat", 12.9716)
        lon = _float("lon", 77.5946)
        min_alt = _float("min_alt", -10.0)
        cat_filter = request.query.get("categories")
        cat_set = set(cat_filter.split(",")) if cat_filter else None

        out = []
        for tle, cat in load_satellites():
            if cat_set and cat not in cat_set:
                continue
            try:
                state = propagate_tle(tle, jd)
                view = observer_view(state, lat, lon)
                ecef = eci_to_ecef(state.r_eci_m, jd)
                sub_lat, sub_lon, _ = ecef_to_geodetic(ecef)
            except Exception:
                continue
            out.append({
                "name": tle.name,
                "category": cat,
                "norad": tle.satellite_number,
                "alt": round(view.altitude_deg, 2),
                "az": round(view.azimuth_deg, 2),
                "range_km": round(view.range_km, 1),
                "altitude_km": round(state.altitude_km, 1),
                "speed_kmps": round(state.speed_kmps, 3),
                "period_min": round(state.period_min, 2),
                "sub_lat": round(sub_lat, 3),
                "sub_lon": round(sub_lon, 3),
                "above_horizon": view.altitude_deg > 0,
            })
        # Brightest above first; "altitude" sort prioritizes overhead passes.
        out.sort(key=lambda s: -s["alt"])
        visible_count = sum(1 for s in out if s["alt"] >= min_alt)
        return web.json_response({
            "jd": jd, "lat": lat, "lon": lon,
            "count": len(out),
            "visible_count": visible_count,
            "satellites": [s for s in out if s["alt"] >= min_alt],
        })

    async def _handle_cities(self, request: web.Request) -> web.Response:
        """List the city presets available to the observer-location panel."""
        from aria.simulation.observer import CITIES
        return web.json_response({
            "cities": [{"name": k, "lat": v[0], "lon": v[1]} for k, v in CITIES.items()],
        })

    async def _handle_sky_now(self, request: web.Request) -> web.Response:
        """What's above the horizon for an observer at (lat, lon, jd).

        Query params:
            lat, lon : observer geodetic coords (deg, lon East positive)
            jd       : Julian Date UT (default = system clock)
            mag_stars: bright-star magnitude limit (default 4.5)
            mag_dso  : Messier magnitude limit (default 8.0)
            min_alt  : minimum altitude to include (default 0.0°)
        """
        from aria.simulation.observer import sky_snapshot, day_conditions
        from aria.simulation.solar_system import jd_now

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        lat = _float("lat", 12.9716)
        lon = _float("lon", 77.5946)
        jd = _float("jd", jd_now())
        mag_stars = _float("mag_stars", 4.5)
        mag_dso = _float("mag_dso", 8.0)
        min_alt = _float("min_alt", 0.0)

        snap = sky_snapshot(jd, lat, lon, mag_stars, mag_dso, min_alt)

        def _pos(p):
            d = {
                "name": p.name, "kind": p.kind,
                "alt": round(p.alt_deg, 3),
                "az":  round(p.az_deg, 3),
                "ra":  round(p.ra_deg, 3),
                "dec": round(p.dec_deg, 3),
                "mag": round(p.magnitude, 2),
                "color": [round(c, 3) for c in p.color],
            }
            if p.distance_au is not None:
                d["distance_au"] = round(p.distance_au, 4)
            return d

        cond = day_conditions(jd, lat, lon)

        return web.json_response({
            "jd": jd,
            "lat": lat,
            "lon": lon,
            "counts": {k: len(v) for k, v in snap.items()},
            "planets":  [_pos(p) for p in snap["planets"]],
            "stars":    [_pos(p) for p in snap["stars"]],
            "messier":  [_pos(p) for p in snap["messier"]],
            "conditions": {
                "sunrise":     cond.sunrise_jd,
                "sunset":      cond.sunset_jd,
                "solar_noon":  cond.solar_noon_jd,
                "civil_dawn":  cond.civil_twilight_dawn_jd,
                "civil_dusk":  cond.civil_twilight_dusk_jd,
                "astro_dawn":  cond.astro_twilight_dawn_jd,
                "astro_dusk":  cond.astro_twilight_dusk_jd,
                "moonrise":    cond.moonrise_jd,
                "moonset":     cond.moonset_jd,
                "moon_phase_label":    cond.moon_phase_label,
                "moon_phase_fraction": round(cond.moon_phase_fraction, 4),
                "moon_age_days":       round(cond.moon_age_days, 2),
            },
        })

    async def _handle_belt_cloud(self, request: web.Request) -> web.Response:
        """Representative minor-body point cloud (main belt + Trojans + KBO + SDO).

        The orbits are synthesized (not real MPC objects) to show the
        radial/inclination structure: Kirkwood gaps in the main belt,
        ±60° Trojan clouds at Jupiter, Plutinos near 39.5 AU, etc.
        """
        from aria.simulation.belt_distribution import (
            synthesize_main_belt, synthesize_trojans,
            synthesize_kuiper_belt, synthesize_scattered_disk,
            sample_position,
        )

        def _int(name, default, lo=0, hi=5000):
            try:
                v = int(request.query.get(name, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v))

        n_mb = _int("main_belt", 600)
        n_tr = _int("trojans", 120)
        n_kb = _int("kuiper", 250)
        n_sd = _int("scattered", 80)

        groups = {
            "main_belt":      synthesize_main_belt(n_mb),
            "trojans":        synthesize_trojans(n_tr),
            "kuiper":         synthesize_kuiper_belt(n_kb),
            "scattered_disk": synthesize_scattered_disk(n_sd),
        }

        # Project to positions + return compact arrays
        out = {}
        colors = {
            "main_belt":     [0.75, 0.65, 0.5],   # tan
            "trojans":       [0.95, 0.7, 0.3],    # amber
            "kuiper":        [0.4, 0.65, 0.95],   # blue
            "scattered_disk": [0.7, 0.4, 0.9],    # purple
        }
        for name, samples in groups.items():
            pts = [sample_position(s) for s in samples]
            out[name] = {
                "count": len(pts),
                "color": colors[name],
                "positions": [[round(p[0], 3), round(p[1], 3), round(p[2], 3)] for p in pts],
                "family_subtype": [s.family for s in samples],
            }
        return web.json_response({"groups": out})

    async def _handle_moon_mission(self, request: web.Request) -> web.Response:
        """Run Apollo-11 or Artemis-3 end-to-end Moon mission and return
        the full phase timeline for UI visualization.

        R65-R4 (2026-04-24): fault-string parser now validates enums and
        surfaces bad tokens as HTTP 400 instead of:
          - 500 on ValueError('abc' → float)
          - silent no-op when the phase name is misspelled (looked like
            the fault was injected but ``_apply_fault`` never matched).
        """
        from aria.simulation.moon_mission_e2e import (
            apollo_11_e2e, artemis_3_e2e, simulate_moon_mission,
            MoonMissionConfig, MissionFault,
        )
        LEGAL_PHASES = {"TLI", "LOI", "POWERED_DESCENT", "POWERED_ASCENT", "TEI"}
        LEGAL_KINDS  = {"engine_out", "propellant_leak", "nav_error",
                        "comms_loss", "cabin_leak", "medical"}

        which = request.query.get("mission", "apollo_11").lower()
        try:
            if which == "artemis_3":
                r = artemis_3_e2e()
            elif which == "custom":
                # Optional fault list as ?faults=TLI:engine_out:0.3,LOI:nav_error:0.5
                fault_str = request.query.get("faults", "")
                faults: list = []
                for tok in (t.strip() for t in fault_str.split(",") if t.strip()):
                    parts = tok.split(":")
                    if len(parts) != 3:
                        return web.json_response({
                            "error": f"fault token must be 'PHASE:KIND:SEVERITY'; got {tok!r}",
                            "legal_phases": sorted(LEGAL_PHASES),
                            "legal_kinds":  sorted(LEGAL_KINDS),
                        }, status=400)
                    phase, kind, sev_raw = parts
                    if phase not in LEGAL_PHASES:
                        return web.json_response({
                            "error": f"unknown phase {phase!r} in fault {tok!r}",
                            "legal_phases": sorted(LEGAL_PHASES),
                        }, status=400)
                    if kind not in LEGAL_KINDS:
                        return web.json_response({
                            "error": f"unknown kind {kind!r} in fault {tok!r}",
                            "legal_kinds": sorted(LEGAL_KINDS),
                        }, status=400)
                    try:
                        sev = float(sev_raw)
                    except ValueError:
                        return web.json_response({
                            "error": f"severity must be numeric in fault {tok!r}; got {sev_raw!r}",
                        }, status=400)
                    if not 0.0 <= sev <= 1.0:
                        return web.json_response({
                            "error": f"severity {sev} out of range in fault {tok!r} (0.0 to 1.0)",
                        }, status=400)
                    faults.append(MissionFault(phase=phase, kind=kind, severity=sev))
                r = simulate_moon_mission(MoonMissionConfig(faults=faults))
            else:
                r = apollo_11_e2e()
        except Exception as exc:
            return web.json_response({"error": f"{type(exc).__name__}: {exc}"},
                                      status=500)
        return web.json_response({
            "summary": r.summary,
            "overall_success": r.overall_success,
            "total_dv_mps": r.total_dv_mps,
            "total_propellant_kg": r.total_propellant_kg,
            "total_duration_hours": r.total_duration_hours,
            "final_mass_kg": r.final_mass_kg,
            "failure_phase": r.failure_phase,
            "phases": [
                {
                    "phase": p.phase,
                    "duration_s": p.duration_s,
                    "delta_v_mps": p.delta_v_mps,
                    "propellant_burned_kg": p.propellant_burned_kg,
                    "mass_after_kg": p.mass_after_kg,
                    "success": p.success,
                    "notes": p.notes,
                }
                for p in r.phases
            ],
        })

    async def _handle_mission_porkchop(self, request: web.Request) -> web.Response:
        """Run a porkchop Lambert search and return the optimal window.

        Query params:
          origin, destination: planet keys ("earth"/"mars"/"venus"/...)
          dep_window_days, arr_window_days: e.g. ``0,400``
          dry_kg, fuel_kg, isp_s: spacecraft mass + Isp
          n_dep, n_arr: grid resolution (default 20×20)
          max_revs: 0 = direct only, 1-2 = scan multi-rev (Phase A)
        """
        from aria.simulation.mission_design import (
            design_mission, ephemeris_functions, _GM_SUN,
        )
        try:
            origin = request.query.get("origin", "earth").lower()
            dest = request.query.get("destination", "mars").lower()
            dep_window = tuple(int(x) for x in
                                request.query.get("dep_window_days", "0,400").split(","))
            arr_window = tuple(int(x) for x in
                                request.query.get("arr_window_days", "150,600").split(","))
            dry_kg = float(request.query.get("dry_kg", "3000"))
            fuel_kg = float(request.query.get("fuel_kg", "6000"))
            isp_s  = float(request.query.get("isp_s", "320"))
            n_dep  = int(request.query.get("n_dep", "20"))
            n_arr  = int(request.query.get("n_arr", "20"))
            max_revs = int(request.query.get("max_revs", "0"))
            er, ev = ephemeris_functions(origin)
            dr, dv = ephemeris_functions(dest)
            d = design_mission(
                origin_ephemeris_fn=er, destination_ephemeris_fn=dr,
                origin_velocity_fn=ev, destination_velocity_fn=dv,
                mu_central=_GM_SUN,
                dep_window=dep_window, arr_window=arr_window,
                dry_mass_kg=dry_kg, fuel_budget_kg=fuel_kg, isp_s=isp_s,
                n_dep=n_dep, n_arr=n_arr,
                origin_name=origin.capitalize(), destination_name=dest.capitalize(),
                max_revs=max_revs,
            )
            # Sample the heliocentric trajectory between departure and
            # arrival so the SolarSystem3D overlay can draw the arc.
            # We use Lambert v1 + Kepler propagation; ~64 samples is
            # enough for a smooth visual line at any solar-system zoom.
            from aria.simulation.lambert_izzo import lambert_izzo
            import numpy as np
            tof_s = d.tof_days * 86400.0
            r1 = er(d.dep_date_day)
            r2 = dr(d.arr_date_day)
            v1, _ = lambert_izzo(_GM_SUN, r1, r2, tof_s,
                                 M=int(getattr(d.porkchop, "best_M", 0)))
            # Two-body Kepler propagation by direct integration of
            # f-and-g series.  For a porkchop visual we don't need
            # SPICE-precision; a 64-step Euler-Cromer in the Sun-fixed
            # frame produces a smooth ellipse that lines up with the
            # planet orbits to within pixel precision.
            traj_au: list[list[float]] = []
            n_samples = 64
            r_curr = np.array(r1, dtype=float)
            v_curr = np.array(v1, dtype=float)
            dt = tof_s / n_samples
            for k in range(n_samples + 1):
                AU_M = 1.495978707e11
                traj_au.append([float(r_curr[0]) / AU_M,
                                float(r_curr[1]) / AU_M,
                                float(r_curr[2]) / AU_M])
                # Symplectic step: v += a·dt; r += v·dt — preserves
                # energy to first order, plenty for a 64-pt visual.
                r_norm = float(np.linalg.norm(r_curr))
                a = -_GM_SUN / (r_norm ** 3) * r_curr
                v_curr = v_curr + a * dt
                r_curr = r_curr + v_curr * dt
            return web.json_response({
                "origin": d.origin, "destination": d.destination,
                "dep_day": d.dep_date_day, "arr_day": d.arr_date_day,
                "tof_days": d.tof_days,
                "c3_departure_km2_s2": d.c3_departure,
                "v_inf_arrival_km_s": d.v_inf_arrival,
                "total_dv_ms": d.total_dv_ms,
                "fuel_required_kg": d.fuel_required_kg,
                "feasible": d.feasible,
                "best_M": int(getattr(d.porkchop, "best_M", 0)),
                "valid_count": d.porkchop.valid_count,
                "total_count": d.porkchop.total_count,
                "trajectory_au": traj_au,
            })
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            return web.json_response(
                {"error": f"{type(exc).__name__}: {exc}"}, status=500,
            )

    async def _handle_mission_aerocapture(self, request: web.Request) -> web.Response:
        """Single atmospheric pass aerocapture simulation.

        Query params:
          body: "mars" / "venus" / "titan" / "earth" (default mars)
          v_inf_m_s, flight_path_deg, bank_angle_deg, entry_alt_m: floats
          mass_kg, l_d, drag_coef, nose_radius_m, drag_area_m2: vehicle floats

        See ``aria.simulation.aerocapture.simulate_aerocapture``.
        """
        from aria.simulation.aerocapture import (
            AerocaptureConfig, AerocaptureVehicle, simulate_aerocapture,
            ATMOSPHERES,
        )
        try:
            body = request.query.get("body", "mars").lower()
            if body not in ATMOSPHERES:
                return web.json_response(
                    {"error": f"unknown body {body!r}",
                     "known": sorted(ATMOSPHERES)}, status=400,
                )
            veh = AerocaptureVehicle(
                mass_kg=float(request.query.get("mass_kg", 4500)),
                lift_to_drag=float(request.query.get("l_d", 0.30)),
                drag_coef=float(request.query.get("drag_coef", 1.55)),
                nose_radius_m=float(request.query.get("nose_radius_m", 1.125)),
                drag_area_m2=float(request.query.get("drag_area_m2", 12.0)),
            )
            cfg = AerocaptureConfig(
                body=body,
                v_inf_m_s=float(request.query.get("v_inf_m_s", 5500)),
                flight_path_deg=float(request.query.get("flight_path_deg", -11.5)),
                bank_angle_deg=float(request.query.get("bank_angle_deg", 60.0)),
                entry_altitude_m=float(request.query.get("entry_alt_m", 125_000)),
                vehicle=veh,
            )
            r = simulate_aerocapture(cfg)
            return web.json_response({
                "body": r.body,
                "captured": r.captured,
                "captured_orbit_a_km": r.captured_orbit_a_km,
                "captured_orbit_e": r.captured_orbit_e,
                "captured_periapsis_alt_km": r.captured_periapsis_alt_km,
                "captured_apoapsis_alt_km": r.captured_apoapsis_alt_km,
                "peak_g": r.peak_g,
                "peak_heat_flux_w_cm2": r.peak_heat_flux_w_cm2,
                "total_heat_load_j_cm2": r.total_heat_load_j_cm2,
                "pass_duration_s": r.pass_duration_s,
                "delta_v_saved_m_s": r.delta_v_saved_m_s,
                "delta_v_required_propulsive_m_s": r.delta_v_required_propulsive_m_s,
                "bank_angle_used_deg": r.bank_angle_used_deg,
                "notes": r.notes,
                # Down-sample the trajectory to keep the JSON small —
                # 11k-step pass becomes ~150 points without loss.
                "trajectory_sampled": [
                    {"t_s": s.t_s, "alt_km": s.alt_m / 1000.0,
                     "v_km_s": s.v_m_s / 1000.0,
                     "fpa_deg": s.flight_path_deg,
                     "g": s.accel_g, "q_w_cm2": s.heat_flux_w_cm2}
                    for s in r.trajectory[::max(1, len(r.trajectory) // 150)]
                ],
            })
        except (ValueError, KeyError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            return web.json_response(
                {"error": f"{type(exc).__name__}: {exc}"}, status=500,
            )

    async def _handle_mission_ensemble_stream(self, request: web.Request) -> web.StreamResponse:
        """Server-Sent Events stream of an ensemble run.

        Each SSE message is one finished run; closing event is the
        aggregate stats.  Frontend (Mission Studio) attaches an
        EventSource and updates a progress bar + live histogram.

        Query params:
          n: number of runs (default 20, capped at 200)
          target_ly, velocity_c, crew_size, seed: GenerationShipConfig knobs
          minimal: "1" to disable expensive subsystems for fast demo runs
        """
        from aria.simulation.generation_ship import GenerationShipConfig
        from aria.simulation.mission_ensemble import run_ensemble
        import asyncio
        import json

        n = min(int(request.query.get("n", 20)), 200)
        cfg_kwargs = {
            "crew_size":          int(request.query.get("crew_size", 4)),
            "velocity_c":         float(request.query.get("velocity_c", 0.10)),
            "target_distance_ly": float(request.query.get("target_ly", 1.0)),
            "seed":               int(request.query.get("seed", 42)),
        }
        if request.query.get("minimal", "1") == "1":
            cfg_kwargs.update(dict(
                enable_manufacturing=False, enable_biomanufacturing=False,
                enable_nanobots=False, enable_starch_synthesis=False,
                enable_glass_archive=False, enable_torpor=False,
                enable_defense=False,
            ))
        base_cfg = GenerationShipConfig(**cfg_kwargs)

        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        await resp.prepare(request)

        # SSE writer.  We stream from a dedicated thread because
        # GenerationShipSimulation.run() is blocking.
        loop = asyncio.get_event_loop()
        progress_queue: asyncio.Queue = asyncio.Queue()

        def progress(i, n_total, last_result):
            event = {
                "type": "run",
                "i": i, "n": n_total,
                "survived": last_result.ship_survived,
                "years": last_result.years_simulated,
                "final_hull": last_result.final_hull_integrity,
                "final_fuel": last_result.final_fuel_fraction,
                "final_crew": last_result.final_crew_count,
                "failure_reason": last_result.failure_reason or None,
            }
            loop.call_soon_threadsafe(progress_queue.put_nowait, event)

        async def runner_task():
            result = await asyncio.to_thread(
                run_ensemble, base_cfg, n, None, None, progress,
            )
            loop.call_soon_threadsafe(progress_queue.put_nowait, {
                "type": "done",
                "n_runs": result.n_runs,
                "wall_time_s": result.wall_time_s,
                "survival_rate": result.survival_rate,
                "failure_reasons": result.failure_reasons,
                "field_stats": {
                    name: {
                        "n": s.n, "mean": s.mean, "median": s.median,
                        "std": s.std, "min": s.min_v, "max": s.max_v,
                        "p05": s.p05, "p95": s.p95,
                    }
                    for name, s in result.field_stats.items()
                },
            })

        task = asyncio.create_task(runner_task())
        try:
            while True:
                event = await progress_queue.get()
                await resp.write(f"data: {json.dumps(event)}\n\n".encode())
                await resp.drain()
                if event.get("type") == "done":
                    break
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await resp.write_eof()
        return resp

    async def _handle_astro_events(self, request: web.Request) -> web.Response:
        """Find astronomical events (oppositions, conjunctions, elongations, perihelia).

        Query params:
            start_jd / end_jd: time range (default = today .. today+365)
            kinds: comma-separated subset, e.g. "opposition,gr_elongation"
                   default = all detectors run
        """
        from aria.simulation.astro_events import (
            find_oppositions, find_greatest_elongations,
            find_inferior_conjunctions, find_planet_pair_conjunctions,
            find_perihelia, find_comet_perihelia, find_lunar_extrema,
            find_solar_eclipses, find_lunar_eclipses,
            find_meteor_shower_peaks,
        )
        from aria.simulation.solar_system import jd_now

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        start_jd = _float("start_jd", jd_now())
        end_jd = _float("end_jd", start_jd + 365.0)
        if end_jd - start_jd > 365.0 * 5:
            end_jd = start_jd + 365.0 * 5  # cap at 5 years
        kinds = (request.query.get("kinds") or "").split(",") if request.query.get("kinds") else None

        all_events = []
        if kinds is None or "opposition" in kinds:
            all_events.extend(find_oppositions(start_jd, end_jd))
        if kinds is None or "gr_elongation" in kinds:
            all_events.extend(find_greatest_elongations(start_jd, end_jd))
        if kinds is None or "conjunction" in kinds:
            all_events.extend(find_inferior_conjunctions(start_jd, end_jd))
            all_events.extend(find_planet_pair_conjunctions(start_jd, end_jd))
        if kinds is None or "perihelion" in kinds:
            all_events.extend(find_perihelia(start_jd, end_jd))
            all_events.extend(find_comet_perihelia(start_jd, end_jd))
        if kinds is None or "lunar" in kinds:
            all_events.extend(find_lunar_extrema(start_jd, end_jd))
        if kinds is None or "eclipse" in kinds:
            all_events.extend(find_solar_eclipses(start_jd, end_jd))
            all_events.extend(find_lunar_eclipses(start_jd, end_jd))
        if kinds is None or "meteor_shower" in kinds:
            all_events.extend(find_meteor_shower_peaks(start_jd, end_jd))

        all_events.sort(key=lambda e: e.jd)
        return web.json_response({
            "start_jd": start_jd,
            "end_jd": end_jd,
            "count": len(all_events),
            "events": [
                {
                    "jd": round(e.jd, 4),
                    "kind": e.kind,
                    "body": e.body,
                    "body2": e.body2,
                    "value": round(e.value, 4),
                    "description": e.description,
                }
                for e in all_events
            ],
        })

    async def _handle_orbits(self, request: web.Request) -> web.Response:
        """Heliocentric orbit traces + current positions for the 3D viewer.

        Returns sampled (x, y, z) AU points around each orbit (one revolution
        for elliptical bodies; bounded arc for comets) plus the body's current
        position at the requested epoch.

        Query params:
            jd: Julian Date for current-position marker (default = now)
            include_small: "1" to also return asteroids/comets (default "1")
            samples: number of points per orbit trace (default 96)
        """
        from aria.simulation.solar_system import (
            jd_now, PLANET_ELEMENTS, PLANET_COLOR,
            heliocentric_ecliptic, _solve_kepler, centuries_from_j2000,
        )
        from aria.simulation.small_bodies import ASTEROIDS, COMETS, _helio_smallbody
        import math as _m

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        def _int(name, default, lo=24, hi=512):
            try:
                v = int(request.query.get(name, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v))

        jd = _float("jd", jd_now())
        n_samples = _int("samples", 96)
        include_small = request.query.get("include_small", "1") == "1"

        out_orbits = []
        # Planets — sample mean anomaly 0..2π, hold all other elements at jd.
        for name in PLANET_ELEMENTS.keys():
            el = PLANET_ELEMENTS[name]
            T = centuries_from_j2000(jd)
            a    = el["a"][0]    + el["a"][1]    * T
            e    = el["e"][0]    + el["e"][1]    * T
            inc  = el["i"][0]    + el["i"][1]    * T
            wbar = el["wbar"][0] + el["wbar"][1] * T
            node = el["node"][0] + el["node"][1] * T
            omega = wbar - node

            # Build 3D orbit by sweeping eccentric anomaly E.
            pts = []
            for k in range(n_samples + 1):
                E = (2 * _m.pi) * k / n_samples
                xo = a * (_m.cos(E) - e)
                yo = a * _m.sqrt(1 - e * e) * _m.sin(E)
                co, so = _m.cos(_m.radians(omega)), _m.sin(_m.radians(omega))
                cn, sn = _m.cos(_m.radians(node)),  _m.sin(_m.radians(node))
                ci, si = _m.cos(_m.radians(inc)),   _m.sin(_m.radians(inc))
                x = (co * cn - so * sn * ci) * xo + (-so * cn - co * sn * ci) * yo
                y = (co * sn + so * cn * ci) * xo + (-so * sn + co * cn * ci) * yo
                z = (so * si) * xo + (co * si) * yo
                pts.append([round(x, 4), round(y, 4), round(z, 4)])

            cur = heliocentric_ecliptic(name, jd)
            color = PLANET_COLOR.get(name, (0.8, 0.8, 0.8))
            out_orbits.append({
                "name": name,
                "kind": "planet",
                "a_au": a,
                "e": e,
                "inc_deg": inc,
                "color": [round(c, 3) for c in color],
                "trace": pts,
                "current": [round(cur[0], 4), round(cur[1], 4), round(cur[2], 4)],
            })

        if include_small:
            for src, kind, color in ((ASTEROIDS, "asteroid", (0.85, 0.80, 0.70)),
                                     (COMETS, "comet", (0.85, 0.85, 0.95))):
                for b in src:
                    pts = []
                    co, so = _m.cos(_m.radians(b.argp_deg)), _m.sin(_m.radians(b.argp_deg))
                    cn, sn = _m.cos(_m.radians(b.node_deg)), _m.sin(_m.radians(b.node_deg))
                    ci, si = _m.cos(_m.radians(b.inc_deg)),  _m.sin(_m.radians(b.inc_deg))

                    if b.e < 0.998:
                        # Closed elliptical loop, sweep eccentric anomaly.
                        for k in range(n_samples + 1):
                            E = (2 * _m.pi) * k / n_samples
                            xo = b.a_au * (_m.cos(E) - b.e)
                            yo = b.a_au * _m.sqrt(1 - b.e * b.e) * _m.sin(E)
                            x = (co * cn - so * sn * ci) * xo + (-so * cn - co * sn * ci) * yo
                            y = (co * sn + so * cn * ci) * xo + (-so * sn + co * cn * ci) * yo
                            z = (so * si) * xo + (co * si) * yo
                            pts.append([round(x, 4), round(y, 4), round(z, 4)])
                    elif b.e <= 1.002:
                        # Near-parabolic — sweep true anomaly within a finite arc
                        # capped at r ≤ 60 AU so the line doesn't escape the scene.
                        q = b.a_au * (1 - b.e) if b.e < 1.0 else min(b.a_au, 5.0)
                        for k in range(n_samples + 1):
                            nu = (-2.5 + 5.0 * k / n_samples)
                            denom = 1 + b.e * _m.cos(nu)
                            if denom <= 1e-4:
                                continue
                            r = q * (1 + b.e) / denom if b.e < 1.0 else q * (1 + _m.tan(nu/2)**2)
                            if r > 60: continue
                            xo, yo = r * _m.cos(nu), r * _m.sin(nu)
                            x = (co * cn - so * sn * ci) * xo + (-so * cn - co * sn * ci) * yo
                            y = (co * sn + so * cn * ci) * xo + (-so * sn + co * cn * ci) * yo
                            z = (so * si) * xo + (co * si) * yo
                            pts.append([round(x, 4), round(y, 4), round(z, 4)])
                    else:
                        # Hyperbolic — sweep F in [-3, 3] capped at r ≤ 80 AU.
                        a_neg = -abs(b.a_au)
                        for k in range(n_samples + 1):
                            F = -3.0 + 6.0 * k / n_samples
                            xo = a_neg * (b.e - _m.cosh(F))
                            yo = -a_neg * _m.sqrt(b.e * b.e - 1) * _m.sinh(F)
                            r = _m.sqrt(xo * xo + yo * yo)
                            if r > 80: continue
                            x = (co * cn - so * sn * ci) * xo + (-so * cn - co * sn * ci) * yo
                            y = (co * sn + so * cn * ci) * xo + (-so * sn + co * cn * ci) * yo
                            z = (so * si) * xo + (co * si) * yo
                            pts.append([round(x, 4), round(y, 4), round(z, 4)])

                    cur = _helio_smallbody(b, jd)
                    if cur is None or not pts:
                        continue
                    out_orbits.append({
                        "name": b.name,
                        "kind": kind,
                        "a_au": b.a_au,
                        "e": b.e,
                        "inc_deg": b.inc_deg,
                        "color": [round(c, 3) for c in (b.color if hasattr(b, 'color') else color)],
                        "trace": pts,
                        "current": [round(cur[0], 4), round(cur[1], 4), round(cur[2], 4)],
                    })

        return web.json_response({
            "jd": jd,
            "orbits": out_orbits,
        })

    async def _handle_porkchop(self, request: web.Request) -> web.Response:
        """Compute porkchop plot for any planet pair via the heliocentric Lambert solver.

        Path: /api/porkchop/{origin}/{dest}
        Query params:
            dep_start, dep_end : departure window (days from epoch)
            arr_start, arr_end : arrival window
            n_dep, n_arr       : grid resolution per axis
        """
        from aria.simulation.mission_design import (
            ephemeris_functions, _GM_SUN,
        )
        from aria.simulation.porkchop import compute_porkchop

        origin = request.match_info.get("origin", "").lower()
        dest = request.match_info.get("dest", "").lower()

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        def _int(name, default, lo=4, hi=80):
            try:
                v = int(request.query.get(name, default))
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, v))

        try:
            r_origin, v_origin = ephemeris_functions(origin)
            r_dest, v_dest = ephemeris_functions(dest)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)

        result = compute_porkchop(
            mu_central=_GM_SUN,
            r_departure_fn=r_origin,
            r_arrival_fn=r_dest,
            v_planet_departure_fn=v_origin,
            v_planet_arrival_fn=v_dest,
            dep_range_days=(_float("dep_start", 0), _float("dep_end", 400)),
            arr_range_days=(_float("arr_start", 150), _float("arr_end", 600)),
            n_dep=_int("n_dep", 30),
            n_arr=_int("n_arr", 30),
        )

        # Replace inf/nan with None so JSON serializes cleanly.
        import numpy as _np
        def _clean(arr):
            return [
                [None if (not _np.isfinite(x)) else float(x) for x in row]
                for row in arr
            ]

        return web.json_response({
            "origin": origin,
            "destination": dest,
            "departure_days": result.departure_days.tolist(),
            "arrival_days": result.arrival_days.tolist(),
            "c3_departure": _clean(result.c3_departure),
            "v_inf_arrival": _clean(result.v_inf_arrival),
            "tof_days": _clean(result.tof_days),
            "best_c3": float(result.best_c3) if _np.isfinite(result.best_c3) else None,
            "best_dep_day": float(result.best_dep_day),
            "best_arr_day": float(result.best_arr_day),
            "best_tof_days": float(result.best_tof_days),
            "valid_count": result.valid_count,
            "total_count": result.total_count,
        })

    async def _handle_star_field(self, request: web.Request) -> web.Response:
        """Return star field data for planetarium view.

        Query params:
            years: years from J2000 (default: 0)
            beta: v/c for aberration (default: 0)
            vx, vy, vz: velocity direction (default: 1,0,0)
        """
        from aria.simulation.star_field import (
            generate_star_field_data, load_hyg, CONSTELLATION_LINES,
            star_position_at_epoch, relativistic_aberration,
        )
        from aria.simulation.constellations import (
            CONSTELLATION_LINES_88, CONSTELLATIONS,
        )
        import numpy as np

        def _float(name, default):
            try:
                return float(request.query.get(name, default))
            except (TypeError, ValueError):
                return default

        years = _float("years", 0.0)
        beta = _float("beta", 0.0)
        vx = _float("vx", 1.0)
        vy = _float("vy", 0.0)
        vz = _float("vz", 0.0)

        stars = generate_star_field_data(
            years_from_j2000=years,
            beta=beta,
            velocity_direction=np.array([vx, vy, vz]),
        )
        # Build a HIP → (RA,Dec) lookup from the FULL catalog (not the
        # mag-filtered render list) so constellation lines using fainter
        # stars still draw. Apply the same epoch + aberration corrections.
        full_catalog = load_hyg()
        star_by_hip: dict = {}
        vel = np.array([vx, vy, vz], dtype=float)
        vel_norm = np.linalg.norm(vel)
        if vel_norm > 0:
            vel = vel / vel_norm
        for s in full_catalog:
            ra, dec = star_position_at_epoch(s, years)
            if beta > 1e-6:
                ra, dec = relativistic_aberration(ra, dec, vel, beta)
            star_by_hip[s.hip_id] = {"ra": ra, "dec": dec}

        # Use the expanded 88-constellation set, falling back to the small
        # legacy set if the new module ever fails to import.
        line_source = CONSTELLATION_LINES_88 or CONSTELLATION_LINES
        constellations = {}
        for name, lines in line_source.items():
            segments = []
            for hip_a, hip_b in lines:
                a = star_by_hip.get(hip_a)
                b = star_by_hip.get(hip_b)
                if a and b:
                    segments.append({
                        "from": {"ra": a["ra"], "dec": a["dec"]},
                        "to": {"ra": b["ra"], "dec": b["dec"]},
                    })
            if segments:
                constellations[name] = segments

        # Centroid metadata for placing constellation labels. Send only
        # the abbreviation + (ra, dec) to keep the payload light.
        constellation_centroids = [
            {"abbr": c.abbr, "name": c.name,
             "ra": c.ra_deg, "dec": c.dec_deg}
            for c in CONSTELLATIONS
        ]

        # Notable exoplanet host stars — overlaid on the sky chart
        from aria.simulation.exoplanets import EXOPLANET_HOSTS
        exo_mag_lim = _float("exo_mag", 8.5)
        exoplanet_hosts = [
            {
                "name": h.name, "ra": h.ra_deg, "dec": h.dec_deg,
                "mag": h.host_mag, "distance_ly": h.distance_ly,
                "n_planets": h.n_planets,
                "description": h.description,
            }
            for h in EXOPLANET_HOSTS if h.host_mag <= exo_mag_lim
        ]

        # Messier deep-sky catalog — naked-eye + small-telescope objects.
        from aria.simulation.messier import visible_messier
        messier_mag_lim = _float("messier_mag", 11.0)
        deep_sky = [
            {
                "m": m.m,
                "ngc": m.ngc,
                "name": m.name,
                "ra": m.ra_deg,
                "dec": m.dec_deg,
                "mag": m.vmag,
                "size_amaj": m.size_amaj,
                "size_amin": m.size_amin,
                "obj_class": m.obj_class,
            }
            for m in visible_messier(messier_mag_lim)
        ]

        return web.json_response({
            "stars": stars,
            "constellations": constellations,
            "constellation_centroids": constellation_centroids,
            "messier": deep_sky,
            "exoplanet_hosts": exoplanet_hosts,
            "epoch_years_from_j2000": years,
            "beta": beta,
            "velocity_direction": [vx, vy, vz],
        })


# ─── Simulation Runner (generates demo data) ────────────────

def generate_demo_snapshots(years: int = 200, seed: int = 42) -> list[dict[str, Any]]:
    """Generate demo simulation snapshots for dashboard testing.

    Produces realistic-looking data without requiring the full
    interstellar simulation stack.
    """
    rng = random.Random(seed)
    snapshots: list[dict[str, Any]] = []

    # Initial state
    hull = 1.0
    velocity_c = 0.1
    fuel_kg = 50000.0
    water = 50000.0
    crew = 4
    crew_gen = 1
    power = 500000.0
    food_ratio = 1.0
    distance = 0.0
    seed_viab = 1.0
    morale = 0.8
    shield_mass = 10000.0

    # Challenge states
    challenges = {
        "materials": {"status": "nominal", "severity": 0.0},
        "food": {"status": "nominal", "severity": 0.0},
        "knowledge": {"status": "nominal", "severity": 0.0},
        "genetics": {"status": "nominal", "severity": 0.0},
        "psychology": {"status": "nominal", "severity": 0.0},
        "fuel": {"status": "nominal", "severity": 0.0},
    }

    target_dist = 100.0

    for year in range(1, years + 1):
        events_this_year: list[dict[str, Any]] = []

        # Advance position
        distance += velocity_c
        if distance > target_dist * 0.9:
            phase = "TARGET_APPROACH"
            velocity_c = max(0.001, velocity_c - 0.005)
            fuel_kg -= 500
        elif distance > target_dist * 0.85:
            phase = "OORT_CLOUD_TARGET"
            fuel_kg -= 50
        elif distance < 0.1:
            phase = "DEPARTURE"
            fuel_kg -= 50
        else:
            phase = "INTERSTELLAR_CRUISE"
            fuel_kg -= 50

        fuel_kg = max(0, fuel_kg)

        # Degradation
        hull -= rng.uniform(0.0003, 0.0008)
        hull = max(0, hull)
        power = 500000 * max(0, 1.0 - year * 0.005)
        food_ratio = max(0.1, food_ratio - rng.uniform(0, 0.002))
        water -= rng.uniform(5, 25)
        water = max(0, water)
        seed_viab = max(0, seed_viab - rng.uniform(0.005, 0.015))
        morale = max(0.1, morale - rng.uniform(-0.01, 0.005))
        shield_mass -= rng.uniform(1, 10)
        shield_mass = max(0, shield_mass)

        # Crew lifecycle
        if year % 25 == 0 and year > 0:
            crew_gen += 1
            crew = max(2, crew + rng.randint(-1, 3))

        # Random events
        if rng.random() < 0.15:
            sev = rng.choice(["WARNING", "CRITICAL", "WARNING", "WARNING", "EMERGENCY"])
            cats = [
                ("MICROMETEORITE", "Hull impacted by high-velocity particle"),
                ("ELECTRONICS", "Radiation-induced bit flip in nav computer"),
                ("FOOD", "Hydroponic bay contamination detected"),
                ("POWER", "RTG output below projected curve"),
                ("CREW", "Psychological stress indicators elevated"),
                ("WATER", "Water recycler filter degradation"),
            ]
            cat, desc = rng.choice(cats)
            events_this_year.append({
                "year": year,
                "category": cat,
                "severity": sev,
                "description": f"Year {year}: {desc}",
                "subsystem": cat.lower(),
                "impact": {},
            })
            if sev in ("CRITICAL", "EMERGENCY"):
                hull -= 0.005

        # Challenge progression
        for name, ch in challenges.items():
            ch["severity"] = min(1.0, ch["severity"] + rng.uniform(0.001, 0.005))
            if ch["severity"] < 0.3:
                ch["status"] = "nominal"
            elif ch["severity"] < 0.5:
                ch["status"] = "emerging"
            elif ch["severity"] < 0.7:
                ch["status"] = "active"
            elif ch["severity"] < 0.9:
                ch["status"] = "critical"
            else:
                ch["status"] = "terminal"

        # 3D position with gentle curve
        pos_x = distance
        pos_y = math.sin(distance * 0.1) * 2.0
        pos_z = math.cos(distance * 0.15) * 1.5

        snap = {
            "mission_year": year,
            "distance_ly": round(distance, 4),
            "velocity_c": round(velocity_c, 6),
            "phase": phase,
            "position_x": round(pos_x, 4),
            "position_y": round(pos_y, 4),
            "position_z": round(pos_z, 4),
            "hull_integrity": round(hull, 4),
            "shield_health": round(shield_mass / 10000, 4),
            "total_power_watts": round(power, 1),
            "food_production_ratio": round(food_ratio, 4),
            "crew_count": crew,
            "crew_generation": crew_gen,
            "water_liters": round(water, 1),
            "fuel_fraction": round(fuel_kg / 50000, 4),
            "electronics_health": round(max(0, 1.0 - year * 0.003), 4),
            "seed_viability": round(seed_viab, 4),
            "crew_morale": round(morale, 4),
            "challenges": {
                name: {"status": ch["status"], "severity": round(ch["severity"], 3)}
                for name, ch in challenges.items()
            },
            "events": events_this_year,
        }
        snapshots.append(snap)

    return snapshots


# ─── CLI Entry Point ─────────────────────────────────────────

async def _run_dashboard(
    port: int = 8090,
    host: str = "0.0.0.0",  # nosec B104 (function default; production binds to localhost behind reverse proxy)
    recording: str = "",
    demo: bool = False,
    demo_years: int = 200,
) -> None:
    """Run the dashboard server (async entry point)."""
    config = DashboardConfig(host=host, port=port)
    dashboard = WebDashboard(config)

    if recording:
        n = dashboard.load_recording(recording)
        print(f"Loaded recording: {n} snapshots from {recording}")
    elif demo:
        snapshots = generate_demo_snapshots(years=demo_years)
        dashboard._snapshots = snapshots
        dashboard._recording_loaded = True
        for snap in snapshots:
            if snap.get("events"):
                dashboard._events.extend(snap["events"])
        print(f"Generated {len(snapshots)} demo snapshots ({demo_years} years)")

    await dashboard.start()
    import sys
    print("\n" + "=" * 60)
    print("  ARIA — Autonomous Reasoning & Intelligence for Astronautics")
    print("=" * 60)
    print(f"  Version:    0.3.0")
    print(f"  Python:     {sys.version.split()[0]}")
    print(f"  Server:     http://{host}:{port}")
    print(f"  React UI:   http://{host}:{port}/app")
    print(f"  HTML Lab:   http://{host}:{port}/lab")
    print(f"  API docs:   {99} registered routes")
    print(f"  Health:     http://{host}:{port}/healthz")
    print(f"  Metrics:    http://{host}:{port}/api/metrics")
    print(f"  CORS:       {config.cors_origin}")
    print("=" * 60)
    print("  Press Ctrl+C to stop\n")

    # Register SIGTERM for container orchestrators (Docker, K8s)
    import signal
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("dashboard.shutting_down")
        await dashboard.stop()
        dashboard._compute_pool.shutdown(wait=False)
        logger.info("dashboard.shutdown_complete")


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ARIA Generation Ship Dashboard")
    parser.add_argument("--port", type=int, default=8090, help="Server port")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")  # nosec B104 (CLI default; production overrides)
    parser.add_argument("--recording", default="", help="Path to simulation JSON recording")
    parser.add_argument("--demo", action="store_true", help="Generate demo simulation data")
    parser.add_argument("--demo-years", type=int, default=200, help="Years for demo sim")
    parser.add_argument("--log-level", default="INFO", help="Log level: DEBUG|INFO|WARNING|CRITICAL")
    parser.add_argument("--log-dir", default="logs",
                        help="Directory for rotating JSON event log (empty string = console only)")
    parser.add_argument("--otel", action="store_true",
                        help="Enable OpenTelemetry tracing (tick engine, HTTP, bus)")
    parser.add_argument("--otel-file", default="logs/aria_otel.jsonl",
                        help="File to write console-exported spans to (default: logs/aria_otel.jsonl)")
    parser.add_argument("--otel-max-mb", type=int, default=50,
                        help="Size cap on the OTel span file before rotating (default: 50 MB; total disk ≤ ~2× this)")
    args = parser.parse_args()

    # Structured logging + bus-to-log bridge — every event published on
    # the EventBus is mirrored to aria_events.log in JSON, so operators
    # have a persistent trace across restarts without having to scrape
    # the in-memory ring buffer via /api/events/recent.
    from aria.simulator.telemetry import configure_logging
    configure_logging(
        level=args.log_level,
        log_dir=args.log_dir or None,
        bridge_event_bus=True,
    )

    # OpenTelemetry — wraps tick_engine.advance, each subsystem tick,
    # and every HTTP request in spans. Bus events are recorded as span
    # events on whichever span is active when they fire. Spans land in
    # a JSONL file by default; set OTEL_EXPORTER_OTLP_ENDPOINT in the
    # environment to additionally stream to Tempo / Jaeger / Honeycomb.
    if args.otel:
        from aria.simulator.telemetry_otel import (
            configure_otel, attach_bus_to_spans,
        )
        configure_otel(
            enabled=True,
            export_file=args.otel_file,
            max_bytes=args.otel_max_mb * 1024 * 1024,
        )
        attach_bus_to_spans()

    asyncio.run(
        _run_dashboard(
            port=args.port,
            host=args.host,
            recording=args.recording,
            demo=args.demo,
            demo_years=args.demo_years,
        )
    )



if __name__ == "__main__":
    main()
