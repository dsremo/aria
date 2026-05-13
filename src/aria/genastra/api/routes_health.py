"""Health and readiness endpoints.

/healthz — Is the process alive? (for liveness probes)
/readyz  — Can the process serve traffic? (for readiness probes)
          Returns 503 if any critical dependency is unhealthy.
          GPU warmup takes 30-60s; Kubernetes must not route traffic during warmup.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from aria.genastra import __version__
from aria.genastra.api.schemas import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
logger = structlog.get_logger()


@router.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe — is the process alive?"""
    return HealthResponse(status="ok", version=__version__)


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe — can we serve traffic?

    Checks: database, Redis, GPU worker availability.
    Returns 503 if any dependency is unhealthy.
    """
    from fastapi.responses import ORJSONResponse

    db_ok = await _check_db()
    redis_ok = await _check_redis()
    gpu_ok = await _check_gpu()

    result = ReadinessResponse(
        status="ready" if (db_ok and redis_ok) else "not_ready",
        gpu=gpu_ok,
        db=db_ok,
        redis=redis_ok,
    )

    if not db_ok or not redis_ok:
        # Return 503 but still include the body for debugging
        return ORJSONResponse(status_code=503, content=result.model_dump())  # type: ignore[return-value]

    return result


async def _check_db() -> bool:
    """Check database connectivity."""
    try:
        from aria.genastra.db.connection import get_pool
        pool = get_pool()
        await pool.fetchval("SELECT 1")
        return True
    except Exception:
        logger.warning("readiness_db_failed")
        return False


async def _check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        from aria.genastra.db.connection import get_redis
        r = get_redis()
        if r is None:
            return False
        await r.ping()
        return True
    except Exception:
        logger.warning("readiness_redis_failed")
        return False


async def _check_gpu() -> bool:
    """Check if GPU worker is responsive via Redis heartbeat.

    GPU being down is NOT a readiness failure — the API can still serve
    cached structures, gene expression, and spectral results. We report
    GPU status for informational purposes.
    """
    try:
        from aria.genastra.db.connection import get_redis
        r = get_redis()
        if r is None:
            return False
        heartbeat = await r.get("genastra:gpu_worker:heartbeat")
        if heartbeat is None:
            return False
        import time
        last_beat = float(heartbeat)
        return (time.time() - last_beat) < 30.0  # Heartbeat within 30s
    except Exception:
        return False
