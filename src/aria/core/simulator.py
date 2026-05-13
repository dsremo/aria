"""Simulated Sensor Framework — generates realistic telemetry for testing.

Produces sensor readings on the message bus so ARIA can be tested
without real hardware. Each sensor generates data at its configured rate
with configurable noise and fault injection.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()


@dataclass
class SimulatedSensor:
    """Configuration for a simulated sensor."""

    topic: str
    base_value: float
    noise_std: float = 0.01
    drift_rate: float = 0.0  # Per-second drift
    orbital_amplitude: float = 0.0  # Sinusoidal variation (orbital period)
    orbital_period_s: float = 5400.0  # 90 min LEO orbit
    sample_interval_s: float = 1.0
    unit: str = ""
    payload_key: str = "value"
    extra_payload: dict[str, Any] = field(default_factory=dict)


class SensorSimulator:
    """Generates simulated spacecraft telemetry on the ARIA message bus.

    Provides realistic data for:
      - Power: battery SoC, solar power, bus voltage
      - Thermal: zone temperatures
      - Navigation: GPS, IMU
      - ECLSS: O2, CO2, pressure
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._sensors: list[SimulatedSensor] = []
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._start_time = time.time()
        self._fault_injections: dict[str, dict[str, Any]] = {}

    def add_sensor(self, sensor: SimulatedSensor) -> None:
        self._sensors.append(sensor)

    def add_default_sensors(self) -> None:
        """Add a standard set of spacecraft sensors."""
        self._sensors.extend([
            # Power
            SimulatedSensor(
                topic="aria.sensor.power.battery",
                base_value=85.0, noise_std=0.2, drift_rate=-0.001,
                payload_key="soc_percent",
                extra_payload={"temperature_c": 25.0},
            ),
            SimulatedSensor(
                topic="aria.sensor.power.solar",
                base_value=2500.0, noise_std=10.0,
                orbital_amplitude=2500.0, orbital_period_s=5400.0,
                payload_key="power_watts",
            ),
            SimulatedSensor(
                topic="aria.sensor.power.bus",
                base_value=28.0, noise_std=0.05,
                payload_key="voltage_v",
            ),

            # Thermal
            SimulatedSensor(
                topic="aria.sensor.thermal.battery_pack",
                base_value=22.0, noise_std=0.3,
                orbital_amplitude=3.0, orbital_period_s=5400.0,
                payload_key="temperature_c",
            ),
            SimulatedSensor(
                topic="aria.sensor.thermal.crew_cabin",
                base_value=22.0, noise_std=0.1,
                payload_key="temperature_c",
            ),
            SimulatedSensor(
                topic="aria.sensor.thermal.electronics_bay",
                base_value=30.0, noise_std=0.5,
                payload_key="temperature_c",
            ),

            # Navigation
            SimulatedSensor(
                topic="aria.sensor.nav.gps",
                base_value=400.0, noise_std=0.01,
                payload_key="altitude_km",
                extra_payload={
                    "fix": True, "satellites": 8,
                    "latitude_deg": 0.0, "longitude_deg": 0.0,
                    "velocity_ms": 7660.0,
                },
                sample_interval_s=1.0,
            ),
            SimulatedSensor(
                topic="aria.sensor.nav.imu",
                base_value=0.0, noise_std=0.02,
                payload_key="angular_rate_x_dps",
                extra_payload={"angular_rate_y_dps": 0.0, "angular_rate_z_dps": 0.0},
                sample_interval_s=0.5,
            ),

            # ECLSS
            SimulatedSensor(
                topic="aria.sensor.eclss.atmosphere",
                base_value=20.9, noise_std=0.02,
                payload_key="o2_percent",
                extra_payload={"co2_mmhg": 2.5, "humidity_percent": 45.0, "temperature_c": 22.0},
                sample_interval_s=5.0,
            ),
            SimulatedSensor(
                topic="aria.sensor.eclss.pressure",
                base_value=14.7, noise_std=0.005,
                payload_key="pressure_psi",
                sample_interval_s=2.0,
            ),

            # Propulsion
            SimulatedSensor(
                topic="aria.sensor.propulsion.tank",
                base_value=95.0, noise_std=0.01, drift_rate=-0.0001,
                payload_key="propellant_kg",
                extra_payload={"pressure_psi": 250.0, "temperature_c": 20.0},
                sample_interval_s=10.0,
            ),

            # Communications
            SimulatedSensor(
                topic="aria.sensor.comms.link",
                base_value=-85.0, noise_std=2.0,
                payload_key="signal_dbm",
                extra_payload={"snr_db": 15.0, "ber": 1e-9, "data_rate_kbps": 256.0},
                sample_interval_s=5.0,
            ),

            # Science / Radiation
            SimulatedSensor(
                topic="aria.sensor.science.radiation",
                base_value=0.5, noise_std=0.05,
                payload_key="dose_rate_usv_hr",
                extra_payload={"cumulative_dose_msv": 25.0},
                sample_interval_s=10.0,
            ),

            # Medical / Crew vitals
            SimulatedSensor(
                topic="aria.sensor.medical.vitals.commander",
                base_value=72.0, noise_std=3.0,
                payload_key="heart_rate_bpm",
                extra_payload={
                    "crew_id": "commander", "spo2_percent": 98.0,
                    "temperature_c": 36.8, "bp_systolic": 120.0,
                    "respiratory_rate": 16.0,
                },
                sample_interval_s=10.0,
            ),

        ])

    def inject_fault(self, sensor_topic: str, fault_type: str, **kwargs: Any) -> None:
        """Inject a fault into a simulated sensor.

        Fault types:
          - "drift": add constant drift_rate
          - "spike": random spikes of given magnitude
          - "stuck": freeze at current value
          - "noise": increase noise
          - "offset": add constant offset
        """
        self._fault_injections[sensor_topic] = {"type": fault_type, **kwargs}
        logger.info("simulator.fault_injected", topic=sensor_topic, fault=fault_type)

    def clear_fault(self, sensor_topic: str) -> None:
        self._fault_injections.pop(sensor_topic, None)

    async def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        for sensor in self._sensors:
            task = asyncio.create_task(self._sensor_loop(sensor))
            self._tasks.append(task)
        logger.info("simulator.started", sensors=len(self._sensors))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("simulator.stopped")

    async def _sensor_loop(self, sensor: SimulatedSensor) -> None:
        while self._running:
            try:
                value = self._generate_value(sensor)
                payload = {sensor.payload_key: value, **sensor.extra_payload}

                await self._bus.publish(
                    Message(
                        topic=sensor.topic,
                        payload=payload,
                        priority=EventPriority.P4_BULK,
                        source_agent="simulator",
                    )
                )
                await asyncio.sleep(sensor.sample_interval_s)
            except asyncio.CancelledError:
                break

    def _generate_value(self, sensor: SimulatedSensor) -> float:
        elapsed = time.time() - self._start_time
        value = sensor.base_value

        # Orbital variation
        if sensor.orbital_amplitude > 0:
            phase = 2 * math.pi * elapsed / sensor.orbital_period_s
            # Solar power: clip to 0 during "eclipse" (half orbit)
            if "solar" in sensor.topic:
                value = max(0.0, sensor.base_value * (0.5 + 0.5 * math.sin(phase)))
            else:
                value += sensor.orbital_amplitude * math.sin(phase)

        # Drift
        value += sensor.drift_rate * elapsed

        # Noise
        value += random.gauss(0, sensor.noise_std)

        # Fault injection
        fault = self._fault_injections.get(sensor.topic)
        if fault:
            ft = fault["type"]
            if ft == "offset":
                value += fault.get("offset", 10.0)
            elif ft == "spike" and random.random() < fault.get("probability", 0.1):
                value += fault.get("magnitude", 50.0)
            elif ft == "stuck":
                value = fault.get("stuck_value", sensor.base_value)
            elif ft == "noise":
                value += random.gauss(0, fault.get("extra_noise", sensor.noise_std * 5))
            elif ft == "drift":
                value += fault.get("drift_rate", 0.1) * elapsed

        return round(value, 4)
