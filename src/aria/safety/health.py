"""Health Scorer — computes a 0-100 health score for the spacecraft.

Subsystem weights reflect criticality:
  ECLSS:       25% (crew life depends on it)
  Power:       20% (everything depends on power)
  Navigation:  15% (position/attitude knowledge)
  ADCS:        10% (pointing control)
  Thermal:     10% (equipment protection)
  Comms:        8% (ground contact)
  Propulsion:   7% (maneuver capability)
  Science:      5% (mission objectives)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from aria.core.types import AgentStatus

logger = structlog.get_logger()

SUBSYSTEM_WEIGHTS: dict[str, float] = {
    "eclss": 0.25,
    "power": 0.20,
    "navigation": 0.15,
    "thermal": 0.10,
    "telemetry": 0.10,
    "comms": 0.08,
    "propulsion": 0.07,
    "science": 0.05,
}

# Agent status to health score mapping
STATUS_SCORES: dict[str, float] = {
    AgentStatus.READY.name: 1.0,
    AgentStatus.BUSY.name: 1.0,
    AgentStatus.INITIALIZING.name: 0.8,
    AgentStatus.DEGRADED.name: 0.6,
    AgentStatus.ERROR.name: 0.1,
    AgentStatus.SHUTTING_DOWN.name: 0.3,
    AgentStatus.STOPPED.name: 0.0,
}


@dataclass
class HealthReport:
    """Complete health assessment."""

    overall_score: float = 100.0  # 0-100
    subsystem_scores: dict[str, float] = None  # type: ignore[assignment]
    degraded_subsystems: list[str] = None  # type: ignore[assignment]
    critical_subsystems: list[str] = None  # type: ignore[assignment]
    tool_health: dict[str, Any] = None  # type: ignore[assignment]
    recommendation: str = ""

    def __post_init__(self) -> None:
        if self.subsystem_scores is None:
            self.subsystem_scores = {}
        if self.degraded_subsystems is None:
            self.degraded_subsystems = []
        if self.critical_subsystems is None:
            self.critical_subsystems = []
        if self.tool_health is None:
            self.tool_health = {}


class HealthScorer:
    """Computes spacecraft health score from agent and tool status."""

    def compute(
        self,
        agent_statuses: dict[str, str],
        tool_health: dict[str, Any] | None = None,
        sensor_gaps: list[str] | None = None,
    ) -> HealthReport:
        """Compute overall and per-subsystem health scores.

        Args:
            agent_statuses: {agent_name: status_string}
            tool_health: from ToolRegistry.health_report()
            sensor_gaps: list of offline sensor names
        """
        report = HealthReport()
        report.tool_health = tool_health or {}

        # Score each subsystem based on its agent status
        weighted_sum = 0.0
        total_weight = 0.0

        for subsystem, weight in SUBSYSTEM_WEIGHTS.items():
            status = agent_statuses.get(subsystem, "STOPPED")
            score = STATUS_SCORES.get(status, 0.0) * 100.0

            # Penalize if tools for this subsystem have circuit breakers open
            if tool_health:
                tripped = tool_health.get("circuit_breakers_open", [])
                if any(subsystem in t for t in tripped):
                    score *= 0.5

            # Penalize for sensor gaps in this subsystem
            if sensor_gaps:
                gaps_in_subsystem = [g for g in sensor_gaps if subsystem in g.lower()]
                if gaps_in_subsystem:
                    score *= max(0.3, 1.0 - 0.1 * len(gaps_in_subsystem))

            report.subsystem_scores[subsystem] = round(score, 1)
            weighted_sum += score * weight
            total_weight += weight

            if score < 50:
                report.critical_subsystems.append(subsystem)
            elif score < 80:
                report.degraded_subsystems.append(subsystem)

        report.overall_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0

        # Generate recommendation
        if report.overall_score >= 90:
            report.recommendation = "All systems nominal. No action required."
        elif report.overall_score >= 70:
            report.recommendation = (
                f"System degraded. Affected: {', '.join(report.degraded_subsystems)}. "
                "Monitor closely. Consider reducing non-essential operations."
            )
        elif report.overall_score >= 50:
            report.recommendation = (
                f"System in reduced capability. Critical: {', '.join(report.critical_subsystems)}. "
                "Recommend safe mode assessment. Notify ground control."
            )
        else:
            report.recommendation = (
                f"System health critical ({report.overall_score}%). "
                f"Critical subsystems: {', '.join(report.critical_subsystems)}. "
                "RECOMMEND SAFE MODE ENTRY."
            )

        return report
