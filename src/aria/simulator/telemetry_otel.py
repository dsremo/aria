"""Real OpenTelemetry wiring for ARIA.

Layers instrumented
-------------------
1. aiohttp server — every `/api/*` request becomes a span with HTTP
   method, route, status code, and any unhandled exception attached.
2. tick_engine — `advance(dt_s)` is wrapped in a root span; each
   subsystem's `tick()` inside the substep loop becomes a child span
   with `aria.subsystem = <name>`, `aria.dt_s`, and `aria.sim_yr`.
3. event_bus.publish — every bus publish is recorded as a span event
   on the currently-active span, so traces carry the semantic event
   stream inline with the HTTP/tick spans that produced them.

Exporters
---------
* Console exporter (stdout) if no OTLP endpoint is set — zero infra.
* OTLP-HTTP exporter if `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

Disabled by default. Pass `--otel` on the CLI, or call
`configure_otel(enabled=True)` before starting the HTTP server.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

_LOGGER = logging.getLogger("aria.otel")
_CONFIGURED = False
_LOCK = threading.Lock()
_TRACER: Any = None   # opentelemetry.trace.Tracer at runtime


class _RollingFile:
    """Size-capped append-only file wrapper. When the backing file
    exceeds `max_bytes`, it is rotated to `<path>.1` (overwriting the
    prior backup) and the main file is truncated. Keeps disk usage
    bounded at roughly `max_bytes × 2` without requiring an external
    logrotate cron — important because the Console span exporter on a
    century-tick mission produced ~5 MB/s of span JSON and would fill
    a local dev disk in hours.
    """

    def __init__(self, path: str, max_bytes: int = 50 * 1024 * 1024):
        self._path = path
        self._max = max_bytes
        self._fh = open(path, "a", buffering=1)
        self._bytes = self._fh.tell()
        self._lock = threading.Lock()

    def write(self, s: str) -> int:
        with self._lock:
            n = self._fh.write(s)
            self._bytes += n
            if self._bytes >= self._max:
                self._rotate()
            return n

    def flush(self) -> None:
        with self._lock:
            try: self._fh.flush()
            except Exception: pass

    def close(self) -> None:
        with self._lock:
            try: self._fh.close()
            except Exception: pass

    def _rotate(self) -> None:
        try: self._fh.close()
        except Exception: pass
        backup = f"{self._path}.1"
        try:
            if os.path.exists(backup): os.remove(backup)
            os.rename(self._path, backup)
        except Exception:
            pass
        self._fh = open(self._path, "w", buffering=1)
        self._bytes = 0


def configure_otel(
    *,
    enabled: bool = True,
    service_name: str = "aria-simulator",
    service_version: str = "0.1.0",
    export_file: Optional[str] = None,
    max_bytes: int = 50 * 1024 * 1024,
) -> None:
    """Initialise OTel SDK + tracer provider. Idempotent.

    Args:
        enabled: No-op when False — calls to `span(...)` become a zero-cost
            null context so production can ship with OTel disabled.
        service_name / service_version: resource attributes for every span.
        export_file: Path to a text file the Console exporter appends to.
            Default: logs/aria_otel.jsonl. Set to empty string to use
            stdout instead.
    """
    global _CONFIGURED, _TRACER
    with _LOCK:
        if _CONFIGURED:
            return
        if not enabled:
            _CONFIGURED = True
            return

        # Late imports so the module is importable even without OTel installed.
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        resource = Resource.create({
            "service.name":    service_name,
            "service.version": service_version,
            "aria.component":  "web_dashboard",
        })
        provider = TracerProvider(resource=resource)

        # Console / file exporter with size-capped rolling so long runs
        # on local dev boxes don't fill the disk. Rotates at `max_bytes`
        # (default 50 MB), keeping at most one backup (so total usage is
        # bounded at ~2× max_bytes). For short debugging runs this is a
        # no-op — for century missions it caps growth cleanly.
        path = export_file
        if path is None:
            os.makedirs("logs", exist_ok=True)
            path = "logs/aria_otel.jsonl"
        if path:
            # Truncate on startup — operator gets a fresh log per run,
            # no stale spans from a previous backend session.
            try: open(path, "w").close()
            except Exception: pass
            fh = _RollingFile(path, max_bytes=max_bytes)
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=fh)))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Optional OTLP export (Tempo / Jaeger / Honeycomb / etc.)
        otlp_ep = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if otlp_ep:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
                _LOGGER.info(f"OTel OTLP exporter enabled → {otlp_ep}")
            except Exception as e:
                _LOGGER.warning(f"OTel OTLP not wired: {e}")

        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer("aria.simulator")
        _CONFIGURED = True
        _LOGGER.info(f"OTel enabled — exporting to {path or 'stdout'}")


def is_enabled() -> bool:
    return _TRACER is not None


def get_tracer() -> Any:
    """Return the OTel Tracer if enabled, else None."""
    return _TRACER


# ── Span wrapper helpers ────────────────────────────────────────────

class _NullCtx:
    """Context-manager that does nothing — returned when OTel is disabled
    so callers can always write `with otel.span("...") as span: ...`."""

    def __enter__(self):  return self
    def __exit__(self, *a): return False
    def set_attribute(self, *a, **kw): pass
    def add_event(self, *a, **kw): pass
    def record_exception(self, *a, **kw): pass
    def set_status(self, *a, **kw): pass


_NULL = _NullCtx()


def span(name: str, **attrs: Any):
    """Start a span if OTel is enabled, else return a no-op context.

    Usage:
        with otel.span("tick_engine.advance", aria_dt_s=dt_s) as s:
            ...
            s.add_event("phase_transition", {"to": "cruise"})
    """
    if _TRACER is None:
        return _NULL
    ctx = _TRACER.start_as_current_span(name)
    cm = _SpanProxy(ctx, attrs)
    return cm


class _SpanProxy:
    """Thin wrapper that sets initial attributes on span entry + forwards
    errors to the span (records exception and sets status=ERROR)."""

    def __init__(self, ctx, attrs):
        self._ctx = ctx
        self._attrs = attrs or {}
        self._span = None

    def __enter__(self):
        self._span = self._ctx.__enter__()
        for k, v in self._attrs.items():
            try:
                self._span.set_attribute(k, v)
            except Exception:
                pass
        return self._span

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and self._span is not None:
            from opentelemetry.trace import Status, StatusCode
            try:
                self._span.record_exception(exc)
                self._span.set_status(Status(StatusCode.ERROR, str(exc)[:200]))
            except Exception:
                pass
        return self._ctx.__exit__(exc_type, exc, tb)


# ── Bus bridge ──────────────────────────────────────────────────────

def attach_bus_to_spans() -> None:
    """Subscribe a listener so every bus publish adds an event to the
    currently-active span. Safe to call when OTel is disabled (no-op)."""
    if not is_enabled():
        return
    from aria.simulator.event_bus import get_event_bus

    def _on_event(ev):
        from opentelemetry import trace
        cur = trace.get_current_span()
        if cur is None:
            return
        try:
            cur.add_event(
                f"bus.{ev.topic}",
                attributes={
                    "aria.topic":    ev.topic,
                    "aria.severity": ev.severity,
                    "aria.source":   ev.source,
                    "aria.sim_yr":   float(ev.sim_time_yr),
                },
            )
        except Exception:
            pass

    get_event_bus().subscribe("*", _on_event)
