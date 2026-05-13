"""V3-F1: Anomaly action audit trail — ECSS-E-ST-70C §6.3.2 compliance.

Records every operator interaction with anomaly management:
    - acknowledge: operator has seen the anomaly
    - confirm: operator verifies it is a real fault
    - dismiss: operator marks as false positive
    - escalate: operator escalates severity
    - annotate: operator adds free-text context

Each action is immutable and timestamped with the operator_id.
All verification_state transitions must go through this module.

Reference: ECSS-E-ST-70C (2008) §6.3.2: anomaly management and operator
           action logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, unique


@unique
class ActionType(str, Enum):
    """Types of operator actions on anomalies."""

    ACKNOWLEDGE = "acknowledge"
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    ESCALATE = "escalate"
    ANNOTATE = "annotate"


# Valid transitions: (old_state, action) → new_state.
_VALID_TRANSITIONS: dict[tuple[str, ActionType], str] = {
    ("suspected", ActionType.ACKNOWLEDGE): "pending_verification",
    ("suspected", ActionType.CONFIRM): "confirmed",
    ("suspected", ActionType.DISMISS): "false_positive",
    ("suspected", ActionType.ESCALATE): "suspected",
    ("pending_verification", ActionType.CONFIRM): "confirmed",
    ("pending_verification", ActionType.DISMISS): "false_positive",
    ("pending_verification", ActionType.ESCALATE): "pending_verification",
    ("confirmed", ActionType.ANNOTATE): "confirmed",
    ("confirmed", ActionType.ESCALATE): "confirmed",
    ("false_positive", ActionType.ANNOTATE): "false_positive",
}


@dataclass(frozen=True, slots=True)
class AnomalyAction:
    """Immutable record of one operator action on an anomaly."""

    id: str
    anomaly_id: str
    operator_id: str
    action_type: ActionType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str = ""
    old_state: str = ""
    new_state: str = ""


class AnomalyActionLog:
    """In-memory audit log with DB persistence support.

    Usage in API routes:
        log = AnomalyActionLog()
        action = log.record(
            anomaly_id="...",
            operator_id="ops-1",
            action_type=ActionType.CONFIRM,
            rationale="Verified via backup sensor",
            current_state="suspected",
        )
        # action.new_state == "confirmed"
        # Persist to DB: INSERT INTO anomaly_actions (...)

    All transitions are validated — invalid transitions raise ValueError.
    """

    def __init__(self) -> None:
        self._actions: list[AnomalyAction] = []

    def record(
        self,
        anomaly_id: str,
        operator_id: str,
        action_type: ActionType,
        rationale: str = "",
        current_state: str = "suspected",
    ) -> AnomalyAction:
        """Record an operator action.  Returns the immutable action record.

        Raises ValueError if the transition is not allowed.
        """
        key = (current_state, action_type)
        if action_type == ActionType.ANNOTATE:
            new_state = current_state  # annotations don't change state
        elif key not in _VALID_TRANSITIONS:
            raise ValueError(
                f"Invalid transition: {current_state!r} + {action_type.value!r}. "
                f"Allowed from {current_state!r}: "
                f"{[a.value for (s, a) in _VALID_TRANSITIONS if s == current_state]}"
            )
        else:
            new_state = _VALID_TRANSITIONS[key]

        import uuid  # noqa: PLC0415
        action = AnomalyAction(
            id=str(uuid.uuid4()),
            anomaly_id=anomaly_id,
            operator_id=operator_id,
            action_type=action_type,
            rationale=rationale,
            old_state=current_state,
            new_state=new_state,
        )
        self._actions.append(action)
        return action

    def get_actions(self, anomaly_id: str) -> list[AnomalyAction]:
        """Return all actions for a given anomaly, oldest first."""
        return [a for a in self._actions if a.anomaly_id == anomaly_id]

    def get_recent(self, limit: int = 100) -> list[AnomalyAction]:
        """Return the most recent actions across all anomalies."""
        return self._actions[-limit:]
