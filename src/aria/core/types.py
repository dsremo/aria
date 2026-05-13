"""Core type definitions for ARIA.

Every enum and dataclass here is used across all ARIA subsystems.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any


class AuthorityLevel(Enum):
    """Who can authorize this action.

      ARIA:         sensor-only -> routine -> supervised -> consent -> advisory -> captain-only
    """

    SENSOR_ONLY = 0  # Read-only telemetry queries. No human needed.
    ROUTINE = 1  # Automated ops (heater toggle, antenna slew). Logged, not prompted.
    SUPERVISED = 2  # AI acts, Captain notified after. (e.g. cell balancing)
    CONSENT = 3  # AI proposes, Captain can veto within timeout.
    ADVISORY = 4  # Captain decides; AI recommends. (e.g. maneuver planning)
    CAPTAIN_ONLY = 5  # Only Captain can initiate. (e.g. abort, EVA start)


class SafetyLevel(Enum):
    """How dangerous is this tool's action.

    Standard tool flags: isReadOnly / isDestructive / isConcurrencySafe.
    """

    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"
    EMERGENCY = "emergency"


class Severity(Enum):
    """Anomaly / alert severity levels. Aligned with Dsremo thresholds."""

    NOMINAL = 0  # No issue
    WATCH = 1  # Confidence >= 0.50
    WARNING = 2  # Confidence >= 0.65
    CRITICAL = 3  # Confidence >= 0.85
    EMERGENCY = 4  # Imminent danger to crew or vehicle


class InterruptBehavior(Enum):
    """How a tool handles mid-execution interrupts.

    Tool-lifecycle hook: interruptBehavior().
    """

    CANCEL = "cancel"  # Stop and discard (safe for read-only tools)
    BLOCK = "block"  # Keep running, queue the interrupt
    CHECKPOINT = "checkpoint"  # Save state then yield (ARIA extension)


class ToolCategory(Enum):
    """Broad tool classification for registry filtering and agent routing."""

    TELEMETRY = auto()
    NAVIGATION = auto()
    PROPULSION = auto()
    LIFE_SUPPORT = auto()
    COMMUNICATION = auto()
    POWER = auto()
    SCIENCE = auto()
    STRUCTURAL = auto()
    EMERGENCY = auto()
    DIAGNOSTIC = auto()
    PLANNING = auto()
    FLEET = auto()


class AgentStatus(Enum):
    """Lifecycle state of a SubsystemAgent."""

    INITIALIZING = auto()
    READY = auto()
    BUSY = auto()
    DEGRADED = auto()
    ERROR = auto()
    SHUTTING_DOWN = auto()
    STOPPED = auto()


class MissionPhase(Enum):
    """Current mission phase — drives configuration, authority, and thresholds."""

    PRE_LAUNCH = auto()
    LAUNCH_ASCENT = auto()
    EARLY_ORBIT = auto()
    NOMINAL_LEO = auto()
    ORBIT_TRANSFER = auto()
    PROXIMITY_OPS = auto()
    PLANETARY_APPROACH = auto()
    ENTRY_DESCENT_LANDING = auto()
    SURFACE_OPS = auto()
    DEEP_SPACE_CRUISE = auto()
    EMERGENCY = auto()


# Mission phase → default authority level and active agent configuration
PHASE_CONFIG: dict[str, dict[str, Any]] = {
    "PRE_LAUNCH": {
        "authority": "CAPTAIN_ONLY",
        "description": "Pre-launch checkout — captain controls everything",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "comms"],
        "autonomy_level": 0,
    },
    "LAUNCH_ASCENT": {
        "authority": "SUPERVISED",
        "description": "Launch/ascent — automated sequences with human override",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "propulsion"],
        "autonomy_level": 2,
    },
    "EARLY_ORBIT": {
        "authority": "SUPERVISED",
        "description": "Early orbit — deployment, checkout, commissioning",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "comms", "propulsion"],
        "autonomy_level": 3,
    },
    "NOMINAL_LEO": {
        "authority": "SUPERVISED",
        "description": "Nominal LEO operations — full agent suite, AI assists",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "comms", "propulsion", "science", "medical"],
        "autonomy_level": 3,
    },
    "ORBIT_TRANSFER": {
        "authority": "SUPERVISED",
        "description": "Orbit transfer — propulsion active, heightened monitoring",
        "active_agents": ["telemetry", "power", "thermal", "navigation", "propulsion", "comms"],
        "autonomy_level": 3,
    },
    "PROXIMITY_OPS": {
        "authority": "CAPTAIN_ONLY",
        "description": "Proximity operations — docking/undocking, captain authority",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "comms", "propulsion"],
        "autonomy_level": 1,
    },
    "DEEP_SPACE_CRUISE": {
        "authority": "ROUTINE",
        "description": "Deep space cruise — high autonomy, long comm delays",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "comms", "propulsion", "science", "medical"],
        "autonomy_level": 4,
    },
    "EMERGENCY": {
        "authority": "SUPERVISED",
        "description": "Emergency — AI acts immediately, captain notified",
        "active_agents": ["telemetry", "power", "thermal", "eclss", "navigation", "comms", "propulsion"],
        "autonomy_level": 4,
    },
}


class EventPriority(Enum):
    """Message bus priority. Lower number = higher priority."""

    P0_EMERGENCY = 0  # Immediate: fire, depress, collision
    P1_CRITICAL = 1  # Seconds: attitude loss, power failure
    P2_WARNING = 2  # Minutes: anomaly escalation, conjunction alert
    P3_ROUTINE = 3  # Operational: telemetry summary, schedule update
    P4_BULK = 4  # Best-effort: science data, logs
    P5_BACKGROUND = 5  # Housekeeping: model updates, calibration
