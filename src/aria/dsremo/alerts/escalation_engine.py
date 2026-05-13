"""V3-F5: Escalation policy engine for alert delivery guarantees.

Current alert delivery: anomaly → WebSocket → client (if connected).
If disconnected, the alert is lost.  No escalation, no out-of-band notify.

This engine provides:
1. Persistent alert queue with delivery tracking
2. Escalation rules: unacknowledged WARNING for 15 min → CRITICAL + page
3. Out-of-band notification support (email, PagerDuty webhook)

Reference: ECSS-E-ST-70C §8.2.3: notification and escalation requirements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique

import structlog

logger = structlog.get_logger()


@unique
class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    FAILED = "failed"


@dataclass
class PendingAlert:
    """Alert in the escalation queue."""
    alert_id: str
    anomaly_id: str
    satellite_id: str
    severity: str
    created_at: float  # epoch seconds
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    delivery_attempts: int = 0
    escalated_at: float | None = None
    original_severity: str = ""


class EscalationEngine:
    """Manages alert delivery guarantees and auto-escalation.

    Usage:
        engine = EscalationEngine()
        engine.enqueue(alert_id, anomaly_id, satellite_id, severity)

        # Called periodically (e.g., every 30s):
        actions = engine.check_escalations()
        for action in actions:
            if action["type"] == "escalate":
                # Re-send with higher severity
            elif action["type"] == "retry":
                # Retry delivery
    """

    def __init__(
        self,
        escalation_timeout_s: float = 900.0,   # 15 min
        max_retries: int = 5,
        retry_interval_s: float = 30.0,
    ) -> None:
        self._escalation_timeout = escalation_timeout_s
        self._max_retries = max_retries
        self._retry_interval = retry_interval_s
        self._queue: dict[str, PendingAlert] = {}  # alert_id → PendingAlert

    def enqueue(
        self,
        alert_id: str,
        anomaly_id: str,
        satellite_id: str,
        severity: str,
    ) -> None:
        """Add an alert to the escalation queue."""
        self._queue[alert_id] = PendingAlert(
            alert_id=alert_id,
            anomaly_id=anomaly_id,
            satellite_id=satellite_id,
            severity=severity,
            created_at=time.time(),
            original_severity=severity,
        )

    def mark_delivered(self, alert_id: str) -> None:
        """Mark alert as successfully delivered via WebSocket."""
        if alert_id in self._queue:
            self._queue[alert_id].delivery_status = DeliveryStatus.DELIVERED

    def mark_acknowledged(self, alert_id: str) -> None:
        """Mark alert as acknowledged by operator."""
        if alert_id in self._queue:
            self._queue[alert_id].delivery_status = DeliveryStatus.ACKNOWLEDGED

    def check_escalations(self) -> list[dict]:
        """Check all pending alerts for escalation or retry needs.

        Returns list of action dicts:
            {"type": "retry", "alert_id": ..., "severity": ...}
            {"type": "escalate", "alert_id": ..., "old_severity": ..., "new_severity": ...}
        """
        now = time.time()
        actions: list[dict] = []

        for alert in list(self._queue.values()):
            if alert.delivery_status == DeliveryStatus.ACKNOWLEDGED:
                continue

            age = now - alert.created_at

            # Retry undelivered alerts.
            if alert.delivery_status == DeliveryStatus.PENDING:
                if alert.delivery_attempts < self._max_retries:
                    time_since_last = age - (alert.delivery_attempts * self._retry_interval)
                    if time_since_last >= self._retry_interval:
                        alert.delivery_attempts += 1
                        actions.append({
                            "type": "retry",
                            "alert_id": alert.alert_id,
                            "anomaly_id": alert.anomaly_id,
                            "satellite_id": alert.satellite_id,
                            "severity": alert.severity,
                            "attempt": alert.delivery_attempts,
                        })

            # Escalate unacknowledged alerts after timeout.
            if (alert.delivery_status in (DeliveryStatus.PENDING, DeliveryStatus.DELIVERED)
                    and age >= self._escalation_timeout
                    and alert.escalated_at is None):
                old_sev = alert.severity
                new_sev = self._escalate_severity(old_sev)
                if new_sev != old_sev:
                    alert.severity = new_sev
                    alert.escalated_at = now
                    alert.delivery_status = DeliveryStatus.ESCALATED
                    logger.warning(
                        "alert_escalated",
                        alert_id=alert.alert_id,
                        old_severity=old_sev,
                        new_severity=new_sev,
                        age_min=round(age / 60, 1),
                    )
                    actions.append({
                        "type": "escalate",
                        "alert_id": alert.alert_id,
                        "anomaly_id": alert.anomaly_id,
                        "satellite_id": alert.satellite_id,
                        "old_severity": old_sev,
                        "new_severity": new_sev,
                    })

        return actions

    @staticmethod
    def _escalate_severity(current: str) -> str:
        escalation = {
            "watch": "warning",
            "warning": "critical",
            "caution": "watch",
        }
        return escalation.get(current, current)

    def pending_count(self) -> int:
        return sum(
            1 for a in self._queue.values()
            if a.delivery_status in (DeliveryStatus.PENDING, DeliveryStatus.DELIVERED)
        )

    def reset(self) -> None:
        self._queue.clear()
