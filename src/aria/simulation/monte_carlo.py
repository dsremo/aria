"""Monte Carlo Mission Runner — statistical analysis across N random missions.

Runs the same mission type N times with different random seeds and collects
statistics on outcomes, allowing probabilistic mission planning.

Usage:
    mc = MonteCarloRunner(
        base_config=MissionConfig(mission_type="INTERSTELLAR", ...),
        num_runs=100,
    )
    stats = await mc.run()
    print(stats.summary())

    # Or via CLI:
    python -m aria.cli montecarlo --mission interstellar --runs 100 --years 500
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class MonteCarloStats:
    """Statistical results from N Monte Carlo mission runs."""
    num_runs: int = 0
    num_successful: int = 0
    total_wall_time_s: float = 0.0

    # Event statistics
    event_counts: list[int] = field(default_factory=list)
    alert_counts: list[int] = field(default_factory=list)

    # Interstellar challenge statistics
    terminal_counts: list[int] = field(default_factory=list)
    challenge_terminal_rates: dict[str, float] = field(default_factory=dict)

    # Severity distributions across all runs
    severity_totals: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.num_successful / self.num_runs if self.num_runs > 0 else 0.0

    @property
    def avg_events(self) -> float:
        return sum(self.event_counts) / len(self.event_counts) if self.event_counts else 0

    @property
    def avg_alerts(self) -> float:
        return sum(self.alert_counts) / len(self.alert_counts) if self.alert_counts else 0

    @property
    def avg_terminal(self) -> float:
        return sum(self.terminal_counts) / len(self.terminal_counts) if self.terminal_counts else 0

    def summary(self) -> str:
        lines = [
            f"Monte Carlo Results ({self.num_runs} runs)",
            f"{'='*50}",
            f"Success rate:     {self.success_rate:.1%} ({self.num_successful}/{self.num_runs})",
            f"Wall time:        {self.total_wall_time_s:.2f}s ({self.total_wall_time_s/max(self.num_runs,1):.3f}s/run)",
            f"Avg events:       {self.avg_events:.0f}",
            f"Avg alerts:       {self.avg_alerts:.0f}",
        ]

        if self.terminal_counts:
            lines.append(f"Avg terminal:     {self.avg_terminal:.1f}/6 challenges")

        if self.challenge_terminal_rates:
            lines.append(f"\nChallenge Terminal Rates:")
            for name, rate in sorted(self.challenge_terminal_rates.items(), key=lambda x: -x[1]):
                bar = "█" * int(rate * 20)
                lines.append(f"  {name:20s} {rate:5.1%} {bar}")

        if self.severity_totals:
            lines.append(f"\nSeverity Totals (across all runs):")
            for sev, count in sorted(self.severity_totals.items()):
                lines.append(f"  {sev:12s} {count:>8,}")

        return "\n".join(lines)


class MonteCarloRunner:
    """Runs N mission simulations with different seeds for statistical analysis.

    Supports both orbital (Basilisk) and interstellar missions.
    """

    def __init__(
        self,
        mission_type: str = "INTERSTELLAR",
        num_runs: int = 100,
        years: int = 100,
        crew_size: int = 4,
        altitude_km: float = 400.0,
        inclination_deg: float = 51.6,
        sim_duration_s: float = 5520.0,
    ) -> None:
        self._mission_type = mission_type
        self._num_runs = num_runs
        self._years = years
        self._crew_size = crew_size
        self._altitude_km = altitude_km
        self._inclination_deg = inclination_deg
        self._sim_duration_s = sim_duration_s

    async def run(self) -> MonteCarloStats:
        """Execute all Monte Carlo runs and collect statistics."""
        stats = MonteCarloStats(num_runs=self._num_runs)
        t0 = time.time()

        challenge_terminal_counts: dict[str, int] = {}

        logger.info("montecarlo.starting", runs=self._num_runs, type=self._mission_type)

        for i in range(self._num_runs):
            try:
                result = await self._run_single(seed=i)
                stats.num_successful += 1 if result["success"] else 0
                stats.event_counts.append(result["events"])
                stats.alert_counts.append(result["alerts"])

                if "terminal_count" in result:
                    stats.terminal_counts.append(result["terminal_count"])

                # Track per-challenge terminal rates
                for name, status in result.get("challenge_states", {}).items():
                    if name not in challenge_terminal_counts:
                        challenge_terminal_counts[name] = 0
                    if status == "terminal":
                        challenge_terminal_counts[name] += 1

                # Aggregate severity
                for sev, count in result.get("severity_dist", {}).items():
                    stats.severity_totals[sev] = stats.severity_totals.get(sev, 0) + count

                if (i + 1) % max(1, self._num_runs // 10) == 0:
                    logger.info("montecarlo.progress", run=i + 1, total=self._num_runs)

            except Exception as e:
                logger.warning("montecarlo.run_failed", run=i, error=str(e))
                stats.event_counts.append(0)
                stats.alert_counts.append(0)

        # Compute terminal rates
        for name, count in challenge_terminal_counts.items():
            stats.challenge_terminal_rates[name] = count / self._num_runs

        stats.total_wall_time_s = time.time() - t0
        logger.info("montecarlo.complete", runs=self._num_runs,
                     success_rate=f"{stats.success_rate:.1%}",
                     wall_time=f"{stats.total_wall_time_s:.2f}s")
        return stats

    async def _run_single(self, seed: int) -> dict[str, Any]:
        """Run a single mission with given seed."""
        if self._mission_type == "INTERSTELLAR":
            return await self._run_interstellar(seed)
        else:
            return await self._run_orbital(seed)

    async def _run_interstellar(self, seed: int) -> dict[str, Any]:
        """Run interstellar mission with challenge orchestrator."""
        from aria.simulation.interstellar import InterstellarSimulation
        from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator

        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=self._crew_size, seed=seed)
        orch = InterstellarChallengeOrchestrator(crew_size=self._crew_size, seed=seed)

        total_events = 0
        total_alerts = 0
        severity_dist: dict[str, int] = {}

        for year in range(1, self._years + 1):
            events = sim.simulate_year()
            cr = orch.simulate_year(float(year), sim.state.distance_ly)

            total_events += len(events) + len(cr["events"])
            for e in cr["events"]:
                sev = e.get("severity", "UNKNOWN")
                severity_dist[sev] = severity_dist.get(sev, 0) + 1
                if sev in ("CRITICAL", "EMERGENCY"):
                    total_alerts += 1

        summary = orch.get_summary()
        terminal = sum(1 for s in summary.values() if s["status"] == "terminal")

        return {
            "success": True,
            "events": total_events,
            "alerts": total_alerts,
            "terminal_count": terminal,
            "challenge_states": {n: s["status"] for n, s in summary.items()},
            "severity_dist": severity_dist,
        }

    async def _run_orbital(self, seed: int) -> dict[str, Any]:
        """Run orbital mission with Basilisk."""
        from aria.simulation.mission_runner import MissionConfig, MissionRunner

        runner = MissionRunner(MissionConfig(
            name=f"MC-{seed}",
            mission_type="LEO",
            altitude_km=self._altitude_km,
            inclination_deg=self._inclination_deg,
            sim_duration_s=self._sim_duration_s,
            telemetry_interval_s=60.0,
            enable_agents=False,
        ))
        results = await runner.run()

        return {
            "success": results.success,
            "events": results.total_events,
            "alerts": results.total_alerts,
            "severity_dist": results.severity_distribution,
        }
