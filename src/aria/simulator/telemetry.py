"""Structured logging + bus-to-log bridge for ARIA.

Motivation
----------
Every live mission run surfaced bugs that unit tests missed because the
bus-history ring buffer (512 events, in-memory) was the only record.
Operators had to scrape the bus via /api/events/recent after the fact;
nothing was persisted; nothing carried structured metadata for
downstream analysis.

This module gives us three things without introducing OpenTelemetry's
packaging + config burden:

1. A JSON-formatted root logger so every module that already uses the
   stdlib `logging` module emits structured lines instead of free text.
2. A bus → logger bridge: every event published on the EventBus is
   mirrored to the logger with the same severity, sim time, topic,
   source, and payload. Operators who tail the log file see the same
   stream they'd see via `/api/events/recent`.
3. An optional rotating file sink at `logs/aria_events.log` so mission
   traces survive process restarts.

If OpenTelemetry is installed later, the same JSON records flow through
a log-exporter without code changes — the existing event bus becomes
the OTEL "log signal" source of truth.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import threading
from typing import Any, Dict, Optional

from aria.simulator.event_bus import Event, get_event_bus


# ── Severity mapping ────────────────────────────────────────────────

_BUS_TO_LOG = {
    "debug":    logging.DEBUG,
    "info":     logging.INFO,
    "warning":  logging.WARNING,
    "critical": logging.CRITICAL,
}


# ── JSON formatter ──────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Shape:
        {"ts": "...", "lvl": "info", "topic": "...", "sim_yr": 1.23,
         "source": "...", "msg": "...", "payload": {...}}

    Unknown fields on the LogRecord (anything under `record.__dict__`
    that isn't standard) are preserved under their own keys so callers
    who call `logger.info("foo", extra={"bus_payload": {...}})` don't
    lose structure.
    """

    _STD_ATTRS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        # stdlib Formatter.formatTime uses time.strftime which does NOT
        # consume %f — it passes the literal string through. Old log
        # lines carried "17:15:09.%f" in the ts field. Build the
        # timestamp directly from datetime so microseconds resolve.
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        base: Dict[str, Any] = {
            "ts":   ts.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
            "lvl":  record.levelname.lower(),
            "mod":  record.name,
            "msg":  record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in self._STD_ATTRS or k.startswith("_"):
                continue
            if isinstance(v, (str, int, float, bool, list, dict, tuple, type(None))):
                base[k] = v
        return json.dumps(base, default=str, sort_keys=False)


# ── Configuration ──────────────────────────────────────────────────

_CONFIGURED = False
_CONFIG_LOCK = threading.Lock()
_BUS_LOGGER_NAME = "aria.bus"
_bus_listener: Optional[Any] = None


def configure_logging(
    *,
    level: str = "INFO",
    log_dir: Optional[str] = None,
    log_filename: str = "aria_events.log",
    max_bytes: int = 10 * 1024 * 1024,   # 10 MB before rotate
    backup_count: int = 5,
    bridge_event_bus: bool = True,
) -> None:
    """Initialise JSON logging + optional file rotation + bus bridge.

    Idempotent: calling twice in the same process re-uses the existing
    handlers (avoids duplicate log lines when both a test and the web
    server initialise the same singleton).

    Args:
        level: Minimum log level — "DEBUG"/"INFO"/"WARNING"/"CRITICAL".
        log_dir: If set, also write JSON-formatted logs to a rotating
            file under that directory. If None, console-only.
        log_filename: Name of the file inside log_dir.
        max_bytes: Rotate file once it exceeds this size.
        backup_count: How many rotated files to keep.
        bridge_event_bus: If True, subscribe a listener to the EventBus
            that mirrors every event to the "aria.bus" logger so bus
            history and log history share the same stream.
    """
    global _CONFIGURED, _bus_listener
    with _CONFIG_LOCK:
        if _CONFIGURED:
            return

        root = logging.getLogger("aria")
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        # Clear any pre-existing handlers so reconfiguration stays clean.
        for h in list(root.handlers):
            root.removeHandler(h)

        fmt = _JsonFormatter()
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, log_filename)
            rot = logging.handlers.RotatingFileHandler(
                path, maxBytes=max_bytes, backupCount=backup_count,
            )
            rot.setFormatter(fmt)
            root.addHandler(rot)

        # Don't propagate to the default Python root (would double-log).
        root.propagate = False

        if bridge_event_bus:
            _bus_listener = _install_bus_bridge()

        _CONFIGURED = True


def _install_bus_bridge() -> Any:
    """Subscribe a listener to the EventBus that mirrors to the logger."""
    bus = get_event_bus()
    logger = logging.getLogger(_BUS_LOGGER_NAME)

    def _on_event(ev: Event) -> None:
        lvl = _BUS_TO_LOG.get(ev.severity.lower(), logging.INFO)
        # Use `extra` so JsonFormatter carries structure.
        logger.log(
            lvl,
            ev.topic,
            extra={
                "topic":   ev.topic,
                "sim_yr":  ev.sim_time_yr,
                "source":  ev.source,
                "payload": dict(ev.payload),
            },
        )

    bus.subscribe("*", _on_event)
    return _on_event


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger under the `aria` root."""
    return logging.getLogger(name if name.startswith("aria") else f"aria.{name}")


def is_configured() -> bool:
    return _CONFIGURED
