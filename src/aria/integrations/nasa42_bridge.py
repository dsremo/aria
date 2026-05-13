"""NASA 42 Spacecraft Simulator Bridge for ARIA.

NASA 42 is a comprehensive spacecraft attitude and orbit dynamics simulator
from NASA Goddard Space Flight Center. It uses socket-based IPC for data
exchange and configuration files for scenario definition.

This bridge:
  1. Generates NASA 42 config files (Inp_Sim.txt, SC_*.txt, Orb_*.txt)
  2. Parses NASA 42 output files (spacecraft state, orbital elements)
  3. Connects via IPC socket to receive real-time attitude/orbit data
  4. Maps NASA 42 state vectors to ARIA bus topics
  5. Supports generating 42 scenarios from ARIA MissionConfig

NASA 42 features not in Basilisk:
  - Multi-body environments (solar system ephemeris: DE430/DE440)
  - IGRF magnetic field model
  - Solar pressure + albedo effects
  - Multi-spacecraft simulation
  - Ground station contact analysis

Reference: https://github.com/ericstoneking/42
"""

from __future__ import annotations

import asyncio
import math
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Nasa42OrbitConfig:
    """Orbit configuration for NASA 42."""
    orbit_type: str = "FIXED"  # FIXED, FLIGHT, CENTRAL, THREE_BODY
    world: str = "EARTH"
    # Keplerian elements
    semi_major_axis_km: float = 6778.0  # Re + 400 km
    eccentricity: float = 0.0001
    inclination_deg: float = 51.6
    raan_deg: float = 0.0
    arg_periapsis_deg: float = 0.0
    true_anomaly_deg: float = 0.0


@dataclass
class Nasa42SpacecraftConfig:
    """Spacecraft configuration for NASA 42."""
    name: str = "ARIA-SC"
    mass_kg: float = 500.0
    # Inertia (kg·m²)
    inertia_xx: float = 100.0
    inertia_yy: float = 100.0
    inertia_zz: float = 80.0
    # Geometry
    num_bodies: int = 1
    # Attitude mode
    attitude_type: str = "QUATERNION"  # QUATERNION, TRN_MATRIX
    # Initial attitude (quaternion)
    q0: float = 1.0
    q1: float = 0.0
    q2: float = 0.0
    q3: float = 0.0
    # Angular velocity (rad/s)
    omega_x: float = 0.0
    omega_y: float = 0.0
    omega_z: float = 0.0


@dataclass
class Nasa42SimConfig:
    """Complete simulation configuration for NASA 42."""
    time_mode: str = "FAST"  # FAST, REAL, EXTERNAL
    duration_s: float = 10000.0
    step_size_s: float = 0.1
    output_interval_s: float = 10.0
    graphics: bool = False
    rng_seed: int = 0
    date: tuple[int, int, int] = (4, 8, 2024)  # Month, Day, Year
    time_utc: tuple[int, int, float] = (0, 0, 0.0)  # Hr, Min, Sec
    orbit: Nasa42OrbitConfig = field(default_factory=Nasa42OrbitConfig)
    spacecraft: Nasa42SpacecraftConfig = field(default_factory=Nasa42SpacecraftConfig)
    # IPC
    enable_ipc: bool = False
    ipc_host: str = "localhost"
    ipc_port: int = 10001


@dataclass
class Nasa42State:
    """Parsed spacecraft state from NASA 42."""
    time_s: float = 0.0
    # Position (ECI, meters)
    position_m: list[float] = field(default_factory=lambda: [0, 0, 0])
    # Velocity (ECI, m/s)
    velocity_m_s: list[float] = field(default_factory=lambda: [0, 0, 0])
    # Attitude quaternion (scalar-first)
    quaternion: list[float] = field(default_factory=lambda: [1, 0, 0, 0])
    # Angular velocity (body frame, rad/s)
    omega_rad_s: list[float] = field(default_factory=lambda: [0, 0, 0])
    # Orbital elements
    semi_major_axis_km: float = 0.0
    eccentricity: float = 0.0
    inclination_deg: float = 0.0
    raan_deg: float = 0.0
    arg_periapsis_deg: float = 0.0
    true_anomaly_deg: float = 0.0
    # Derived
    altitude_km: float = 0.0
    orbital_velocity_m_s: float = 0.0


class Nasa42ScriptGenerator:
    """Generates NASA 42 configuration files for various missions."""

    def generate_sim_config(self, config: Nasa42SimConfig, output_dir: str | Path) -> str:
        """Generate Inp_Sim.txt."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        m, d, y = config.date
        h, mn, s = config.time_utc

        content = f"""<<<<<<<<<<<<<<<<<  42: The Mostly Harmless Simulator  >>>>>>>>>>>>>>>>>
