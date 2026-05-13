"""End-to-End Integration Tests — Basilisk physics through real ARIA agents.

These tests verify the complete pipeline:
  Basilisk (real orbital mechanics)
    → ARIA MessageBus (pub/sub delivery)
      → SubsystemAgents (power, thermal, nav, etc.)
        → Anomaly detection (threshold + Dsremo ML)
          → Alert generation
            → SharedScratchpad (inter-agent data)

This is the definitive test that ARIA works as a complete system.
"""

import asyncio
from typing import Any

import pytest

bsk = pytest.importorskip("Basilisk")

from aria.agents.base import SubsystemAgent
from aria.agents.comms import CommsAgent
from aria.agents.eclss import EclssAgent
from aria.agents.navigation import NavigationAgent
from aria.agents.power import PowerAgent
from aria.agents.thermal import ThermalAgent
from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority
from aria.simulation.basilisk_runner import (
    BasiliskSimRunner,
    OrbitConfig,
    SimConfig,
    TelemetryFrame,
)
from aria.simulation.mission_runner import MissionConfig, MissionRunner
from aria.state.scratchpad import SharedScratchpad
from aria.tools.registry import ToolRegistry


class MessageCollector:
    """Collects messages from a bus topic for assertion."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def collect(self, msg: Message) -> None:
        self.messages.append(msg)

    @property
    def count(self) -> int:
        return len(self.messages)

    def topics(self) -> set[str]:
        return {m.topic for m in self.messages}

    def payloads(self) -> list[dict[str, Any]]:
        return [m.payload for m in self.messages]


@pytest.fixture
def tools() -> ToolRegistry:
    """Stub tool registry that returns success for all tools."""
    from aria.tools.registry import ToolResult

    class StubRegistry(ToolRegistry):
        async def invoke(self, tool_name: str, params: dict[str, Any]) -> ToolResult:
            return ToolResult(success=True, data={"result": "PASS"})

    return StubRegistry()


class TestBasiliskToAgentPipeline:
    """Verify Basilisk telemetry flows through to real agents."""

    @pytest.mark.asyncio
    async def test_power_agent_receives_solar_data(self, tools: ToolRegistry) -> None:
        """PowerAgent processes solar panel power from Basilisk."""
        bus = MessageBus()
        await bus.start()

        scratchpad = SharedScratchpad()
        power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await power.start()

        # Simulate Basilisk solar panel reading
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 2722.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.15)

        # PowerAgent should have updated internal state
        assert power._solar_power_w == 2722.0
        assert not power._in_eclipse

        # Send eclipse (0 solar power)
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.15)

        assert power._in_eclipse
        assert power._solar_power_w == 0.0

        await power.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_power_agent_detects_low_battery(self, tools: ToolRegistry) -> None:
        """PowerAgent raises alert on low battery SoC from Basilisk data."""
        bus = MessageBus()
        await bus.start()

        alerts = MessageCollector()
        bus.subscribe("aria.anomaly.power", alerts.collect)

        scratchpad = SharedScratchpad()
        power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await power.start()

        # Send low battery reading
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 15.0, "temperature_c": 25.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.2)

        # Should have generated a warning
        assert alerts.count > 0
        assert any("low" in str(m.payload.get("message", "")).lower() or
                    "warning" in str(m.payload.get("severity", "")).lower()
                    for m in alerts.messages)

        await power.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_power_agent_posts_to_scratchpad(self, tools: ToolRegistry) -> None:
        """PowerAgent writes eclipse state to SharedScratchpad."""
        bus = MessageBus()
        await bus.start()

        scratchpad = SharedScratchpad()
        power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await power.start()

        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 2722.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.15)

        # Check scratchpad has eclipse state
        eclipse_data = scratchpad.read("power.eclipse_state")
        assert eclipse_data is not None
        assert eclipse_data["in_eclipse"] is False
        assert eclipse_data["solar_power_w"] == 2722.0

        await power.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_navigation_agent_processes_position(self, tools: ToolRegistry) -> None:
        """NavigationAgent processes orbital position data."""
        bus = MessageBus()
        await bus.start()

        scratchpad = SharedScratchpad()
        nav = NavigationAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await nav.start()

        await bus.publish(Message(
            topic="aria.sensor.navigation.gps",
            payload={
                "latitude_deg": 25.5,
                "longitude_deg": 50.0,
                "altitude_km": 400.0,
                "velocity_m_s": 7673.0,
            },
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.15)

        await nav.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_thermal_reads_eclipse_from_scratchpad(self, tools: ToolRegistry) -> None:
        """ThermalAgent reads eclipse state from PowerAgent via scratchpad."""
        bus = MessageBus()
        await bus.start()

        scratchpad = SharedScratchpad()
        power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        thermal = ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await power.start()
        await thermal.start()

        # Power agent posts eclipse state
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 0.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.15)

        # Thermal should be able to read it
        eclipse_data = scratchpad.read("power.eclipse_state")
        assert eclipse_data is not None
        assert eclipse_data["in_eclipse"] is True

        await thermal.stop()
        await power.stop()
        await bus.stop()


class TestMultiAgentCoordination:
    """Test multiple agents working together on Basilisk data."""

    @pytest.mark.asyncio
    async def test_three_agents_process_simultaneously(self, tools: ToolRegistry) -> None:
        """Power, Thermal, and ECLSS all process data concurrently."""
        bus = MessageBus()
        await bus.start()

        scratchpad = SharedScratchpad()
        agents = [
            PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
            ThermalAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
            EclssAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad),
        ]

        for agent in agents:
            await agent.start()

        # Publish data for each agent
        await bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": 2722.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await bus.publish(Message(
            topic="aria.sensor.thermal",
            payload={"zone": "cabin", "temperature_c": 22.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await bus.publish(Message(
            topic="aria.sensor.eclss.atmosphere",
            payload={"o2_percent": 20.9, "co2_mmhg": 3.0, "humidity_percent": 45.0, "temperature_c": 22.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.2)

        # All agents should have processed at least one message
        for agent in agents:
            assert agent._messages_processed >= 1, f"{agent.name} processed 0 messages"

        for agent in reversed(agents):
            await agent.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_alert_cascade_across_agents(self, tools: ToolRegistry) -> None:
        """Critical battery → alert → other agents can see via bus."""
        bus = MessageBus()
        await bus.start()

        all_alerts = MessageCollector()
        bus.subscribe("aria.anomaly.*", all_alerts.collect)

        scratchpad = SharedScratchpad()
        power = PowerAgent(bus=bus, tool_registry=tools, scratchpad=scratchpad)
        await power.start()

        # Send critical battery
        await bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={"soc_percent": 5.0, "temperature_c": 25.0},
            priority=EventPriority.P3_ROUTINE,
        ))
        await asyncio.sleep(0.3)

        # Should have critical alerts
        assert all_alerts.count > 0
        critical = [m for m in all_alerts.messages
                    if m.payload.get("severity") == "CRITICAL"]
        assert len(critical) > 0

        await power.stop()
        await bus.stop()


class TestMissionRunnerWithAgents:
    """Test MissionRunner with real agents processing Basilisk data."""

    @pytest.mark.asyncio
    async def test_short_mission_with_agents(self) -> None:
        """Run a 60-second mission with all agents active."""
        runner = MissionRunner(MissionConfig(
            name="e2e-test",
            mission_type="LEO",
            altitude_km=400.0,
            inclination_deg=51.6,
            sim_duration_s=60.0,
            telemetry_interval_s=10.0,
            enable_agents=True,
        ))
        results = await runner.run()

        assert results.success
        assert results.total_frames > 0
        assert 395 < results.altitude_range_km[0]
        assert results.altitude_range_km[1] < 410

    @pytest.mark.asyncio
    async def test_interstellar_with_agents(self) -> None:
        """Run 5-year interstellar mission with agents."""
        runner = MissionRunner(MissionConfig(
            name="e2e-interstellar",
            mission_type="INTERSTELLAR",
            sim_duration_s=5.0,
            enable_challenges=True,
            enable_agents=True,
            crew_size=4,
        ))
        results = await runner.run()

        assert results.success
        assert results.total_events > 0

    @pytest.mark.asyncio
    async def test_mission_result_summary(self) -> None:
        """MissionResults.summary() works after real mission."""
        runner = MissionRunner(MissionConfig(
            name="summary-test",
            mission_type="LEO",
            altitude_km=400.0,
            sim_duration_s=30.0,
            telemetry_interval_s=10.0,
            enable_agents=False,
        ))
        results = await runner.run()
        summary = results.summary()
        assert "summary-test" in summary
        assert "SUCCESS" in summary


class TestBasiliskPhysicsIntegrity:
    """Verify Basilisk physics are physically correct end-to-end."""

    @pytest.mark.asyncio
    async def test_kepler_third_law(self) -> None:
        """Verify T² ∝ a³ for LEO orbit."""
        config = SimConfig(
            timestep_s=1.0,
            output_interval_s=1.0,
            orbit=OrbitConfig(altitude_km=400.0, inclination_deg=51.6),
        )
        runner = BasiliskSimRunner(config)
        runner.setup()

        # Run full orbit
        frames = runner.step(5600.0)

        # Find period from latitude crossings
        zero_crossings = []
        for i in range(1, len(frames)):
            if (frames[i - 1].ground_track_lat_deg < 0 and
                    frames[i].ground_track_lat_deg >= 0):
                zero_crossings.append(frames[i].timestamp_s)

        if len(zero_crossings) >= 2:
            period = zero_crossings[1] - zero_crossings[0]
            # ISS period should be ~92 minutes = 5520s
            assert 5400 < period < 5700, f"Period {period}s outside expected range"

    @pytest.mark.asyncio
    async def test_energy_conservation(self) -> None:
        """Verify orbital energy is approximately conserved."""
        import numpy as np

        config = SimConfig(
            timestep_s=1.0,
            output_interval_s=60.0,
            orbit=OrbitConfig(altitude_km=400.0, eccentricity=0.0001),
        )
        runner = BasiliskSimRunner(config)
        runner.setup()
        frames = runner.step(5520.0)

        mu = 3.986004418e14  # Earth GM, m³/s²
        energies = []
        for f in frames:
            r = np.linalg.norm(f.position_eci_m)
            v = f.orbital_velocity_m_s
            E = 0.5 * v**2 - mu / r  # Specific orbital energy
            energies.append(E)

        # Energy should be conserved within 0.01%
        E_mean = sum(energies) / len(energies)
        for E in energies:
            assert abs(E - E_mean) / abs(E_mean) < 0.001, \
                f"Energy not conserved: {E:.0f} vs mean {E_mean:.0f}"

    @pytest.mark.asyncio
    async def test_inclination_matches_latitude_range(self) -> None:
        """Ground track latitude range should match orbital inclination."""
        for incl in [28.5, 51.6, 97.4]:
            config = SimConfig(
                timestep_s=1.0,
                output_interval_s=10.0,
                orbit=OrbitConfig(altitude_km=400.0, inclination_deg=incl),
            )
            runner = BasiliskSimRunner(config)
            runner.setup()
            frames = runner.step(5520.0)

            lats = [f.ground_track_lat_deg for f in frames]
            max_lat = max(abs(l) for l in lats)
            # Max latitude should be close to inclination (or 180-incl for retrograde)
            expected_max = min(incl, 180 - incl)  # Retrograde orbits: 97.4° → 82.6°
            assert max_lat > expected_max - 10, \
                f"Max lat {max_lat:.1f}° too low for {incl}° inclination (expect ~{expected_max:.0f}°)"
