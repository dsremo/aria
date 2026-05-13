"""EventLogger — structured audit trail for all ARIA system events.

Per CENTRAL_AI_MASTER_PLAN Part 9 and Part 16:
  Every AI decision, anomaly, FDIR response, and state change must be logged
  with enough detail for post-mission review and regulatory compliance.

Event categories:
  ANOMALY   — anomaly detection events from agents or Dsremo
  DECISION  — decision engine verdicts (approved/rejected/timeout)
  FDIR      — fault detection and recovery actions
  ALERT     — captain alerts and crew notifications
  STATE     — system state changes (safe mode, phase transitions)
  AGENT     — agent lifecycle events (start, stop, restart, error)
  TOOL      — tool invocations (name, params, result, latency)
  SECURITY  — authentication, injection attempts, access denials
  REASONING — cognitive engine reasoning traces

Storage:
  In-memory ring buffer with optional disk persistence.
  Each event has: timestamp, category, severity, source, payload, trace_id.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus

logger = structlog.get_logger()


@dataclass
class AuditEvent:
    """A single audit event in the log."""
    timestamp: str
    category: str
    severity: str
    source: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""


class EventLogger:
    """System-wide audit event logger.

    Subscribes to key bus topics and records a structured audit trail.
    Provides query interface for post-mission review.
    """

    def __init__(self, bus: MessageBus, max_events: int = 10_000) -> None:
        self._bus = bus
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._counts: dict[str, int] = {}

    async def start(self) -> None:
        """Subscribe to all auditable topics."""
        self._bus.subscribe("aria.anomaly.*", self._on_anomaly)
        self._bus.subscribe("aria.captain.alert", self._on_alert)
        self._bus.subscribe("aria.fdir.*", self._on_fdir)
        self._bus.subscribe("aria.safety.mode_change", self._on_state_change)
        self._bus.subscribe("aria.anomaly.correlation", self._on_correlation)
        self._bus.subscribe("aria.propulsion.maneuver.*", self._on_maneuver)
        self._bus.subscribe("aria.emergency.*", self._on_emergency)
        # Wiring audit Pass 1 (F7.2) — `ResourceBudgetGate.commit()`
        # publishes `aria.budget.soft_breach` + `.hard_breach` events
        # that previously had no subscriber. Logging them here surfaces
        # them in `/api/events/recent` for the operator console.
        self._bus.subscribe("aria.budget.*", self._on_anomaly)
        logger.info("event_logger.started")

    async def stop(self) -> None:
        pass

    def log(
        self,
        category: str,
        severity: str,
        source: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        trace_id: str = "",
    ) -> None:
        """Manually log an event (for use by components not on the bus)."""
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            severity=severity,
            source=source,
            summary=summary,
            payload=payload or {},
            trace_id=trace_id,
        )
        self._events.append(event)
        self._counts[category] = self._counts.get(category, 0) + 1

    # -----------------------------------------------------------------------
    # Bus event handlers
    # -----------------------------------------------------------------------

    async def _on_anomaly(self, message: Message) -> None:
        self.log(
            category="ANOMALY",
            severity=message.payload.get("severity", "WATCH"),
            source=message.source_agent or "unknown",
            summary=message.payload.get("message", f"Anomaly on {message.topic}"),
            payload=message.payload,
        )

    async def _on_alert(self, message: Message) -> None:
        self.log(
            category="ALERT",
            severity=message.payload.get("severity", "WARNING"),
            source=message.payload.get("source", "coordinator"),
            summary=message.payload.get("message", message.payload.get("description", "Captain alert")),
            payload=message.payload,
        )

    async def _on_fdir(self, message: Message) -> None:
        category = "FDIR"
        if "resolved" in message.topic:
            summary = f"Fault resolved: {message.payload.get('fault_type', '?')}"
        else:
            summary = f"FDIR response: {message.payload.get('fault_type', '?')} — {message.payload.get('actions', [])}"
        self.log(
            category=category,
            severity=message.payload.get("severity", "WARNING"),
            source="fdir_manager",
            summary=summary,
            payload=message.payload,
        )

    async def _on_state_change(self, message: Message) -> None:
        self.log(
            category="STATE",
            severity="WARNING",
            source="safe_mode_manager",
            summary=f"Safe mode: {message.payload.get('from_level', '?')} → {message.payload.get('to_level', '?')}",
            payload=message.payload,
        )

    async def _on_correlation(self, message: Message) -> None:
        self.log(
            category="ANOMALY",
            severity=message.payload.get("severity", "WARNING"),
            source="anomaly_correlator",
            summary=f"Root cause: {message.payload.get('root_cause', '?')} (confidence={message.payload.get('confidence', 0):.0%})",
            payload=message.payload,
        )

    async def _on_maneuver(self, message: Message) -> None:
        action = "started" if "started" in message.topic else "completed" if "completed" in message.topic else "event"
        self.log(
            category="DECISION",
            severity="WARNING",
            source="propulsion",
            summary=f"Maneuver {action}: {message.payload.get('maneuver_id', '?')}",
            payload=message.payload,
        )

    async def _on_emergency(self, message: Message) -> None:
        self.log(
            category="ALERT",
            severity="EMERGENCY",
            source=message.source_agent or "unknown",
            summary=f"Emergency: {message.topic}",
            payload=message.payload,
        )

    # -----------------------------------------------------------------------
    # Query interface
    # -----------------------------------------------------------------------

    def query(
        self,
        category: str | None = None,
        severity: str | None = None,
        source: str | None = None,
        limit: int = 50,
    ) -> list[AuditEvent]:
        """Query recent events with optional filters."""
        results = list(self._events)

        if category:
            results = [e for e in results if e.category == category]
        if severity:
            results = [e for e in results if e.severity == severity]
        if source:
            results = [e for e in results if e.source == source]

        return results[-limit:]

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def counts_by_category(self) -> dict[str, int]:
        return dict(self._counts)

    def summary(self) -> dict[str, Any]:
        """Summary statistics for the audit log."""
        severity_counts: dict[str, int] = {}
        for e in self._events:
            severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1

        return {
            "total_events": len(self._events),
            "by_category": dict(self._counts),
            "by_severity": severity_counts,
        }