************************** Simulation Control **************************
{config.time_mode:30s}!  Time Mode (FAST, REAL, EXTERNAL, or NOS3)
{config.duration_s:<10.1f} {config.step_size_s:<10.1f}       !  Sim Duration, Step Size [sec]
{config.output_interval_s:<10.1f}                    !  File Output Interval [sec]
{config.rng_seed:<10d}                    !  RNG Seed
{"TRUE" if config.graphics else "FALSE":30s}!  Graphics Front End?
Inp_Cmd.txt                     !  Command Script File Name
**************************  Reference Orbits  **************************
1                               !  Number of Reference Orbits
TRUE   Orb_Mission.txt          !  Input file name for Orb 0
*****************************  Spacecraft  *****************************
1                               !  Number of Spacecraft
TRUE 0 SC_Mission.txt           !  Existence, RefOrb, Input file for SC 0
***************************** Environment  *****************************
{m:02d} {d:02d} {y:04d}                      !  Date (UTC) (Month, Day, Year)
{h:02d} {mn:02d} {s:05.2f}                      !  Time (UTC) (Hr,Min,Sec)
37.0                            !  Leap Seconds (sec)
NOMINAL                         !  F10.7, Ap (USER, NOMINAL or TWOSIGMA)
230.0                           !  USER-provided F10.7
100.0                           !  USER-provided Ap
IGRF                            !  Magfield (NONE,DIPOLE,IGRF)
8   8                           !  IGRF Degree and Order (<=10)
8   8                           !  Earth Gravity Model N and M (<=18)
2   0                           !  Mars Gravity Model N and M (<=18)
2   0                           !  Luna Gravity Model N and M (<=18)
TRUE    TRUE                    !  Aerodynamic Forces & Torques (Shadows)
TRUE                            !  Gravity Gradient Torques
TRUE    TRUE                    !  Solar Pressure Forces & Torques (Shadows)
TRUE                            !  Residual Magnetic Moment Torques
TRUE                            !  Gravity Perturbation Forces
FALSE                           !  Thruster Plume Forces & Torques
FALSE                           !  Contact Forces and Torques
FALSE                           !  CFD Slosh Forces and Torques
FALSE                           !  Albedo Effect on CSS Measurements
FALSE                           !  Output Environmental Torques to Files
********************* Celestial Bodies of Interest *********************
MEAN                            !  Ephem Option (MEAN, DE430, DE440)
TRUE                            !  Mercury
TRUE                            !  Venus
TRUE                            !  Earth
TRUE                            !  Mars
TRUE                            !  Jupiter
TRUE                            !  Saturn
FALSE                           !  Uranus
FALSE                           !  Neptune
FALSE                           !  Pluto
TRUE                            !  Luna
"""
        path = output_dir / "Inp_Sim.txt"
        path.write_text(content)
        return str(path)

    def generate_orbit_config(self, config: Nasa42OrbitConfig, output_dir: str | Path) -> str:
        """Generate Orb_Mission.txt."""
        output_dir = Path(output_dir)

        content = f"""<<<<<<<<<<<<<<<<<  42: Orbit Configuration  >>>>>>>>>>>>>>>>>
{config.orbit_type:30s}!  Orbit Type (FIXED, FLIGHT, CENTRAL, THREE_BODY)
{config.world:30s}!  World
TRUE                            !  Propagate Orbit
ENCKE                           !  Prop Method (COWELL, ENCKE)
**************************  Keplerian Elements  **************************
{config.semi_major_axis_km:<20.3f}          !  Semi-Major Axis (km)
{config.eccentricity:<20.6f}          !  Eccentricity
{config.inclination_deg:<20.4f}          !  Inclination (deg)
{config.raan_deg:<20.4f}          !  RAAN (deg)
{config.arg_periapsis_deg:<20.4f}          !  Argument of Periapsis (deg)
{config.true_anomaly_deg:<20.4f}          !  True Anomaly (deg)
"""
        path = output_dir / "Orb_Mission.txt"
        path.write_text(content)
        return str(path)

    def generate_spacecraft_config(
        self, config: Nasa42SpacecraftConfig, output_dir: str | Path
    ) -> str:
        """Generate SC_Mission.txt (simplified)."""
        output_dir = Path(output_dir)

        content = f"""<<<<<<<<<<<<<<<<<  42: Spacecraft Configuration  >>>>>>>>>>>>>>>>>
