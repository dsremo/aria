"""OpenC3/COSMOS Command and Telemetry Bridge for ARIA.

Integrates ARIA with the OpenC3 COSMOS command-and-control system, mapping
ARIA bus commands and telemetry to the OpenC3 target/packet model.

OpenC3 concepts mapped to ARIA:
  - **Target**: ARIA spacecraft (target name ``ARIA``)
  - **Commands**: Spacecraft operations routed through the ARIA message bus
  - **Telemetry packets**: ARIA sensor data formatted as OpenC3 telemetry items
  - **REST API**: OpenC3's ``cmd-tlm-api`` at ``/api`` (JSON-RPC over HTTP)

The bridge operates in two modes:
  1. **Live mode** — connects to a running OpenC3 instance, forwards commands
     from OpenC3 to the ARIA bus, and publishes ARIA telemetry back.
  2. **Mock mode** — no OpenC3 server required; command/telemetry round-trips
     are handled in-process for testing and development.

Command definitions follow the OpenC3 ``COMMAND`` format (BIG_ENDIAN, with
typed PARAMETER fields). Telemetry definitions follow the ``TELEMETRY`` format
with APPEND_ITEM fields.

References:
  - https://docs.openc3.com/docs
  - OpenC3 Python scripting API: cmd(), tlm(), inject_tlm()
  - OpenC3 REST API: POST /api with JSON-RPC body
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenC3Config:
    """Configuration for the OpenC3/COSMOS bridge."""

    # OpenC3 API connection (used in live mode)
    api_hostname: str = "localhost"
    api_port: int = 2900
    api_schema: str = "http"
    api_password: str = ""
    api_scope: str = "DEFAULT"

    # ARIA target identity within OpenC3
    target_name: str = "ARIA"
    target_description: str = "ARIA Autonomous Spacecraft AI"

    # Telemetry publishing interval (seconds)
    telemetry_publish_interval: float = 1.0

    # Mock mode: bypass OpenC3 server entirely
    mock_mode: bool = True

    @property
    def api_url(self) -> str:
        return f"{self.api_schema}://{self.api_hostname}:{self.api_port}"


# ---------------------------------------------------------------------------
# OpenC3 data type enumeration
# ---------------------------------------------------------------------------

class ParamType(Enum):
    """OpenC3 parameter/item data types."""
    UINT = "UINT"
    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    BLOCK = "BLOCK"
    DERIVED = "DERIVED"


class Endianness(Enum):
    """Byte ordering."""
    BIG_ENDIAN = "BIG_ENDIAN"
    LITTLE_ENDIAN = "LITTLE_ENDIAN"


# ---------------------------------------------------------------------------
# Command parameter definition
# ---------------------------------------------------------------------------

@dataclass
class CommandParameter:
    """A single parameter in an OpenC3 command definition.

    Mirrors the OpenC3 ``PARAMETER`` keyword:
      PARAMETER <name> <bit_offset> <bit_size> <type> <min> <max> <default> <description>
    """
    name: str
    bit_size: int
    param_type: ParamType
    default: Any
    description: str
    minimum: float | int | None = None
    maximum: float | int | None = None
    states: dict[str, Any] | None = None
    units: str = ""
    required: bool = False
    hazardous: str = ""

    def to_openc3_definition(self, bit_offset: int) -> str:
        """Render this parameter as an OpenC3 PARAMETER line."""
        min_str = str(self.minimum) if self.minimum is not None else "MIN"
        max_str = str(self.maximum) if self.maximum is not None else "MAX"
        default_str = json.dumps(self.default) if isinstance(self.default, str) else str(self.default)

        line = (
            f"  PARAMETER {self.name} {bit_offset} {self.bit_size} "
            f"{self.param_type.value} {min_str} {max_str} {default_str} "
            f'"{self.description}"'
        )
        parts = [line]
        if self.required:
            parts.append("    REQUIRED")
        if self.units:
            parts.append(f"    UNITS {self.units} {self.units[0]}")
        if self.states:
            for state_name, state_val in self.states.items():
                haz = " HAZARDOUS" if state_name == self.hazardous else ""
                parts.append(f"    STATE {state_name} {state_val}{haz}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Command definition
# ---------------------------------------------------------------------------

@dataclass
class CommandDefinition:
    """Full OpenC3 command definition for an ARIA command.

    Mirrors the OpenC3 ``COMMAND`` keyword:
      COMMAND <target> <name> <endianness> "<description>"
    """
    name: str
    description: str
    parameters: list[CommandParameter] = field(default_factory=list)
    hazardous: str = ""
    endianness: Endianness = Endianness.BIG_ENDIAN
    disabled: bool = False

    # Mapping to ARIA bus
    bus_topic: str = ""
    priority: EventPriority = EventPriority.P1_CRITICAL

    def to_openc3_definition(self, target_name: str = "ARIA") -> str:
        """Render the full OpenC3 command definition text."""
        parts = [
            f'COMMAND {target_name} {self.name} {self.endianness.value} '
            f'"{self.description}"'
        ]
        if self.hazardous:
            parts.append(f'  HAZARDOUS "{self.hazardous}"')
        if self.disabled:
            parts.append("  DISABLE_MESSAGES")

        bit_offset = 0
        for param in self.parameters:
            parts.append(param.to_openc3_definition(bit_offset))
            bit_offset += param.bit_size

        return "\n".join(parts)

    @property
    def total_bit_size(self) -> int:
        return sum(p.bit_size for p in self.parameters)


# ---------------------------------------------------------------------------
# Telemetry item definition
# ---------------------------------------------------------------------------

@dataclass
class TelemetryItem:
    """A single item in an OpenC3 telemetry packet.

    Mirrors the OpenC3 ``APPEND_ITEM`` keyword:
      APPEND_ITEM <name> <bit_size> <type> "<description>"
    """
    name: str
    bit_size: int
    item_type: ParamType
    description: str
    units: str = ""
    format_string: str = ""
    limits_enabled: bool = False
    limits: dict[str, tuple] | None = None

    def to_openc3_definition(self) -> str:
        """Render as an OpenC3 APPEND_ITEM line."""
        parts = [
            f'  APPEND_ITEM {self.name} {self.bit_size} '
            f'{self.item_type.value} "{self.description}"'
        ]
        if self.units:
            parts.append(f"    UNITS {self.units} {self.units[0]}")
        if self.format_string:
            parts.append(f'    FORMAT_STRING "{self.format_string}"')
        if self.limits_enabled and self.limits:
            for limit_set, vals in self.limits.items():
                limits_str = " ".join(str(v) for v in vals)
                parts.append(f"    LIMITS {limit_set} 1 ENABLED {limits_str}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Telemetry packet definition
# ---------------------------------------------------------------------------

@dataclass
class TelemetryPacketDefinition:
    """Full OpenC3 telemetry packet definition.

    Mirrors the OpenC3 ``TELEMETRY`` keyword:
      TELEMETRY <target> <name> <endianness> "<description>"
    """
    name: str
    description: str
    items: list[TelemetryItem] = field(default_factory=list)
    endianness: Endianness = Endianness.BIG_ENDIAN

    # Mapping from ARIA bus
    bus_topics: list[str] = field(default_factory=list)

    def to_openc3_definition(self, target_name: str = "ARIA") -> str:
        """Render as OpenC3 telemetry definition text."""
        parts = [
            f'TELEMETRY {target_name} {self.name} {self.endianness.value} '
            f'"{self.description}"'
        ]
        for item in self.items:
            parts.append(item.to_openc3_definition())
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# ARIA command definitions for OpenC3
# ---------------------------------------------------------------------------

def _build_aria_commands() -> list[CommandDefinition]:
    """Define all ARIA commands that OpenC3 can issue."""
    return [
        CommandDefinition(
            name="SAFE_MODE",
            description="Transition ARIA spacecraft to safe mode — minimal power, "
                        "sun-pointing attitude, non-essential systems off",
            # Wiring audit Pass 4 (F7.12) — renamed to match the
            # ``aria.command.<subsystem>.<verb>`` shape that PowerAgent
            # already subscribes to (``aria.command.power.*``). The old
            # top-level ``aria.command.safe_mode`` had no agent handler.
            bus_topic="aria.command.power.safe_mode",
            priority=EventPriority.P0_EMERGENCY,
            hazardous="Entering safe mode halts all active operations",
            parameters=[
                CommandParameter(
                    name="REASON",
                    bit_size=256,
                    param_type=ParamType.STRING,
                    default="operator_commanded",
                    description="Reason for safe mode entry",
                ),
                CommandParameter(
                    name="SHED_LEVEL",
                    bit_size=8,
                    param_type=ParamType.UINT,
                    default=3,
                    minimum=0,
                    maximum=5,
                    description="Load shedding aggressiveness (0=minimal, 5=survival)",
                    states={
                        "MINIMAL": 0,
                        "MODERATE": 2,
                        "AGGRESSIVE": 3,
                        "SURVIVAL": 5,
                    },
                ),
                CommandParameter(
                    name="DURATION_S",
                    bit_size=32,
                    param_type=ParamType.UINT,
                    default=0,
                    minimum=0,
                    maximum=86400,
                    description="Duration in seconds (0 = indefinite until cleared)",
                    units="seconds",
                ),
            ],
        ),
        CommandDefinition(
            name="LOAD_SHED",
            description="Selectively shed non-critical electrical loads to conserve power",
            # Wiring audit Pass 4 (F7.12) — renamed to match
            # PowerAgent's ``aria.command.power.shed_loads`` handler
            # at agents/power.py:209.
            bus_topic="aria.command.power.shed_loads",
            priority=EventPriority.P1_CRITICAL,
            parameters=[
                CommandParameter(
                    name="TARGET_POWER_W",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    minimum=0.0,
                    maximum=5000.0,
                    description="Target total power draw in watts (0 = shed to minimum)",
                    units="Watts",
                ),
                CommandParameter(
                    name="PRIORITY_FLOOR",
                    bit_size=8,
                    param_type=ParamType.UINT,
                    default=2,
                    minimum=0,
                    maximum=5,
                    description="Minimum subsystem priority to keep powered (0=keep all, 5=life-support only)",
                    states={
                        "KEEP_ALL": 0,
                        "SHED_INSTRUMENTS": 1,
                        "SHED_COMMS": 2,
                        "SHED_THERMAL": 3,
                        "LIFE_SUPPORT_ONLY": 5,
                    },
                ),
                CommandParameter(
                    name="EXCLUDE_SUBSYSTEMS",
                    bit_size=512,
                    param_type=ParamType.STRING,
                    default="",
                    description="Comma-separated subsystem names to exclude from shedding",
                ),
            ],
        ),
        CommandDefinition(
            name="ATTITUDE_CHANGE",
            description="Command a spacecraft attitude maneuver to a target quaternion",
            # Wiring audit Pass 4 (F7.12) — renamed to match
            # NavigationAgent's ``aria.command.nav.plan_maneuver``
            # handler at agents/navigation.py:94.
            bus_topic="aria.command.nav.plan_maneuver",
            priority=EventPriority.P2_WARNING,
            parameters=[
                CommandParameter(
                    name="TARGET_QW",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=1.0,
                    minimum=-1.0,
                    maximum=1.0,
                    description="Target quaternion scalar component (w)",
                ),
                CommandParameter(
                    name="TARGET_QX",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    minimum=-1.0,
                    maximum=1.0,
                    description="Target quaternion vector component (x)",
                ),
                CommandParameter(
                    name="TARGET_QY",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    minimum=-1.0,
                    maximum=1.0,
                    description="Target quaternion vector component (y)",
                ),
                CommandParameter(
                    name="TARGET_QZ",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    minimum=-1.0,
                    maximum=1.0,
                    description="Target quaternion vector component (z)",
                ),
                CommandParameter(
                    name="SLEW_RATE_DEG_S",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=0.5,
                    minimum=0.01,
                    maximum=5.0,
                    description="Maximum slew rate in degrees per second",
                    units="deg/s",
                ),
                CommandParameter(
                    name="MODE",
                    bit_size=128,
                    param_type=ParamType.STRING,
                    default="EIGENAXIS",
                    description="Slew mode",
                    states={
                        "EIGENAXIS": "EIGENAXIS",
                        "MOMENTUM_BIAS": "MOMENTUM_BIAS",
                        "SUN_SAFE": "SUN_SAFE",
                    },
                ),
            ],
        ),
        CommandDefinition(
            name="ORBIT_MANEUVER",
            description="Execute an orbital maneuver (delta-V burn)",
            # Wiring audit Pass 4 (F7.12) — renamed to PropulsionAgent's
            # ``aria.command.propulsion.fire_thruster`` handler
            # (agents/propulsion.py:190). Orbit-maneuver commands flow
            # through propulsion's thruster-fire path.
            bus_topic="aria.command.propulsion.fire_thruster",
            priority=EventPriority.P1_CRITICAL,
            hazardous="Orbital maneuver commits propellant and changes trajectory",
            parameters=[
                CommandParameter(
                    name="DELTA_V_X_MS",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    description="Delta-V in velocity-frame X (m/s)",
                    units="m/s",
                ),
                CommandParameter(
                    name="DELTA_V_Y_MS",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    description="Delta-V in velocity-frame Y (m/s)",
                    units="m/s",
                ),
                CommandParameter(
                    name="DELTA_V_Z_MS",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    description="Delta-V in velocity-frame Z (m/s)",
                    units="m/s",
                ),
                CommandParameter(
                    name="BURN_START_EPOCH",
                    bit_size=64,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    description="Burn start time as Unix epoch (0 = execute immediately)",
                ),
                CommandParameter(
                    name="BURN_DURATION_S",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=0.0,
                    minimum=0.0,
                    maximum=3600.0,
                    description="Burn duration in seconds (0 = compute from delta-V)",
                    units="seconds",
                ),
                CommandParameter(
                    name="ENGINE_ID",
                    bit_size=8,
                    param_type=ParamType.UINT,
                    default=0,
                    minimum=0,
                    maximum=3,
                    description="Engine identifier (0=primary, 1-3=RCS clusters)",
                    states={
                        "PRIMARY": 0,
                        "RCS_CLUSTER_1": 1,
                        "RCS_CLUSTER_2": 2,
                        "RCS_CLUSTER_3": 3,
                    },
                ),
            ],
        ),
        CommandDefinition(
            name="ECLSS_ADJUST",
            description="Adjust Environmental Control and Life Support System parameters",
            # Wiring audit Pass 4 (F7.12) — renamed to match the
            # ``aria.command.eclss.*`` family that EclssAgent subscribes
            # to (agents/eclss.py:56).  No specific handler for
            # ``adjust`` exists yet; EclssAgent's wildcard catches it
            # and the LLM directive path is the intended consumer.
            bus_topic="aria.command.eclss.adjust",
            priority=EventPriority.P2_WARNING,
            parameters=[
                CommandParameter(
                    name="SUBSYSTEM",
                    bit_size=128,
                    param_type=ParamType.STRING,
                    default="ATMOSPHERE",
                    description="ECLSS subsystem to adjust",
                    states={
                        "ATMOSPHERE": "ATMOSPHERE",
                        "THERMAL": "THERMAL",
                        "WATER": "WATER",
                        "WASTE": "WASTE",
                        "FIRE_SUPPRESSION": "FIRE_SUPPRESSION",
                    },
                ),
                CommandParameter(
                    name="TARGET_TEMP_K",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=295.0,
                    minimum=273.0,
                    maximum=308.0,
                    description="Target cabin temperature in Kelvin",
                    units="Kelvin",
                ),
                CommandParameter(
                    name="TARGET_PRESSURE_KPA",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=101.3,
                    minimum=70.0,
                    maximum=110.0,
                    description="Target cabin pressure in kilopascals",
                    units="kPa",
                ),
                CommandParameter(
                    name="O2_FRACTION",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=0.21,
                    minimum=0.16,
                    maximum=0.25,
                    description="Target O2 partial pressure fraction",
                ),
                CommandParameter(
                    name="HUMIDITY_PERCENT",
                    bit_size=32,
                    param_type=ParamType.FLOAT,
                    default=50.0,
                    minimum=20.0,
                    maximum=80.0,
                    description="Target relative humidity percentage",
                    units="percent",
                ),
                CommandParameter(
                    name="FAN_SPEED_RPM",
                    bit_size=16,
                    param_type=ParamType.UINT,
                    default=2000,
                    minimum=0,
                    maximum=5000,
                    description="Cabin air circulation fan speed",
                    units="RPM",
                ),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# ARIA telemetry packet definitions for OpenC3
# ---------------------------------------------------------------------------

def _build_aria_telemetry() -> list[TelemetryPacketDefinition]:
    """Define all ARIA telemetry packets that OpenC3 can monitor."""
    return [
        TelemetryPacketDefinition(
            name="HEALTH_STATUS",
            description="Core ARIA health and status telemetry",
            bus_topics=["aria.sensor.*"],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("SPACECRAFT_MODE", 128, ParamType.STRING, "Current spacecraft mode"),
                TelemetryItem("UPTIME_S", 64, ParamType.FLOAT, "Seconds since boot", units="seconds"),
                TelemetryItem("CPU_LOAD_PCT", 32, ParamType.FLOAT, "AI processor load",
                              units="percent", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (-1.0, -1.0, 90.0, 98.0)}),
                TelemetryItem("MEMORY_USED_MB", 32, ParamType.FLOAT, "Memory usage in MB",
                              units="MB", format_string="%0.1f"),
                TelemetryItem("BUS_MSGS_TOTAL", 32, ParamType.UINT, "Total bus messages processed"),
                TelemetryItem("ANOMALY_COUNT", 16, ParamType.UINT, "Active anomaly alerts"),
                TelemetryItem("AGENT_COUNT", 8, ParamType.UINT, "Number of active agents"),
            ],
        ),
        TelemetryPacketDefinition(
            name="NAVIGATION",
            description="Navigation and attitude telemetry",
            bus_topics=[
                "aria.sensor.navigation.attitude",
                "aria.sensor.navigation.orbit",
            ],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("QW", 64, ParamType.FLOAT, "Quaternion scalar (w)"),
                TelemetryItem("QX", 64, ParamType.FLOAT, "Quaternion X"),
                TelemetryItem("QY", 64, ParamType.FLOAT, "Quaternion Y"),
                TelemetryItem("QZ", 64, ParamType.FLOAT, "Quaternion Z"),
                TelemetryItem("OMEGA_X", 64, ParamType.FLOAT, "Angular velocity X",
                              units="rad/s", format_string="%0.6f"),
                TelemetryItem("OMEGA_Y", 64, ParamType.FLOAT, "Angular velocity Y",
                              units="rad/s", format_string="%0.6f"),
                TelemetryItem("OMEGA_Z", 64, ParamType.FLOAT, "Angular velocity Z",
                              units="rad/s", format_string="%0.6f"),
                TelemetryItem("ALTITUDE_KM", 64, ParamType.FLOAT, "Orbital altitude",
                              units="km", format_string="%0.3f",
                              limits_enabled=True,
                              limits={"DEFAULT": (150.0, 200.0, 800.0, 2000.0)}),
                TelemetryItem("TRUE_ANOMALY_DEG", 64, ParamType.FLOAT, "True anomaly",
                              units="deg", format_string="%0.2f"),
                TelemetryItem("INCLINATION_DEG", 64, ParamType.FLOAT, "Orbital inclination",
                              units="deg", format_string="%0.4f"),
                TelemetryItem("SMA_KM", 64, ParamType.FLOAT, "Semi-major axis",
                              units="km", format_string="%0.3f"),
            ],
        ),
        TelemetryPacketDefinition(
            name="POWER",
            description="Electrical power system telemetry",
            bus_topics=[
                "aria.sensor.power.solar_panels",
                "aria.sensor.power.battery",
                "aria.sensor.power.eclipse",
            ],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("TOTAL_POWER_W", 32, ParamType.FLOAT, "Total solar array power",
                              units="Watts", format_string="%0.1f"),
                TelemetryItem("PANEL_0_W", 32, ParamType.FLOAT, "Solar panel 1 power",
                              units="Watts"),
                TelemetryItem("PANEL_1_W", 32, ParamType.FLOAT, "Solar panel 2 power",
                              units="Watts"),
                TelemetryItem("BATTERY_SOC", 32, ParamType.FLOAT, "Battery state of charge",
                              units="percent", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (10.0, 20.0, 100.0, 100.0)}),
                TelemetryItem("IN_ECLIPSE", 8, ParamType.UINT, "Eclipse flag (1=in eclipse)"),
                TelemetryItem("SUN_ANGLE_DEG", 32, ParamType.FLOAT, "Sun angle",
                              units="deg", format_string="%0.1f"),
            ],
        ),
        TelemetryPacketDefinition(
            name="THERMAL",
            description="Thermal subsystem temperatures",
            bus_topics=["aria.sensor.thermal.nodes"],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("SOLAR_PANEL_1_K", 32, ParamType.FLOAT, "Solar panel 1 temp",
                              units="Kelvin", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (50.0, 100.0, 370.0, 400.0)}),
                TelemetryItem("SOLAR_PANEL_2_K", 32, ParamType.FLOAT, "Solar panel 2 temp",
                              units="Kelvin", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (50.0, 100.0, 370.0, 400.0)}),
                TelemetryItem("BATTERY_PACK_K", 32, ParamType.FLOAT, "Battery pack temp",
                              units="Kelvin", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (250.0, 270.0, 310.0, 330.0)}),
                TelemetryItem("PAYLOAD_BAY_K", 32, ParamType.FLOAT, "Payload bay temp",
                              units="Kelvin", format_string="%0.1f"),
                TelemetryItem("RW_CLUSTER_K", 32, ParamType.FLOAT, "Reaction wheel cluster temp",
                              units="Kelvin", format_string="%0.1f"),
                TelemetryItem("STAR_TRACKER_K", 32, ParamType.FLOAT, "Star tracker temp",
                              units="Kelvin", format_string="%0.1f"),
                TelemetryItem("PROP_TANK_K", 32, ParamType.FLOAT, "Propellant tank temp",
                              units="Kelvin", format_string="%0.1f"),
                TelemetryItem("AVIONICS_BAY_K", 32, ParamType.FLOAT, "Avionics bay temp",
                              units="Kelvin", format_string="%0.1f"),
            ],
        ),
        TelemetryPacketDefinition(
            name="PROPULSION",
            description="Propulsion and actuator telemetry",
            bus_topics=["aria.sensor.propulsion.reaction_wheels"],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("RW_0_RPM", 32, ParamType.FLOAT, "Reaction wheel 1 speed",
                              units="RPM", format_string="%0.0f",
                              limits_enabled=True,
                              limits={"DEFAULT": (-6000.0, -5500.0, 5500.0, 6000.0)}),
                TelemetryItem("RW_1_RPM", 32, ParamType.FLOAT, "Reaction wheel 2 speed",
                              units="RPM", format_string="%0.0f"),
                TelemetryItem("RW_2_RPM", 32, ParamType.FLOAT, "Reaction wheel 3 speed",
                              units="RPM", format_string="%0.0f"),
                TelemetryItem("RW_3_RPM", 32, ParamType.FLOAT, "Reaction wheel 4 speed",
                              units="RPM", format_string="%0.0f"),
            ],
        ),
        TelemetryPacketDefinition(
            name="ECLSS",
            description="Environmental Control and Life Support System telemetry",
            bus_topics=["aria.sensor.eclss.*"],
            items=[
                TelemetryItem("TIMESTAMP", 64, ParamType.FLOAT, "Unix epoch timestamp"),
                TelemetryItem("CABIN_TEMP_K", 32, ParamType.FLOAT, "Cabin temperature",
                              units="Kelvin", format_string="%0.1f",
                              limits_enabled=True,
                              limits={"DEFAULT": (283.0, 289.0, 301.0, 308.0)}),
                TelemetryItem("CABIN_PRESSURE_KPA", 32, ParamType.FLOAT, "Cabin pressure",
                              units="kPa", format_string="%0.2f",
                              limits_enabled=True,
                              limits={"DEFAULT": (70.0, 90.0, 105.0, 110.0)}),
                TelemetryItem("O2_FRACTION", 32, ParamType.FLOAT, "O2 partial pressure fraction",
                              format_string="%0.3f",
                              limits_enabled=True,
                              limits={"DEFAULT": (0.16, 0.19, 0.23, 0.25)}),
                TelemetryItem("CO2_PPM", 32, ParamType.FLOAT, "CO2 concentration",
                              units="ppm", format_string="%0.0f",
                              limits_enabled=True,
                              limits={"DEFAULT": (-1.0, -1.0, 5000.0, 10000.0)}),
                TelemetryItem("HUMIDITY_PCT", 32, ParamType.FLOAT, "Relative humidity",
                              units="percent", format_string="%0.1f"),
                TelemetryItem("FAN_SPEED_RPM", 16, ParamType.UINT, "Air circulation fan speed",
                              units="RPM"),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Telemetry extractor — ARIA bus messages to OpenC3 packet items
# ---------------------------------------------------------------------------

# Mapping from ARIA bus topics to (packet_name, field_extraction_function)
# Each extractor returns a dict of {ITEM_NAME: value} for the packet.

def _extract_navigation_attitude(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract attitude telemetry from aria.sensor.navigation.attitude."""
    q = payload.get("quaternion", [0, 0, 0, 1])
    omega = payload.get("angular_velocity_rad_s", [0, 0, 0])
    return {
        "QW": q[3] if len(q) > 3 else 1.0,
        "QX": q[0] if len(q) > 0 else 0.0,
        "QY": q[1] if len(q) > 1 else 0.0,
        "QZ": q[2] if len(q) > 2 else 0.0,
        "OMEGA_X": omega[0] if len(omega) > 0 else 0.0,
        "OMEGA_Y": omega[1] if len(omega) > 1 else 0.0,
        "OMEGA_Z": omega[2] if len(omega) > 2 else 0.0,
    }


