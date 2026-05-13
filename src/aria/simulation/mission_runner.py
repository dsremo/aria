"""Unified Mission Runner — Basilisk physics + ARIA agents + challenges + telemetry.

The single entry point that runs everything together:

  Basilisk (real physics)
      ↓ telemetry frames
  ARIA Message Bus
      ↓ sensor messages
  9 SubsystemAgents (power, thermal, eclss, nav, propulsion, comms, science, medical, telemetry)
      ↓ anomalies, alerts, scratchpad
  AriaCoordinator (FDIR, correlation, decisions)
      ↓ state updates
  Telemetry Server (WebSocket + HTTP)
      ↓ streaming
  OpenMCT Dashboard (browser)

Additionally runs InterstellarChallengeOrchestrator for long-duration missions.

Usage:
    # Quick LEO mission (1 orbit)
    runner = MissionRunner.leo_iss()
    results = await runner.run()

    # Full interstellar mission
    runner = MissionRunner.interstellar()
    results = await runner.run()
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority

logger = structlog.get_logger()


@dataclass
class MissionConfig:
    """Configuration for a complete mission run."""
    name: str = "ARIA-Mission"
    mission_type: str = "LEO"  # LEO, GEO, INTERSTELLAR

    # Basilisk orbit config
    altitude_km: float = 400.0
    inclination_deg: float = 51.6

    # Timing
    sim_duration_s: float = 5520.0  # One orbit
    sim_timestep_s: float = 1.0
    telemetry_interval_s: float = 10.0
    real_time_factor: float = 0.0  # 0 = as fast as possible

    # Telemetry server
    enable_telemetry_server: bool = False
    server_port: int = 8080

    # Interstellar challenges
    enable_challenges: bool = False
    crew_size: int = 4

    # Agent configuration
    enable_agents: bool = True

    # Real data overlay
    replay_battery_data: str = ""    # Path to NASA battery .mat or CSV
    replay_noaa_data: str = ""       # Path to NOAA GOES CSV
    replay_eden_data: str = ""       # Path to EDEN ISS directory

    # Limits
    max_events: int = 100000


@dataclass
class MissionResults:
    """Results from a completed mission run."""
    mission_name: str
    mission_type: str
    duration_sim_s: float = 0.0
    duration_wall_s: float = 0.0
    total_frames: int = 0
    total_events: int = 0
    total_alerts: int = 0

    # Telemetry summary
    altitude_range_km: tuple[float, float] = (0, 0)
    velocity_range_m_s: tuple[float, float] = (0, 0)
    latitude_range_deg: tuple[float, float] = (0, 0)
    eclipse_count: int = 0

    # Agent summary
    agent_messages_processed: int = 0
    anomalies_detected: int = 0
    severity_distribution: dict[str, int] = field(default_factory=dict)

    # Challenge summary (interstellar only)
    challenge_states: dict[str, str] = field(default_factory=dict)
    terminal_challenges: int = 0

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Mission: {self.mission_name} ({self.mission_type})",
            f"Duration: {self.duration_sim_s:.0f}s sim / {self.duration_wall_s:.2f}s wall",
            f"Frames: {self.total_frames} | Events: {self.total_events} | Alerts: {self.total_alerts}",
            f"Altitude: {self.altitude_range_km[0]:.1f}-{self.altitude_range_km[1]:.1f} km",
            f"Velocity: {self.velocity_range_m_s[0]:.0f}-{self.velocity_range_m_s[1]:.0f} m/s",
            f"Latitude: {self.latitude_range_deg[0]:.1f}° to {self.latitude_range_deg[1]:.1f}°",
            f"Eclipses: {self.eclipse_count}",
        ]
        if self.challenge_states:
            lines.append(f"Terminal challenges: {self.terminal_challenges}/6")
        if self.errors:
            lines.append(f"ERRORS: {len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"  - {e}")
        else:
            lines.append("Status: SUCCESS")
        return "\n".join(lines)


class MissionRunner:
    """Unified mission runner — Basilisk + ARIA agents + challenges + telemetry.

    Orchestrates all subsystems into a single coherent simulation:
    1. Basilisk produces high-fidelity physics telemetry
    2. Telemetry is published on ARIA bus
    3. Agents process telemetry, detect anomalies, make decisions
    4. Challenge orchestrator adds long-duration degradation
    5. Telemetry server streams everything to OpenMCT
    """

    def __init__(self, config: MissionConfig | None = None) -> None:
        self._config = config or MissionConfig()
        self._bus = MessageBus()
        self._results = MissionResults(
            mission_name=self._config.name,
            mission_type=self._config.mission_type,
        )
        self._events: list[dict[str, Any]] = []
        self._alert_count = 0
        self._msg_count = 0

        # Components (initialized in setup)
        self._basilisk_runner: Any = None
        self._telemetry_server: Any = None
        self._alerter: Any = None
        self._mission_store: Any = None
        self._challenge_orch: Any = None

    @classmethod
    def leo_iss(cls) -> MissionRunner:
        """ISS-like LEO orbit mission."""
        return cls(MissionConfig(
            name="LEO-ISS",
            mission_type="LEO",
            altitude_km=400.0,
            inclination_deg=51.6,
            sim_duration_s=5520.0,  # 1 orbit
            telemetry_interval_s=10.0,
        ))

    @classmethod
    def leo_sso(cls) -> MissionRunner:
        """Sun-synchronous orbit mission."""
        return cls(MissionConfig(
            name="LEO-SSO",
            mission_type="LEO",
            altitude_km=600.0,
            inclination_deg=97.4,
            sim_duration_s=5760.0,
            telemetry_interval_s=10.0,
        ))

    @classmethod
    def geo_comms(cls) -> MissionRunner:
        """Geostationary communications satellite."""
        return cls(MissionConfig(
            name="GEO-Comms",
            mission_type="GEO",
            altitude_km=35786.0,
            inclination_deg=0.0,
            sim_duration_s=86400.0,  # 1 day
            telemetry_interval_s=60.0,
        ))

    @classmethod
    def interstellar(cls, years: int = 100, crew: int = 4) -> MissionRunner:
        """Interstellar generation ship mission."""
        return cls(MissionConfig(
            name=f"Interstellar-{years}yr",
            mission_type="INTERSTELLAR",
            altitude_km=400.0,  # Start in LEO
            sim_duration_s=float(years),  # Years, not seconds
            enable_challenges=True,
            crew_size=crew,
        ))

    @classmethod
    def with_real_data(
        cls,
        battery_data: str = "",
        noaa_data: str = "",
        eden_data: str = "",
    ) -> MissionRunner:
        """LEO mission with real data overlay from NASA/NOAA/EDEN ISS."""
        return cls(MissionConfig(
            name="RealData-LEO",
            mission_type="LEO",
            altitude_km=400.0,
            inclination_deg=51.6,
            sim_duration_s=5520.0,
            replay_battery_data=battery_data,
            replay_noaa_data=noaa_data,
            replay_eden_data=eden_data,
        ))

    async def setup(self) -> None:
        """Initialize all mission components."""
        cfg = self._config
        logger.info("mission.setup", name=cfg.name, type=cfg.mission_type)

        # Start bus
        await self._bus.start()

        # Subscribe to alerts
        self._bus.subscribe("aria.anomaly.*", self._on_alert)

        # Setup Basilisk
        if cfg.mission_type != "INTERSTELLAR":
            try:
                from aria.simulation.basilisk_runner import (
                    BasiliskSimRunner, SimConfig, OrbitConfig,
                    BASILISK_AVAILABLE,
                )
                if BASILISK_AVAILABLE:
                    sim_cfg = SimConfig(
                        timestep_s=cfg.sim_timestep_s,
                        output_interval_s=cfg.telemetry_interval_s,
                        orbit=OrbitConfig(
                            altitude_km=cfg.altitude_km,
                            inclination_deg=cfg.inclination_deg,
                        ),
                    )
                    self._basilisk_runner = BasiliskSimRunner(sim_cfg)
                    self._basilisk_runner.setup()
                    logger.info("mission.basilisk_ready")
            except Exception as e:
                logger.warning("mission.basilisk_failed", error=str(e))

        # Setup challenges (interstellar)
        if cfg.enable_challenges:
            from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator
            self._challenge_orch = InterstellarChallengeOrchestrator(
                crew_size=cfg.crew_size, seed=42
            )
            logger.info("mission.challenges_ready")

        # Setup ARIA agents
        if cfg.enable_agents:
            await self._setup_agents()

        # Setup telemetry server
        if cfg.enable_telemetry_server:
            from aria.dashboard.telemetry_server import ARIATelemetryServer
            self._telemetry_server = ARIATelemetryServer(port=cfg.server_port)
            await self._telemetry_server.start()
            logger.info("mission.telemetry_server_ready", port=cfg.server_port)

    async def run(self) -> MissionResults:
        """Run the complete mission."""
        cfg = self._config
        t_start = time.time()

        await self.setup()

        if cfg.mission_type == "INTERSTELLAR":
            await self._run_interstellar()
        else:
            await self._run_orbital()

        # Overlay real data if configured
        await self._replay_real_data()

        # Stop agents before bus
        await self._stop_agents()

        self._results.duration_wall_s = time.time() - t_start
        await self._bus.stop()

        # Auto-save to mission store
        try:
            from aria.persistence.mission_store import MissionStore
            store = MissionStore()
            mission_id = store.save(self._results)
            self._results.mission_id = mission_id  # type: ignore[attr-defined]
            store.close()
        except Exception:
            pass  # Persistence is optional

        logger.info("mission.complete",
                     frames=self._results.total_frames,
                     events=self._results.total_events,
                     wall_time=f"{self._results.duration_wall_s:.2f}s")
        return self._results

    async def _setup_agents(self) -> None:
        """Initialize and start all 9 ARIA subsystem agents."""
        from aria.agents.power import PowerAgent
        from aria.agents.thermal import ThermalAgent
        from aria.agents.eclss import EclssAgent
        from aria.agents.navigation import NavigationAgent
        from aria.agents.propulsion import PropulsionAgent
        from aria.agents.comms import CommsAgent
        from aria.agents.science import ScienceAgent
        from aria.agents.medical import MedicalAgent
        from aria.agents.telemetry import TelemetryAgent
        from aria.tools.registry import ToolRegistry
        from aria.state.scratchpad import SharedScratchpad

        tools = ToolRegistry()
        scratchpad = SharedScratchpad()

        agent_classes = [
            PowerAgent, ThermalAgent, EclssAgent, NavigationAgent,
            PropulsionAgent, CommsAgent, ScienceAgent, MedicalAgent,
            TelemetryAgent,
        ]

        self._agents: list[Any] = []
        for cls in agent_classes:
            try:
                agent = cls(bus=self._bus, tool_registry=tools, scratchpad=scratchpad)
                await agent.start()
                self._agents.append(agent)
            except Exception as e:
                logger.warning("mission.agent_start_failed", agent=cls.__name__, error=str(e))

        self._results.agent_count = len(self._agents)
        logger.info("mission.agents_ready", count=len(self._agents),
                     names=[a.name for a in self._agents])

    async def _stop_agents(self) -> None:
        """Stop all running agents."""
        for agent in reversed(getattr(self, "_agents", [])):
            try:
                await agent.stop()
            except Exception:
                pass

    async def _run_orbital(self) -> None:
        """Run an orbital mission (LEO/GEO) with Basilisk."""
        cfg = self._config
        runner = self._basilisk_runner

        if not runner:
            self._results.errors.append("Basilisk not available")
            return

        elapsed = 0.0
        step = cfg.telemetry_interval_s
        all_alts: list[float] = []
        all_vels: list[float] = []
        all_lats: list[float] = []
        eclipse_transitions = 0
        prev_eclipse = False

        logger.info("mission.orbital_start", duration_s=cfg.sim_duration_s)

        while elapsed < cfg.sim_duration_s:
            frames = runner.step(step)

            for frame in frames:
                self._results.total_frames += 1
                all_alts.append(frame.altitude_km)
                all_vels.append(frame.orbital_velocity_m_s)
                all_lats.append(frame.ground_track_lat_deg)

                if frame.in_eclipse and not prev_eclipse:
                    eclipse_transitions += 1
                prev_eclipse = frame.in_eclipse

                # Publish to ARIA bus
                await self._publish_orbital_telemetry(frame)

                # Push to telemetry server
                if self._telemetry_server:
                    self._telemetry_server.push_basilisk_frame(frame)

            elapsed += step

            # Real-time pacing
            if cfg.real_time_factor > 0:
                await asyncio.sleep(step / cfg.real_time_factor)

        self._results.duration_sim_s = elapsed
        if all_alts:
            self._results.altitude_range_km = (min(all_alts), max(all_alts))
            self._results.velocity_range_m_s = (min(all_vels), max(all_vels))
            self._results.latitude_range_deg = (min(all_lats), max(all_lats))
        self._results.eclipse_count = eclipse_transitions
        self._results.total_alerts = self._alert_count

    async def _run_interstellar(self) -> None:
        """Run an interstellar mission with challenges."""
        cfg = self._config
        orch = self._challenge_orch

        if not orch:
            self._results.errors.append("Challenge orchestrator not initialized")
            return

        # Also run base interstellar simulation
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=cfg.crew_size, seed=42)

        total_years = int(cfg.sim_duration_s)  # sim_duration_s = years for interstellar
        logger.info("mission.interstellar_start", years=total_years)

        severity_counts: Counter[str] = Counter()

        for year in range(1, total_years + 1):
            # Base simulation
            year_events = sim.simulate_year()

            # Challenge orchestrator
            cr = orch.simulate_year(float(year), sim.state.distance_ly)

            # Count events
            for e in year_events:
                self._results.total_events += 1
                severity_counts[e.severity] += 1

            for e in cr["events"]:
                self._results.total_events += 1
                sev = e.get("severity", "UNKNOWN")
                severity_counts[sev] += 1

                # Publish critical+ to bus
                if sev in ("CRITICAL", "EMERGENCY"):
                    self._alert_count += 1
                    await self._bus.publish(Message(
                        topic=f"aria.anomaly.interstellar.{e.get('subsystem', 'unknown')}",
                        payload=e,
                        priority=EventPriority.P1_CRITICAL if sev == "CRITICAL" else EventPriority.P0_EMERGENCY,
                    ))

            self._results.total_frames += 1

        # Final state
        self._results.duration_sim_s = float(total_years)
        self._results.total_alerts = self._alert_count
        self._results.severity_distribution = dict(severity_counts)

        # Challenge final states
        summary = orch.get_summary()
        self._results.challenge_states = {
            name: info["status"] for name, info in summary.items()
        }
        self._results.terminal_challenges = sum(
            1 for s in self._results.challenge_states.values() if s == "terminal"
        )

    async def _publish_orbital_telemetry(self, frame: Any) -> None:
        """Publish Basilisk frame as ARIA bus messages."""
        self._msg_count += 1

        await self._bus.publish(Message(
            topic="aria.sensor.power.solar",
            payload={"power_watts": frame.solar_power_w},
            priority=EventPriority.P3_ROUTINE,
        ))

        await self._bus.publish(Message(
            topic="aria.sensor.power.battery",
            payload={
                "soc_percent": frame.battery_soc * 100,
                "temperature_c": 25.0,
            },
            priority=EventPriority.P3_ROUTINE,
        ))

        await self._bus.publish(Message(
            topic="aria.sensor.navigation",
            payload={
                "altitude_km": frame.altitude_km,
                "velocity_m_s": frame.orbital_velocity_m_s,
                "latitude_deg": frame.ground_track_lat_deg,
                "longitude_deg": frame.ground_track_lon_deg,
            },
            priority=EventPriority.P3_ROUTINE,
        ))

    async def _replay_real_data(self) -> None:
        """Overlay real-world data from NASA/NOAA/EDEN ISS."""
        cfg = self._config
        has_data = cfg.replay_battery_data or cfg.replay_noaa_data or cfg.replay_eden_data
        if not has_data:
            return

        from aria.simulation.data_replay import DataReplayEngine
        replay = DataReplayEngine(self._bus)

        if cfg.replay_noaa_data:
            logger.info("mission.replay_noaa", path=cfg.replay_noaa_data)
            stats = await replay.replay_noaa_proton_flux(
                cfg.replay_noaa_data, time_scale=1000.0, max_readings=5000
            )
            self._results.total_events += stats.get("readings_published", 0)

        if cfg.replay_battery_data:
            logger.info("mission.replay_battery", path=cfg.replay_battery_data)
            stats = await replay.replay_nasa_battery(
                cfg.replay_battery_data, time_scale=1000.0, max_readings=5000
            )
            self._results.total_events += stats.get("readings_published", 0)

        if cfg.replay_eden_data:
            logger.info("mission.replay_eden", path=cfg.replay_eden_data)
            stats = await replay.replay_eden_iss(
                cfg.replay_eden_data, time_scale=1000.0, max_readings_per_file=500
            )
            self._results.total_events += stats.get("readings_published", 0)

    async def _on_alert(self, message: Message) -> None:
        """Handle anomaly alerts from agents."""
        self._alert_count += 1
        self._events.append({
            "topic": message.topic,
            "severity": message.payload.get("severity", "UNKNOWN"),
            "message": message.payload.get("message", ""),
        })
