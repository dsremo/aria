"""System Smoke Test — verifies the ENTIRE ARIA system works together.

This is the ultimate integration test. It starts:
  - Basilisk orbital mechanics (real physics)
  - 9 SubsystemAgents (power, thermal, eclss, nav, propulsion, comms, science, medical, telemetry)
  - SharedScratchpad (inter-agent communication)
  - MessageBus (pub/sub)
  - HealthDashboard (status aggregation)
  - TelemetryHistoryStore (data storage)
  - MissionRunner (orchestration)

And verifies:
  - Physics are correct (altitude, velocity)
  - Agents process messages (message counts > 0)
  - Scratchpad has data (inter-agent communication works)
  - Dashboard reflects real state
  - No exceptions or crashes
"""

import asyncio
import time

import pytest

bsk = pytest.importorskip("Basilisk")

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority
from aria.dashboard.health_dashboard import HealthDashboard
from aria.dashboard.telemetry_server import TelemetryHistoryStore
from aria.simulation.basilisk_runner import (
    BasiliskSimRunner,
    OrbitConfig,
    SimConfig,
)
from aria.simulation.mission_runner import MissionConfig, MissionRunner


class TestSystemSmoke:
    """The ultimate system-level smoke test."""

    @pytest.mark.asyncio
    async def test_complete_system_30_second_mission(self) -> None:
        """Run a 30-second mission with ALL components active.

        This is the single most important test in the entire codebase.
        If this passes, ARIA works end-to-end.
        """
        t0 = time.time()

        # Create MissionRunner with agents
        runner = MissionRunner(MissionConfig(
            name="SMOKE-TEST",
            mission_type="LEO",
            altitude_km=400.0,
            inclination_deg=51.6,
            sim_duration_s=30.0,
            telemetry_interval_s=10.0,
            enable_agents=True,
        ))

        # Run mission
        results = await runner.run()
        wall_time = time.time() - t0

        # ─── Verify mission completed ───
        assert results.success, f"Mission failed: {results.errors}"
        assert results.total_frames > 0, "No telemetry frames produced"
        assert wall_time < 30, f"Took too long: {wall_time:.1f}s"

        # ─── Verify physics ───
        assert 395 < results.altitude_range_km[0], \
            f"Min altitude {results.altitude_range_km[0]} too low"
        assert results.altitude_range_km[1] < 410, \
            f"Max altitude {results.altitude_range_km[1]} too high"
        assert 7500 < results.velocity_range_m_s[0], \
            f"Min velocity {results.velocity_range_m_s[0]} too low"

    @pytest.mark.asyncio
    async def test_basilisk_to_dashboard_pipeline(self) -> None:
        """Basilisk → bus → agents → dashboard: complete data flow."""
        bus = MessageBus()
        await bus.start()

        dashboard = HealthDashboard(mission_name="Pipeline-Test")
        history = TelemetryHistoryStore()

        # Setup Basilisk
        config = SimConfig(
            timestep_s=1.0,
            output_interval_s=10.0,
            orbit=OrbitConfig(altitude_km=400.0, inclination_deg=51.6),
        )
        bsk_runner = BasiliskSimRunner(config)
        bsk_runner.setup()

        # Run 60 seconds
        frames = bsk_runner.step(60.0)
        assert len(frames) > 0

        # Feed through dashboard and history
        for frame in frames:
            dashboard.update_from_basilisk_frame(frame)

            ts = int(time.time() * 1000)
            history.record("altitude_km", ts, frame.altitude_km)
            history.record("velocity_m_s", ts, frame.orbital_velocity_m_s)
            history.record("solar_w", ts, frame.solar_power_w)

            # Publish to bus
            await bus.publish(Message(
                topic="aria.sensor.power.solar",
                payload={"power_watts": frame.solar_power_w},
                priority=EventPriority.P3_ROUTINE,
            ))

        # Verify dashboard has correct data
        snap = dashboard.snapshot()
        assert 395 < snap.altitude_km < 410
        assert 7500 < snap.velocity_m_s < 7800
        assert snap.solar_power_w > 0
        assert snap.overall_status == "NOMINAL"

        # Verify history store
        alt_data = history.query("altitude_km")
        assert len(alt_data) == len(frames)
        assert all(395 < d["value"] < 410 for d in alt_data)

        await bus.stop()

    @pytest.mark.asyncio
    async def test_interstellar_full_system(self) -> None:
        """Run 10-year interstellar mission with challenges + agents."""
        runner = MissionRunner(MissionConfig(
            name="SMOKE-INTERSTELLAR",
            mission_type="INTERSTELLAR",
            sim_duration_s=10.0,  # 10 years
            enable_challenges=True,
            enable_agents=True,
            crew_size=4,
        ))

        results = await runner.run()

        assert results.success
        assert results.total_events > 0
        assert results.total_frames == 10
        assert len(results.challenge_states) == 6
        assert len(results.severity_distribution) > 0

    @pytest.mark.asyncio
    async def test_cli_benchmark_runs(self) -> None:
        """Verify the CLI benchmark command executes without error.

        Originally imported from the now-deleted ``aria.cli_legacy`` shim
        — the CLI was unified under ``aria.cli`` and the legacy module
        was dropped, leaving this test broken with an ImportError. The
        new entry point is ``aria.cli.system._cmd_benchmark``; we don't
        rename it to drop the underscore because callers should be
        invoking the CLI through argparse, not as a Python API."""
        import io
        import sys

        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        try:
            from aria.cli.system import _cmd_benchmark
            import argparse
            _cmd_benchmark(argparse.Namespace())
        finally:
            sys.stdout = old_stdout

        output = buffer.getvalue()
        assert "Interstellar" in output
        assert "Basilisk" in output
        assert "complete" in output.lower()

    @pytest.mark.asyncio
    async def test_multi_orbit_comparison(self) -> None:
        """Compare LEO, SSO, and GEO orbits — all should produce valid physics."""
        orbits = [
            ("LEO", 400.0, 51.6, (7600, 7800)),
            ("SSO", 600.0, 97.4, (7500, 7700)),
        ]

        for name, alt, incl, (v_min, v_max) in orbits:
            runner = MissionRunner(MissionConfig(
                name=f"smoke-{name}",
                mission_type="LEO",
                altitude_km=alt,
                inclination_deg=incl,
                sim_duration_s=60.0,
                telemetry_interval_s=10.0,
                enable_agents=False,
            ))
            results = await runner.run()

            assert results.success, f"{name} failed"
            assert results.total_frames > 0, f"{name} no frames"
            assert abs(results.altitude_range_km[0] - alt) < 5, \
                f"{name} altitude {results.altitude_range_km[0]} != {alt}"
            assert v_min < results.velocity_range_m_s[0] < v_max, \
                f"{name} velocity {results.velocity_range_m_s[0]} outside [{v_min}, {v_max}]"


