"""V3-W4: Mission phase gate — suppresses detection during commissioning.

Problem
-------
At T+0 (satellite deployment) the telemetry transitions from fairing interior
to on-orbit conditions.  Every parameter simultaneously exhibits step
changes, thermal transients, and new periodic patterns.  If the calibration
system enters `warming_up` during this period the first 100-sample reference
window straddles the deployment transient, producing reference statistics
that are a mixture of pre- and post-deployment distributions.  Every
detector then fires continuously for the first few orbits — exactly the
most operationally-critical period.

Solution
--------
Each satellite has a `MissionPhase` state:
    INTEGRATION    — pre-launch (ground testing)
    LAUNCH         — launch vehicle ascent
    COMMISSIONING  — first hours to days on orbit; detectors suppressed
    NOMINAL        — full detection active
    END_OF_LIFE    — graceful disposal / de-orbit; detection still active
                     but alerts downgraded to watch-only

During COMMISSIONING the detector pipeline returns an informational result
rather than running statistical checks; calibration is held (no buffer
accumulation) so the reference window starts clean the moment the operator
transitions to NOMINAL.

Transitioning to NOMINAL happens either (a) on operator command, or (b)
after `commissioning_duration_h` has elapsed from the entry into
COMMISSIONING.  The default duration is 48 h (ESA/SSC commissioning
windows for Earth-observation missions are typically 24-72 h; CCSDS
517.0-B-1 §6.2 recommends explicit operator sign-off for transitions).

References
----------
NASA-STD-7009A (2016).  "Standard for Models and Simulations", §4.4.
CCSDS 517.0-B-1 (2016).  "Mission Operations — Monitoring Service", §6.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, unique

import structlog

logger = structlog.get_logger()


# Default commissioning duration before auto-transition to NOMINAL.
# Most Earth-observation LEO missions complete bus checkout in 24-72 h
# (Wertz & Larson 1999 SMAD §2.4.1).  48 h is the middle of that range.
DEFAULT_COMMISSIONING_DURATION_H: float = 48.0   # SMAD §2.4.1


@unique
class MissionPhase(str, Enum):
    """Mission phase (ECSS-M-ST-10C lifecycle states, subset)."""

    INTEGRATION   = "integration"
    LAUNCH        = "launch"
    COMMISSIONING = "commissioning"
    NOMINAL       = "nominal"
    END_OF_LIFE   = "end_of_life"


@dataclass
class PhaseState:
    """Per-satellite mission-phase record."""

    satellite_id:       str
    phase:              MissionPhase = MissionPhase.NOMINAL
    entered_at:         float        = 0.0   # Unix epoch seconds
    commissioning_duration_h: float = DEFAULT_COMMISSIONING_DURATION_H


class MissionPhaseRegistry:
    """Process-wide registry of mission-phase state per satellite.

    Thread-safe enough for single-loop asyncio use (no locking needed).
    Callers persist the (satellite_id, phase, entered_at) triple to the DB
    after each mutation; reload from DB at server startup via `load_all`.
    """

    def __init__(self) -> None:
        self._states: dict[str, PhaseState] = {}

    def get(self, satellite_id: str) -> PhaseState:
        st = self._states.get(satellite_id)
        if st is None:
            st = PhaseState(satellite_id=satellite_id)
            self._states[satellite_id] = st
        return st

    def set_phase(
        self,
        satellite_id: str,
        phase: MissionPhase,
        epoch: float | None = None,
        commissioning_duration_h: float | None = None,
    ) -> PhaseState:
        """Transition a satellite to a new mission phase.

        `epoch` defaults to the current UTC time.  When transitioning INTO
        COMMISSIONING, callers may override the default auto-transition
        window via `commissioning_duration_h`.
        """
        now = epoch if epoch is not None else datetime.now(timezone.utc).timestamp()
        st = self.get(satellite_id)
        old = st.phase
        st.phase      = phase
        st.entered_at = float(now)
        if commissioning_duration_h is not None:
            st.commissioning_duration_h = float(commissioning_duration_h)
        logger.info(
            "mission_phase_transition",
            satellite_id=satellite_id,
            old_phase=old.value,
            new_phase=phase.value,
            epoch=now,
        )
        return st

    def is_detection_active(self, satellite_id: str, now_epoch: float | None = None) -> bool:
        """True if anomaly detection should run for this satellite.

        Currently suppressed only in COMMISSIONING.  Auto-transitions the
        satellite to NOMINAL if `commissioning_duration_h` has elapsed.
        """
        st = self.get(satellite_id)
        if st.phase != MissionPhase.COMMISSIONING:
            return True
        now = now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()
        duration_s = st.commissioning_duration_h * 3600.0
        if (now - st.entered_at) >= duration_s:
            self.set_phase(satellite_id, MissionPhase.NOMINAL, epoch=now)
            logger.info(
                "mission_phase_auto_transition",
                satellite_id=satellite_id,
                reason="commissioning_duration_elapsed",
            )
            return True
        return False

    def iter_states(self):
        """Yield all registered PhaseState records (persistence helper)."""
        return self._states.values()

    def clear(self) -> None:
        self._states.clear()


# ── Process-wide singleton ────────────────────────────────────────────────── #

_registry: MissionPhaseRegistry | None = None


def get_registry() -> MissionPhaseRegistry:
    global _registry
    if _registry is None:
        _registry = MissionPhaseRegistry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
