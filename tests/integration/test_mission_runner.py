"""Tests for the unified MissionRunner — end-to-end system integration.

Verifies:
  - LEO/GEO/SSO missions run with correct physics
  - Interstellar missions run with challenges
  - Bus messages are published
  - Telemetry frames are collected
  - Results contain valid data
  - Factory methods produce correct configurations
"""

import asyncio

import pytest

bsk = pytest.importorskip("Basilisk")

from aria.simulation.mission_runner import MissionConfig, MissionResults, MissionRunner


class TestMissionFactory:
    """Test factory methods produce valid configurations."""

    def test_leo_iss_factory(self) -> None:
        runner = MissionRunner.leo_iss()
        assert runner._config.altitude_km == 400.0
        assert runner._config.inclination_deg == 51.6
        assert runner._config.mission_type == "LEO"

    def test_leo_sso_factory(self) -> None:
        runner = MissionRunner.leo_sso()
        assert runner._config.altitude_km == 600.0
        assert runner._config.inclination_deg == 97.4

    def test_geo_comms_factory(self) -> None:
        runner = MissionRunner.geo_comms()
        assert runner._config.altitude_km == 35786.0
        assert runner._config.inclination_deg == 0.0
        assert runner._config.mission_type == "GEO"

    def test_interstellar_factory(self) -> None:
        runner = MissionRunner.interstellar(years=50)
        assert runner._config.mission_type == "INTERSTELLAR"
        assert runner._config.enable_challenges
        assert runner._config.sim_duration_s == 50.0


class TestLEOMission:
    """Test LEO orbital missions with Basilisk physics."""

    @pytest.mark.asyncio
    async def test_iss_one_orbit(self) -> None:
        """Run one ISS orbit and validate results."""
        runner = MissionRunner(MissionConfig(
            name="test-iss",
            mission_type="LEO",
            altitude_km=400.0,
            inclination_deg=51.6,
            sim_duration_s=5520.0,
            telemetry_interval_s=60.0,
        ))
        results = await runner.run()

        assert results.success
        assert results.total_frames > 80  # ~92 frames at 60s interval
        assert 395 < results.altitude_range_km[0]  # Min altitude
        assert results.altitude_range_km[1] < 410   # Max altitude
        assert 7600 < results.velocity_range_m_s[0]
        assert results.velocity_range_m_s[1] < 7800
        # ISS ground track should reach ±51.6°
        assert results.latitude_range_deg[0] < -45
        assert results.latitude_range_deg[1] > 45

    @pytest.mark.asyncio
    async def test_sso_orbit(self) -> None:
        """Sun-synchronous orbit at 600 km."""
        runner = MissionRunner(MissionConfig(
            name="test-sso",
            mission_type="LEO",
            altitude_km=600.0,
            inclination_deg=97.4,
            sim_duration_s=5760.0,
            telemetry_interval_s=60.0,
        ))
        results = await runner.run()

        assert results.success
        assert 595 < results.altitude_range_km[0]
        assert results.altitude_range_km[1] < 610

    @pytest.mark.asyncio
    async def test_short_mission(self) -> None:
        """Quick 2-minute mission."""
        runner = MissionRunner(MissionConfig(
            name="test-quick",
            mission_type="LEO",
            altitude_km=400.0,
            sim_duration_s=120.0,
            telemetry_interval_s=10.0,
        ))
        results = await runner.run()
        assert results.success
        assert results.total_frames > 0
        assert results.duration_wall_s < 10  # Should be fast


class TestGEOMission:
    """Test GEO mission."""

    @pytest.mark.asyncio
    async def test_geo_10_minutes(self) -> None:
        runner = MissionRunner(MissionConfig(
            name="test-geo",
            mission_type="GEO",
            altitude_km=35786.0,
            inclination_deg=0.0,
            sim_duration_s=600.0,
            telemetry_interval_s=60.0,
        ))
        results = await runner.run()
        assert results.success
        assert 35700 < results.altitude_range_km[0]
        assert results.altitude_range_km[1] < 35900


