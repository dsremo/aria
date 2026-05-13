"""FastAPI application factory — single entrypoint for the HTTP server.

Wires up middleware, routes, lifespan events, and static file serving.
No global state — everything flows through the app's dependency injection.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from aria.dsremo import __version__
from aria.dsremo.api.middleware import (
    ApiKeyMiddleware,
    AuditLogMiddleware,
    BackpressureMiddleware,
    PayloadLimitMiddleware,
    RateLimitMiddleware,
)
from aria.dsremo.api.routes import router
from aria.dsremo.api.routes_alerts import alerts_router
from aria.dsremo.api.routes_auth import auth_router
from aria.dsremo.api.routes_channels import channels_router
from aria.dsremo.api.routes_connectors import connectors_router
from aria.dsremo.api.routes_incidents import incidents_router
from aria.dsremo.api.routes_health import health_router
from aria.dsremo.api.routes_mission_context import mission_context_router
from aria.dsremo.api.routes_oauth import oauth_router
from aria.dsremo.api.routes_suppress import suppress_router
from aria.dsremo.api.routes_keys import keys_router
from aria.dsremo.api.routes_parameters import parameters_router
from aria.dsremo.api.routes_aria import aria_router
from aria.dsremo.api.routes_tenants import tenants_router
from aria.dsremo.api.routes_users import users_router
from aria.dsremo.api.websocket import ws_router
from aria.dsremo.core.config import load_config

logger = structlog.get_logger()

_DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "dashboard"
_LANDING_DIR   = Path(__file__).resolve().parent.parent.parent.parent / "landing"
_OPS_DIR       = Path(__file__).resolve().parent.parent / "web_assets"  # V3-F4 operator dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect DB (or use memory store in test mode). Shutdown: cleanup."""
    settings = app.state.settings

    if app.state.test_mode:
        # Test mode: swap in the in-memory store so unit tests run without PostgreSQL.
        from aria.dsremo.db import memory_store

        import aria.dsremo.api.routes as routes_mod
        import aria.dsremo.api.routes_alerts as routes_alerts_mod
        import aria.dsremo.api.routes_channels as routes_channels_mod
        import aria.dsremo.api.routes_keys as routes_keys_mod
        import aria.dsremo.api.routes_mission_context as routes_mission_context_mod
        import aria.dsremo.api.routes_parameters as routes_parameters_mod
        import aria.dsremo.api.routes_tenants as routes_tenants_mod
        import aria.dsremo.api.routes_users as routes_users_mod
        import aria.dsremo.detection.detector as detector_mod

        routes_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_channels_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_alerts_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_mission_context_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_parameters_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_users_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_tenants_mod.queries = memory_store  # type: ignore[attr-defined]
        routes_keys_mod.queries = memory_store  # type: ignore[attr-defined]
        detector_mod.queries = memory_store  # type: ignore[attr-defined]

    else:
        from aria.dsremo.db.connection import close_pool, init_pool
        from aria.dsremo.db.migrations import run_migrations

        db = settings.get("database", {})
        await init_pool(
            host=db.get("host", "localhost"),
            port=db.get("port", 5432),
            database=db.get("name", "dsremo"),
            user=db.get("user", "dsremo"),
            password=db.get("password", ""),
            min_size=db.get("pool_min", 2),
            max_size=db.get("pool_max", 10),
        )
        await run_migrations()

        # Load api_key → tenant_id map for the auth middleware.
        # Uses a direct pool connection (bypasses RLS) so it sees all tenants' keys.
        from aria.dsremo.db.queries import load_api_key_map
        app.state.api_key_tenant_map = await load_api_key_map()
        logger.info("api_key_map_loaded", count=len(app.state.api_key_tenant_map))

        # Load per-channel threshold configs into the detector cache.
        # Uses a direct pool connection (bypasses RLS) — same pattern as api_key_map.
        from aria.dsremo.db.queries import load_all_channel_configs
        from aria.dsremo.detection.detector import load_channel_configs
        channel_configs = await load_all_channel_configs()
        load_channel_configs(channel_configs)
        logger.info("channel_configs_loaded", count=len(channel_configs))

        # Load per-tenant alert configs into the AlertService class-level cache.
        from aria.dsremo.alerts.service import AlertService
        from aria.dsremo.db.queries import load_all_alert_configs
        alert_configs = await load_all_alert_configs()
        AlertService.load_configs(alert_configs)

        # Background task: check for anomaly escalations every 60s.
        import asyncio

        async def _escalation_loop() -> None:
            while True:
                await asyncio.sleep(60)
                try:
                    n = await AlertService.check_escalations()
                    if n:
                        logger.info("escalations_dispatched", count=n)
                except Exception as exc:
                    logger.error("escalation_loop_error", error=str(exc))

        asyncio.create_task(_escalation_loop())

        # Load JWT secret from env/config. Warn (not fail) so server still
        # starts in dev mode without a secret — auth routes return 503.
        import os
        jwt_secret = settings.get("auth", {}).get(
            "jwt_secret", os.environ.get("DSREMO_JWT_SECRET", "")
        )
        app.state.jwt_secret = jwt_secret
        if jwt_secret:
            logger.info("jwt_secret_loaded", length=len(jwt_secret))
        else:
            # Wiring audit Pass 5 (F13.9) — production deploys must
            # NOT silently fall back to "auth routes return 503"; that
            # masks a misconfigured deploy as "service is degraded"
            # rather than "operator forgot to set a secret". Pattern
            # matches Pass 1 F13.1 (heartbeat secret) and Pass 3
            # F13.4 / F13.5 / F13.6.
            if os.environ.get("ARIA_ENVIRONMENT", "development") == "production":
                logger.critical(
                    "dsremo.jwt_secret_missing_in_production",
                    impact="auth would silently degrade to 503; refusing to start",
                    fix="set DSREMO_JWT_SECRET env var or auth.jwt_secret in config",
                )
                raise RuntimeError(
                    "dsremo refuses to start in production without DSREMO_JWT_SECRET"
                )
            logger.warning("jwt_secret_missing", hint="Set DSREMO_JWT_SECRET env var")

    # Wire config thresholds into detector singletons
    from aria.dsremo.detection.detector import init_detectors
    init_detectors(settings)

    app.state.start_time = time.monotonic()
    logger.info("dsremo_started", version=__version__)
    yield
    if not app.state.test_mode:
        from aria.dsremo.db.connection import close_pool
        await close_pool()
    logger.info("dsremo_stopped")


