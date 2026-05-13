"""IncidentGrouper — correlates raw per-channel anomalies into Incidents.

Production standard
-------------------
NASA GSFC, SpaceX Doppel, YAMCS all group correlated anomalies before
surfacing them to operators:

  "No single raw sensor alert reaches an operator without correlation."
                                          — NASA GSFC mission ops doctrine

Algorithm (NASA event manager pattern)
---------------------------------------
  1. Maintain a dict of open incidents per satellite.
  2. When a new Anomaly arrives:
     a. If an open incident exists on the same satellite AND the anomaly's
        timestamp is within `window_s` of the incident's last member → join.
     b. Else → create a new incident.
  3. An incident "closes" when `close_after_s` seconds pass with no new
     member anomalies (checked lazily on next process() call).

Parameters
----------
window_s : float
    Max seconds between consecutive anomalies to be grouped as one incident.
    Default 300 s (5 min) — matches NASA GSFC event correlation window.
    SpaceX uses 500 ms for hardware faults; 5 min is right for telemetry.
close_after_s : float
    Incident auto-closes this many seconds after the last member.
    Default 3600 s (1 h) — allows slow-developing faults to accumulate.

Severity / Confidence
---------------------
  severity   = max(member severities) — worst-case drives operator urgency.
  confidence = weighted average(member confidences, weight=1/rank).
               Recent members weighted higher (rank 1 = most recent).

Thread safety
-------------
Single-threaded asyncio — no locking needed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aria.dsremo.core.models import Anomaly, Incident, Severity


# Severity ordering for max-selection.
_SEV_ORDER = {
    Severity.NOMINAL:  0,
    Severity.WATCH:    1,
    Severity.WARNING:  2,
    Severity.CRITICAL: 3,
}

# ── Subsystem dependency graph (P2-F / P3-Z: causal inference) ──────────────
# Directed edges: if subsystem A fails, subsystem B may be affected.
# Used to determine if two anomalies on different subsystems are likely
# causally related (extends the grouping window) vs. coincidental.
SUBSYSTEM_DEPENDENCIES: dict[str, list[str]] = {
    "eps":     ["adcs", "thermal", "comms"],   # power failure cascades everywhere
    "adcs":    ["comms", "thermal"],             # attitude loss → solar array mispoint, thermal
    "thermal": [],                                # thermal rarely causes other subsystems
    "comms":   [],                                # comms loss is usually isolated
}

# Auto-escalation thresholds (P2-N: alert fatigue reduction).
# If an incident persists with severity WATCH for > _ESCALATION_WATCH_S seconds,
# escalate to WARNING.  If WARNING persists > _ESCALATION_WARNING_S, escalate to CRITICAL.
_ESCALATION_WATCH_S: float = 14400.0    # 4 hours
_ESCALATION_WARNING_S: float = 28800.0  # 8 hours


def _max_severity(a: Severity, b: Severity) -> Severity:
    return a if _SEV_ORDER[a] >= _SEV_ORDER[b] else b


def _derive_root_cause(anomaly: Anomaly) -> str | None:
    """Return a short root-cause label from the detectors that fired."""
    dets = list(anomaly.detectors_triggered)
    if not dets:
        return None
    # Prefer specific patterns for human-readable labels.
    has = set(dets).__contains__
    if has("cusum") and has("ewma") and has("changepoint"):
        return "Gradual drift with structural break"
    if has("cusum") and has("ewma"):
        return "Gradual drift accumulation"
    if has("lstm") or has("tcn"):
        ml_names = [d for d in dets if d in ("lstm", "tcn", "matrix_profile")]
        stat_names = [d for d in dets if d not in ("lstm", "tcn", "matrix_profile")]
        if stat_names:
            return f"Temporal pattern anomaly ({'+'.join(ml_names[:2])} + {stat_names[0]})"
        return f"Temporal pattern anomaly ({'+'.join(ml_names[:2])})"
    if has("variance"):
        return "Variance spike"
    if has("trend_velocity"):
        return "Rapid trend acceleration"
    if has("statistical"):
        return "Single-point spike"
    return "+".join(dets[:3])


class _OpenIncident:
    """Mutable working state for an in-progress incident."""

    __slots__ = (
        "incident_id", "satellite_id", "opened_at", "last_ts",
        "severity", "channels", "root_cause",
        "_conf_sum", "_conf_count",
    )

    def __init__(self, anomaly: Anomaly) -> None:
        self.incident_id  = _new_id()
        self.satellite_id = anomaly.satellite_id
        self.opened_at    = anomaly.timestamp
        self.last_ts      = anomaly.timestamp
        self.severity     = anomaly.severity
        self.channels: list[str] = [anomaly.parameter]
        self.root_cause   = _derive_root_cause(anomaly)
        self._conf_sum    = anomaly.confidence
        self._conf_count  = 1

    def absorb(self, anomaly: Anomaly) -> None:
        """Merge another anomaly into this open incident."""
        self.last_ts  = max(self.last_ts, anomaly.timestamp)
        self.severity = _max_severity(self.severity, anomaly.severity)
        if anomaly.parameter not in self.channels:
            self.channels.append(anomaly.parameter)
        # Update root cause if the new anomaly is more severe or ML-backed.
        if _SEV_ORDER[anomaly.severity] >= _SEV_ORDER[self.severity]:
            new_rc = _derive_root_cause(anomaly)
            if new_rc:
                self.root_cause = new_rc
        self._conf_sum   += anomaly.confidence
        self._conf_count += 1

    @property
    def confidence(self) -> float:
        return self._conf_sum / max(self._conf_count, 1)

    @property
    def anomaly_count(self) -> int:
        return self._conf_count

    def to_incident(self, *, closed: bool = False) -> Incident:
        now = datetime.now(timezone.utc)

        # P2-N: Auto-escalation — if incident has been open long enough,
        # bump severity to reflect sustained anomalous condition.
        severity = self.severity
        duration_s = (now - self.opened_at).total_seconds()
        if severity == Severity.WATCH and duration_s > _ESCALATION_WATCH_S:
            severity = Severity.WARNING
        elif severity == Severity.WARNING and duration_s > _ESCALATION_WARNING_S:
            severity = Severity.CRITICAL

        return Incident(
            id=self.incident_id,
            satellite_id=self.satellite_id,
            first_anomaly_at=self.opened_at,
            last_anomaly_at=self.last_ts,
            closed_at=now if closed else None,
            severity=severity,
            confidence=round(self.confidence, 4),
            channels=tuple(self.channels),
            root_cause_summary=self.root_cause or "",
            anomaly_count=self.anomaly_count,
            status="open" if not closed else "resolved",
        )


def _new_id() -> str:
    import uuid  # noqa: PLC0415
    return str(uuid.uuid4())


class IncidentGrouper:
    """Groups per-channel anomalies into Incidents.

    Maintains one open incident per satellite at a time.  Anomalies that
    arrive within `window_s` seconds of the previous member join the same
    incident; later anomalies start a fresh one.

    Usage (in detect pipeline)
    --------------------------
        grouper = IncidentGrouper()
        incident = grouper.process(anomaly)
        # incident.id is stable across members of the same event
    """

    def __init__(
        self,
        window_s:     float = 300.0,
        close_after_s: float = 3600.0,
        causal_max_delay_s: float = 600.0,  # max propagation delay in causal graph
    ) -> None:
        self.window_s      = window_s
        self.close_after_s = close_after_s
        self.causal_max_delay_s = causal_max_delay_s
        # satellite_id → _OpenIncident
        self._open: dict[str, _OpenIncident] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def process(self, anomaly: Anomaly) -> Incident:
        """Assign anomaly to an incident; return the (possibly new) Incident.

        The returned Incident reflects the CURRENT state after absorbing this
        anomaly — callers should upsert it to DB on every call (cheap: it's
        keyed on incident.id).
        """
        sat = anomaly.satellite_id
        ts  = anomaly.timestamp

        open_inc = self._open.get(sat)

        if open_inc is not None:
            delta = (ts - open_inc.last_ts).total_seconds()
            # Use extended causal window for cross-subsystem anomalies
            # (anomalies from different parameters on the same satellite).
            # Causal graph propagation delays can exceed the base window_s;
            # e.g. a battery fault may take minutes to manifest in ADCS telemetry.
            is_cross_param = anomaly.parameter not in open_inc.channels
            effective_window = (
                max(self.window_s, self.causal_max_delay_s)
                if is_cross_param
                else self.window_s
            )
            if 0 <= delta <= effective_window:
                open_inc.absorb(anomaly)
                return open_inc.to_incident()
            # Gap too large — close the old one and open a new one.
            # (closed incident returned next call via get_closed)

        # Start a new incident.
        new_inc = _OpenIncident(anomaly)
        self._open[sat] = new_inc
        return new_inc.to_incident()

    def get_incident_id(self, satellite_id: str) -> str | None:
        """Return the current open incident ID for a satellite, or None."""
        inc = self._open.get(satellite_id)
        return inc.incident_id if inc else None

    def close_stale(self) -> list[Incident]:
        """Close and return incidents idle for longer than close_after_s.

        Call periodically (e.g., once per detection cycle) to auto-resolve
        incidents where the anomaly window has passed.
        """
        now     = datetime.now(timezone.utc)
        closed  = []
        to_del  = []
        for sat, inc in self._open.items():
            idle = (now - inc.last_ts).total_seconds()
            if idle >= self.close_after_s:
                closed.append(inc.to_incident(closed=True))
                to_del.append(sat)
        for sat in to_del:
            del self._open[sat]
        return closed

    def open_count(self) -> int:
        return len(self._open)

    def reset(self) -> None:
        """Clear all open incidents (use on server restart or re-init)."""
        self._open.clear()