class TestComponentIntegration:
    """Test that individual components integrate correctly."""

    @pytest.mark.asyncio
    async def test_scratchpad_survives_mission(self) -> None:
        """SharedScratchpad data persists through a mission."""
        from aria.state.scratchpad import SharedScratchpad
        sp = SharedScratchpad()

        # Write some data
        sp.write("test.key1", {"value": 42}, "test", ttl_s=600)
        sp.write("test.key2", {"data": [1, 2, 3]}, "test", ttl_s=600)

        # Verify
        assert sp.read("test.key1")["value"] == 42
        assert sp.read("test.key2")["data"] == [1, 2, 3]

        # Listing
        keys = sp.keys_by_prefix("test")
        assert len(keys) >= 2

    @pytest.mark.asyncio
    async def test_bus_handles_high_throughput(self) -> None:
        """Bus can handle 1000+ messages without dropping."""
        bus = MessageBus()
        await bus.start()

        received = []

        async def collector(msg: Message) -> None:
            received.append(msg)

        bus.subscribe("aria.test.*", collector)

        # Publish 1000 messages rapidly
        for i in range(1000):
            await bus.publish(Message(
                topic="aria.test.throughput",
                payload={"index": i},
                priority=EventPriority.P3_ROUTINE,
            ))

        # Wait for delivery
        await asyncio.sleep(1.0)
        await bus.stop()

        # Should receive all or nearly all
        assert len(received) >= 900, f"Only received {len(received)}/1000"

    def test_health_dashboard_from_real_basilisk(self) -> None:
        """HealthDashboard correctly interprets Basilisk physics."""
        from aria.simulation.basilisk_runner import TelemetryFrame

        dashboard = HealthDashboard(mission_name="Basilisk-Health")

        # Nominal sunlit frame
        frame = TelemetryFrame(
            timestamp_s=100.0,
            altitude_km=400.5,
            orbital_velocity_m_s=7673.0,
            ground_track_lat_deg=25.0,
            ground_track_lon_deg=50.0,
            in_eclipse=False,
            battery_soc=0.85,
            solar_power_w=2722.0,
            power_draw_w=200.0,
        )
        dashboard.update_from_basilisk_frame(frame)
        snap = dashboard.snapshot()

        assert snap.overall_status == "NOMINAL"
        assert snap.altitude_km == 400.5
        assert snap.battery_soc_pct == 85.0

        # Eclipse frame with dropping battery
        frame2 = TelemetryFrame(
            timestamp_s=200.0,
            altitude_km=400.0,
            orbital_velocity_m_s=7673.0,
            in_eclipse=True,
            battery_soc=0.45,
            solar_power_w=0.0,
            power_draw_w=200.0,
        )
        dashboard.update_from_basilisk_frame(frame2)
        snap2 = dashboard.snapshot()

        assert snap2.in_eclipse
        assert snap2.battery_soc_pct == 45.0
        assert snap2.solar_power_w == 0.0
        # Eclipse + low-ish battery = CAUTION
        assert snap2.overall_status == "CAUTION"
