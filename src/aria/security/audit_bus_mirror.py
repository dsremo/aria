"""audit_bus_mirror — subscribe to the live event bus and mirror
high-severity / always-audited topics into the hash-chained audit log.

R34 (2026-04-25). Closes the gap where the AuditLog (Schneier-Kelsey
1999) was implemented but only the aiohttp middleware was writing to
it. Approval-queue transitions, kill-switch trips, sandbagging-detector
alerts, sealed-prompt loads, and the safety-replay drift alarm all go
through the bus already; this module is the single place that copies
those events into the durable chain.

Coverage policy (declared once here so it's auditable + tweakable):

  ALWAYS_AUDIT — log every match regardless of severity:
    "aria.security.*"
    "aria.safety.*"
    "aria.emergency.*"
    "aria.approval.*"
    "aria.kill_switch.*"
    "aria.monitor.*"
    "aria.boot.*"
    "aria.constitution.*"
    "aria.action.executed"
    "aria.action.denied"
    "*.tamper*"
    "*.violation*"
    "*.alarm*"
    "*.suspect*"
    "*.drift*"

  MIN_SEVERITY — log everything else above the configured threshold.
  Default 'warning'; tune with ARIA_AUDIT_MIN_SEVERITY=info|warning|critical.

The mirror runs in-process (the simulator EventBus is sync + thread-safe),
so its delivery latency is microseconds. It does not write back to the
bus — anchor publishing lives in AuditLog itself.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, Iterable, Optional

import structlog

logger = structlog.get_logger()


# ── Topic policy ────────────────────────────────────────────────


# Patterns that match these prefixes are logged at ALL severities,
# including info. These are the safety/security/audit-relevant topics.
DEFAULT_ALWAYS_AUDIT_PREFIXES: tuple[str, ...] = (
    "aria.security.",
    "aria.safety.",
    "aria.emergency.",
    "aria.approval.",
    "aria.kill_switch.",
    "aria.monitor.",
    "aria.boot.",
    "aria.constitution.",
    "aria.action.executed",
    "aria.action.denied",
    "aria.action.gated",
)

# Substrings — match anywhere in the topic. For threat events that
# can come from many subsystems (e.g. "aria.eclss.tamper" or
# "aria.power.violation").
DEFAULT_ALWAYS_AUDIT_SUBSTRINGS: tuple[str, ...] = (
    "tamper",
    "violation",
    "alarm",
    "suspect",
    "drift",
    "intrusion",
    "anomaly_detected",
)


_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}


def _topic_matches_always(
    topic: str,
    *,
    prefixes: Iterable[str],
    substrings: Iterable[str],
) -> bool:
    if any(topic.startswith(p) for p in prefixes):
        return True
    if any(s in topic for s in substrings):
        return True
    return False


# ── Mirror lifecycle ────────────────────────────────────────────


class AuditBusMirror:
    """Bus-event → AuditLog bridge. Idempotent start/stop."""

    def __init__(
        self,
        *,
        min_severity: Optional[str] = None,
        always_audit_prefixes: Iterable[str] = DEFAULT_ALWAYS_AUDIT_PREFIXES,
        always_audit_substrings: Iterable[str] = DEFAULT_ALWAYS_AUDIT_SUBSTRINGS,
    ) -> None:
        env = os.environ.get("ARIA_AUDIT_MIN_SEVERITY")
        configured = min_severity or env or "warning"
        if configured not in _SEVERITY_RANK:
            logger.warning("audit_mirror.invalid_severity",
                           value=configured, fallback="warning")
            configured = "warning"
        self._min_rank = _SEVERITY_RANK[configured]
        self._always_prefixes = tuple(always_audit_prefixes)
        self._always_substrings = tuple(always_audit_substrings)
        self._subscribed: bool = False
        self._lock = threading.Lock()
        self._stats = {"received": 0, "logged": 0, "skipped": 0,
                       "errors": 0}
        # Wiring audit Pass 3 (F6.9) — when audit-chain writes start
        # failing, fire ``aria.security.audit_mirror_failed`` so the
        # operator console + safe-mode FDIR can react. Without this,
        # the durability promise of the mirror could break invisibly.
        self._error_alert_threshold = 5
        self._last_alert_at_errors = 0
        self._alert_publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def set_alert_publish_fn(
        self,
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]],
    ) -> None:
        """Wire the alert publish callable from main.py — same pattern
        as IncidentRegistry.set_publish_fn (Pass 1 F6.2 / F10.4)."""
        with self._lock:
            self._alert_publish_fn = publish_fn

    def _on_event(self, event) -> None:
        from aria.security.audit import get_audit_log
        self._stats["received"] += 1
        topic = getattr(event, "topic", "") or ""
        sev = getattr(event, "severity", "info") or "info"
        sev_rank = _SEVERITY_RANK.get(sev, 0)
        always = _topic_matches_always(
            topic,
            prefixes=self._always_prefixes,
            substrings=self._always_substrings,
        )
        if not always and sev_rank < self._min_rank:
            self._stats["skipped"] += 1
            return
        try:
            get_audit_log().log_bus_event(event)
            self._stats["logged"] += 1
        except Exception as exc:
            self._stats["errors"] += 1
            logger.error("audit_mirror.log_failed",
                         error=str(exc), topic=topic)
            # Wiring audit Pass 3 (F6.9) — surface a structured alert
            # the moment errors cross the threshold AND every Nth
            # error after, so a sustained audit-chain break is visible
            # to operators / FDIR rather than only in the error log.
            errors = self._stats["errors"]
            if (
                self._alert_publish_fn is not None
                and errors >= self._error_alert_threshold
                and errors - self._last_alert_at_errors >= self._error_alert_threshold
            ):
                self._last_alert_at_errors = errors
                try:
                    self._alert_publish_fn(
                        "aria.security.audit_mirror_failed",
                        {
                            "errors": errors,
                            "received": self._stats["received"],
                            "logged": self._stats["logged"],
                            "last_topic": topic,
                            "last_error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                except Exception as alert_exc:    # noqa: BLE001
                    logger.error(
                        "audit_mirror.alert_publish_failed",
                        error=str(alert_exc),
                    )

    def start(self, bus=None) -> None:
        """Subscribe to the bus. Idempotent. Pass an explicit bus for
        tests; production calls it with no args and it pulls the
        process singleton."""
        with self._lock:
            if self._subscribed:
                return
            if bus is None:
                from aria.simulator.event_bus import get_event_bus
                bus = get_event_bus()
            # `*` catches every event; the per-event handler decides
            # whether to log. The simulator EventBus dispatches matches
            # under a lock-free path so this is essentially free.
            bus.subscribe("*", self._on_event)
            self._subscribed = True
        logger.info("audit_mirror.started",
                    min_rank=self._min_rank,
                    always_prefixes=len(self._always_prefixes),
                    always_substrings=len(self._always_substrings))

    def stats(self) -> dict[str, int]:
        return dict(self._stats)


# ── Module-level singleton ──────────────────────────────────────


_INSTANCE: Optional[AuditBusMirror] = None
_INSTANCE_LOCK = threading.Lock()


def get_audit_bus_mirror() -> AuditBusMirror:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = AuditBusMirror()
    return _INSTANCE


def start_audit_bus_mirror(bus=None) -> AuditBusMirror:
    """Convenience: get-or-create + subscribe. Safe to call multiple
    times; second + subsequent calls are no-ops."""
    mirror = get_audit_bus_mirror()
    mirror.start(bus=bus)
    return mirror


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
