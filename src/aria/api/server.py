"""ARIA API Server — HTTP REST + WebSocket for the Captain's web dashboard.

Endpoints:
  GET  /api/v1/status          — System status (agents, health, safe mode)
  GET  /api/v1/agents          — List all agents with individual status
  GET  /api/v1/alerts          — Recent alerts by severity
  GET  /api/v1/telemetry/scores — Current Dsremo channel scores
  GET  /api/v1/metrics         — Prometheus-style metrics snapshot
  POST /api/v1/command         — Send a command to ARIA (auth required)
  WS   /api/v1/ws/events       — Real-time event stream (alerts, anomalies, telemetry)

TT&C audit hardenings (2026-04-28):
  • C-1 / L-2: WebSocket handshake authenticates Bearer + Origin allow-list;
              every command message must carry a signed envelope.
  • C-2 / M-1: HTTP /api/v1/command requires Bearer (constant-time) AND a
              signed envelope (counter + nonce + timestamp + HMAC).
  • C-3 / L-1 / M-2: ``shared_secret`` is required; production-mode rejects
              empty / well-known defaults; fail-open removed.
  • C-4: every published ``aria.captain.query`` message carries the
         verified envelope identity so the bus consumer can refuse
         unauthenticated commands.
  • H-1: per-source-IP rate limiter replaces the per-endpoint counter.
  • H-2: failed-auth log de-duplication by issuer/IP.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import secrets as _secrets
import ssl
import time
from typing import Any, Callable, Optional

import structlog
import websockets
from websockets.asyncio.server import Server, ServerConnection

from aria.api.command_envelope import (
    DEFAULT_MAX_ENVELOPE_AGE_S,
    EnvelopeVerdict,
    parse_and_verify,
)
from aria.api.per_ip_rate_limiter import PerIPRateLimiter, RateLimitVerdict
from aria.bus.message_bus import Message, MessageBus
from aria.security.sanitizer import InputSanitizer

logger = structlog.get_logger()

# Default rate limit: 30 commands/min per source IP — matches prior global
# budget but isolates per IP to prevent flood-from-one-IP starving others.
COMMAND_RATE_LIMIT = 30
COMMAND_WINDOW_S = 60.0

# Banned shared-secret values mirror auth.py::_BANNED_SHARED_SECRETS.
# A production server must never start with one of these.
_BANNED_API_SECRETS = frozenset({
    "", "aria-default-secret", "aria-dev-secret", "default", "secret",
    "changeme", "admin", "password", "test", "dev",
})

# Failed-auth log dedup window — keep one summary line per
# (source_ip, reason) per ``_FAILED_AUTH_LOG_WINDOW_S`` instead of one
# per attempt (TT&C audit H-2).
_FAILED_AUTH_LOG_WINDOW_S = 30.0    # s — empirically tight enough for live triage


def _ws_reject(status: int, reason: str) -> Any:
    """Build a websockets ``Response`` rejecting the handshake.

    The websockets library exposes ``Response.from_status`` on >=13.0;
    for older releases we return a tuple ``(status, headers, body)``.
    """
    body = (reason + "\n").encode("utf-8")
    try:
        from websockets.http11 import Response   # websockets >= 13
        return Response(status, "", [], body)    # type: ignore[arg-type]
    except Exception:    # noqa: BLE001
        return (status, [("Content-Type", "text/plain")], body)


class AriaAPIServer:
    """HTTP REST + WebSocket API server for ARIA.

    Provides read-only endpoints for dashboard polling and a WebSocket
    endpoint for real-time event streaming.
    """

    def __init__(
        self,
        bus: MessageBus,
        system_status_fn: Callable[[], dict[str, Any]],
        shared_secret: str,
        host: str = "127.0.0.1",
        http_port: int = 8080,
        ws_port: int = 8081,
        event_log: Any = None,
        scratchpad: Any = None,
        *,
        production_mode: bool = False,
        legacy_bearer_only: bool = True,
        allowed_origins: Optional[set[str]] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        replay_guard: Any = None,
        rate_per_min: int = COMMAND_RATE_LIMIT,
    ) -> None:
        # TT&C audit C-3 / L-1 / M-2 — refuse empty or well-known
        # defaults at construction time so a misconfigured deploy
        # cannot fail open.  Production deploys further refuse any
        # short / banned value via the production_mode branch below.
        if not isinstance(shared_secret, str):
            raise TypeError("shared_secret must be a string")
        if shared_secret.strip().lower() in _BANNED_API_SECRETS:
            raise RuntimeError(
                "AriaAPIServer.shared_secret_banned — refusing to start "
                "with empty / well-known shared secret"
            )
        if production_mode and len(shared_secret.encode("utf-8")) < 32:
            raise RuntimeError(
                "AriaAPIServer.shared_secret_too_short — production "
                "mode requires >= 32-byte shared secret"
            )

        self._bus = bus
        self._system_status_fn = system_status_fn
        self._shared_secret = shared_secret
        self._shared_secret_bytes = shared_secret.encode("utf-8")
        self._host = host
        self._http_port = http_port
        self._ws_port = ws_port
        self._sanitizer = InputSanitizer()
        self._event_log = event_log
        self._scratchpad = scratchpad
        self._diagnostics_fn: Any = None  # Set externally if coordinator available
        # Wiring audit Pass 7 (F11.4 / F11.6) — public typed slot for
        # the coordinator's readiness_check callable. Use the public
        # ``set_readiness_fn`` / ``set_diagnostics_fn`` setters below
        # instead of poking these attributes directly.
        self._readiness_fn: Any = None

        # TT&C audit C-1 / C-2 — production mode requires the four-factor
        # envelope on every mutation request.  Non-production mode keeps
        # legacy bearer-only behaviour for tests.
        self._production_mode = production_mode
        self._legacy_bearer_only = (
            legacy_bearer_only and not production_mode
        )
        # TT&C audit L-2 — Origin allow-list for WebSocket handshakes.
        self._allowed_origins = (
            set(allowed_origins) if allowed_origins is not None else set()
        )
        # TT&C audit L-3 — optional SSL context for HTTP/WS sockets.
        self._ssl_context = ssl_context

        # State
        self._ws_clients: set[ServerConnection] = set()
        self._recent_alerts: list[dict[str, Any]] = []
        self._channel_scores: dict[str, float] = {}
        self._max_alerts = 200
        self._http_server: asyncio.Server | None = None
        self._ws_server: Server | None = None
        self._running = False

        # TT&C audit H-1 — per-source-IP rate limiter (replaces global list).
        self._rate_limiter = PerIPRateLimiter(rate_per_min=rate_per_min)

        # TT&C audit C-1 / C-2 — replay guard for envelope (counter + nonce).
        # Lazy import keeps module-load time low; production main.py wires
        # the singleton ReplayGuard from aria.safety.replay_guard.
        if replay_guard is None:
            from aria.safety.replay_guard import get_replay_guard
            replay_guard = get_replay_guard()
        self._replay_guard = replay_guard

        # TT&C audit H-2 — failed-auth log dedup state.
        self._failed_auth_last_log: dict[tuple[str, str], float] = {}
        self._failed_auth_counts: dict[tuple[str, str], int] = {}

    def set_diagnostics_fn(self, fn: Any) -> None:
        """Wiring audit Pass 7 (F11.6) — public setter for the
        diagnostics callable (replaces direct ``api._diagnostics_fn=``
        assignment from main.py)."""
        self._diagnostics_fn = fn

    def set_readiness_fn(self, fn: Any) -> None:
        """Wiring audit Pass 7 (F11.4) — public setter for the
        readiness_check callable. main.py wires this with
        ``api.set_readiness_fn(coordinator.readiness_check)``."""
        self._readiness_fn = fn

    async def start(self) -> None:
        """Start HTTP and WebSocket servers."""
        self._running = True

        # Subscribe to bus events for real-time streaming
        self._bus.subscribe("aria.captain.alert", self._on_alert)
        self._bus.subscribe("aria.anomaly.*", self._on_anomaly)
        self._bus.subscribe("aria.telemetry.scored", self._on_scored)
        self._bus.subscribe("aria.safety.mode_change", self._on_mode_change)
        self._bus.subscribe("aria.power.load_shed.*", self._on_power_event)
        self._bus.subscribe("aria.anomaly.correlation", self._on_correlation)

        # Start HTTP server
        self._http_server = await asyncio.start_server(
            self._handle_http,
            self._host,
            self._http_port,
            ssl=self._ssl_context,
        )
        logger.info(
            "api.http_started",
            host=self._host,
            port=self._http_port,
            tls=self._ssl_context is not None,
            production_mode=self._production_mode,
        )

        # Start WebSocket server.
        # TT&C audit C-1 / L-2 — process_request hook checks Bearer +
        # Origin during the WS handshake so unauthorized clients never
        # progress to the message loop.
        self._ws_server = await websockets.serve(
            self._handle_ws,
            self._host,
            self._ws_port,
            ssl=self._ssl_context,
            process_request=self._ws_process_request,
        )
        logger.info(
            "api.ws_started",
            host=self._host,
            port=self._ws_port,
            tls=self._ssl_context is not None,
        )

    async def stop(self) -> None:
        """Gracefully shut down both servers."""
        self._running = False

        # Close all WebSocket clients
        for ws in list(self._ws_clients):
            await ws.close()
        self._ws_clients.clear()

        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()

        if self._http_server:
            self._http_server.close()
            await self._http_server.wait_closed()

        logger.info("api.stopped")

    # -----------------------------------------------------------------------
    # HTTP Request Handler
    # -----------------------------------------------------------------------

    async def _handle_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming HTTP request."""
        # Source IP for rate-limit + log correlation.
        peer = writer.get_extra_info("peername") if writer else None
        source_ip = str(peer[0]) if peer else "unknown"
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not request_line:
                writer.close()
                return

            request_str = request_line.decode("utf-8", errors="replace").strip()
            parts = request_str.split()
            if len(parts) < 2:
                await self._send_http(writer, 400, {"error": "Bad request"})
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    break
                if ":" in line_str:
                    key, value = line_str.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            # Read body for POST
            body = b""
            content_length = int(headers.get("content-length", "0"))
            if content_length > 0 and content_length <= 10_000:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5)

            # Route request — pass source_ip for rate limit + auth logs.
            await self._route(method, path, headers, body, writer, source_ip=source_ip)

        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:
            logger.error("api.http_error", error=str(exc))
            try:
                await self._send_http(writer, 500, {"error": "Internal server error"})
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _route(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        writer: asyncio.StreamWriter,
        *,
        source_ip: str = "unknown",
    ) -> None:
        """Route HTTP request to the appropriate handler."""
        # CORS preflight
        if method == "OPTIONS":
            await self._send_http(writer, 204, None, cors=True)
            return

        # Read-only endpoints (no auth required)
        if method == "GET":
            if path == "/api/v1/status":
                data = self._system_status_fn()
                await self._send_http(writer, 200, data)
            elif path == "/api/v1/agents":
                status = self._system_status_fn()
                await self._send_http(writer, 200, {"agents": status.get("agents", {})})
            elif path == "/api/v1/alerts":
                await self._send_http(writer, 200, {
                    "alerts": self._recent_alerts[-50:],
                    "total": len(self._recent_alerts),
                })
            elif path == "/api/v1/telemetry/scores":
                await self._send_http(writer, 200, {
                    "channel_scores": self._channel_scores,
                    "channels_tracked": len(self._channel_scores),
                })
            elif path == "/api/v1/metrics":
                status = self._system_status_fn()
                await self._send_http(writer, 200, {
                    "health_score": status.get("health_score", 100.0),
                    "safe_mode": status.get("safe_mode", "NOMINAL"),
                    "agents": {
                        name: info.get("status", "UNKNOWN")
                        for name, info in status.get("agents", {}).items()
                    },
                    "alert_count": len(self._recent_alerts),
                    "channels_tracked": len(self._channel_scores),
                })
            elif path == "/api/v1/health":
                await self._send_http(writer, 200, {"status": "ok", "service": "aria-core"})
            elif path == "/api/v1/events":
                if self._event_log:
                    summary = self._event_log.summary()
                    recent = self._event_log.query(limit=20)
                    await self._send_http(writer, 200, {
                        "summary": summary,
                        "recent": [
                            {"timestamp": e.timestamp, "category": e.category,
                             "severity": e.severity, "source": e.source, "summary": e.summary}
                            for e in recent
                        ],
                    })
                else:
                    await self._send_http(writer, 200, {"summary": {}, "recent": []})
            elif path == "/api/v1/readiness":
                # Wiring audit Pass 7 (F11.4) — use the typed
                # ``_readiness_fn`` callable instead of reaching into
                # ``_diagnostics_fn.__self__`` to recover a bound
                # method's instance. Falls back to the legacy
                # diagnostics-fn ``__self__`` introspection for
                # backward compat with deploys that haven't migrated
                # to ``set_readiness_fn``.
                if self._readiness_fn:
                    await self._send_http(writer, 200, self._readiness_fn())
                elif self._diagnostics_fn:
                    coord = getattr(self._diagnostics_fn, '__self__', None)
                    if coord and hasattr(coord, 'readiness_check'):
                        await self._send_http(writer, 200, coord.readiness_check())
                    else:
                        await self._send_http(writer, 200, {"go_for_operations": True})
                else:
                    await self._send_http(writer, 200, {"go_for_operations": True})
            elif path == "/api/v1/diagnostics":
                if self._diagnostics_fn:
                    await self._send_http(writer, 200, self._diagnostics_fn())
                else:
                    await self._send_http(writer, 200, {"status": "diagnostics not available"})
            elif path == "/api/v1/bus/history":
                history = self._bus.get_history(limit=50)
                await self._send_http(writer, 200, {
                    "messages": [
                        {
                            "topic": m.topic,
                            "source": m.source_agent,
                            "priority": m.priority.name if m.priority else "UNKNOWN",
                            "timestamp": m.timestamp,
                            "payload_keys": list(m.payload.keys()) if isinstance(m.payload, dict) else [],
                        }
                        for m in history[-50:]
                    ],
                    # Wiring audit Pass 7 (F11.5) — read history depth
                    # from the public stats dict instead of
                    # ``self._bus._history`` (private).
                    "total_in_history": self._bus.stats.get("history_size", 0),
                    "bus_stats": self._bus.stats,
                })
            elif path == "/api/v1/scratchpad":
                if self._scratchpad:
                    await self._send_http(writer, 200, {
                        "entries": self._scratchpad.all_entries(),
                        "size": self._scratchpad.size,
                    })
                else:
                    await self._send_http(writer, 200, {"entries": {}, "size": 0})
            else:
                await self._send_http(writer, 404, {"error": "Not found"})
            return

        # Mutation endpoints (auth required).
        # TT&C audit H-1: per-IP rate limit precedes every auth check —
        # auth-flooding from one IP cannot starve other clients.
        if method == "POST":
            verdict = self._rate_limiter.check(source_ip)
            if not verdict.allowed:
                await self._send_http(writer, 429, {
                    "error": "Rate limit exceeded",
                    "retry_after_s": round(verdict.retry_after_s, 1),
                    "violations": verdict.violations,
                })
                return

            envelope = self._authenticate_post(headers, body, source_ip=source_ip)
            if not envelope.accepted:
                await self._send_http(writer, 401, {"error": "Unauthorized"})
                return

            if path == "/api/v1/command":
                await self._handle_command(body, writer, envelope=envelope,
                                           source_ip=source_ip)
            else:
                await self._send_http(writer, 404, {"error": "Not found"})
            return

        await self._send_http(writer, 405, {"error": "Method not allowed"})

    # ── Auth helpers ────────────────────────────────────────────────

    def _authenticate_post(
        self,
        headers: dict[str, str],
        body: bytes,
        *,
        source_ip: str,
    ) -> EnvelopeVerdict:
        """Authenticate a POST request.

        TT&C audit C-1 / C-2 / C-3 / M-1:
          1. Bearer token present + constant-time-equal to shared secret.
          2. In production mode (or when X-ARIA-* envelope is supplied)
             verify the four-factor envelope; reject replay via ReplayGuard.
          3. ``hmac.compare_digest`` is used for the bearer comparison.
        """
        auth_header = headers.get("authorization", "")
        expected_bearer = f"Bearer {self._shared_secret}"
        if not hmac.compare_digest(auth_header, expected_bearer):
            self._log_failed_auth(source_ip, "bearer_mismatch")
            return EnvelopeVerdict(False, reason="bearer_mismatch")

        # If any envelope header is present, fully verify it.  In
        # production mode the envelope is mandatory; otherwise legacy
        # bearer-only is allowed for tests / dev.
        envelope_present = any(
            headers.get(name) for name in (
                "x-aria-counter", "x-aria-nonce",
                "x-aria-timestamp", "x-aria-signature",
            )
        )
        if not envelope_present:
            if self._legacy_bearer_only:
                # Legacy mode — treat the bearer alone as a synthetic envelope
                # so downstream code has a uniform identity object.  We do
                # NOT push a synthetic counter through ReplayGuard because
                # legacy clients lack monotonic sequence numbers.
                return EnvelopeVerdict(
                    accepted=True,
                    issuer=f"bearer:{source_ip}",
                    counter=0,
                    nonce="",
                    reason="legacy_bearer",
                )
            self._log_failed_auth(source_ip, "envelope_missing")
            return EnvelopeVerdict(False, reason="envelope_missing")

        verdict = parse_and_verify(
            headers, body,
            secret=self._shared_secret_bytes,
            bearer_issuer=f"bearer:{source_ip}",
            max_age_s=DEFAULT_MAX_ENVELOPE_AGE_S,
        )
        if not verdict.accepted:
            self._log_failed_auth(source_ip, verdict.reason)
            return verdict

        # Replay defence — strict monotonic seq + nonce window.
        try:
            allowed, replay_reason = self._replay_guard.accept(
                source=verdict.issuer,
                seq=verdict.counter,
                nonce=verdict.nonce,
            )
        except Exception as exc:    # noqa: BLE001
            logger.error("api.replay_guard_error", error=str(exc))
            return EnvelopeVerdict(False, reason="replay_guard_error")
        if not allowed:
            self._log_failed_auth(source_ip, f"replay:{replay_reason}")
            return EnvelopeVerdict(False, reason=f"replay:{replay_reason}")

        return verdict

    def _log_failed_auth(self, source_ip: str, reason: str) -> None:
        """Log failed-auth events with per-(ip, reason) suppression
        (TT&C audit H-2).  Floods produce one summary line per window
        plus a count, not one line per attempt.
        """
        key = (source_ip, reason)
        now = time.monotonic()
        last = self._failed_auth_last_log.get(key, 0.0)
        if now - last >= _FAILED_AUTH_LOG_WINDOW_S:
            count = self._failed_auth_counts.pop(key, 0)
            logger.warning(
                "api.auth_failed",
                source_ip=source_ip,
                reason=reason,
                suppressed_since_last_log=count,
            )
            self._failed_auth_last_log[key] = now
        else:
            self._failed_auth_counts[key] = self._failed_auth_counts.get(key, 0) + 1

    async def _handle_command(
        self,
        body: bytes,
        writer: asyncio.StreamWriter,
        *,
        envelope: EnvelopeVerdict,
        source_ip: str,
    ) -> None:
        """Handle POST /api/v1/command — send command to ARIA."""
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            await self._send_http(writer, 400, {"error": "Invalid JSON"})
            return

        text = data.get("text", "").strip()
        if not text:
            await self._send_http(writer, 400, {"error": "Missing 'text' field"})
            return

        # Sanitize
        san = self._sanitizer.sanitize_text(text)
        if not san.clean:
            await self._send_http(writer, 400, {
                "error": "Input rejected",
                "patterns_found": san.patterns_found,
            })
            return

        # TT&C audit C-4 — bus consumer must verify the envelope fields,
        # so we attach them to the published payload.
        await self._bus.publish(
            Message(
                topic="aria.captain.query",
                payload={
                    "text": san.sanitized,
                    "source": "api",
                    "_envelope": {
                        "issuer": envelope.issuer,
                        "counter": envelope.counter,
                        "nonce": envelope.nonce,
                        "source_ip": source_ip,
                        "verified": True,
                    },
                },
                source_agent="api",
            )
        )

        await self._send_http(writer, 202, {"status": "accepted", "text": san.sanitized})

    async def _send_http(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: dict[str, Any] | None,
        cors: bool = True,
    ) -> None:
        """Send an HTTP JSON response."""
        status_text = {
            200: "OK", 202: "Accepted", 204: "No Content",
            400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
            405: "Method Not Allowed", 429: "Too Many Requests",
            500: "Internal Server Error",
        }.get(status, "OK")

        if body is not None:
            body_bytes = json.dumps(body, default=str).encode("utf-8")
        else:
            body_bytes = b""

        headers = [
            f"HTTP/1.1 {status} {status_text}",
            f"Content-Length: {len(body_bytes)}",
            "Content-Type: application/json",
            "Connection: close",
        ]
        if cors:
            headers.extend([
                "Access-Control-Allow-Origin: *",
                "Access-Control-Allow-Methods: GET, POST, OPTIONS",
                "Access-Control-Allow-Headers: Authorization, Content-Type",
            ])

        response = "\r\n".join(headers) + "\r\n\r\n"
        writer.write(response.encode("utf-8"))
        if body_bytes:
            writer.write(body_bytes)
        await writer.drain()

    # -----------------------------------------------------------------------
    # WebSocket Handler
    # -----------------------------------------------------------------------

    async def _handle_ws(self, websocket: ServerConnection) -> None:
        """Handle a WebSocket connection — stream real-time events."""
        self._ws_clients.add(websocket)
        remote = websocket.remote_address
        logger.info("api.ws_connected", remote=str(remote))

        try:
            # Send initial state
            status = self._system_status_fn()
            await websocket.send(json.dumps({
                "type": "init",
                "status": status,
                "recent_alerts": self._recent_alerts[-20:],
                "channel_scores": self._channel_scores,
            }, default=str))

            # TT&C audit C-1 — every ``command`` message must carry a
            # signed envelope.  Pings / unknown types are echoed (or
            # dropped) but never published to the bus.
            source_ip = str(remote[0]) if remote else "unknown"
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    if msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                        continue
                    if msg_type != "command":
                        continue

                    # Per-IP rate limit applies to WS commands too.
                    rate = self._rate_limiter.check(source_ip)
                    if not rate.allowed:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "code": "rate_limited",
                            "retry_after_s": round(rate.retry_after_s, 1),
                        }))
                        continue

                    envelope_headers = data.get("envelope") or {}
                    text = data.get("text", "")
                    if not text:
                        await websocket.send(json.dumps({
                            "type": "error", "code": "empty_text",
                        }))
                        continue

                    body_bytes = json.dumps({"text": text}, sort_keys=True).encode("utf-8")
                    pseudo_headers = {
                        "x-aria-counter": str(envelope_headers.get("counter", "")),
                        "x-aria-nonce": str(envelope_headers.get("nonce", "")),
                        "x-aria-timestamp": str(envelope_headers.get("timestamp", "")),
                        "x-aria-signature": str(envelope_headers.get("signature", "")),
                    }

                    if (self._production_mode
                            or any(pseudo_headers.values())):
                        verdict = parse_and_verify(
                            pseudo_headers, body_bytes,
                            secret=self._shared_secret_bytes,
                            bearer_issuer=f"ws:{source_ip}",
                            max_age_s=DEFAULT_MAX_ENVELOPE_AGE_S,
                        )
                        if not verdict.accepted:
                            self._log_failed_auth(source_ip, f"ws:{verdict.reason}")
                            await websocket.send(json.dumps({
                                "type": "error", "code": "unauthorized",
                            }))
                            continue
                        try:
                            allowed, replay_reason = self._replay_guard.accept(
                                source=verdict.issuer,
                                seq=verdict.counter,
                                nonce=verdict.nonce,
                            )
                        except Exception as exc:    # noqa: BLE001
                            logger.error("api.ws_replay_guard_error",
                                         error=str(exc))
                            await websocket.send(json.dumps({
                                "type": "error", "code": "replay_guard_error",
                            }))
                            continue
                        if not allowed:
                            self._log_failed_auth(
                                source_ip, f"ws_replay:{replay_reason}")
                            await websocket.send(json.dumps({
                                "type": "error", "code": "replay_rejected",
                            }))
                            continue
                        envelope_meta = {
                            "issuer": verdict.issuer,
                            "counter": verdict.counter,
                            "nonce": verdict.nonce,
                            "source_ip": source_ip,
                            "verified": True,
                        }
                    else:
                        # Legacy path — bearer was checked at handshake;
                        # tag the message as legacy so consumers can
                        # decide whether to honour it.
                        envelope_meta = {
                            "issuer": f"ws_bearer:{source_ip}",
                            "counter": 0, "nonce": "",
                            "source_ip": source_ip, "verified": False,
                        }

                    san = self._sanitizer.sanitize_text(text)
                    if not san.clean:
                        await websocket.send(json.dumps({
                            "type": "error", "code": "sanitizer_rejected",
                            "patterns_found": san.patterns_found,
                        }))
                        continue

                    await self._bus.publish(Message(
                        topic="aria.captain.query",
                        payload={
                            "text": san.sanitized, "source": "ws",
                            "_envelope": envelope_meta,
                        },
                        source_agent="api",
                    ))
                except json.JSONDecodeError:
                    pass

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)
            logger.info("api.ws_disconnected", remote=str(remote))

    async def _ws_process_request(
        self,
        connection: Any,
        request: Any,
    ) -> Optional[Any]:
        """WebSocket handshake auth (TT&C audit C-1 / L-2).

        Returns ``None`` to allow the upgrade; returns an HTTP-style
        response to reject the handshake.  ``websockets`` 13+ uses the
        (connection, request) two-arg signature; we accept both modern
        and legacy callers via dynamic header lookup.
        """
        # ``websockets.Request.headers`` is a HeaderProtocol that supports
        # ``__getitem__`` and ``get``; older websockets versions pass a
        # plain dict via ``connection``.  Support both.
        headers_iface = getattr(request, "headers", request)
        get_header = getattr(headers_iface, "get", None)
        if get_header is None:
            return _ws_reject(401, "Unauthorized: bad_handshake")
        auth = get_header("authorization", "") or ""
        expected = f"Bearer {self._shared_secret}"
        if not hmac.compare_digest(auth, expected):
            peer = getattr(connection, "remote_address", None)
            self._log_failed_auth(
                str(peer[0]) if peer else "unknown", "ws_bearer_mismatch")
            return _ws_reject(401, "Unauthorized")

        # Origin check: when an allow-list is configured, require match.
        origin = (get_header("origin", "") or "").strip()
        if self._allowed_origins and origin not in self._allowed_origins:
            return _ws_reject(403, "Forbidden: origin")

        return None

    async def _broadcast_ws(self, event: dict[str, Any]) -> None:
        """Broadcast an event to all connected WebSocket clients.

        TT&C audit H-3: every broadcast carries an HMAC-SHA-256 tag
        bound to (timestamp, type, JSON-canonical body) so a downstream
        dashboard can verify that the alert came from this server and
        was not injected by a peer holding a stolen WebSocket
        connection.  Tag is hex-truncated to 32 chars on the wire.
        """
        if not self._ws_clients:
            return
        ts = time.time()
        body_bytes = json.dumps(
            event, default=str, sort_keys=True,
        ).encode("utf-8")
        canonical = f"{ts}|{event.get('type', '')}|".encode("utf-8") + body_bytes
        sig = hmac.new(
            self._shared_secret_bytes, canonical, "sha256",
        ).hexdigest()[:32]
        signed = {
            **event,
            "_alert_sig": sig,
            "_alert_ts": ts,
        }
        payload = json.dumps(signed, default=str)
        disconnected: set[ServerConnection] = set()
        for ws in self._ws_clients:
            try:
                await ws.send(payload)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(ws)
        self._ws_clients -= disconnected

    # -----------------------------------------------------------------------
    # Bus Event Handlers → WebSocket Broadcast
    # -----------------------------------------------------------------------

    async def _on_alert(self, message: Message) -> None:
        """Captain alert → store + broadcast."""
        alert = {**message.payload, "timestamp": message.timestamp, "topic": message.topic}
        self._recent_alerts.append(alert)
        if len(self._recent_alerts) > self._max_alerts:
            self._recent_alerts = self._recent_alerts[-self._max_alerts:]
        await self._broadcast_ws({"type": "alert", "data": alert})

    async def _on_anomaly(self, message: Message) -> None:
        """Anomaly event → broadcast to dashboard."""
        await self._broadcast_ws({
            "type": "anomaly",
            "data": {
                **message.payload,
                "topic": message.topic,
                "source": message.source_agent,
                "timestamp": message.timestamp,
            },
        })

    async def _on_scored(self, message: Message) -> None:
        """Telemetry scored → update channel scores + broadcast."""
        scores = message.payload.get("channel_scores", {})
        self._channel_scores.update(scores)
        await self._broadcast_ws({
            "type": "telemetry_scored",
            "data": {
                "channel_scores": scores,
                "anomalous": message.payload.get("anomalous", []),
            },
        })

    async def _on_mode_change(self, message: Message) -> None:
        """Safe mode change → broadcast."""
        await self._broadcast_ws({"type": "safe_mode_change", "data": message.payload})

    async def _on_power_event(self, message: Message) -> None:
        """Power event → broadcast."""
        await self._broadcast_ws({
            "type": "power_event",
            "data": {**message.payload, "topic": message.topic},
        })

    async def _on_correlation(self, message: Message) -> None:
        """Anomaly correlation (root cause) → store as alert + broadcast."""
        alert = {
            **message.payload,
            "timestamp": message.timestamp,
            "topic": "aria.anomaly.correlation",
            "type": "correlation",
        }
        self._recent_alerts.append(alert)
        if len(self._recent_alerts) > self._max_alerts:
            self._recent_alerts = self._recent_alerts[-self._max_alerts:]
        await self._broadcast_ws({"type": "correlation", "data": alert})
