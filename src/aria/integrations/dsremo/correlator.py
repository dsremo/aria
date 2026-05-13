"""AnomalyCorrelator — cross-channel root cause analysis.

When multiple Dsremo channels flag simultaneously, this module:
  1. Groups concurrent anomalies within a time window
  2. Maps channel groups to known failure signatures
  3. Assigns root-cause hypotheses with confidence scores
  4. Publishes aria.anomaly.correlation events for the cognitive engine

Why this matters:
  - A battery SoC drop + bus undervoltage + solar power drop happening
    together = eclipse entry, NOT a fault
  - But battery SoC drop + thermal runaway temp + bus undervoltage together
    = likely battery failure — emergency action needed
  - Without correlation, each agent raises its own alert and the captain
    gets 5 separate alerts instead of 1 root cause

Architecture:
  - Subscribe to aria.anomaly.* on the bus
  - Maintain a sliding time window of recent anomalies
  - On each new anomaly, check for known multi-channel patterns
  - Publish aria.anomaly.correlation with root_cause + confidence + involved_channels
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()


@dataclass
class AnomalyEvent:
    """A single anomaly event in the correlation window."""
    channel_id: str
    subsystem: str
    severity: str
    score: float
    timestamp: float = field(default_factory=time.time)
    source_topic: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrelationResult:
    """Result of cross-channel correlation analysis."""
    root_cause: str
    confidence: float  # 0-1
    involved_channels: list[str]
    involved_subsystems: list[str]
    severity: str
    description: str
    recommendation: str
    evidence: list[str]


# ---------------------------------------------------------------------------
# Known multi-channel failure signatures
# ---------------------------------------------------------------------------
# Each pattern: (name, required_channels_any_of, min_count, confidence, description, recommendation)

FAILURE_SIGNATURES: list[dict[str, Any]] = [
    {
        "name": "BATTERY_THERMAL_RUNAWAY",
        "channels_match": ["eps.battery.temperature_c", "eps.battery.soc_percent", "eps.bus.voltage_v"],
        "min_match": 2,
        "severity": "CRITICAL",
        "confidence": 0.85,
        "description": "Battery thermal runaway precursor: simultaneous temperature spike and voltage drop",
        "recommendation": "Execute emergency battery disconnect procedure. Activate backup power.",
        "evidence_template": "Channels {channels} flagged simultaneously within {window}s",
    },
    {
        "name": "ECLIPSE_INDUCED_POWER_DROP",
        "channels_match": ["eps.solar.power_watts", "eps.battery.soc_percent"],
        "min_match": 2,
        "severity": "WATCH",
        "confidence": 0.75,
        "description": "Normal eclipse power reduction pattern — not a fault",
        "recommendation": "Monitor battery SoC through eclipse. Verify solar recovery after exit.",
        "evidence_template": "Solar power and SoC dropped together — consistent with eclipse",
    },
    {
        "name": "CO2_SCRUBBER_FAILURE",
        "channels_match": ["eclss.atmosphere.co2_mmhg", "eclss.atmosphere.o2_percent",
                           "eclss.atmosphere.humidity_percent"],
        "min_match": 2,
        "severity": "CRITICAL",
        "confidence": 0.90,
        "description": "CO2 scrubber failure: multiple atmosphere channels degrading simultaneously",
        "recommendation": "Activate backup CO2 scrubber. Increase cabin ventilation. Crew to emergency O2.",
        "evidence_template": "Atmosphere channels {channels} all anomalous — scrubber likely failed",
    },
    {
        "name": "CABIN_DEPRESSURIZATION",
        "channels_match": ["eclss.cabin.pressure_psi", "eclss.atmosphere.o2_percent"],
        "min_match": 2,
        "severity": "EMERGENCY",
        "confidence": 0.92,
        "description": "Cabin depressurization: pressure and O2 both dropping",
        "recommendation": "IMMEDIATE: Don emergency suits. Seal suspected leak section. Prepare for emergency landing.",
        "evidence_template": "Pressure AND O2 both anomalous — possible hull breach",
    },
    {
        "name": "ATTITUDE_CONTROL_FAILURE",
        "channels_match": [
            "nav.imu.angular_rate_x_dps", "nav.imu.angular_rate_y_dps", "nav.imu.angular_rate_z_dps",
        ],
        "min_match": 2,
        "severity": "CRITICAL",
        "confidence": 0.88,
        "description": "ADCS failure: multiple IMU axes anomalous simultaneously",
        "recommendation": "Switch to backup attitude sensor. Activate safe-point mode.",
        "evidence_template": "Multiple IMU axes {channels} anomalous — possible reaction wheel failure",
    },
    {
        "name": "THERMAL_RUNAWAY_MULTI_ZONE",
        "channels_match": [
            "thermal.battery_pack.temperature_c",
            "thermal.electronics_bay.temperature_c",
            "thermal.propulsion.temperature_c",
        ],
        "min_match": 2,
        "severity": "CRITICAL",
        "confidence": 0.80,
        "description": "Multi-zone thermal anomaly: possible cooling system failure",
        "recommendation": "Reduce power load on affected zones. Check coolant loop pressure.",
        "evidence_template": "Thermal zones {channels} simultaneously above normal — cooling failure?",
    },
    {
        "name": "POWER_GRID_FAILURE",
        "channels_match": ["eps.battery.soc_percent", "eps.bus.voltage_v", "eps.battery.temperature_c"],
        "min_match": 3,
        "severity": "EMERGENCY",
        "confidence": 0.95,
        "description": "Total power system failure: battery, bus, and temperature all anomalous",
        "recommendation": "EMERGENCY: Activate survival mode. Switch to emergency power bus.",
        "evidence_template": "Complete power system signature: {channels} all flagged",
    },
    {
        "name": "PROPULSION_LEAK",
        "channels_match": [
            "propulsion.tank.propellant_kg",
            "propulsion.tank.pressure_psi",
            "propulsion.tank.temperature_c",
        ],
        "min_match": 2,
        "severity": "CRITICAL",
        "confidence": 0.82,
        "description": "Propellant leak: fuel mass and tank pressure both dropping abnormally",
        "recommendation": "Isolate propulsion feed lines. Check valve seals. Prepare for reduced delta-V budget.",
        "evidence_template": "Propulsion channels {channels} anomalous — possible leak",
    },
    {
        "name": "BEARING_DEGRADATION",
        "channels_match": [
            "nav.imu.angular_rate_x_dps", "nav.imu.angular_rate_y_dps",
            "nav.imu.angular_rate_z_dps",
        ],
        "min_match": 2,
        "severity": "WARNING",
        "confidence": 0.75,
        "description": "Reaction wheel bearing degradation: multiple IMU axes showing unusual patterns",
        "recommendation": "Schedule wheel replacement. Switch to backup ADCS mode if available.",
        "evidence_template": "IMU channels {channels} anomalous — possible bearing wear",
    },
    {
        "name": "COMMS_ANTENNA_MISPOINT",
        "channels_match": [
            "comms.link.signal_dbm", "comms.link.snr_db",
        ],
        "min_match": 2,
        "severity": "WARNING",
        "confidence": 0.78,
        "description": "Communication degradation: signal and SNR both dropping — possible antenna mispoint",
        "recommendation": "Check antenna pointing. Try switching to backup antenna or LGA.",
        "evidence_template": "Comms channels {channels} degraded simultaneously",
    },
    {
        "name": "SOLAR_PARTICLE_EVENT",
        "channels_match": [
            "science.radiation.dose_rate_usv_hr",
            "comms.link.signal_dbm",
            "comms.link.snr_db",
        ],
        "min_match": 2,
        "severity": "EMERGENCY",
        "confidence": 0.88,
        "description": "Solar particle event: radiation spike with communication degradation",
        "recommendation": "IMMEDIATE: Crew to radiation shelter. Switch to low-gain antenna. Protect electronics.",
        "evidence_template": "Radiation + comms degradation: {channels} — likely SPE",
    },
]


class AnomalyCorrelator:
    """Cross-channel anomaly correlator — maps simultaneous anomalies to root causes.

    Subscribes to aria.anomaly.* events and publishes aria.anomaly.correlation
    when multiple channels flag within the same time window.
    """

    def __init__(
        self,
        bus: MessageBus,
        window_s: float = 30.0,
        min_events: int = 2,
    ) -> None:
        self._bus = bus
        self._window_s = window_s  # Correlation window in seconds
        self._min_events = min_events
        self._events: list[AnomalyEvent] = []
        self._last_correlation_time: float = 0.0
        self._correlation_cooldown_s: float = 60.0  # Prevent spam
        self._subscribed = False

    async def start(self) -> None:
        """Subscribe to anomaly events."""
        self._bus.subscribe("aria.anomaly.*", self._on_anomaly)
        self._subscribed = True
        logger.info("correlator.started", window_s=self._window_s)

    async def stop(self) -> None:
        self._subscribed = False

    async def _on_anomaly(self, message: Message) -> None:
        """Process incoming anomaly event."""
        payload = message.payload

        # Extract channel info
        channel_id = payload.get("channel_id", "")
        subsystem = payload.get("subsystem", message.source_agent or "unknown")
        severity = payload.get("severity", "WATCH")
        score = float(payload.get("dsremo_score", payload.get("anomaly_score", 0.5)))

        if not channel_id:
            # Try to infer channel from subsystem + message
            channel_id = f"{subsystem}.unknown"

        event = AnomalyEvent(
            channel_id=channel_id,
            subsystem=subsystem,
            severity=severity,
            score=score,
            source_topic=message.topic,
            payload=payload,
        )
        self._events.append(event)

        # Prune old events outside window
        cutoff = time.time() - self._window_s
        self._events = [e for e in self._events if e.timestamp >= cutoff]

        # Run correlation if we have enough events
        if len(self._events) >= self._min_events:
            await self._correlate()

    async def _correlate(self) -> None:
        """Check current event window against failure signatures."""
        now = time.time()
        if now - self._last_correlation_time < self._correlation_cooldown_s:
            return  # Cooldown: don't spam correlation events

        active_channels = {e.channel_id for e in self._events}
        active_subsystems = {e.subsystem for e in self._events}

        for sig in FAILURE_SIGNATURES:
            matched = [c for c in sig["channels_match"] if c in active_channels]
            if len(matched) >= sig["min_match"]:
                result = CorrelationResult(
                    root_cause=sig["name"],
                    confidence=sig["confidence"],
                    involved_channels=matched,
                    involved_subsystems=list(active_subsystems & set(
                        c.split(".")[0] for c in matched
                    )),
                    severity=sig["severity"],
                    description=sig["description"],
                    recommendation=sig["recommendation"],
                    evidence=[
                        sig["evidence_template"].format(
                            channels=matched,
                            window=self._window_s,
                        )
                    ],
                )

                await self._publish_correlation(result)
                self._last_correlation_time = now
                # Only publish the highest-priority correlation
                break

    async def _publish_correlation(self, result: CorrelationResult) -> None:
        """Publish correlation result to the bus."""
        priority = {
            "EMERGENCY": EventPriority.P0_EMERGENCY,
            "CRITICAL": EventPriority.P1_CRITICAL,
            "WARNING": EventPriority.P2_WARNING,
            "WATCH": EventPriority.P3_ROUTINE,
        }.get(result.severity, EventPriority.P2_WARNING)

        await self._bus.publish(
            Message(
                topic="aria.anomaly.correlation",
                payload={
                    "root_cause": result.root_cause,
                    "confidence": result.confidence,
                    "severity": result.severity,
                    "description": result.description,
                    "recommendation": result.recommendation,
                    "involved_channels": result.involved_channels,
                    "involved_subsystems": result.involved_subsystems,
                    "evidence": result.evidence,
                    "window_s": self._window_s,
                    "event_count": len(self._events),
                },
                priority=priority,
                source_agent="anomaly_correlator",
            )
        )

        logger.warning(
            "correlator.root_cause_identified",
            root_cause=result.root_cause,
            confidence=result.confidence,
            severity=result.severity,
            channels=result.involved_channels,
        )

    def get_recent_events(self, window_s: float | None = None) -> list[AnomalyEvent]:
        """Get recent anomaly events within the correlation window."""
        cutoff = time.time() - (window_s or self._window_s)
        return [e for e in self._events if e.timestamp >= cutoff]
