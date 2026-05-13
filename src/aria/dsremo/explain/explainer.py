"""Explainability engine — turns anomaly scores into operator understanding.

This is Dsremo's competitive moat. Any tool can flag "anomaly detected."
Only Dsremo says:
  - "Battery voltage dropped because solar panel current decreased 12% during this orbit"
  - "Thermal anomaly likely caused by EPS instability — battery_temp and battery_voltage
    correlated anomalies detected within 30 seconds"
  - "If battery_voltage had been 0.3V higher, this would be classified as nominal"

Three explanation layers:
  1. Feature attribution — which parameters drove the score
  2. Cross-parameter reasoning — causal chain identification
  3. Root-cause grouping — clusters related anomalies into incidents
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import structlog

from aria.dsremo.core.models import Anomaly, Severity

logger = structlog.get_logger()

# Known causal relationships between satellite parameters.
# Direction: source → affected. These encode basic spacecraft physics.
CAUSAL_GRAPH: dict[str, list[str]] = {
    "solar_array_current": ["battery_voltage", "battery_current", "bus_voltage"],
    "battery_voltage": ["bus_voltage", "battery_temp"],
    "bus_voltage": ["wheel_speed_x", "wheel_speed_y", "wheel_speed_z", "electronics_temp"],
    "battery_temp": ["battery_voltage"],  # thermal runaway feedback loop
    "wheel_speed_x": ["pointing_error"],
    "wheel_speed_y": ["pointing_error"],
    "wheel_speed_z": ["pointing_error"],
}

# Subsystem grouping for incident correlation
SUBSYSTEM_PARAMS: dict[str, list[str]] = {
    "eps": ["battery_voltage", "battery_current", "solar_array_current", "bus_voltage"],
    "adcs": ["wheel_speed_x", "wheel_speed_y", "wheel_speed_z", "pointing_error"],
    "thermal": ["panel_temp_sun", "panel_temp_shade", "battery_temp", "electronics_temp"],
    "comms": ["signal_strength", "bit_error_rate", "link_margin"],
}


@dataclass
class Explanation:
    """Rich explanation for a detected anomaly."""

    anomaly_id: str
    summary: str                          # one-line for dashboard
    detail: str                           # full explanation
    contributing_params: dict[str, float]  # parameter → contribution
    causal_chain: list[str]               # e.g., ["solar_array_current ↓", "→ battery_voltage ↓"]
    root_cause_group: str | None          # incident group ID
    counterfactual: str                   # "If X had been Y, this would be nominal"
    confidence_breakdown: dict[str, float]  # per-detector confidence


@dataclass
class IncidentGroup:
    """Clusters related anomalies into a single operational incident."""

    group_id: str
    anomalies: list[str] = field(default_factory=list)
    subsystems: set[str] = field(default_factory=set)
    root_parameter: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0


class AnomalyExplainer:
    """Generates rich explanations for detected anomalies."""

    def __init__(self, grouping_window_sec: float = 120.0):
        self.grouping_window = grouping_window_sec
        self._active_groups: dict[str, IncidentGroup] = {}
        self._recent_anomalies: list[tuple[float, Anomaly]] = []

    def explain(self, anomaly: Anomaly, recent_anomalies: list[Anomaly] | None = None) -> Explanation:
        """Generate a full explanation for an anomaly."""
        now = time.monotonic()

        # Track for grouping
        self._recent_anomalies.append((now, anomaly))
        self._prune_old(now)

        # 1. Feature attribution
        contributions = anomaly.contributing_params

        # 2. Causal chain
        chain = self._trace_causal_chain(anomaly.parameter, recent_anomalies or [])

        # 3. Root-cause grouping
        group = self._assign_to_group(anomaly, now)

        # 4. Counterfactual
        counterfactual = self._generate_counterfactual(anomaly)

        # 5. Build human-readable explanation
        summary = self._build_summary(anomaly, chain, group)
        detail = self._build_detail(anomaly, chain, contributions, counterfactual)

        return Explanation(
            anomaly_id=anomaly.id,
            summary=summary,
            detail=detail,
            contributing_params=contributions,
            causal_chain=chain,
            root_cause_group=group.group_id if group else None,
            counterfactual=counterfactual,
            confidence_breakdown={d: 0.0 for d in anomaly.detectors_triggered},
        )

    def _trace_causal_chain(self, parameter: str, recent: list[Anomaly]) -> list[str]:
        """Walk the causal graph to find upstream causes.

        If battery_voltage is anomalous and solar_array_current was also
        anomalous recently, the chain is: solar_array_current → battery_voltage.
        """
        chain: list[str] = []
        recent_params = {a.parameter for a in recent}

        # Look for upstream causes
        for source, affected in CAUSAL_GRAPH.items():
            if parameter in affected and source in recent_params:
                chain.append(f"{source} → {parameter}")

        # Look for downstream effects
        downstream = CAUSAL_GRAPH.get(parameter, [])
        for d in downstream:
            if d in recent_params:
                chain.append(f"{parameter} → {d}")

        return chain if chain else [f"{parameter} (no correlated parameters)"]

    def _assign_to_group(self, anomaly: Anomaly, now: float) -> IncidentGroup | None:
        """Assign this anomaly to an incident group, or create a new one.

        Groups anomalies that occur within the same time window and share
        causal relationships. One incident = one operator action needed.
        """
        param = anomaly.parameter
        subsystem = anomaly.subsystem

        # Check if any existing group is related
        for gid, group in self._active_groups.items():
            if now - group.last_seen > self.grouping_window:
                continue

            # Same subsystem? Related via causal graph?
            is_related = (
                subsystem in group.subsystems
                or any(
                    param in CAUSAL_GRAPH.get(gp, []) or gp in CAUSAL_GRAPH.get(param, [])
                    for gp in [a_param for _, a in self._recent_anomalies for a_param in [a.parameter] if a.id in group.anomalies]
                )
            )

            if is_related:
                group.anomalies.append(anomaly.id)
                group.subsystems.add(subsystem)
                group.last_seen = now
                return group

        # New incident group
        group = IncidentGroup(
            group_id=f"INC-{anomaly.id[:8]}",
            anomalies=[anomaly.id],
            subsystems={subsystem},
            root_parameter=param,
            first_seen=now,
            last_seen=now,
        )
        self._active_groups[group.group_id] = group
        return group

    def _generate_counterfactual(self, anomaly: Anomaly) -> str:
        """Generate a "what-if" explanation.

        "If battery_voltage had been 7.2V instead of 6.1V, this would be nominal."
        Helps operators understand the threshold and decide urgency.
        """
        param = anomaly.parameter
        value = anomaly.value
        severity = anomaly.severity

        if severity == Severity.CRITICAL:
            return f"If {param} were within 10% of its rolling average, this would be nominal"
        elif severity == Severity.WARNING:
            return f"If {param} were stable (low rate-of-change), this would be downgraded to WATCH"
        else:
            return f"If {param} returns to nominal within 5 minutes, this alert will auto-resolve"

    def _build_summary(
        self, anomaly: Anomaly, chain: list[str], group: IncidentGroup | None
    ) -> str:
        """One-line summary for dashboard display."""
        parts = [f"{anomaly.parameter}: {anomaly.severity.value.upper()}"]

        if chain and "→" in chain[0]:
            parts.append(f"({chain[0]})")

        if group and len(group.anomalies) > 1:
            parts.append(f"[Incident {group.group_id}, {len(group.anomalies)} related anomalies]")

        return " ".join(parts)

    def _build_detail(
        self,
        anomaly: Anomaly,
        chain: list[str],
        contributions: dict[str, float],
        counterfactual: str,
    ) -> str:
        """Full explanation text."""
        lines = [
            f"Parameter: {anomaly.parameter} = {anomaly.value} ({anomaly.subsystem})",
            f"Severity: {anomaly.severity.value} | Confidence: {anomaly.confidence:.1%}",
            f"Detectors: {', '.join(anomaly.detectors_triggered)}",
        ]

        if chain:
            lines.append(f"Causal chain: {' | '.join(chain)}")

        if contributions:
            top = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            lines.append("Top contributing parameters: " + ", ".join(f"{k} ({v:+.3f})" for k, v in top))

        lines.append(f"What-if: {counterfactual}")
        return "\n".join(lines)

    def _prune_old(self, now: float) -> None:
        """Remove expired anomalies and groups from tracking."""
        cutoff = now - self.grouping_window * 2
        self._recent_anomalies = [(t, a) for t, a in self._recent_anomalies if t > cutoff]
        expired = [gid for gid, g in self._active_groups.items() if now - g.last_seen > self.grouping_window * 3]
        for gid in expired:
            del self._active_groups[gid]
