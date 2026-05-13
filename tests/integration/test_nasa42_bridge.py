"""Tests for NASA 42 spacecraft simulator bridge."""

import math
import os
import tempfile

import pytest

from aria.integrations.nasa42_bridge import (
    Nasa42Bridge,
    Nasa42OrbitConfig,
    Nasa42OutputParser,
    Nasa42ScriptGenerator,
    Nasa42SimConfig,
    Nasa42SpacecraftConfig,
    Nasa42State,
)


class TestScriptGeneration:
    """Test NASA 42 config file generation."""

    def test_generate_sim_config(self) -> None:
        gen = Nasa42ScriptGenerator()
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_sim_config(Nasa42SimConfig(), td)
            assert os.path.exists(path)
            content = open(path).read()
            assert "FAST" in content
            assert "10000.0" in content

    def test_generate_orbit_config(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42OrbitConfig(semi_major_axis_km=6778, inclination_deg=51.6)
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_orbit_config(config, td)
            content = open(path).read()
            assert "6778" in content
            assert "51.6" in content

    def test_generate_spacecraft_config(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SpacecraftConfig(name="TestSC", mass_kg=1000)
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_spacecraft_config(config, td)
            content = open(path).read()
            assert "TestSC" in content
            assert "1000" in content

    def test_generate_ipc_enabled(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SimConfig(enable_ipc=True, ipc_port=12345)
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_ipc_config(config, td)
            content = open(path).read()
            assert "TX" in content
            assert "12345" in content

    def test_generate_ipc_disabled(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SimConfig(enable_ipc=False)
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_ipc_config(config, td)
            content = open(path).read()
            assert "0" in content.split("\n")[1]  # 0 sockets

    def test_generate_full_scenario(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SimConfig()
        with tempfile.TemporaryDirectory() as td:
            files = gen.generate_full_scenario(config, td)
            assert len(files) == 4
            for f in files:
                assert os.path.exists(f)

    def test_graphics_disabled(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SimConfig(graphics=False)
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_sim_config(config, td)
            content = open(path).read()
            assert "FALSE" in content

    def test_custom_date(self) -> None:
        gen = Nasa42ScriptGenerator()
        config = Nasa42SimConfig(date=(12, 25, 2025))
        with tempfile.TemporaryDirectory() as td:
            path = gen.generate_sim_config(config, td)
            content = open(path).read()
            assert "12 25 2025" in content


class TestOutputParsing:
    """Test NASA 42 output parsing."""

    def test_parse_position_line(self) -> None:
        state = Nasa42OutputParser.parse_state_line("SC[0].PosN = 6778000.0 0.0 0.0")
        assert state is not None
        assert abs(state.position_m[0] - 6778000.0) < 1
        assert abs(state.altitude_km - 407.0) < 5

    def test_parse_velocity_line(self) -> None:
        state = Nasa42OutputParser.parse_state_line("SC[0].VelN = 0.0 4766.0 6014.0")
        assert state is not None
        assert abs(state.velocity_m_s[1] - 4766.0) < 1
        assert state.orbital_velocity_m_s > 7000

    def test_parse_quaternion_line(self) -> None:
        state = Nasa42OutputParser.parse_state_line("SC[0].qbn = 1.0 0.0 0.0 0.0")
        assert state is not None
        assert state.quaternion == [1.0, 0.0, 0.0, 0.0]

    def test_parse_omega_line(self) -> None:
        state = Nasa42OutputParser.parse_state_line("SC[0].wbn = 0.001 0.002 0.003")
        assert state is not None
        assert abs(state.omega_rad_s[0] - 0.001) < 1e-6

    def test_parse_empty_line(self) -> None:
        assert Nasa42OutputParser.parse_state_line("") is None

    def test_parse_invalid_line(self) -> None:
        assert Nasa42OutputParser.parse_state_line("garbage") is None

    def test_parse_output_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".42", delete=False) as f:
            f.write("SC[0].PosN = 6778000.0 0.0 0.0\n")
            f.write("SC[0].VelN = 0.0 4766.0 6014.0\n")
            f.write("SC[0].qbn = 1.0 0.0 0.0 0.0\n")
            f.write("--- TIME ---\n")
            f.write("SC[0].PosN = 6778100.0 100.0 50.0\n")
            f.write("SC[0].VelN = -10.0 4765.0 6013.0\n")
            f.name_saved = f.name

        try:
            states = Nasa42OutputParser.parse_output_file(f.name_saved)
            assert len(states) >= 1
            assert states[0].altitude_km > 0
        finally:
            os.unlink(f.name_saved)

    def test_parse_nonexistent_file(self) -> None:
        states = Nasa42OutputParser.parse_output_file("/nonexistent/path.42")
        assert states == []


class TestBridge:
    """Test main Nasa42Bridge class."""

    def test_bridge_creates(self) -> None:
        bridge = Nasa42Bridge()
        assert bridge is not None

    def test_generate_scenario(self) -> None:
        bridge = Nasa42Bridge()
        config = Nasa42SimConfig()
        with tempfile.TemporaryDirectory() as td:
            files = bridge.generate_scenario(config, td)
            assert len(files) == 4

    def test_state_to_aria_nav(self) -> None:
        state = Nasa42State(
            position_m=[6778000, 0, 0],
            velocity_m_s=[0, 4766, 6014],
            altitude_km=407,
            orbital_velocity_m_s=7673,
        )
        nav = Nasa42Bridge.state_to_aria_nav(state)
        assert nav["altitude_km"] == 407
        assert nav["orbital_velocity_m_s"] == 7673
        assert len(nav["position_eci_m"]) == 3

    def test_state_to_aria_attitude(self) -> None:
        state = Nasa42State(
            quaternion=[1, 0, 0, 0],  # Identity
            omega_rad_s=[0, 0, 0.001],
        )
        att = Nasa42Bridge.state_to_aria_attitude(state)
        assert abs(att["roll_deg"]) < 1
        assert abs(att["pitch_deg"]) < 1
        assert abs(att["yaw_deg"]) < 1
        assert att["angular_rate_rad_s"] == [0, 0, 0.001]

    def test_attitude_conversion_nonzero(self) -> None:
        """Test non-identity quaternion produces non-zero Euler angles."""
        # 90° yaw rotation
        import math
        angle = math.pi / 4  # 45°
        state = Nasa42State(
            quaternion=[math.cos(angle / 2), 0, 0, math.sin(angle / 2)],
        )
        att = Nasa42Bridge.state_to_aria_attitude(state)
        assert abs(att["yaw_deg"] - 45.0) < 1.0


class TestPrebuiltConfigs:
    """Test pre-built scenario configurations."""

    def test_iss_config(self) -> None:
        config = Nasa42Bridge.iss_config()
        assert config.orbit.semi_major_axis_km == 6778.0
        assert config.orbit.inclination_deg == 51.6
        assert config.spacecraft.mass_kg == 420000.0
        assert not config.graphics

    def test_lunar_transfer_config(self) -> None:
        config = Nasa42Bridge.lunar_transfer_config()
        assert config.orbit.eccentricity > 0.9  # Highly elliptical
        assert config.duration_s > 86400  # Multi-day

    def test_iss_generates_files(self) -> None:
        bridge = Nasa42Bridge()
        config = Nasa42Bridge.iss_config()
        with tempfile.TemporaryDirectory() as td:
            files = bridge.generate_scenario(config, td)
            assert len(files) == 4
            # Verify ISS parameters in orbit file
            orb_content = open(os.path.join(td, "Orb_Mission.txt")).read()
            assert "6778" in orb_content
            assert "51.6" in orb_content
