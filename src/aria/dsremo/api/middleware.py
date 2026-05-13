"""Security middleware — auth, rate limiting, audit logging, payload limits.

Every request passes through these layers before reaching route handlers.
Defense in depth: even if one layer fails, others catch threats.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import ClassVar

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from aria.dsremo.core.security import RateLimiter
from aria.dsremo.core.tenant import get_trace_id, new_trace_id, set_tenant

logger = structlog.get_logger()


def _is_websocket(scope: dict) -> bool:
    """Check if the current request is a WebSocket upgrade."""
    return scope.get("type") == "websocket"


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies exceeding the size limit.

    First line of defense against memory exhaustion attacks.
    Upload paths are excluded so large CSV files can be sent
    (the route handler enforces its own per-endpoint limit).
    """

    # Paths exempt from the global payload cap (each handler owns its limit).
    _UPLOAD_PATHS: frozenset[str] = frozenset({
        "/api/v1/telemetry/upload",
        "/api/v1/parameters/import-xtce",
    })

    def __init__(self, app, max_bytes: int = 1_048_576):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_websocket(request.scope):
            return await call_next(request)
        if request.url.path in self._UPLOAD_PATHS:
            return await call_next(request)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            logger.warning("payload_too_large", size=content_length)
            return JSONResponse(
                status_code=413,
                content={"detail": f"Payload exceeds {self.max_bytes} bytes"},
            )
        return await call_next(request)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Validate API key on every request (except health check and docs).

    The key→tenant map is read from request.app.state.api_key_tenant_map on
    every request — populated by lifespan after DB connects, refreshable at
    any time (e.g., when new keys are created via CLI).

    On success, the request's tenant is set via ContextVar so all downstream
    DB calls are filtered to that tenant by PostgreSQL RLS.

    The unhashed key never touches disk or logs.
    """

    EXEMPT_PATHS = frozenset({"/api/v1/health", "/docs", "/openapi.json", "/", "/dashboard"})

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_websocket(request.scope):
            return await call_next(request)
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/dashboard"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return JSONResponse(status_code=401, content={"detail": "Missing API key"})

        key_hash = hashlib.sha256(f"dsremo::{api_key}".encode()).hexdigest()
        # Read the live map from app.state — safe to refresh without restart.
        key_tenant_map: dict[str, str] = getattr(
            request.app.state, "api_key_tenant_map", {}
        )
        tenant_id = key_tenant_map.get(key_hash)
        if tenant_id is None:
            logger.warning("auth_failed", path=path, key_prefix=api_key[:8] if api_key else "")
            return JSONResponse(status_code=403, content={"detail": "Invalid API key"})

        # Propagate tenant to all DB calls made during this request.
        set_tenant(tenant_id)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-key sliding window rate limiting."""

    def __init__(self, app, max_requests: int = 300, window_seconds: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(max_requests, window_seconds)

    # Paths that bypass rate limiting (static UI, health checks)
    _EXEMPT_PREFIXES = ("/dashboard", "/landing", "/docs", "/openapi.json", "/redoc")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_websocket(request.scope):
            return await call_next(request)
        path = request.url.path
        # Exempt dashboard/static/docs from rate limiting — only meter API calls
        if path == "/" or any(path.startswith(p) for p in self._EXEMPT_PREFIXES):
            return await call_next(request)
        # Rate limit by API key or by IP for unauthenticated API endpoints
        key = request.headers.get("X-API-Key", "")
        if not key:
            key = request.client.host if request.client else "unknown"

        if not self.limiter.is_allowed(key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log every API request for security auditing.

    Captures: timestamp, method, path, status code, latency, API key prefix.
    Never logs request bodies or full API keys.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_websocket(request.scope):
            return await call_next(request)
        trace_id = new_trace_id()
        start = time.monotonic()
        response = await call_next(request)
        latency_ms = (time.monotonic() - start) * 1000

        api_key = request.headers.get("X-API-Key", "")
        logger.info(
            "api_request",
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=round(latency_ms, 1),
            key_prefix=api_key[:8] if api_key else "none",
            client=request.client.host if request.client else "unknown",
        )
        return response


class BackpressureMiddleware(BaseHTTPMiddleware):
    """Reject POST /telemetry and /connectors requests when pipeline is overloaded."""

    _MAX_CONCURRENT: ClassVar[int] = 50
    _sem: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(50)
    _GATED: ClassVar[tuple[str, ...]] = ("/api/v1/telemetry", "/api/v1/connectors")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "POST" and any(path.startswith(p) for p in self._GATED):
            if self._sem.locked():
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Detection pipeline at capacity. Retry later."},
                    headers={"Retry-After": "5"},
                )
            async with self._sem:
                return await call_next(request)
        return await call_next(request)
