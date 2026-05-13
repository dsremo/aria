"""Dsremo Channel Mapper — converts any ARIA sensor message to Dsremo channels.

Every numeric value from every sensor is a telemetry channel that Dsremo
can monitor with its 12-detector ensemble. This module is the bridge.

Architecture:
  - Each sensor topic → one or more channel_id strings
  - Each channel_id carries exactly one numeric value
  - Dsremo treats these as independent time-series streams

Channel naming convention:
  <subsystem>.<component>.<metric>
  e.g. "eps.battery.soc_percent", "thermal.battery_pack.temperature_c"

This allows Dsremo to:
  1. Detect anomalies per-channel (CUSUM, EWMA, Z-score, GMM, BOCPD, etc.)
  2. Correlate across channels (e.g., battery voltage + SoC drop together)
  3. Provide contextual scoring that each agent can use to augment its own logic
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TelemetryReading:
    """A single numeric telemetry reading for Dsremo ingestion."""

    satellite_id: str
    channel_id: str
    value: float
    timestamp: str = ""
    subsystem: str = ""   # Source subsystem for correlation
    source_topic: str = ""  # Original bus topic


# ---------------------------------------------------------------------------
# Sensor topic → channel extraction rules
# ---------------------------------------------------------------------------
# Each entry: (topic_prefix, extraction_fn)
# extraction_fn(payload) -> list[TelemetryReading]

def _extract_power_battery(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    if "soc_percent" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eps.battery.soc_percent",
            value=float(payload["soc_percent"]), subsystem="power", source_topic=topic,
        ))
    if "temperature_c" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eps.battery.temperature_c",
            value=float(payload["temperature_c"]), subsystem="power", source_topic=topic,
        ))
    if "voltage_v" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eps.battery.voltage_v",
            value=float(payload["voltage_v"]), subsystem="power", source_topic=topic,
        ))
    return readings


def _extract_power_solar(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    if "power_watts" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eps.solar.power_watts",
            value=float(payload["power_watts"]), subsystem="power", source_topic=topic,
        ))
    return readings


def _extract_power_bus(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    if "voltage_v" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eps.bus.voltage_v",
            value=float(payload["voltage_v"]), subsystem="power", source_topic=topic,
        ))
    return readings


def _extract_thermal(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    """Extract thermal readings — zone name is in the topic."""
    zone = topic.split(".")[-1]  # e.g. "battery_pack" from "aria.sensor.thermal.battery_pack"
    readings = []
    if "temperature_c" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id=f"thermal.{zone}.temperature_c",
            value=float(payload["temperature_c"]), subsystem="thermal", source_topic=topic,
        ))
    if "heater_on" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id=f"thermal.{zone}.heater_state",
            value=1.0 if payload["heater_on"] else 0.0, subsystem="thermal", source_topic=topic,
        ))
    return readings


def _extract_eclss_atmosphere(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "o2_percent": "eclss.atmosphere.o2_percent",
        "co2_mmhg": "eclss.atmosphere.co2_mmhg",
        "humidity_percent": "eclss.atmosphere.humidity_percent",
        "temperature_c": "eclss.atmosphere.temperature_c",
        "pressure_psi": "eclss.atmosphere.pressure_psi",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="eclss", source_topic=topic,
            ))
    return readings


def _extract_eclss_pressure(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    if "pressure_psi" in payload:
        readings.append(TelemetryReading(
            satellite_id=sat_id, channel_id="eclss.cabin.pressure_psi",
            value=float(payload["pressure_psi"]), subsystem="eclss", source_topic=topic,
        ))
    return readings


def _extract_nav_gps(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "altitude_km": "nav.gps.altitude_km",
        "velocity_ms": "nav.gps.velocity_ms",
        "latitude_deg": "nav.gps.latitude_deg",
        "longitude_deg": "nav.gps.longitude_deg",
        "satellites": "nav.gps.satellites",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="navigation", source_topic=topic,
            ))
    return readings


def _extract_nav_imu(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "angular_rate_x_dps": "nav.imu.angular_rate_x_dps",
        "angular_rate_y_dps": "nav.imu.angular_rate_y_dps",
        "angular_rate_z_dps": "nav.imu.angular_rate_z_dps",
        "accel_x_ms2": "nav.imu.accel_x_ms2",
        "accel_y_ms2": "nav.imu.accel_y_ms2",
        "accel_z_ms2": "nav.imu.accel_z_ms2",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="navigation", source_topic=topic,
            ))
    return readings


def _extract_nav_star_tracker(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    if "quaternion" in payload:
        q = payload["quaternion"]
        if isinstance(q, (list, tuple)) and len(q) == 4:
            for i, component in enumerate(["w", "x", "y", "z"]):
                readings.append(TelemetryReading(
                    satellite_id=sat_id, channel_id=f"nav.star_tracker.q_{component}",
                    value=float(q[i]), subsystem="navigation", source_topic=topic,
                ))
    return readings


# ---------------------------------------------------------------------------
# Channel Mapper Class
# ---------------------------------------------------------------------------

def _extract_propulsion_tank(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "propellant_kg": "propulsion.tank.propellant_kg",
        "pressure_psi": "propulsion.tank.pressure_psi",
        "temperature_c": "propulsion.tank.temperature_c",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="propulsion", source_topic=topic,
            ))
    return readings


def _extract_comms_link(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "signal_dbm": "comms.link.signal_dbm",
        "snr_db": "comms.link.snr_db",
        "data_rate_kbps": "comms.link.data_rate_kbps",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="comms", source_topic=topic,
            ))
    return readings


def _extract_science_radiation(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    readings = []
    mapping = {
        "dose_rate_usv_hr": "science.radiation.dose_rate_usv_hr",
        "cumulative_dose_msv": "science.radiation.cumulative_dose_msv",
    }
    for key, channel_id in mapping.items():
        if key in payload:
            readings.append(TelemetryReading(
                satellite_id=sat_id, channel_id=channel_id,
                value=float(payload[key]), subsystem="science", source_topic=topic,
            ))
    return readings


# Topic prefix → extractor function
_EXTRACTORS: list[tuple[str, Any]] = [
    ("aria.sensor.power.battery", _extract_power_battery),
    ("aria.sensor.power.solar", _extract_power_solar),
    ("aria.sensor.power.bus", _extract_power_bus),
    ("aria.sensor.thermal.", _extract_thermal),
    ("aria.sensor.eclss.atmosphere", _extract_eclss_atmosphere),
    ("aria.sensor.eclss.pressure", _extract_eclss_pressure),
    ("aria.sensor.nav.gps", _extract_nav_gps),
    ("aria.sensor.nav.imu", _extract_nav_imu),
    ("aria.sensor.nav.star_tracker", _extract_nav_star_tracker),
    ("aria.sensor.propulsion.tank", _extract_propulsion_tank),
    ("aria.sensor.comms.link", _extract_comms_link),
    ("aria.sensor.science.radiation", _extract_science_radiation),
]


def _extract_medical_vitals(payload: dict[str, Any], sat_id: str, topic: str) -> list[TelemetryReading]:
    """Extract crew vital sign readings for Dsremo monitoring."""
    crew_id = payload.get("crew_id", topic.split(".")[-1])
    readings = []
    vitals = ["heart_rate_bpm", "spo2_percent", "temperature_c", "bp_systolic", "respiratory_rate"]
    for vital in vitals:
        if vital in payload and isinstance(payload[vital], (int, float)):
            readings.append(TelemetryReading(
                satellite_id=sat_id,
                channel_id=f"medical.{crew_id}.{vital}",
                value=float(payload[vital]),
                subsystem="medical",
                source_topic=topic,
            ))
    return readings


# Add medical extractor to the list (defined after function to avoid forward reference)
_EXTRACTORS.append(("aria.sensor.medical.vitals.", _extract_medical_vitals))


class DsremoChannelMapper:
    """Maps any ARIA sensor message to one or more Dsremo TelemetryReadings.

    Usage:
        mapper = DsremoChannelMapper(satellite_id="sat-01")
        readings = mapper.extract(topic="aria.sensor.eclss.atmosphere", payload={...})
        for r in readings:
            await dsremo_ingest(r)
    """

    def __init__(self, satellite_id: str = "sat-01") -> None:
        self._satellite_id = satellite_id

    def extract(self, topic: str, payload: dict[str, Any]) -> list[TelemetryReading]:
        """Extract all Dsremo readings from a sensor message.

        Returns empty list if the topic is unknown or no numeric values are found.
        """
        # Try specialized extractors first
        for prefix, extractor in _EXTRACTORS:
            if topic.startswith(prefix):
                readings = extractor(payload, self._satellite_id, topic)
                if readings:
                    return readings
                # If specialized extractor returns empty, fall through to generic

        # Generic extractor: pull all numeric values using dot-path channel naming
        return self._generic_extract(topic, payload)

    def _generic_extract(self, topic: str, payload: dict[str, Any]) -> list[TelemetryReading]:
        """Generic fallback: convert any numeric payload field to a channel."""
        # Convert topic to channel prefix: "aria.sensor.foo.bar" → "foo.bar"
        parts = topic.split(".")
        if len(parts) >= 3 and parts[0] == "aria" and parts[1] == "sensor":
            channel_prefix = ".".join(parts[2:])
            subsystem = parts[2] if len(parts) > 2 else "unknown"
        else:
            channel_prefix = topic.replace(".", "_")
            subsystem = "unknown"

        readings = []
        for key, value in payload.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                import math
                if not math.isnan(value) and not math.isinf(value):
                    readings.append(TelemetryReading(
                        satellite_id=self._satellite_id,
                        channel_id=f"{channel_prefix}.{key}",
                        value=float(value),
                        subsystem=subsystem,
                        source_topic=topic,
                    ))
        return readings

    def extract_single(
        self,
        subsystem: str,
        component: str,
        metric: str,
        value: float,
    ) -> TelemetryReading:
        """Create a reading from explicit parts. For use inside agents."""
        return TelemetryReading(
            satellite_id=self._satellite_id,
            channel_id=f"{subsystem}.{component}.{metric}",
            value=value,
            subsystem=subsystem,
            source_topic=f"aria.agent.{subsystem}",
        )