def create_app(config_path: Path | None = None, demo: bool = False) -> FastAPI:
    """Build and return the configured FastAPI application.

    Args:
        config_path: Path to dsremo.yaml. Uses default discovery if None.
        demo:        Test-only flag. Runs entirely in-memory with a mock admin user
                     so unit tests work without PostgreSQL. Never used in production.
    """
    settings = load_config(config_path)

    app = FastAPI(
        title="Dsremo",
        description="AI Telemetry Anomaly Detection Engine",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.state.settings = settings
    app.state.start_time = time.monotonic()
    app.state.test_mode = demo        # internal flag for lifespan + health check
    app.state.demo_mode = demo        # backwards-compat alias used by some tests
    # Populated in lifespan after DB connects. Empty dict = no keys loaded yet.
    app.state.api_key_tenant_map: dict[str, str] = {}
    # JWT secret — populated in lifespan from DSREMO_JWT_SECRET env var.
    app.state.jwt_secret: str = ""

    # Test mode: inject a mock admin user so routes work without real auth.
    if demo:
        from aria.dsremo.api.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "test-admin",
            "tenant_id": "default",
            "role": "admin",
            "scope": "tenant",
            "email": "admin@test.local",
        }

    # --- Middleware stack (order matters: outermost runs first) ---
    sec = settings.get("security", {})

    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=sec.get("rate_limit_per_minute", 300),
    )
    app.add_middleware(
        ApiKeyMiddleware,
        enabled=False,  # disabled until first key is generated via CLI
        # key→tenant map is read from app.state.api_key_tenant_map per-request
    )
    app.add_middleware(
        PayloadLimitMiddleware,
        max_bytes=sec.get("max_payload_bytes", 1_048_576),
    )
    app.add_middleware(BackpressureMiddleware)

    cors = settings.get("server", {}).get("cors_origins", ["http://localhost:8400"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # --- Routes ---
    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(oauth_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(mission_context_router, prefix="/api/v1")
    app.include_router(suppress_router, prefix="/api/v1")
    app.include_router(channels_router, prefix="/api/v1")
    app.include_router(connectors_router, prefix="/api/v1")
    app.include_router(tenants_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(keys_router, prefix="/api/v1")
    app.include_router(parameters_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")
    app.include_router(aria_router, prefix="/api/v1")

    # --- Static files ---
    # Landing page (public marketing site) served at /
    # Dashboard app served at /dashboard/ (requires auth — JS redirects to / if no token)
    # Operator dashboard (V3-F4) served at /ops/ — mission timeline + context sidebar
    if _OPS_DIR.exists():
        app.mount("/ops", StaticFiles(directory=str(_OPS_DIR), html=True), name="ops")

    if _DASHBOARD_DIR.exists():
        app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")

    if _LANDING_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_LANDING_DIR), html=True), name="landing")

    return app
