"""Request middleware: backpressure, rate limiting, payload limits, tenant context."""

from __future__ import annotations

import time
from collections import defaultdict

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from aria.genastra.core.tenant import clear_tenant

logger = structlog.get_logger()

# ── Payload size limit ─────────────────────────────────────────────
MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50 MB (FASTA uploads, FITS files)


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies larger than MAX_REQUEST_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return Response(
                content='{"error": "PayloadTooLarge", "detail": "Request body exceeds 50 MB"}',
                status_code=413,
                media_type="application/json",
            )
        return await call_next(request)


# ── Request logging & timing ───────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 1),
            client=request.client.host if request.client else None,
        )
        return response


# ── Tenant context cleanup ─────────────────────────────────────────

class TenantCleanupMiddleware(BaseHTTPMiddleware):
    """Clear tenant context at the end of every request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        try:
            return await call_next(request)
        finally:
            clear_tenant()


# ── Simple in-memory rate limiter (per-IP) ─────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter per client IP.

    Allows `max_requests` per `window_seconds`. For production,
    replace with Redis-based rate limiting.
    """

    def __init__(self, app: FastAPI, max_requests: int = 100, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Skip rate limiting for health endpoints
        if request.url.path in ("/healthz", "/readyz"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Prune old entries
        bucket = self._buckets[client_ip]
        cutoff = now - self.window_seconds
        self._buckets[client_ip] = [t for t in bucket if t > cutoff]

        if len(self._buckets[client_ip]) >= self.max_requests:
            return Response(
                content='{"error": "RateLimited", "detail": "Too many requests"}',
                status_code=429,
                media_type="application/json",
            )

        self._buckets[client_ip].append(now)
        return await call_next(request)


def register_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI app (order matters: last added = first executed)."""
    app.add_middleware(TenantCleanupMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(PayloadLimitMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=200, window_seconds=60)
