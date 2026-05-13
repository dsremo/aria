"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from aria.genastra import __version__
from aria.genastra.api.errors import register_error_handlers
from aria.genastra.api.middleware import register_middleware
from aria.genastra.core.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle management."""
    # ── Startup ──
    logger.info("genastra_starting", version=__version__)

    # Initialize database
    db_dsn = settings.get("DATABASE_URL", "postgresql://genastra:genastra@localhost:5432/genastra")
    from aria.genastra.db.connection import init_db
    try:
        await init_db(db_dsn)
    except Exception:
        logger.warning("db_init_failed", msg="Database unavailable — DB-backed endpoints will return 503")

    # Initialize Redis
    redis_url = settings.get("REDIS_URL", "redis://localhost:6379/0")
    from aria.genastra.db.connection import init_redis
    try:
        await init_redis(redis_url)
    except Exception:
        logger.warning("redis_init_failed", msg="Redis unavailable — job queue will not work")

    logger.info("genastra_ready", version=__version__)

    yield

    # ── Shutdown ──
    from aria.genastra.db.connection import close_db, close_redis
    await close_redis()
    await close_db()
    logger.info("genastra_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="GenAstra — Genome & Astrobiology Analysis",
        description=(
            "Protein structure prediction (ESMFold), space radiation damage modeling, "
            "spaceflight gene expression analysis (DESeq2), and exoplanet biosignature "
            "detection (Bayesian nested sampling on JWST spectra)."
        ),
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get("CORS_ORIGINS", ["*"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware
    register_middleware(app)

    # Error handlers
    register_error_handlers(app)

    # Routes
    from aria.genastra.api.routes_auth import router as auth_router
    from aria.genastra.api.routes_health import router as health_router

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")

    # Conditionally include routes as modules are built
    _include_optional_routers(app)

    return app


def _include_optional_routers(app: FastAPI) -> None:
    """Include routers for modules that may not be fully built yet."""
    prefix = "/api/v1"

    try:
        from aria.genastra.api.routes_proteins import router as proteins_router
        app.include_router(proteins_router, prefix=prefix)
    except ImportError:
        pass

    try:
        from aria.genastra.api.routes_expression import router as expression_router
        app.include_router(expression_router, prefix=prefix)
    except ImportError:
        pass

    try:
        from aria.genastra.api.routes_radiation import router as radiation_router
        app.include_router(radiation_router, prefix=prefix)
    except ImportError:
        pass

    try:
        from aria.genastra.api.routes_spectra import router as spectra_router
        app.include_router(spectra_router, prefix=prefix)
    except ImportError:
        pass

    try:
        from aria.genastra.api.routes_jobs import router as jobs_router
        app.include_router(jobs_router, prefix=prefix)
    except ImportError:
        pass

    try:
        from aria.genastra.api.routes_reports import router as reports_router
        app.include_router(reports_router, prefix=prefix)
    except ImportError:
        pass

    # ARIA integration routes (synchronous convenience endpoints)
    try:
        from aria.genastra.api.routes_aria import aria_router
        app.include_router(aria_router, prefix=prefix)
    except ImportError:
        pass
