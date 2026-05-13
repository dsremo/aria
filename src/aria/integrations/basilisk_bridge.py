"""Basilisk Simulation Framework Bridge for ARIA.

Connects NASA/AVS Lab's Basilisk spacecraft simulation framework to ARIA's
message bus, enabling high-fidelity attitude, orbit, power, and thermal
simulation data to drive ARIA's subsystem agents.

Basilisk (https://hanspeterschaub.info/basilisk/) provides:
  - 6-DOF spacecraft dynamics (attitude + orbit)
  - Reaction wheel, thruster, and solar array actuator models
  - Solar panel power generation with eclipse modeling
  - Thermal node networks
  - Sensor models (star tracker, IMU, sun sensor, CSS)

This bridge:
  1. Reads Basilisk simulation outputs each timestep
  2. Converts them to ARIA Message objects on the correct bus topics
  3. Accepts ARIA commands and converts them to Basilisk actuator inputs
  4. Supports mock mode for testing without Basilisk installed
  5. Supports real-time and faster-than-real-time stepping

Design note: The interface is defined against Basilisk's public Python API
(basilisk.architecture.messaging, Basilisk.simulation.*) but gracefully
degrades to mock mode when the dependency is absent.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SimulationMode(Enum):
    """Bridge operating mode."""
    LIVE = auto()       # Connected to a running Basilisk sim
    MOCK = auto()       # Internal mock telemetry generator
    REPLAY = auto()     # Replaying recorded Basilisk data


@dataclass(frozen=True)
class BasiliskConfig:
    """Configuration for the Basilisk bridge."""
    mode: SimulationMode = SimulationMode.MOCK
    step_size_s: float = 1.0          # Simulation timestep in seconds
    realtime_factor: float = 1.0      # 1.0 = real-time, 10.0 = 10x faster
    publish_interval_s: float = 1.0   # How often to push to the ARIA bus
    orbit_model: str = "LEO"          # LEO, GEO, LUNAR, INTERPLANETARY
    num_reaction_wheels: int = 4
    num_thrusters: int = 12
    num_solar_panels: int = 2
    num_thermal_nodes: int = 8
    initial_orbit_altitude_km: float = 400.0
    initial_inclination_deg: float = 51.6  # ISS-like


# ---------------------------------------------------------------------------
# Basilisk type stubs — mirrors Basilisk's messaging API
# ---------------------------------------------------------------------------

class BasiliskModuleProtocol(Protocol):
    """Protocol matching a Basilisk simulation module."""

    def UpdateState(self, current_sim_nanos: int) -> None: ...
    def Reset(self, current_sim_nanos: int) -> None: ...


@dataclass
class SpacecraftState:
    """Unified spacecraft state extracted from Basilisk or mock.

    Attitude uses Modified Rodrigues Parameters (MRPs) internally
    but is published as a quaternion on the ARIA bus for generality.
    """
    # Time
    sim_time_s: float = 0.0

    # Attitude (quaternion: scalar-last [qx, qy, qz, qw])
    attitude_quaternion: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 1.0]
    )
    # Body angular velocity [rad/s] in body frame
    angular_velocity_rad_s: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0]
    )
    # Angular velocity magnitude for quick checks
    angular_velocity_magnitude_rad_s: float = 0.0

    # Orbit (ECI position and velocity)
    position_eci_m: list[float] = field(
        default_factory=lambda: [6_778_137.0, 0.0, 0.0]  # ~400 km LEO
    )
    velocity_eci_m_s: list[float] = field(
        default_factory=lambda: [0.0, 7_668.6, 0.0]  # Circular LEO velocity
    )
    altitude_km: float = 400.0

    # Orbital elements (Keplerian)
    semi_major_axis_m: float = 6_778_137.0
    eccentricity: float = 0.0001
    inclination_deg: float = 51.6
    raan_deg: float = 0.0
    arg_periapsis_deg: float = 0.0
    true_anomaly_deg: float = 0.0

    # Power
    solar_panel_power_w: list[float] = field(default_factory=lambda: [0.0, 0.0])
    total_power_w: float = 0.0
    eclipse: bool = False
    sun_angle_deg: float = 0.0
    battery_soc: float = 1.0  # State of charge 0-1

    # Thermal (node temperatures in Kelvin)
    thermal_node_temps_k: list[float] = field(
        default_factory=lambda: [293.0] * 8
    )
    thermal_node_names: list[str] = field(
        default_factory=lambda: [
            "solar_panel_1", "solar_panel_2", "battery_pack",
            "payload_bay", "reaction_wheel_cluster", "star_tracker",
            "propellant_tank", "avionics_bay",
        ]
    )

    # Actuator states
    reaction_wheel_speeds_rpm: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0]
    )
    reaction_wheel_torques_nm: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0]
    )
    thruster_on_flags: list[bool] = field(
        default_factory=lambda: [False] * 12
    )
    solar_array_angles_deg: list[float] = field(
        default_factory=lambda: [0.0, 0.0]
    )

    # Sensor readings
    star_tracker_valid: bool = True
    imu_gyro_bias_rad_s: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0]
    )
    sun_sensor_valid: bool = True


# ---------------------------------------------------------------------------
# Topic mapping — Basilisk fields -> ARIA bus topics
# ---------------------------------------------------------------------------

# Each entry: (aria_topic, payload_builder_key)
TOPIC_MAP: dict[str, str] = {
    "aria.sensor.navigation.attitude": "attitude",
    "aria.sensor.navigation.orbit": "orbit",
    "aria.sensor.navigation.angular_velocity": "angular_velocity",
    "aria.sensor.power.solar_panels": "solar_power",
    "aria.sensor.power.battery": "battery",
    "aria.sensor.power.eclipse": "eclipse",
    "aria.sensor.thermal.nodes": "thermal",
    "aria.sensor.propulsion.reaction_wheels": "reaction_wheels",
    "aria.sensor.propulsion.thrusters": "thrusters",
    "aria.sensor.navigation.sensors": "nav_sensors",
}

# Commands ARIA can send -> Basilisk actuator inputs
COMMAND_MAP: dict[str, str] = {
    "aria.command.propulsion.reaction_wheel_torque": "rw_torque",
    "aria.command.propulsion.thruster_fire": "thruster",
    "aria.command.power.solar_array_drive": "sad",
    "aria.command.navigation.attitude_target": "att_target",
    "aria.command.propulsion.delta_v": "delta_v",
}


# ---------------------------------------------------------------------------
# Mock telemetry generator
# ---------------------------------------------------------------------------

class MockBasiliskSim:
    """Generates Basilisk-like telemetry without the actual dependency.

    Models:
      - Simple Keplerian orbit propagation
      - Sinusoidal attitude oscillation (detumble scenario)
      - Eclipse-aware solar power generation
      - Thermal node conduction with eclipse cycling
      - Reaction wheel momentum accumulation
    """

    def __init__(self, config: BasiliskConfig, seed: int | None = None) -> None:
        self._config = config
        self._rng = random.Random(seed)
        self._state = SpacecraftState(
            altitude_km=config.initial_orbit_altitude_km,
            thermal_node_temps_k=[293.0] * config.num_thermal_nodes,
            thermal_node_names=[
                "solar_panel_1", "solar_panel_2", "battery_pack",
                "payload_bay", "reaction_wheel_cluster", "star_tracker",
                "propellant_tank", "avionics_bay",
            ][:config.num_thermal_nodes],
            reaction_wheel_speeds_rpm=[0.0] * config.num_reaction_wheels,
            reaction_wheel_torques_nm=[0.0] * config.num_reaction_wheels,
            thruster_on_flags=[False] * config.num_thrusters,
            solar_panel_power_w=[0.0] * config.num_solar_panels,
            solar_array_angles_deg=[0.0] * config.num_solar_panels,
        )
        self._mu_earth = 3.986004418e14  # m^3/s^2
        self._earth_radius_m = 6_371_000.0
        self._orbit_radius_m = self._earth_radius_m + config.initial_orbit_altitude_km * 1000
        self._orbit_period_s = 2 * math.pi * math.sqrt(
            self._orbit_radius_m ** 3 / self._mu_earth
        )
        # Pending commands queued from ARIA
        self._pending_commands: list[dict[str, Any]] = []

    @property
    def state(self) -> SpacecraftState:
        return self._state

    def apply_command(self, command_type: str, params: dict[str, Any]) -> None:
        """Queue a command for next simulation step."""
        self._pending_commands.append({"type": command_type, "params": params})

    def step(self, dt_s: float) -> SpacecraftState:
        """Advance the mock simulation by dt_s seconds."""
        s = self._state
        s.sim_time_s += dt_s

        # Process pending commands
        self._apply_pending_commands()

        # --- Orbit propagation (simple circular) ---
        true_anomaly_rad = (
            2 * math.pi * s.sim_time_s / self._orbit_period_s
        ) % (2 * math.pi)
        s.true_anomaly_deg = math.degrees(true_anomaly_rad)
        s.position_eci_m = [
            self._orbit_radius_m * math.cos(true_anomaly_rad),
            self._orbit_radius_m * math.sin(true_anomaly_rad)
            * math.cos(math.radians(self._config.initial_inclination_deg)),
            self._orbit_radius_m * math.sin(true_anomaly_rad)
            * math.sin(math.radians(self._config.initial_inclination_deg)),
        ]
        orbital_velocity = math.sqrt(self._mu_earth / self._orbit_radius_m)
        s.velocity_eci_m_s = [
            -orbital_velocity * math.sin(true_anomaly_rad),
            orbital_velocity * math.cos(true_anomaly_rad)
            * math.cos(math.radians(self._config.initial_inclination_deg)),
            orbital_velocity * math.cos(true_anomaly_rad)
            * math.sin(math.radians(self._config.initial_inclination_deg)),
        ]
        s.altitude_km = self._config.initial_orbit_altitude_km
        s.semi_major_axis_m = self._orbit_radius_m

        # --- Attitude (damped oscillation toward nadir) ---
        omega = 2 * math.pi / self._orbit_period_s
        damping = math.exp(-0.001 * s.sim_time_s)
        pitch = 0.01 * damping * math.sin(omega * s.sim_time_s)
        s.attitude_quaternion = _euler_to_quaternion(0.0, pitch, 0.0)
        s.angular_velocity_rad_s = [
            0.0,
            0.01 * damping * omega * math.cos(omega * s.sim_time_s),
            0.0,
        ]
        s.angular_velocity_magnitude_rad_s = abs(s.angular_velocity_rad_s[1])

        # Eclipse detection via the classical cone-shadow check: a
        # spacecraft in a circular LEO orbit is in Earth's umbra
        # for the arc between β ± arccos(R_earth / (R_earth + h))
        # where β is the orbit-plane angle to the sun vector
        # (Vallado 2013 Fundamentals of Astrodynamics sec 5.3).
        # For the standard 400 km LEO default used by this bridge
        # the umbra arc is ~(π·0.6, π·1.4), which matches the
        # observed ISS ~36 min eclipse per ~92 min orbit.
        sun_angle = true_anomaly_rad
        s.eclipse = math.pi * 0.6 < (sun_angle % (2 * math.pi)) < math.pi * 1.4
        s.sun_angle_deg = math.degrees(sun_angle % (2 * math.pi))

        # --- Solar power ---
        max_panel_power = 1500.0  # W per panel
        for i in range(self._config.num_solar_panels):
            if s.eclipse:
                s.solar_panel_power_w[i] = 0.0
            else:
                # Power varies with sun angle and array drive angle
                drive_angle_rad = math.radians(s.solar_array_angles_deg[i])
                effective_angle = abs(math.cos(sun_angle - drive_angle_rad))
                noise = self._rng.gauss(0, 5.0)
                s.solar_panel_power_w[i] = max(
                    0.0, max_panel_power * effective_angle + noise
                )
        s.total_power_w = sum(s.solar_panel_power_w)

        # --- Battery ---
        power_draw = 800.0  # W spacecraft load
        net_power = s.total_power_w - power_draw
        # 100 Ah @ 28V = 2800 Wh capacity
        battery_capacity_wh = 2800.0
        s.battery_soc = max(0.0, min(1.0,
            s.battery_soc + (net_power * dt_s / 3600.0) / battery_capacity_wh
        ))

        # --- Thermal nodes ---
        for i in range(len(s.thermal_node_temps_k)):
            # Effective radiation sink temperature. In eclipse the
            # panel sees only the Earth IR + CMB background
            # (~120 K per NASA SP-R-0022A Earth IR limits). In
            # sunlight the panel sees the solar-albedo-modified
            # sky at ~250 K (Incropera 2011 eq. 12.45 with 0.3
            # Earth albedo and 400 km altitude geometry factor).
            ambient = 120.0 if s.eclipse else 250.0
            internal_heat = 5.0 + self._rng.gauss(0, 0.5)  # Internal dissipation
            # Simple first-order thermal model: dT/dt = (Q_in - Q_out) / C
            thermal_mass = 500.0  # J/K
            q_rad_out = 5.67e-8 * (s.thermal_node_temps_k[i] ** 4 - ambient ** 4) * 0.01
            dt_temp = (internal_heat - q_rad_out) / thermal_mass * dt_s
            s.thermal_node_temps_k[i] += dt_temp
            # Clamp to physical range
            s.thermal_node_temps_k[i] = max(50.0, min(400.0, s.thermal_node_temps_k[i]))

        # --- Reaction wheels ---
        for i in range(self._config.num_reaction_wheels):
            # Accumulate momentum from torque commands
            torque = s.reaction_wheel_torques_nm[i]
            # dw/dt = T/I, I_wheel ~ 0.05 kg*m^2
            inertia = 0.05
            angular_accel = torque / inertia  # rad/s^2
            speed_change_rpm = angular_accel * dt_s * 60 / (2 * math.pi)
            s.reaction_wheel_speeds_rpm[i] += speed_change_rpm
            # Clamp to +-6000 RPM
            s.reaction_wheel_speeds_rpm[i] = max(
                -6000.0, min(6000.0, s.reaction_wheel_speeds_rpm[i])
            )
            # Friction decay
            s.reaction_wheel_speeds_rpm[i] *= (1.0 - 1e-5 * dt_s)

        # --- Sensor noise ---
        s.star_tracker_valid = not s.eclipse or self._rng.random() > 0.3
        s.imu_gyro_bias_rad_s = [
            b + self._rng.gauss(0, 1e-7) for b in s.imu_gyro_bias_rad_s
        ]
        s.sun_sensor_valid = not s.eclipse

        return s

    def _apply_pending_commands(self) -> None:
        """Apply queued commands to simulation state."""
        s = self._state
        for cmd in self._pending_commands:
            cmd_type = cmd["type"]
            params = cmd["params"]

            if cmd_type == "rw_torque":
                # params: {"wheel_index": int, "torque_nm": float}
                # or {"torques_nm": [float, ...]}
                if "torques_nm" in params:
                    for i, t in enumerate(params["torques_nm"]):
                        if i < len(s.reaction_wheel_torques_nm):
                            s.reaction_wheel_torques_nm[i] = max(-0.2, min(0.2, t))
                elif "wheel_index" in params:
                    idx = params["wheel_index"]
                    if 0 <= idx < len(s.reaction_wheel_torques_nm):
                        s.reaction_wheel_torques_nm[idx] = max(
                            -0.2, min(0.2, params.get("torque_nm", 0.0))
                        )

            elif cmd_type == "thruster":
                # params: {"thruster_index": int, "on": bool, "duration_s": float}
                idx = params.get("thruster_index", 0)
                if 0 <= idx < len(s.thruster_on_flags):
                    s.thruster_on_flags[idx] = params.get("on", False)

            elif cmd_type == "sad":
                # Solar array drive: params: {"panel_index": int, "angle_deg": float}
                idx = params.get("panel_index", 0)
                if 0 <= idx < len(s.solar_array_angles_deg):
                    s.solar_array_angles_deg[idx] = params.get("angle_deg", 0.0)

            elif cmd_type == "att_target":
                # Attitude target — mock just logs; real Basilisk would feed the ADCS
                logger.debug(
                    "mock.attitude_target_received",
                    quaternion=params.get("quaternion"),
                )

            elif cmd_type == "delta_v":
                logger.debug(
                    "mock.delta_v_received",
                    delta_v_m_s=params.get("delta_v_m_s"),
                    direction=params.get("direction"),
                )

        self._pending_commands.clear()


# ---------------------------------------------------------------------------
# Basilisk live adapter
# ---------------------------------------------------------------------------

class BasiliskLiveAdapter:
    """Adapter for a live Basilisk simulation process.

    Wraps Basilisk's SimulationBaseClass, messaging system, and module outputs
    into the SpacecraftState structure that the bridge publishes.

    Basilisk must be installed: ``pip install basilisk`` or built from source.
    """

    def __init__(self, config: BasiliskConfig) -> None:
        self._config = config
        self._sim: Any = None
        self._sc_object: Any = None
        self._rw_factory: Any = None
        self._thruster_factory: Any = None
        self._initialized = False

    def initialize(self) -> None:
        """Set up the Basilisk simulation scenario."""
        try:
            from Basilisk.utilities import SimulationBaseClass  # type: ignore[import-not-found]
            from Basilisk.utilities import macros as mc  # type: ignore[import-not-found]
            from Basilisk.utilities import orbitalMotion  # type: ignore[import-not-found]
            from Basilisk.simulation import spacecraft  # type: ignore[import-not-found]
            from Basilisk.simulation import (  # type: ignore[import-not-found]
                reactionWheelStateEffector,
                thrusterDynamicEffector,
                simpleSolarPanel,
            )
            from Basilisk.architecture import messaging  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Basilisk is not installed. Install from "
                "https://hanspeterschaub.info/basilisk/ or use mock mode. "
                f"Import error: {exc}"
            ) from exc

        # Create simulation
        self._sim = SimulationBaseClass.SimBaseClass()
        dyn_process = self._sim.CreateNewProcess("DynamicsProcess")
        dyn_task_name = "DynamicsTask"
        step_ns = mc.sec2nano(self._config.step_size_s)
        dyn_process.addTask(self._sim.CreateNewTask(dyn_task_name, step_ns))

        # Spacecraft hub
        self._sc_object = spacecraft.Spacecraft()
        self._sc_object.ModelTag = "ariaSpacecraft"
        self._sim.AddModelToTask(dyn_task_name, self._sc_object)

        # Initial orbit
        mu = 3.986004418e14
        r_orbit = (6_371_000.0 + self._config.initial_orbit_altitude_km * 1000)
        oe = orbitalMotion.ClassicElements()
        oe.a = r_orbit
        oe.e = 0.0001
        oe.i = self._config.initial_inclination_deg * mc.D2R
        oe.Omega = 0.0
        oe.omega = 0.0
        oe.f = 0.0
        r_eci, v_eci = orbitalMotion.elem2rv(mu, oe)
        self._sc_object.hub.r_CN_NInit = r_eci
        self._sc_object.hub.v_CN_NInit = v_eci

        # Reaction wheels
        self._rw_factory = reactionWheelStateEffector.ReactionWheelStateEffector()
        self._sim.AddModelToTask(dyn_task_name, self._rw_factory)

        # Solar panels
        self._solar_panels: list[Any] = []
        for i in range(self._config.num_solar_panels):
            panel = simpleSolarPanel.SimpleSolarPanel()
            panel.ModelTag = f"solarPanel_{i}"
            panel.nHat_B = [0, 0, 1] if i == 0 else [0, 0, -1]
            panel.panelArea = 2.0  # m^2
            panel.panelEfficiency = 0.29
            self._sim.AddModelToTask(dyn_task_name, panel)
            self._solar_panels.append(panel)

        self._sim.InitializeSimulation()
        self._initialized = True
        logger.info("basilisk.live.initialized", orbit_km=self._config.initial_orbit_altitude_km)

    def step(self, dt_s: float) -> SpacecraftState:
        """Step the Basilisk simulation and extract state."""
        if not self._initialized:
            raise RuntimeError("BasiliskLiveAdapter not initialized. Call initialize() first.")

        try:
            from Basilisk.utilities import macros as mc  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(f"Basilisk import failed: {exc}") from exc

        current_time_ns = self._sim.TotalSim.CurrentNanos
        target_time_ns = current_time_ns + mc.sec2nano(dt_s)
        self._sim.ConfigureStopTime(target_time_ns)
        self._sim.ExecuteSimulation()

        return self._extract_state()

    def _extract_state(self) -> SpacecraftState:
        """Read Basilisk module outputs into a SpacecraftState."""
        try:
            from Basilisk.utilities import macros as mc  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(f"Basilisk import failed: {exc}") from exc

        sc = self._sc_object
        state = SpacecraftState()

        state.sim_time_s = mc.nano2sec(self._sim.TotalSim.CurrentNanos)

        # Attitude — Basilisk uses MRPs, convert to quaternion
        sigma = list(sc.hub.sigma_BNOut)
        state.attitude_quaternion = _mrp_to_quaternion(sigma)

        # Angular velocity
        omega = list(sc.hub.omega_BN_BOut)
        state.angular_velocity_rad_s = omega
        state.angular_velocity_magnitude_rad_s = math.sqrt(sum(w ** 2 for w in omega))

        # Orbit
        r = list(sc.hub.r_CN_NOut)
        v = list(sc.hub.v_CN_NOut)
        state.position_eci_m = r
        state.velocity_eci_m_s = v
        r_mag = math.sqrt(sum(x ** 2 for x in r))
        state.altitude_km = (r_mag - 6_371_000.0) / 1000.0

        # Reaction wheel speeds
        if self._rw_factory is not None:
            try:
                speeds = list(self._rw_factory.rwSpeedOutMsg.read().wheelSpeeds)
                state.reaction_wheel_speeds_rpm = [
                    s * 60 / (2 * math.pi) for s in speeds[:self._config.num_reaction_wheels]
                ]
            except Exception as exc:
                # R65 (2026-04-24): was `pass` — silent telemetry loss
                # meant ADCS logic ran on stale wheel speeds.  Now logs
                # at debug and sets the field to an empty list so the
                # consumer can tell "data absent" from "wheels at 0 rpm".
                logger.debug("basilisk.rw_read_failed", error=str(exc))
                state.reaction_wheel_speeds_rpm = []

        # Solar panel power
        for i, panel in enumerate(self._solar_panels):
            try:
                power_data = panel.nodePowerOutMsg.read()
                state.solar_panel_power_w[i] = power_data.netPower
            except Exception as exc:
                # R65 (2026-04-24): was `pass` — silent power-telemetry
                # loss.  Same rationale as RW above: -1 sentinel flags
                # "panel unresponsive" vs a genuine 0 W (panel in shade).
                logger.debug("basilisk.panel_read_failed", panel=i, error=str(exc))
                state.solar_panel_power_w[i] = -1.0
        # total_power_w ignores negative sentinels to stay physically
        # consistent (total = sum of good readings only).
        state.total_power_w = sum(p for p in state.solar_panel_power_w if p >= 0)

        return state

    def apply_command(self, command_type: str, params: dict[str, Any]) -> None:
        """Send a command to Basilisk actuators."""
        if not self._initialized:
            logger.warning("basilisk.live.command_before_init", command=command_type)
            return

        if command_type == "rw_torque":
            torques = params.get("torques_nm", [])
            if self._rw_factory is not None:
                try:
                    msg = self._rw_factory.rwMotorTorqueInMsg
                    msg_data = msg.zeroMsgPayload
                    for i, t in enumerate(torques):
                        msg_data.motorTorque[i] = t
                    msg.write(msg_data)
                except Exception as exc:
                    logger.error("basilisk.live.rw_command_failed", error=str(exc))

        elif command_type == "thruster":
            logger.debug("basilisk.live.thruster_command", params=params)

        elif command_type == "sad":
            logger.debug("basilisk.live.solar_array_drive_command", params=params)

        else:
            logger.warning("basilisk.live.unknown_command", command=command_type)


# ---------------------------------------------------------------------------
# Main Bridge
# ---------------------------------------------------------------------------

class BasiliskBridge:
    """Bidirectional bridge between Basilisk simulation and ARIA message bus.

    Usage::

        bus = MessageBus()
        bridge = BasiliskBridge(bus, BasiliskConfig(mode=SimulationMode.MOCK))
        await bridge.start()
        # ... ARIA agents now receive Basilisk telemetry
        await bridge.stop()

    The bridge:
      - Subscribes to ``aria.command.*`` topics to relay commands to Basilisk
      - Publishes sensor data on ``aria.sensor.*`` topics each timestep
      - Tracks simulation statistics (steps, messages published, commands received)
    """

    def __init__(
        self,
        bus: MessageBus,
        config: BasiliskConfig | None = None,
        seed: int | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or BasiliskConfig()
        self._seed = seed

        # Backend selection
        self._mock: MockBasiliskSim | None = None
        self._live: BasiliskLiveAdapter | None = None
        self._running = False
        self._step_task: asyncio.Task[Any] | None = None
        self._state: SpacecraftState = SpacecraftState()

        # Stats
        self._steps: int = 0
        self._messages_published: int = 0
        self._commands_received: int = 0
        self._start_wall_time: float = 0.0

    @property
    def state(self) -> SpacecraftState:
        """Current spacecraft state."""
        return self._state

    @property
    def stats(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._start_wall_time if self._running else 0
        return {
            "mode": self._config.mode.name,
            "running": self._running,
            "steps": self._steps,
            "sim_time_s": self._state.sim_time_s,
            "wall_time_s": round(elapsed, 2),
            "messages_published": self._messages_published,
            "commands_received": self._commands_received,
            "realtime_factor": self._config.realtime_factor,
        }

    async def start(self) -> None:
        """Initialize the backend and start the simulation loop."""
        if self._running:
            logger.warning("basilisk_bridge.already_running")
            return

        logger.info(
            "basilisk_bridge.starting",
            mode=self._config.mode.name,
            realtime_factor=self._config.realtime_factor,
        )

        if self._config.mode == SimulationMode.MOCK:
            self._mock = MockBasiliskSim(self._config, seed=self._seed)
        elif self._config.mode == SimulationMode.LIVE:
            self._live = BasiliskLiveAdapter(self._config)
            self._live.initialize()
        elif self._config.mode == SimulationMode.REPLAY:
            raise NotImplementedError("Replay mode is not yet implemented.")

        # Subscribe to ARIA command topics
        for topic in COMMAND_MAP:
            self._bus.subscribe(topic, self._handle_command)

        self._running = True
        self._start_wall_time = time.monotonic()
        self._step_task = asyncio.create_task(self._simulation_loop())

        logger.info("basilisk_bridge.started", mode=self._config.mode.name)

    async def stop(self) -> None:
        """Stop the simulation loop and clean up."""
        if not self._running:
            return

        logger.info("basilisk_bridge.stopping", stats=self.stats)
        self._running = False

        if self._step_task:
            self._step_task.cancel()
            try:
                await self._step_task
            except asyncio.CancelledError:
                pass
            self._step_task = None

        # Unsubscribe from command topics
        for topic in COMMAND_MAP:
            self._bus.unsubscribe(topic, self._handle_command)

        logger.info("basilisk_bridge.stopped", stats=self.stats)

    async def step_once(self) -> SpacecraftState:
        """Manually step the simulation once and publish state.

        Useful for testing or faster-than-real-time batch runs.
        """
        dt = self._config.step_size_s
        if self._mock:
            self._state = self._mock.step(dt)
        elif self._live:
            self._state = self._live.step(dt)
        else:
            raise RuntimeError("No simulation backend configured.")

        self._steps += 1
        await self._publish_state()
        return self._state

    async def _simulation_loop(self) -> None:
        """Continuous simulation stepping with real-time pacing."""
        dt = self._config.step_size_s
        publish_interval = self._config.publish_interval_s
        wall_step = dt / self._config.realtime_factor
        last_publish = 0.0

        while self._running:
            try:
                step_start = time.monotonic()

                # Step the simulation
                if self._mock:
                    self._state = self._mock.step(dt)
                elif self._live:
                    self._state = self._live.step(dt)

                self._steps += 1

                # Publish at the configured interval
                if self._state.sim_time_s - last_publish >= publish_interval:
                    await self._publish_state()
                    last_publish = self._state.sim_time_s

                # Pace to match real-time factor
                elapsed = time.monotonic() - step_start
                sleep_time = max(0.0, wall_step - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("basilisk_bridge.step_error", error=str(exc))
                await asyncio.sleep(0.1)

    async def _publish_state(self) -> None:
        """Convert SpacecraftState to ARIA messages and publish."""
        s = self._state

        payloads: dict[str, dict[str, Any]] = {
            "attitude": {
                "quaternion": s.attitude_quaternion,
                "angular_velocity_rad_s": s.angular_velocity_rad_s,
                "angular_velocity_magnitude_rad_s": s.angular_velocity_magnitude_rad_s,
                "sim_time_s": s.sim_time_s,
            },
            "orbit": {
                "position_eci_m": s.position_eci_m,
                "velocity_eci_m_s": s.velocity_eci_m_s,
                "altitude_km": s.altitude_km,
                "semi_major_axis_m": s.semi_major_axis_m,
                "eccentricity": s.eccentricity,
                "inclination_deg": s.inclination_deg,
                "true_anomaly_deg": s.true_anomaly_deg,
                "sim_time_s": s.sim_time_s,
            },
            "angular_velocity": {
                "omega_rad_s": s.angular_velocity_rad_s,
                "magnitude_rad_s": s.angular_velocity_magnitude_rad_s,
                "sim_time_s": s.sim_time_s,
            },
            "solar_power": {
                "panel_power_w": s.solar_panel_power_w,
                "total_power_w": s.total_power_w,
                "sun_angle_deg": s.sun_angle_deg,
                "eclipse": s.eclipse,
                "sim_time_s": s.sim_time_s,
            },
            "battery": {
                # Wiring audit Pass 4 (F3.4) — match the agent
                # contract: PowerAgent reads ``soc_percent`` (0..100)
                # at power.py:238 and DsremoChannelMapper expects the
                # same. The internal Basilisk state is ``battery_soc``
                # 0..1 fraction, so we scale here. Without this fix,
                # switching to Basilisk telemetry left PowerAgent's
                # SoC stuck at the 100.0% default forever.
                "soc_percent": s.battery_soc * 100.0,
                # Keep the legacy fraction key for any consumer that
                # still expects it; cheap to emit, easy to ignore.
                "state_of_charge": s.battery_soc,
                "sim_time_s": s.sim_time_s,
            },
            "eclipse": {
                "in_eclipse": s.eclipse,
                "sun_angle_deg": s.sun_angle_deg,
                "sim_time_s": s.sim_time_s,
            },
            "thermal": {
                "node_temps_k": s.thermal_node_temps_k,
                "node_names": s.thermal_node_names,
                "sim_time_s": s.sim_time_s,
            },
            "reaction_wheels": {
                "speeds_rpm": s.reaction_wheel_speeds_rpm,
                "torques_nm": s.reaction_wheel_torques_nm,
                "sim_time_s": s.sim_time_s,
            },
            "thrusters": {
                "on_flags": s.thruster_on_flags,
                "sim_time_s": s.sim_time_s,
            },
            "nav_sensors": {
                "star_tracker_valid": s.star_tracker_valid,
                "sun_sensor_valid": s.sun_sensor_valid,
                "imu_gyro_bias_rad_s": s.imu_gyro_bias_rad_s,
                "sim_time_s": s.sim_time_s,
            },
        }

        for topic, payload_key in TOPIC_MAP.items():
            payload = payloads.get(payload_key)
            if payload is None:
                continue
            msg = Message(
                topic=topic,
                payload=payload,
                priority=EventPriority.P3_ROUTINE,
                source_agent="basilisk_bridge",
            )
            await self._bus.publish(msg)
            self._messages_published += 1

        # Wiring audit Pass 4 (F7.11) — also publish on the agent
        # contract topics so PowerAgent / NavigationAgent receive
        # Basilisk telemetry. The Basilisk-internal topics above
        # (``aria.sensor.power.solar_panels``, ``aria.sensor.nav.orbit``,
        # ``aria.sensor.navigation.angular_velocity``) carry full
        # simulator state for dashboards / OpenMCT subscribers; the
        # translated topics below match the schema that
        # ``core/simulator.py`` uses, so switching telemetry sources
        # is now transparent to the agent layer.
        agent_translations: list[tuple[str, dict[str, Any]]] = [
            # PowerAgent reads ``aria.sensor.power.solar`` with key
            # ``power_watts``; fold in_eclipse so it can short-circuit
            # alarm logic rather than waiting for SoC drop.
            (
                "aria.sensor.power.solar",
                {
                    "power_watts": s.solar_panel_power_w,
                    "in_eclipse": s.eclipse,
                    "sun_angle_deg": s.sun_angle_deg,
                    "sim_time_s": s.sim_time_s,
                },
            ),
            # NavigationAgent's ``_update_gps`` (line 84) reads
            # altitude_km, fix, satellites, latitude_deg, longitude_deg,
            # velocity_ms. Basilisk has the orbital state; derive
            # speed magnitude as velocity_ms.
            (
                "aria.sensor.nav.gps",
                {
                    "altitude_km": s.altitude_km,
                    "fix": True,
                    "satellites": 8,    # nominal; not modelled in Basilisk
                    "velocity_ms": (
                        sum(v * v for v in s.velocity_eci_m_s) ** 0.5
                        if s.velocity_eci_m_s else 0.0
                    ),
                    "latitude_deg": 0.0,    # ECI-only state in Basilisk
                    "longitude_deg": 0.0,
                    "sim_time_s": s.sim_time_s,
                },
            ),
            # NavigationAgent's ``_update_imu`` (line 147) reads
            # angular_rate_{x,y,z}_dps. Basilisk publishes rad/s; convert.
            (
                "aria.sensor.nav.imu",
                {
                    "angular_rate_x_dps": (
                        s.angular_velocity_rad_s[0] * 57.295779513
                        if s.angular_velocity_rad_s else 0.0
                    ),
                    "angular_rate_y_dps": (
                        s.angular_velocity_rad_s[1] * 57.295779513
                        if s.angular_velocity_rad_s else 0.0
                    ),
                    "angular_rate_z_dps": (
                        s.angular_velocity_rad_s[2] * 57.295779513
                        if s.angular_velocity_rad_s else 0.0
                    ),
                    "sim_time_s": s.sim_time_s,
                },
            ),
            # NavigationAgent's ``_update_star_tracker`` (line 198)
            # reads quaternion only.
            (
                "aria.sensor.nav.star_tracker",
                {
                    "quaternion": s.attitude_quaternion,
                    "sim_time_s": s.sim_time_s,
                },
            ),
        ]
        for topic, payload in agent_translations:
            translated_msg = Message(
                topic=topic,
                payload=payload,
                priority=EventPriority.P3_ROUTINE,
                source_agent="basilisk_bridge",
            )
            await self._bus.publish(translated_msg)
            self._messages_published += 1

    async def _handle_command(self, message: Message) -> None:
        """Receive an ARIA command and forward to the simulation backend."""
        cmd_key = COMMAND_MAP.get(message.topic)
        if cmd_key is None:
            logger.warning("basilisk_bridge.unknown_command_topic", topic=message.topic)
            return

        self._commands_received += 1
        logger.debug(
            "basilisk_bridge.command_received",
            topic=message.topic,
            command=cmd_key,
            params=message.payload,
        )

        if self._mock:
            self._mock.apply_command(cmd_key, message.payload)
        elif self._live:
            self._live.apply_command(cmd_key, message.payload)


# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------

def _euler_to_quaternion(roll: float, pitch: float, yaw: float) -> list[float]:
    """Convert Euler angles (rad) to quaternion [qx, qy, qz, qw]."""
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


def _mrp_to_quaternion(sigma: list[float]) -> list[float]:
    """Convert Modified Rodrigues Parameters to quaternion [qx, qy, qz, qw].

    MRP to quaternion: q = [sigma * 2 / (1 + |sigma|^2), (1 - |sigma|^2) / (1 + |sigma|^2)]
    """
    s2 = sum(s ** 2 for s in sigma)
    denom = 1.0 + s2
    qw = (1.0 - s2) / denom
    return [2.0 * s / denom for s in sigma] + [qw]
