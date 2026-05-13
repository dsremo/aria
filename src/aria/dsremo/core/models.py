"""Domain models — immutable value objects for the telemetry pipeline.

Every struct here is frozen (immutable) and uses __slots__ for memory efficiency.
These flow through the system as pure data — no methods that mutate state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, unique


@unique
class Severity(str, Enum):
    """Anomaly severity levels — maps directly to operator response urgency.

    P3-V: 4 active levels to align with ISRO FOLIO standard:
        CAUTION  → informational, log-only (ISRO FOLIO: CAUTION)
        WATCH    → worth monitoring (ISRO FOLIO: ADVISORY)
        WARNING  → operator should investigate (ISRO FOLIO: WARNING)
        CRITICAL → immediate attention required (ISRO FOLIO: CRITICAL)
    """

    NOMINAL = "nominal"
    CAUTION = "caution"    # P3-V: informational, no action (ISRO FOLIO CAUTION level)
    WATCH = "watch"        # worth monitoring, no action needed yet
    WARNING = "warning"    # operator should investigate
    CRITICAL = "critical"  # immediate attention required


@unique
class Subsystem(str, Enum):
    """Satellite subsystem identifiers."""

    EPS = "eps"          # Electrical Power System
    ADCS = "adcs"        # Attitude Determination & Control
    THERMAL = "thermal"  # Thermal Control System
    COMMS = "comms"      # Communications


@unique
class FaultType(str, Enum):
    """Injectable fault types for the simulator."""

    DRIFT = "drift"              # gradual parameter drift
    SPIKE = "spike"              # sudden value spike
    DROPOUT = "dropout"          # sensor stops reporting
    DEGRADATION = "degradation"  # slow performance decline
    OSCILLATION = "oscillation"  # unexpected periodic behavior
    CORRELATION_BREAK = "correlation_break"  # cross-parameter link breaks


@dataclass(frozen=True, slots=True)
class TelemetryPoint:
    """Single telemetry measurement from a satellite parameter.

    This is the atomic unit of data flowing through the system.
    Immutable by design — once captured, telemetry is fact.
    """

    satellite_id: str
    timestamp: datetime
    subsystem: str
    parameter: str
    value: float
    unit: str
    quality: float = 1.0  # 0.0 = garbage, 1.0 = perfect


@dataclass(frozen=True, slots=True)
class TelemetryBatch:
    """A batch of telemetry points ingested together.

    Batching reduces API round-trips for high-frequency subsystems.
    """

    points: tuple[TelemetryPoint, ...]
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    hmac_signature: str | None = None  # tamper detection


@dataclass(frozen=True, slots=True)
class DetectorResult:
    """Output from a single anomaly detector."""

    detector_name: str
    is_anomaly: bool
    score: float          # 0.0 = normal, 1.0 = extreme anomaly
    severity: Severity
    details: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Anomaly:
    """A confirmed anomaly — the core output of the detection pipeline.

    Contains everything an operator needs: what happened, how confident
    we are, which detectors agree, and a human-readable explanation.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    satellite_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    subsystem: str = ""
    parameter: str = ""
    value: float = 0.0
    severity: Severity = Severity.WATCH
    confidence: float = 0.0
    detectors_triggered: tuple[str, ...] = ()
    explanation: str = ""
    root_cause_group: str | None = None
    contributing_params: dict[str, float] = field(default_factory=dict)
    # P2-M: Anomaly verification state — tracks whether the anomaly has been
    # verified by operator or autonomous system.
    # "suspected" → initial detection (default)
    # "confirmed" → operator/AI verified as real fault
    # "false_positive" → operator marked as FP
    # "pending_verification" → high-rate data requested for confirmation
    verification_status: str = "suspected"
    # P2-L: FMEA failure mode ID (e.g., "FM-PWR-003")
    failure_mode_id: str | None = None


@dataclass(frozen=True, slots=True)
class Incident:
    """A group of correlated anomalies on the same satellite within a time window.

    Production standard (NASA GSFC, SpaceX Doppel, YAMCS): raw per-channel
    anomalies are never surfaced directly to operators.  Instead they are
    correlated within a time window into a single Incident — operators see
    one card per fault event, not one card per detector firing.

    IncidentGrouper in detection/incident_grouper.py maintains open incidents
    and assigns each new Anomaly to one.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    satellite_id: str = ""
    first_anomaly_at: datetime = field(default_factory=datetime.utcnow)  # opened_at
    last_anomaly_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    severity: Severity = Severity.WATCH          # max severity across members
    confidence: float = 0.0                      # weighted average confidence
    channels: tuple[str, ...] = ()               # all affected parameters
    root_cause_summary: str = ""                 # top contributing detector pattern
    anomaly_count: int = 1
    status: str = "open"                         # open / resolved / false_positive


@dataclass(frozen=True, slots=True)
class Alert:
    """An alert dispatched to operators via webhook/email.

    Alerts are deduplicated — the same ongoing anomaly doesn't spam.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    anomaly_id: str = ""
    satellite_id: str = ""
    severity: Severity = Severity.WARNING
    title: str = ""
    message: str = ""
    dispatched_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class SatelliteProfile:
    """Configuration profile for a monitored satellite.

    Defines what parameters exist, their expected ranges, and
    which subsystem they belong to. Loaded from mission config.
    """

    satellite_id: str
    name: str
    orbit_period_minutes: float = 90.0  # LEO default
    subsystems: tuple[str, ...] = ("eps", "adcs", "thermal", "comms")
    parameters: dict[str, dict] = field(default_factory=dict)
    # parameters example: {"battery_voltage": {"unit": "V", "min": 6.0, "max": 8.4, "subsystem": "eps"}}