def _extract_navigation_orbit(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract orbit telemetry from aria.sensor.navigation.orbit."""
    sma_m = payload.get("semi_major_axis_m", 0)
    return {
        "ALTITUDE_KM": payload.get("altitude_km", 0.0),
        "TRUE_ANOMALY_DEG": payload.get("true_anomaly_deg", 0.0),
        "INCLINATION_DEG": payload.get("inclination_deg", 0.0),
        "SMA_KM": sma_m / 1000.0 if sma_m else 0.0,
    }


def _extract_power_solar(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract solar panel telemetry."""
    panels = payload.get("panel_power_w", [])
    result: dict[str, Any] = {
        "TOTAL_POWER_W": payload.get("total_power_w", 0.0),
        "IN_ECLIPSE": 1 if payload.get("eclipse", False) else 0,
        "SUN_ANGLE_DEG": payload.get("sun_angle_deg", 0.0),
    }
    for i, p in enumerate(panels[:2]):
        result[f"PANEL_{i}_W"] = p
    return result


def _extract_power_battery(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract battery telemetry."""
    soc = payload.get("state_of_charge", 0.0)
    return {"BATTERY_SOC": soc * 100.0}


def _extract_power_eclipse(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract eclipse state telemetry."""
    return {
        "IN_ECLIPSE": 1 if payload.get("in_eclipse", False) else 0,
        "SUN_ANGLE_DEG": payload.get("sun_angle_deg", 0.0),
    }


def _extract_thermal(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract thermal node temperatures."""
    temps = payload.get("node_temps_k", [])
    names = payload.get("node_names", [])
    name_to_item = {
        "solar_panel_1": "SOLAR_PANEL_1_K",
        "solar_panel_2": "SOLAR_PANEL_2_K",
        "battery_pack": "BATTERY_PACK_K",
        "payload_bay": "PAYLOAD_BAY_K",
        "reaction_wheel_cluster": "RW_CLUSTER_K",
        "star_tracker": "STAR_TRACKER_K",
        "propellant_tank": "PROP_TANK_K",
        "avionics_bay": "AVIONICS_BAY_K",
    }
    result: dict[str, Any] = {}
    for i, temp in enumerate(temps):
        name = names[i] if i < len(names) else ""
        item = name_to_item.get(name)
        if item:
            result[item] = temp
    return result


def _extract_reaction_wheels(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract reaction wheel speeds."""
    speeds = payload.get("speeds_rpm", [])
    result: dict[str, Any] = {}
    for i, spd in enumerate(speeds[:4]):
        result[f"RW_{i}_RPM"] = spd
    return result


# Topic -> (packet_name, extractor_fn)
_TOPIC_EXTRACTORS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "aria.sensor.navigation.attitude": ("NAVIGATION", _extract_navigation_attitude),
    "aria.sensor.navigation.orbit": ("NAVIGATION", _extract_navigation_orbit),
    "aria.sensor.power.solar_panels": ("POWER", _extract_power_solar),
    "aria.sensor.power.battery": ("POWER", _extract_power_battery),
    "aria.sensor.power.eclipse": ("POWER", _extract_power_eclipse),
    "aria.sensor.thermal.nodes": ("THERMAL", _extract_thermal),
    "aria.sensor.propulsion.reaction_wheels": ("PROPULSION", _extract_reaction_wheels),
}


# ---------------------------------------------------------------------------
# Command router — OpenC3 commands to ARIA bus messages
# ---------------------------------------------------------------------------

def _command_params_to_bus_payload(
    cmd_def: CommandDefinition,
    openc3_params: dict[str, Any],
) -> dict[str, Any]:
    """Convert OpenC3 command parameters to an ARIA bus payload.

    Parameter names are lowercased to match ARIA bus conventions.
    """
    payload: dict[str, Any] = {}
    for param in cmd_def.parameters:
        value = openc3_params.get(param.name, param.default)
        payload[param.name.lower()] = value
    return payload


# ---------------------------------------------------------------------------
# Mock OpenC3 API client (for testing without a running OpenC3 server)
# ---------------------------------------------------------------------------

class MockOpenC3ApiClient:
    """In-process mock of the OpenC3 REST API.

    Records all sent commands and injected telemetry for verification.
    """

    def __init__(self) -> None:
        self.sent_commands: list[dict[str, Any]] = []
        self.injected_telemetry: list[dict[str, Any]] = []
        self.connected: bool = True

    async def cmd(
        self,
        target_name: str,
        cmd_name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mock sending a command to OpenC3."""
        record = {
            "target_name": target_name,
            "cmd_name": cmd_name,
            "cmd_params": params or {},
            "timestamp": time.time(),
            "id": uuid.uuid4().hex[:16],
        }
        self.sent_commands.append(record)
        logger.debug("mock_openc3.cmd_sent", **record)
        return record

    async def inject_tlm(
        self,
        target_name: str,
        packet_name: str,
        item_hash: dict[str, Any],
    ) -> None:
        """Mock injecting telemetry into OpenC3."""
        record = {
            "target_name": target_name,
            "packet_name": packet_name,
            "items": item_hash,
            "timestamp": time.time(),
        }
        self.injected_telemetry.append(record)
        logger.debug("mock_openc3.tlm_injected", target=target_name, packet=packet_name)

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def clear(self) -> None:
        """Reset all recorded data."""
        self.sent_commands.clear()
        self.injected_telemetry.clear()


# ---------------------------------------------------------------------------
# Live OpenC3 API client (HTTP JSON-RPC)
# ---------------------------------------------------------------------------

class OpenC3ApiClient:
    """HTTP client for the OpenC3 cmd-tlm-api REST endpoint.

    Uses the OpenC3 JSON-RPC protocol:
      POST /api
      {"jsonrpc": "2.0", "method": "cmd", "params": [...], "id": <id>}
    """

    def __init__(self, config: OpenC3Config) -> None:
        self._config = config
        self._session: Any = None
        self.connected: bool = False

    async def connect(self) -> None:
        """Establish HTTP session to OpenC3 API."""
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                base_url=self._config.api_url,
                headers={"Content-Type": "application/json-rpc"},
            )
            # Verify connectivity
            result = await self._rpc("get_all_target_names")
            self.connected = True
            logger.info("openc3_api.connected", url=self._config.api_url, targets=result)
        except Exception as exc:
            logger.error("openc3_api.connect_failed", url=self._config.api_url, error=str(exc))
            self.connected = False
            raise

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
        self.connected = False
        logger.info("openc3_api.disconnected")

    async def _rpc(self, method: str, params: list[Any] | None = None) -> Any:
        """Execute a JSON-RPC call to the OpenC3 API."""
        if not self._session:
            raise RuntimeError("OpenC3 API client not connected")

        request_id = uuid.uuid4().hex[:8]
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": request_id,
            "keyword_params": {"scope": self._config.api_scope},
        }

        auth_header = {}
        if self._config.api_password:
            auth_header["Authorization"] = self._config.api_password

        import aiohttp
        rpc_timeout = aiohttp.ClientTimeout(total=10)
        async with self._session.post("/api", json=body, headers=auth_header, timeout=rpc_timeout) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenC3 API error {resp.status}: {text}")
            result = await resp.json()
            if "error" in result:
                raise RuntimeError(f"OpenC3 RPC error: {result['error']}")
            return result.get("result")

    async def cmd(
        self,
        target_name: str,
        cmd_name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a command through OpenC3."""
        args = [target_name, cmd_name]
        if params:
            args.append(params)
        result = await self._rpc("cmd", args)
        logger.info("openc3_api.cmd_sent", target=target_name, cmd=cmd_name)
        return result or {}

    async def inject_tlm(
        self,
        target_name: str,
        packet_name: str,
        item_hash: dict[str, Any],
    ) -> None:
        """Inject telemetry into OpenC3."""
        await self._rpc("inject_tlm", [target_name, packet_name, item_hash])
        logger.debug("openc3_api.tlm_injected", target=target_name, packet=packet_name)


# ---------------------------------------------------------------------------
# Command validation
# ---------------------------------------------------------------------------

class CommandValidationError(Exception):
    """Raised when a command fails parameter validation."""
    pass


def validate_command_params(
    cmd_def: CommandDefinition,
    params: dict[str, Any],
) -> list[str]:
    """Validate command parameters against the definition.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    for param_def in cmd_def.parameters:
        value = params.get(param_def.name)

        # Check required params
        if param_def.required and value is None:
            errors.append(f"Required parameter '{param_def.name}' is missing")
            continue

        if value is None:
            continue

        # Type checking
        if param_def.param_type in (ParamType.UINT, ParamType.INT):
            if not isinstance(value, (int, float)):
                errors.append(
                    f"Parameter '{param_def.name}' must be numeric, got {type(value).__name__}"
                )
                continue
        elif param_def.param_type == ParamType.FLOAT:
            if not isinstance(value, (int, float)):
                errors.append(
                    f"Parameter '{param_def.name}' must be numeric, got {type(value).__name__}"
                )
                continue
        elif param_def.param_type == ParamType.STRING:
            if not isinstance(value, str):
                errors.append(
                    f"Parameter '{param_def.name}' must be a string, got {type(value).__name__}"
                )
                continue

        # Range checking for numeric types
        if param_def.param_type in (ParamType.UINT, ParamType.INT, ParamType.FLOAT):
            if isinstance(value, (int, float)):
                if param_def.minimum is not None and value < param_def.minimum:
                    errors.append(
                        f"Parameter '{param_def.name}' value {value} below minimum {param_def.minimum}"
                    )
                if param_def.maximum is not None and value > param_def.maximum:
                    errors.append(
                        f"Parameter '{param_def.name}' value {value} above maximum {param_def.maximum}"
                    )

        # State validation
        if param_def.states and value not in param_def.states.values():
            valid = list(param_def.states.values())
            errors.append(
                f"Parameter '{param_def.name}' value {value!r} not in valid states: {valid}"
            )

    # Check for unknown parameters
    known_names = {p.name for p in cmd_def.parameters}
    for key in params:
        if key not in known_names:
            errors.append(f"Unknown parameter '{key}'")

    return errors


# ---------------------------------------------------------------------------
# Command execution result
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    """Result of a command execution through the bridge."""
    command_name: str
    success: bool
    message_id: str = ""
    timestamp: float = 0.0
    errors: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.success and not self.errors


# ---------------------------------------------------------------------------
# Telemetry snapshot
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySnapshot:
    """A snapshot of a telemetry packet's current values."""
    packet_name: str
    items: dict[str, Any]
    timestamp: float
    sequence_count: int = 0


# ---------------------------------------------------------------------------
# Main OpenC3 Bridge
# ---------------------------------------------------------------------------

class OpenC3Bridge:
    """Bidirectional bridge between ARIA message bus and OpenC3/COSMOS.

    Commands flow:  OpenC3 -> Bridge -> ARIA bus
    Telemetry flows:  ARIA bus -> Bridge -> OpenC3

    Usage::

        bus = MessageBus()
        bridge = OpenC3Bridge(bus, OpenC3Config(mock_mode=True))
        await bridge.start()

        # Send a command from OpenC3 side
        result = await bridge.send_command("SAFE_MODE", {"REASON": "test"})

        # Telemetry is auto-published from bus subscriptions
        snap = bridge.get_telemetry_snapshot("NAVIGATION")

        await bridge.stop()
    """

    def __init__(
        self,
        bus: MessageBus,
        config: OpenC3Config | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or OpenC3Config()

        # Build command and telemetry definitions
        self._commands = {c.name: c for c in _build_aria_commands()}
        self._telemetry = {t.name: t for t in _build_aria_telemetry()}

        # API client (mock or live)
        self._api: MockOpenC3ApiClient | OpenC3ApiClient
        if self._config.mock_mode:
            self._api = MockOpenC3ApiClient()
        else:
            self._api = OpenC3ApiClient(self._config)

        # Current telemetry values per packet
        self._current_telemetry: dict[str, dict[str, Any]] = {
            name: {} for name in self._telemetry
        }
        self._telemetry_sequence: dict[str, int] = {
            name: 0 for name in self._telemetry
        }

        # Command history
        self._command_history: list[CommandResult] = []
        self._max_command_history = 1000

        # Publish task
        self._publish_task: asyncio.Task[None] | None = None
        self._running = False

        # Stats
        self._stats = {
            "commands_received": 0,
            "commands_validated": 0,
            "commands_rejected": 0,
            "commands_dispatched": 0,
            "telemetry_messages_ingested": 0,
            "telemetry_packets_published": 0,
        }

    # --- Properties ---

    @property
    def config(self) -> OpenC3Config:
        return self._config

    @property
    def command_definitions(self) -> dict[str, CommandDefinition]:
        """All registered command definitions."""
        return dict(self._commands)

    @property
    def telemetry_definitions(self) -> dict[str, TelemetryPacketDefinition]:
        """All registered telemetry packet definitions."""
        return dict(self._telemetry)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "running": self._running,
            "mock_mode": self._config.mock_mode,
            "commands_defined": len(self._commands),
            "telemetry_packets_defined": len(self._telemetry),
            "command_history_size": len(self._command_history),
        }

    @property
    def api_client(self) -> MockOpenC3ApiClient | OpenC3ApiClient:
        """Direct access to the underlying API client."""
        return self._api

    @property
    def command_history(self) -> list[CommandResult]:
        """Recent command execution history."""
        return list(self._command_history)

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the bridge: connect to OpenC3, subscribe to bus topics."""
        if self._running:
            logger.warning("openc3_bridge.already_running")
            return

        logger.info(
            "openc3_bridge.starting",
            mock_mode=self._config.mock_mode,
            target=self._config.target_name,
        )

        # Connect API client
        await self._api.connect()

        # Subscribe to ARIA bus topics for telemetry
        self._bus.subscribe("aria.sensor.*", self._on_telemetry_message)

        # Subscribe to command topics (commands arriving on the bus)
        self._bus.subscribe("aria.openc3.command.*", self._on_bus_command_request)

        # Start periodic telemetry publishing
        self._running = True
        self._publish_task = asyncio.create_task(self._telemetry_publish_loop())

        logger.info("openc3_bridge.started", stats=self.stats)

    async def stop(self) -> None:
        """Stop the bridge gracefully."""
        if not self._running:
            return

        self._running = False

        # Cancel publish loop
        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass
            self._publish_task = None

        # Unsubscribe from bus
        self._bus.unsubscribe("aria.sensor.*", self._on_telemetry_message)
        self._bus.unsubscribe("aria.openc3.command.*", self._on_bus_command_request)

        # Disconnect API
        await self._api.disconnect()

        logger.info("openc3_bridge.stopped", stats=self.stats)

    # --- Command sending ---

    async def send_command(
        self,
        command_name: str,
        params: dict[str, Any] | None = None,
        *,
        validate: bool = True,
        route_to_bus: bool = True,
    ) -> CommandResult:
        """Send a command through the bridge.

        1. Validates parameters against the command definition
        2. Routes to ARIA bus as a Message
        3. Forwards to OpenC3 API (inject into OpenC3's command history)

        Args:
            command_name: OpenC3 command name (e.g. "SAFE_MODE")
            params: Command parameters dict
            validate: Whether to validate params before sending
            route_to_bus: Whether to publish to the ARIA bus

        Returns:
            CommandResult with success status and any errors
        """
        self._stats["commands_received"] += 1
        params = params or {}

        # Look up command definition
        cmd_def = self._commands.get(command_name)
        if not cmd_def:
            result = CommandResult(
                command_name=command_name,
                success=False,
                errors=[f"Unknown command: {command_name}. "
                        f"Valid commands: {list(self._commands.keys())}"],
                timestamp=time.time(),
            )
            self._stats["commands_rejected"] += 1
            self._record_command(result)
            return result

        # Fill defaults for missing params
        full_params = {}
        for param_def in cmd_def.parameters:
            if param_def.name in params:
                full_params[param_def.name] = params[param_def.name]
            else:
                full_params[param_def.name] = param_def.default

        # Validate
        if validate:
            errors = validate_command_params(cmd_def, full_params)
            if errors:
                result = CommandResult(
                    command_name=command_name,
                    success=False,
                    errors=errors,
                    params=full_params,
                    timestamp=time.time(),
                )
                self._stats["commands_rejected"] += 1
                self._record_command(result)
                return result
            self._stats["commands_validated"] += 1

        # Build ARIA bus message
        bus_payload = _command_params_to_bus_payload(cmd_def, full_params)
        bus_payload["_openc3_source"] = True
        bus_payload["_command_name"] = command_name
        message_id = uuid.uuid4().hex[:16]

        message = Message(
            topic=cmd_def.bus_topic,
            payload=bus_payload,
            priority=cmd_def.priority,
            source_agent="openc3_bridge",
            message_id=message_id,
        )

        # Route to ARIA bus
        if route_to_bus:
            await self._bus.publish(message)

        # Forward to OpenC3 API
        try:
            await self._api.cmd(
                self._config.target_name,
                command_name,
                full_params,
            )
        except Exception as exc:
            logger.error("openc3_bridge.api_cmd_failed", cmd=command_name, error=str(exc))
            # Non-fatal: bus routing already happened

        self._stats["commands_dispatched"] += 1

        result = CommandResult(
            command_name=command_name,
            success=True,
            message_id=message_id,
            params=full_params,
            timestamp=time.time(),
        )
        self._record_command(result)

        logger.info(
            "openc3_bridge.command_sent",
            cmd=command_name,
            message_id=message_id,
            priority=cmd_def.priority.name,
        )
        return result

    # --- Telemetry ---

    def get_telemetry_snapshot(self, packet_name: str) -> TelemetrySnapshot | None:
        """Get the current telemetry values for a packet."""
        if packet_name not in self._current_telemetry:
            return None
        items = self._current_telemetry[packet_name]
        if not items:
            return None
        return TelemetrySnapshot(
            packet_name=packet_name,
            items=dict(items),
            timestamp=items.get("TIMESTAMP", time.time()),
            sequence_count=self._telemetry_sequence.get(packet_name, 0),
        )

    def get_all_telemetry_snapshots(self) -> dict[str, TelemetrySnapshot]:
        """Get current values for all telemetry packets with data."""
        result: dict[str, TelemetrySnapshot] = {}
        for name in self._telemetry:
            snap = self.get_telemetry_snapshot(name)
            if snap:
                result[name] = snap
        return result

    # --- Target definition export ---

    def generate_target_cmd_tlm(self) -> dict[str, str]:
        """Generate OpenC3 target definition files for ARIA.

        Returns a dict of filename -> content for the target's cmd_tlm directory.
        """
        target = self._config.target_name

        # Commands file
        cmd_lines: list[str] = []
        for cmd_def in self._commands.values():
            cmd_lines.append(cmd_def.to_openc3_definition(target))
            cmd_lines.append("")

        # Telemetry file
        tlm_lines: list[str] = []
        for tlm_def in self._telemetry.values():
            tlm_lines.append(tlm_def.to_openc3_definition(target))
            tlm_lines.append("")

        return {
            "aria_cmds.txt": "\n".join(cmd_lines),
            "aria_tlm.txt": "\n".join(tlm_lines),
        }

    def generate_target_txt(self) -> str:
        """Generate the target.txt configuration file."""
        return (
            f"# ARIA Target Configuration for OpenC3/COSMOS\n"
            f"# Auto-generated by ARIA OpenC3 Bridge\n"
            f"#\n"
            f"# Target: {self._config.target_name}\n"
            f"# Description: {self._config.target_description}\n"
            f"\n"
            f"REQUIRE aria_cmds.txt\n"
            f"REQUIRE aria_tlm.txt\n"
        )

    def generate_plugin_txt(self) -> str:
        """Generate the OpenC3 plugin.txt for the ARIA target."""
        target = self._config.target_name
        return (
            f"# OpenC3 Plugin Configuration for ARIA\n"
            f"# Auto-generated by ARIA OpenC3 Bridge\n"
            f"\n"
            f"TARGET {target} {target}\n"
            f'INTERFACE {target}_INT tcpip_client_interface.rb '
            f'{self._config.api_hostname} 8888 8889 10.0 nil LENGTH 0 32 4\n'
            f"  MAP_TARGET {target}\n"
        )

    # --- Bus event handlers ---

    async def _on_telemetry_message(self, message: Message) -> None:
        """Handle an ARIA bus sensor message and update telemetry state."""
        self._stats["telemetry_messages_ingested"] += 1

        extractor = _TOPIC_EXTRACTORS.get(message.topic)
        if not extractor:
            return

        packet_name, extract_fn = extractor
        try:
            items = extract_fn(message.payload)
        except Exception as exc:
            logger.error(
                "openc3_bridge.extract_error",
                topic=message.topic,
                error=str(exc),
            )
            return

        # Update current values
        items["TIMESTAMP"] = time.time()
        self._current_telemetry[packet_name].update(items)
        self._telemetry_sequence[packet_name] = (
            self._telemetry_sequence.get(packet_name, 0) + 1
        )

    async def _on_bus_command_request(self, message: Message) -> None:
        """Handle a command request arriving on the ARIA bus.

        Topic format: aria.openc3.command.<COMMAND_NAME>
        """
        parts = message.topic.split(".")
        if len(parts) < 4:
            return
        cmd_name = parts[3].upper()
        await self.send_command(cmd_name, message.payload)

    async def _telemetry_publish_loop(self) -> None:
        """Periodically publish current telemetry to OpenC3."""
        while self._running:
            try:
                await asyncio.sleep(self._config.telemetry_publish_interval)
            except asyncio.CancelledError:
                break

            for packet_name, items in self._current_telemetry.items():
                if not items:
                    continue

                try:
                    await self._api.inject_tlm(
                        self._config.target_name,
                        packet_name,
                        items,
                    )
                    self._stats["telemetry_packets_published"] += 1
                except Exception as exc:
                    logger.error(
                        "openc3_bridge.publish_error",
                        packet=packet_name,
                        error=str(exc),
                    )

    def _record_command(self, result: CommandResult) -> None:
        """Store a command result in history."""
        self._command_history.append(result)
        if len(self._command_history) > self._max_command_history:
            self._command_history = self._command_history[
                -self._max_command_history:
            ]
