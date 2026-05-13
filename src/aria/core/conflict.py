"""Conflict Resolution — resolves disagreements between subsystem agents.

Per CENTRAL_AI_MASTER_PLAN Section 3.4.4:

When agents conflict (e.g., PowerAgent wants to shed science loads but
ScienceAgent wants to keep instruments running), the ConflictResolver
applies a priority-based strategy where safety always wins.

Priority Order (highest to lowest):
  1. crew_safety       — anything affecting crew survival
  2. spacecraft_safety — spacecraft integrity
  3. mission_critical  — mission-critical operations
  4. mission_nominal   — nominal mission operations
  5. science           — science return
  6. comfort           — crew comfort
  7. optimization      — resource optimization

Resolution Strategy:
  - Different priorities → higher priority wins
  - Same priority → attempt compromise
  - No compromise → escalate to ARIA Core / Captain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()

PRIORITY_ORDER = [
    "crew_safety",
    "spacecraft_safety",
    "mission_critical",
    "mission_nominal",
    "science",
    "comfort",
    "optimization",
]

# Agent subsystem → default priority mapping (when not explicitly specified)
SUBSYSTEM_DEFAULT_PRIORITY: dict[str, str] = {
    "medical": "crew_safety",
    "eclss": "crew_safety",
    "power": "spacecraft_safety",
    "thermal": "spacecraft_safety",
    "navigation": "mission_critical",
    "propulsion": "mission_critical",
    "comms": "mission_nominal",
    "telemetry": "mission_nominal",
    "science": "science",
}


@dataclass
class ConflictRequest:
    """One side of an agent conflict."""
    agent_name: str
    action: str
    priority: str = ""  # One of PRIORITY_ORDER
    reason: str = ""
    resource: str = ""  # What resource is contested (e.g., "power_budget", "attitude")
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Resolution:
    """Outcome of conflict resolution."""
    winner: ConflictRequest | None = None
    compromise: bool = False
    compromise_plan: dict[str, Any] = field(default_factory=dict)
    escalated: bool = False
    reason: str = ""


class ConflictResolver:
    """Resolves conflicts between subsystem agents.

    Strategy: priority-based with safety-first principle.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._conflict_history: list[dict[str, Any]] = []

    async def resolve(self, request_a: ConflictRequest, request_b: ConflictRequest) -> Resolution:
        """Resolve a conflict between two agent requests.

        Returns Resolution with winner, compromise, or escalation.
        """
        # Assign default priorities if not specified
        if not request_a.priority:
            request_a.priority = SUBSYSTEM_DEFAULT_PRIORITY.get(request_a.agent_name, "mission_nominal")
        if not request_b.priority:
            request_b.priority = SUBSYSTEM_DEFAULT_PRIORITY.get(request_b.agent_name, "mission_nominal")

        pri_a = PRIORITY_ORDER.index(request_a.priority) if request_a.priority in PRIORITY_ORDER else 99
        pri_b = PRIORITY_ORDER.index(request_b.priority) if request_b.priority in PRIORITY_ORDER else 99

        # Different priorities → higher (lower index) wins
        if pri_a != pri_b:
            winner = request_a if pri_a < pri_b else request_b
            loser = request_b if pri_a < pri_b else request_a
            resolution = Resolution(
                winner=winner,
                reason=f"Priority: {winner.priority} ({winner.agent_name}) > "
                       f"{loser.priority} ({loser.agent_name})",
            )
        else:
            # Same priority — try compromise
            compromise = self._find_compromise(request_a, request_b)
            if compromise:
                resolution = Resolution(
                    compromise=True,
                    compromise_plan=compromise,
                    reason=f"Compromise found at priority level '{request_a.priority}'",
                )
            else:
                # Escalate to coordinator/captain
                resolution = Resolution(
                    escalated=True,
                    reason=f"Same priority '{request_a.priority}', no compromise — escalating",
                )
                await self._escalate(request_a, request_b)

        # Record
        self._conflict_history.append({
            "agent_a": request_a.agent_name,
            "agent_b": request_b.agent_name,
            "resource": request_a.resource or request_b.resource,
            "resolution": resolution.reason,
            "escalated": resolution.escalated,
        })
        if len(self._conflict_history) > 200:
            self._conflict_history = self._conflict_history[-200:]

        logger.info(
            "conflict.resolved",
            agent_a=request_a.agent_name,
            agent_b=request_b.agent_name,
            result=resolution.reason,
        )

        return resolution

    def _find_compromise(
        self, request_a: ConflictRequest, request_b: ConflictRequest
    ) -> dict[str, Any] | None:
        """Attempt to find a compromise between two same-priority requests.

        Common compromises:
          - Power conflict: partial load reduction instead of full shed
          - Attitude conflict: time-share between pointing modes
          - Comms conflict: interleave data types in downlink
        """
        resource = request_a.resource or request_b.resource

        if resource == "power_budget":
            return {
                "action": "partial_reduction",
                "description": f"Reduce {request_a.agent_name} load by 50% instead of full shed",
                "agents_affected": [request_a.agent_name, request_b.agent_name],
            }

        if resource == "attitude":
            return {
                "action": "time_share",
                "description": "Alternate between requested attitudes in 15-min slots",
                "agents_affected": [request_a.agent_name, request_b.agent_name],
            }

        if resource == "downlink_bandwidth":
            return {
                "action": "interleave",
                "description": "Interleave data from both agents in downlink queue",
                "agents_affected": [request_a.agent_name, request_b.agent_name],
            }

        return None  # No known compromise for this resource type

    async def _escalate(self, request_a: ConflictRequest, request_b: ConflictRequest) -> None:
        """Escalate unresolvable conflict to captain."""
        await self._bus.publish(
            Message(
                topic="aria.captain.alert",
                payload={
                    "type": "conflict_escalation",
                    "severity": "WARNING",
                    "message": (
                        f"Agent conflict: {request_a.agent_name} ({request_a.action}) "
                        f"vs {request_b.agent_name} ({request_b.action}) — "
                        f"same priority '{request_a.priority}', needs captain decision"
                    ),
                    "agent_a": {"name": request_a.agent_name, "action": request_a.action, "reason": request_a.reason},
                    "agent_b": {"name": request_b.agent_name, "action": request_b.action, "reason": request_b.reason},
                },
                priority=EventPriority.P2_WARNING,
                source_agent="conflict_resolver",
            )
        )

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._conflict_history)