"{config.name}"                 !  Description
1                               !  Number of Bodies
FALSE                           !  Flex Active
****************************  Body 0  ****************************
{config.mass_kg:<20.1f}          !  Mass (kg)
{config.inertia_xx:<10.3f} {config.inertia_yy:<10.3f} {config.inertia_zz:<10.3f}  !  Moments of Inertia (kg-m^2)
0.0       0.0       0.0         !  Products of Inertia (kg-m^2)
0.0       0.0       0.0         !  Location of Body CM (m)
0                               !  Number of Wheels
0                               !  Number of MTBs
0                               !  Number of Thrusters
0                               !  Number of Gyro Axes
0                               !  Number of Magnetometer Axes
0                               !  Number of CSS
0                               !  Number of Fine Sun Sensors
0                               !  Number of Star Trackers
0                               !  Number of GPS Receivers
0                               !  Number of Accelerometers
****************************  Initial Attitude  ****************************
QA                              !  Attitude Type (Q, A, C)
{config.q0:<10.6f}  {config.q1:<10.6f}  {config.q2:<10.6f}  {config.q3:<10.6f}  !  Quaternion
{config.omega_x:<10.6f}  {config.omega_y:<10.6f}  {config.omega_z:<10.6f}  !  Angular Velocity (rad/s)
"""
        path = output_dir / "SC_Mission.txt"
        path.write_text(content)
        return str(path)

    def generate_ipc_config(self, config: Nasa42SimConfig, output_dir: str | Path) -> str:
        """Generate Inp_IPC.txt for socket communication."""
        output_dir = Path(output_dir)

        num_sockets = 1 if config.enable_ipc else 0
        mode = "TX" if config.enable_ipc else "OFF"

        content = f"""<<<<<<<<<<<<<<< 42: InterProcess Comm Configuration File >>>>>>>>>>>>>>>>
{num_sockets}                                       ! Number of Sockets
**********************************  IPC 0   *****************************
{mode:36s}! IPC Mode (OFF,TX,RX,TXRX,WRITEFILE,READFILE)
"State00.42"                            ! File name for WRITE or READ
SERVER                                  ! Socket Role (SERVER,CLIENT,GMSEC_CLIENT)
{config.ipc_host:14s}  {config.ipc_port}                     ! Server Host Name, Port
TRUE                                    ! Allow Blocking (i.e. wait on RX)
FALSE                                   ! Echo to stdout
3                                       ! Number of TX prefixes
"SC"                                    ! Prefix 0
"Orb"                                   ! Prefix 1
"World"                                 ! Prefix 2
"""
        path = output_dir / "Inp_IPC.txt"
        path.write_text(content)
        return str(path)

    def generate_full_scenario(
        self, config: Nasa42SimConfig, output_dir: str | Path
    ) -> list[str]:
        """Generate all config files for a complete NASA 42 scenario."""
        files = []
        files.append(self.generate_sim_config(config, output_dir))
        files.append(self.generate_orbit_config(config.orbit, output_dir))
        files.append(self.generate_spacecraft_config(config.spacecraft, output_dir))
        files.append(self.generate_ipc_config(config, output_dir))
        return files


class Nasa42OutputParser:
    """Parses NASA 42 output files and IPC data."""

    @staticmethod
    def parse_state_line(line: str) -> Nasa42State | None:
        """Parse a NASA 42 IPC state line (SC format).

        Format: SC[0].PosN = X Y Z (meters, ECI)
                SC[0].VelN = X Y Z (m/s, ECI)
                SC[0].qbn = q0 q1 q2 q3 (quaternion body-to-inertial)
                SC[0].wbn = wx wy wz (rad/s, body)
        """
        if not line or "=" not in line:
            return None

        try:
            key, value = line.split("=", 1)
            key = key.strip()
            values = [float(v) for v in value.strip().split()]
        except (ValueError, IndexError):
            return None

        state = Nasa42State()

        if "PosN" in key and len(values) >= 3:
            state.position_m = values[:3]
            r = math.sqrt(sum(v**2 for v in values[:3]))
            state.altitude_km = r / 1000.0 - 6371.0
        elif "VelN" in key and len(values) >= 3:
            state.velocity_m_s = values[:3]
            state.orbital_velocity_m_s = math.sqrt(sum(v**2 for v in values[:3]))
        elif "qbn" in key and len(values) >= 4:
            state.quaternion = values[:4]
        elif "wbn" in key and len(values) >= 3:
            state.omega_rad_s = values[:3]

        return state

    @staticmethod
    def parse_output_file(filepath: str | Path) -> list[Nasa42State]:
        """Parse a NASA 42 WRITEFILE output."""
        filepath = Path(filepath)
        if not filepath.exists():
            return []

        states: list[Nasa42State] = []
        current_state = Nasa42State()
        time_s = 0.0

        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parsed = Nasa42OutputParser.parse_state_line(line)
                if parsed:
                    # Merge into current state
                    if parsed.position_m != [0, 0, 0]:
                        current_state.position_m = parsed.position_m
                        current_state.altitude_km = parsed.altitude_km
                    if parsed.velocity_m_s != [0, 0, 0]:
                        current_state.velocity_m_s = parsed.velocity_m_s
                        current_state.orbital_velocity_m_s = parsed.orbital_velocity_m_s
                    if parsed.quaternion != [1, 0, 0, 0]:
                        current_state.quaternion = parsed.quaternion
                    if parsed.omega_rad_s != [0, 0, 0]:
                        current_state.omega_rad_s = parsed.omega_rad_s

                if "TIME" in line.upper() or line.startswith("---"):
                    # New timestep marker
                    if current_state.position_m != [0, 0, 0]:
                        current_state.time_s = time_s
                        states.append(current_state)
                        current_state = Nasa42State()
                        time_s += 10.0  # Default interval

        # Don't forget last state
        if current_state.position_m != [0, 0, 0]:
            current_state.time_s = time_s
            states.append(current_state)

        return states


class Nasa42Bridge:
    """Main bridge between NASA 42 and ARIA.

    Usage:
        bridge = Nasa42Bridge()

        # Generate scenario files
        config = Nasa42SimConfig(
            orbit=Nasa42OrbitConfig(semi_major_axis_km=6778, inclination_deg=51.6),
        )
        files = bridge.generate_scenario(config, "/tmp/42_scenario")

        # Parse pre-computed output
        states = bridge.load_output("/path/to/State00.42")

        # Convert to ARIA format
        for state in states:
            nav_msg = bridge.state_to_aria_nav(state)
            att_msg = bridge.state_to_aria_attitude(state)
    """

    def __init__(self) -> None:
        self._generator = Nasa42ScriptGenerator()
        self._parser = Nasa42OutputParser()

    def generate_scenario(
        self, config: Nasa42SimConfig, output_dir: str | Path
    ) -> list[str]:
        """Generate all NASA 42 config files for a scenario."""
        return self._generator.generate_full_scenario(config, output_dir)

    def load_output(self, filepath: str | Path) -> list[Nasa42State]:
        """Load and parse NASA 42 output file."""
        return self._parser.parse_output_file(filepath)

    @staticmethod
    def state_to_aria_nav(state: Nasa42State) -> dict[str, Any]:
        """Convert NASA 42 state to ARIA navigation message payload."""
        return {
            "position_eci_m": state.position_m,
            "velocity_eci_m_s": state.velocity_m_s,
            "altitude_km": state.altitude_km,
            "orbital_velocity_m_s": state.orbital_velocity_m_s,
        }

    @staticmethod
    def state_to_aria_attitude(state: Nasa42State) -> dict[str, Any]:
        """Convert NASA 42 state to ARIA attitude message payload."""
        q = state.quaternion
        # Quaternion to Euler (scalar-first)
        q0, q1, q2, q3 = q
        roll = math.degrees(math.atan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1**2 + q2**2)))
        sinp = 2 * (q0 * q2 - q3 * q1)
        sinp = max(-1, min(1, sinp))
        pitch = math.degrees(math.asin(sinp))
        yaw = math.degrees(math.atan2(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2**2 + q3**2)))

        return {
            "quaternion": q,
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
            "angular_rate_rad_s": state.omega_rad_s,
        }

    @staticmethod
    def iss_config() -> Nasa42SimConfig:
        """Pre-built ISS orbit configuration."""
        return Nasa42SimConfig(
            duration_s=5520.0,  # One orbit
            step_size_s=0.1,
            output_interval_s=10.0,
            graphics=False,
            orbit=Nasa42OrbitConfig(
                semi_major_axis_km=6778.0,
                eccentricity=0.0001,
                inclination_deg=51.6,
            ),
            spacecraft=Nasa42SpacecraftConfig(
                name="ISS",
                mass_kg=420000.0,
                inertia_xx=100000.0,
                inertia_yy=100000.0,
                inertia_zz=80000.0,
            ),
        )

    @staticmethod
    def lunar_transfer_config() -> Nasa42SimConfig:
        """Pre-built lunar transfer orbit configuration."""
        return Nasa42SimConfig(
            duration_s=345600.0,  # 4 days
            step_size_s=1.0,
            output_interval_s=60.0,
            graphics=False,
            orbit=Nasa42OrbitConfig(
                orbit_type="FLIGHT",
                semi_major_axis_km=200000.0,  # Translunar
                eccentricity=0.97,
                inclination_deg=28.5,
            ),
            spacecraft=Nasa42SpacecraftConfig(
                name="Lunar-Transfer",
                mass_kg=30000.0,
            ),
        )
