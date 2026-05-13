"""Scenario scripting engine for timed fault injection.

Define timed sequences of events — faults, anomalies, nominal telemetry —
and replay them through the MessageBus at real-time or accelerated speed.

Usage:
    engine = ScenarioEngine(bus, APOLLO_13_SCENARIO)
    await engine.run(time_scale=10.0)  # 10x speed
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioEvent:
    """A single timed event in a scenario script."""

    time_offset_s: float  # Seconds from scenario start
    topic: str  # MessageBus topic to publish on
    payload: dict[str, Any]  # Event payload
    description: str = ""  # Human-readable description
    priority: EventPriority = EventPriority.P2_WARNING


@dataclass
class ScenarioScript:
    """An ordered collection of timed events forming a scenario."""

    name: str
    description: str
    events: list[ScenarioEvent] = field(default_factory=list)
    total_duration_s: float = 0.0

    def __post_init__(self) -> None:
        # Auto-compute duration from last event if not set
        if self.events and self.total_duration_s <= 0.0:
            self.total_duration_s = max(e.time_offset_s for e in self.events) + 60.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ScenarioEngine:
    """Executes a ScenarioScript by publishing events to a MessageBus at the
    correct (optionally accelerated) times.

    Args:
        bus: The MessageBus to publish events on.
        script: The ScenarioScript to execute.
    """

    def __init__(self, bus: MessageBus, script: ScenarioScript) -> None:
        self._bus = bus
        self._script = script
        self._fired: list[ScenarioEvent] = []
        self._stopped = False
        self._running = False

    @property
    def script(self) -> ScenarioScript:
        return self._script

    @property
    def fired_events(self) -> list[ScenarioEvent]:
        """Events that have been published so far."""
        return list(self._fired)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def progress(self) -> float:
        """Fraction of events that have fired (0.0 to 1.0)."""
        total = len(self._script.events)
        if total == 0:
            return 1.0
        return len(self._fired) / total

    def stop(self) -> None:
        """Request the scenario to stop after the current sleep."""
        self._stopped = True

    async def run(self, time_scale: float = 1.0) -> None:
        """Execute the scenario.

        Args:
            time_scale: Speed multiplier. 1.0 = real-time, 10.0 = 10x faster.
                        Must be > 0.
        """
        if time_scale <= 0:
            raise ValueError("time_scale must be positive")

        self._stopped = False
        self._running = True
        self._fired = []

        # Sort events by time offset
        sorted_events = sorted(self._script.events, key=lambda e: e.time_offset_s)

        elapsed = 0.0

        try:
            for event in sorted_events:
                if self._stopped:
                    break

                # Wait until this event's time
                wait = (event.time_offset_s - elapsed) / time_scale
                if wait > 0:
                    try:
                        await asyncio.wait_for(self._wait_for_stop(wait), timeout=wait)
                        # If _wait_for_stop returned, we were stopped
                        if self._stopped:
                            break
                    except asyncio.TimeoutError:
                        # Normal — the sleep completed
                        pass

                if self._stopped:
                    break

                elapsed = event.time_offset_s

                # Publish to bus
                message = Message(
                    topic=event.topic,
                    payload={
                        **event.payload,
                        "_scenario": self._script.name,
                        "_description": event.description,
                        "_time_offset_s": event.time_offset_s,
                    },
                    priority=event.priority,
                    source_agent="scenario_engine",
                )
                await self._bus.publish(message)
                self._fired.append(event)
        finally:
            self._running = False

    async def _wait_for_stop(self, duration: float) -> None:
        """Sleep that can be interrupted by stop()."""
        end = asyncio.get_event_loop().time() + duration
        while not self._stopped:
            remaining = end - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            await asyncio.sleep(min(remaining, 0.05))


# ---------------------------------------------------------------------------
# Pre-built scenarios
# ---------------------------------------------------------------------------

APOLLO_13_SCENARIO = ScenarioScript(
    name="apollo_13",
    description="Recreation of Apollo 13 O2 tank failure cascade",
    events=[
        ScenarioEvent(
            time_offset_s=0,
            topic="aria.scenario.start",
            payload={"scenario": "apollo_13"},
            description="Scenario begins — nominal cruise",
            priority=EventPriority.P3_ROUTINE,
        ),
        ScenarioEvent(
            time_offset_s=30 * 60,
            topic="aria.fault.electrical",
            payload={"subsystem": "power", "component": "o2_tank_2_heater", "fault": "short_circuit"},
            description="O2 Tank 2 heater short circuit",
            priority=EventPriority.P1_CRITICAL,
        ),
        ScenarioEvent(
            time_offset_s=30 * 60 + 5,
            topic="aria.fault.explosion",
            payload={"subsystem": "eclss", "component": "o2_tank_2", "fault": "rupture", "pressure_drop_psi": 900},
            description="O2 Tank 2 rupture — loss of cryogenic oxygen",
            priority=EventPriority.P0_EMERGENCY,
        ),
        ScenarioEvent(
            time_offset_s=31 * 60,
            topic="aria.anomaly.detected",
            payload={"subsystem": "power", "component": "fuel_cell_1", "metric": "voltage", "value": 0.0},
            description="Fuel Cell 1 offline due to O2 starvation",
            priority=EventPriority.P0_EMERGENCY,
        ),
        ScenarioEvent(
            time_offset_s=35 * 60,
            topic="aria.anomaly.detected",
            payload={"subsystem": "power", "component": "fuel_cell_3", "metric": "voltage", "value": 0.0},
            description="Fuel Cell 3 offline — single fuel cell remaining",
            priority=EventPriority.P0_EMERGENCY,
        ),
        ScenarioEvent(
            time_offset_s=45 * 60,
            topic="aria.command.power_down",
            payload={"subsystem": "power", "action": "emergency_powerdown", "target_watts": 120},
            description="Emergency power-down to 120W survival mode",
            priority=EventPriority.P0_EMERGENCY,
        ),
    ],
)

SOLAR_STORM_SCENARIO = ScenarioScript(
    name="solar_storm",
    description="Coronal mass ejection impact on LEO station",
    events=[
        ScenarioEvent(
            time_offset_s=0,
            topic="aria.scenario.start",
            payload={"scenario": "solar_storm"},
            description="Scenario begins — solar storm warning received",
            priority=EventPriority.P3_ROUTINE,
        ),
        ScenarioEvent(
            time_offset_s=10 * 60,
            topic="aria.warning.radiation",
            payload={"subsystem": "environment", "component": "rad_sensor_1", "dose_rate_mSv_hr": 0.5},
            description="Elevated radiation — crew advisory",
            priority=EventPriority.P2_WARNING,
        ),
        ScenarioEvent(
            time_offset_s=20 * 60,
            topic="aria.fault.radiation",
            payload={"subsystem": "environment", "component": "rad_sensor_1", "dose_rate_mSv_hr": 5.0},
            description="Radiation spike — shelter in storm shelter",
            priority=EventPriority.P0_EMERGENCY,
        ),
        ScenarioEvent(
            time_offset_s=25 * 60,
            topic="aria.fault.comms",
            payload={"subsystem": "comms", "component": "s_band_antenna", "fault": "signal_loss"},
            description="S-band comms lost due to ionospheric disruption",
            priority=EventPriority.P1_CRITICAL,
        ),
        ScenarioEvent(
            time_offset_s=40 * 60,
            topic="aria.anomaly.detected",
            payload={"subsystem": "power", "component": "solar_array_1", "metric": "output_watts", "value": 800, "nominal": 4000},
            description="Solar array degradation from radiation damage",
            priority=EventPriority.P1_CRITICAL,
        ),
        ScenarioEvent(
            time_offset_s=60 * 60,
            topic="aria.info.radiation_clear",
            payload={"subsystem": "environment", "component": "rad_sensor_1", "dose_rate_mSv_hr": 0.02},
            description="Radiation levels returning to nominal",
            priority=EventPriority.P3_ROUTINE,
        ),
    ],
)

NORMAL_ORBIT_SCENARIO = ScenarioScript(
    name="normal_orbit",
    description="Nominal LEO orbit — routine telemetry, no faults",
    events=[
        ScenarioEvent(
            time_offset_s=0,
            topic="aria.scenario.start",
            payload={"scenario": "normal_orbit"},
            description="Scenario begins — nominal orbit",
            priority=EventPriority.P3_ROUTINE,
        ),
        ScenarioEvent(
            time_offset_s=5 * 60,
            topic="aria.telemetry.summary",
            payload={"subsystem": "eclss", "co2_ppm": 400, "o2_pct": 20.9, "temp_c": 22.0, "humidity_pct": 45},
            description="ECLSS nominal — 5 minute summary",
            priority=EventPriority.P4_BULK,
        ),
        ScenarioEvent(
            time_offset_s=10 * 60,
            topic="aria.telemetry.summary",
            payload={"subsystem": "power", "solar_array_watts": 4200, "battery_soc_pct": 92, "bus_voltage": 28.3},
            description="Power nominal — 10 minute summary",
            priority=EventPriority.P4_BULK,
        ),
        ScenarioEvent(
            time_offset_s=45 * 60,
            topic="aria.navigation.orbit_update",
            payload={"subsystem": "navigation", "altitude_km": 408.2, "inclination_deg": 51.64, "period_min": 92.7},
            description="Orbit determination update — nominal",
            priority=EventPriority.P4_BULK,
        ),
        ScenarioEvent(
            time_offset_s=90 * 60,
            topic="aria.scenario.end",
            payload={"scenario": "normal_orbit", "status": "complete"},
            description="One full orbit completed — scenario end",
            priority=EventPriority.P3_ROUTINE,
        ),
    ],
)
