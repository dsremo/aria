"""Decision Engine — classifies, routes, and escalates ARIA decisions.

The decision engine sits between agents and the Captain:
  - Routine decisions (WATCH) → logged, no human involvement
  - Important decisions (WARNING) → Captain notified, AI acts
  - Critical decisions (CRITICAL) → Captain must acknowledge within timeout
  - Emergency decisions (EMERGENCY) → AI acts immediately, Captain notified after

Inspired by the ARIA Decision Authority Matrix (06-decision-authority/).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import AuthorityLevel, EventPriority, Severity

logger = structlog.get_logger()


@dataclass
class Decision:
    """A decision record — complete audit trail."""

    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str = ""  # "anomaly_response", "maneuver", "load_shed", etc.
    severity: Severity = Severity.NOMINAL
    description: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    chosen_option: str = ""
    confidence: float = 1.0
    authority_used: AuthorityLevel = AuthorityLevel.ROUTINE
    captain_involved: bool = False
    captain_approved: bool | None = None  # None = not asked
    reasoning: str = ""
    outcome: str = "pending"  # "executed", "overridden", "timeout", "cancelled"
    source_agent: str = ""


class DecisionEngine:
    """Routes decisions based on severity and authority level.

    Severity → Autonomy Mapping:
      NOMINAL  → Level 4: Fully autonomous, logged
      WATCH    → Level 3: Supervised, Captain notified after
      WARNING  → Level 2: Consent-based, Captain can veto (30s timeout)
      CRITICAL → Level 1: Advisory, Captain decides (60s timeout, AI acts if no response)
      EMERGENCY → Level 0+: AI acts immediately (<5s), Captain notified after
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._pending_decisions: dict[str, Decision] = {}
        self._decision_history: list[Decision] = []
        self._captain_response_event: dict[str, asyncio.Event] = {}

        # Timeouts per severity (seconds)
        self._timeouts = {
            Severity.WATCH: 0,  # No wait
            Severity.WARNING: 30,
            Severity.CRITICAL: 60,
            Severity.EMERGENCY: 5,  # Very short — AI will act
        }

        # Subscribe to captain responses
        self._bus.subscribe("aria.captain.response", self._on_captain_response)

    async def submit_decision(self, decision: Decision) -> Decision:
        """Submit a decision for routing.

        Returns the decision with outcome filled in.
        """
        logger.info(
            "decision.submitted",
            id=decision.decision_id,
            severity=decision.severity.name,
            category=decision.category,
        )

        if decision.severity == Severity.NOMINAL:
            # Auto-execute, no escalation
            decision.authority_used = AuthorityLevel.ROUTINE
            decision.outcome = "executed"
            self._record(decision)
            return decision

        if decision.severity == Severity.WATCH:
            # Execute and notify
            decision.authority_used = AuthorityLevel.SUPERVISED
            decision.outcome = "executed"
            await self._notify_captain(decision, inform_only=True)
            self._record(decision)
            return decision

        if decision.severity == Severity.EMERGENCY:
            # Act immediately, notify after
            decision.authority_used = AuthorityLevel.ROUTINE  # Emergency override
            decision.outcome = "executed"
            decision.captain_involved = True
            decision.captain_approved = None  # Didn't wait
            await self._notify_captain(decision, inform_only=True)
            self._record(decision)
            logger.warning(
                "decision.emergency_executed",
                id=decision.decision_id,
                description=decision.description,
            )
            return decision

        # WARNING and CRITICAL: ask Captain, wait with timeout
        timeout = self._timeouts.get(decision.severity, 30)
        decision.captain_involved = True

        # Request Captain approval
        event = asyncio.Event()
        self._captain_response_event[decision.decision_id] = event
        self._pending_decisions[decision.decision_id] = decision

        await self._notify_captain(decision, inform_only=False)

        # Wait for response — use try/finally to guarantee cleanup even
        # if an unexpected exception (not just TimeoutError) occurs.
        try:
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
                # Captain responded — decision updated in _on_captain_response
                decision = self._pending_decisions[decision.decision_id]
            except asyncio.TimeoutError:
                # Captain didn't respond in time — AI acts
                decision.captain_approved = None
                decision.outcome = "executed"
                decision.reasoning += f" [Captain timeout after {timeout}s — AI acted autonomously]"
                logger.warning(
                    "decision.captain_timeout",
                    id=decision.decision_id,
                    timeout_s=timeout,
                )
        finally:
            # Cleanup — must run even on unexpected exceptions to prevent
            # leaking entries in _pending_decisions / _captain_response_event.
            self._pending_decisions.pop(decision.decision_id, None)
            self._captain_response_event.pop(decision.decision_id, None)

        self._record(decision)
        return decision

    async def _notify_captain(self, decision: Decision, inform_only: bool) -> None:
        """Send decision notification to Captain's console."""
        msg_type = "info" if inform_only else "approval_required"
        await self._bus.publish(
            Message(
                topic="aria.captain.alert",
                payload={
                    "type": msg_type,
                    "decision_id": decision.decision_id,
                    "severity": decision.severity.name,
                    "category": decision.category,
                    "description": decision.description,
                    "options": decision.options,
                    "chosen_option": decision.chosen_option,
                    "confidence": decision.confidence,
                    "reasoning": decision.reasoning,
                    "timeout_s": self._timeouts.get(decision.severity, 0) if not inform_only else 0,
                    "source_agent": decision.source_agent,
                },
                priority=EventPriority.P1_CRITICAL
                if decision.severity.value >= Severity.CRITICAL.value
                else EventPriority.P2_WARNING,
                source_agent="decision_engine",
            )
        )

    async def _on_captain_response(self, message: Message) -> None:
        """Handle Captain's response to a pending decision."""
        decision_id = message.payload.get("decision_id", "")
        approved = message.payload.get("approved", False)
        override_option = message.payload.get("override_option", "")

        decision = self._pending_decisions.get(decision_id)
        if not decision:
            return

        decision.captain_approved = approved
        if approved:
            decision.outcome = "executed"
        elif override_option:
            decision.chosen_option = override_option
            decision.outcome = "overridden"
        else:
            decision.outcome = "cancelled"

        logger.info(
            "decision.captain_response",
            id=decision_id,
            approved=approved,
            outcome=decision.outcome,
        )

        # Wake up the waiting submit_decision
        event = self._captain_response_event.get(decision_id)
        if event:
            event.set()

    def _record(self, decision: Decision) -> None:
        """Archive decision for audit trail."""
        self._decision_history.append(decision)
        # Keep last 1000 decisions in memory
        if len(self._decision_history) > 1000:
            self._decision_history = self._decision_history[-1000:]

    def get_history(self, limit: int = 50) -> list[Decision]:
        return self._decision_history[-limit:]

    def get_pending(self) -> list[Decision]:
        return list(self._pending_decisions.values())