class TestInterstellarMission:
    """Test interstellar missions with challenge orchestrator."""

    @pytest.mark.asyncio
    async def test_interstellar_10_years(self) -> None:
        runner = MissionRunner.interstellar(years=10, crew=4)
        results = await runner.run()

        assert results.success
        assert results.total_frames == 10
        assert results.total_events > 0
        assert len(results.challenge_states) == 6

    @pytest.mark.asyncio
    async def test_interstellar_100_years(self) -> None:
        runner = MissionRunner.interstellar(years=100, crew=4)
        results = await runner.run()

        assert results.success
        assert results.total_frames == 100
        assert results.total_events > 100
        assert "materials" in results.challenge_states
        assert "food" in results.challenge_states
        assert "genetics" in results.challenge_states

    @pytest.mark.asyncio
    async def test_interstellar_severity_distribution(self) -> None:
        runner = MissionRunner.interstellar(years=50, crew=4)
        results = await runner.run()

        assert len(results.severity_distribution) > 0
        # Should have at least warnings
        total_events = sum(results.severity_distribution.values())
        assert total_events > 0


class TestMissionResults:
    """Test results structure and summary."""

    def test_results_summary_format(self) -> None:
        results = MissionResults(
            mission_name="Test",
            mission_type="LEO",
            duration_sim_s=5520,
            duration_wall_s=2.5,
            total_frames=92,
            altitude_range_km=(399.3, 400.7),
            velocity_range_m_s=(7671.0, 7673.0),
            latitude_range_deg=(-51.6, 51.6),
        )
        summary = results.summary()
        assert "Test" in summary
        assert "5520" in summary
        assert "SUCCESS" in summary

    def test_results_success_flag(self) -> None:
        r = MissionResults(mission_name="ok", mission_type="LEO")
        assert r.success
        r.errors.append("something broke")
        assert not r.success

    @pytest.mark.asyncio
    async def test_results_contain_wall_time(self) -> None:
        runner = MissionRunner(MissionConfig(
            name="timing-test",
            mission_type="LEO",
            altitude_km=400.0,
            sim_duration_s=60.0,
            telemetry_interval_s=10.0,
        ))
        results = await runner.run()
        assert results.duration_wall_s > 0
        assert results.duration_sim_s > 0


class TestBusIntegration:
    """Verify messages flow through the ARIA bus."""

    @pytest.mark.asyncio
    async def test_bus_receives_messages(self) -> None:
        """Verify the bus actually receives published messages."""
        received = []

        async def on_msg(msg):  # type: ignore
            received.append(msg)

        runner = MissionRunner(MissionConfig(
            name="bus-test",
            mission_type="LEO",
            altitude_km=400.0,
            sim_duration_s=30.0,
            telemetry_interval_s=10.0,
        ))

        await runner.setup()
        runner._bus.subscribe("aria.sensor.*", on_msg)

        # Manually step and publish
        if runner._basilisk_runner:
            frames = runner._basilisk_runner.step(10.0)
            for frame in frames:
                await runner._publish_orbital_telemetry(frame)
            # Let bus deliver
            await asyncio.sleep(0.1)

        await runner._bus.stop()
        assert len(received) > 0


class TestEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_zero_duration(self) -> None:
        runner = MissionRunner(MissionConfig(
            name="zero",
            mission_type="LEO",
            sim_duration_s=0.0,
        ))
        results = await runner.run()
        assert results.total_frames == 0

    @pytest.mark.asyncio
    async def test_interstellar_1_year(self) -> None:
        runner = MissionRunner.interstellar(years=1, crew=4)
        results = await runner.run()
        assert results.success
        assert results.total_frames == 1

    def test_config_defaults(self) -> None:
        cfg = MissionConfig()
        assert cfg.altitude_km == 400.0
        assert cfg.sim_duration_s == 5520.0
        assert not cfg.enable_challenges
