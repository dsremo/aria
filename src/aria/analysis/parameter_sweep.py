"""Parameter Sweep — systematically explore how parameters affect outcomes.

Vary one parameter while holding others constant to find optimal values.

Usage:
    sweep = ParameterSweep()
    results = sweep.sweep_crew_size(
        crew_range=[4, 10, 50, 100, 200],
        years=200,
    )
    print(sweep.format_results(results))
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class SweepResult:
    """Result from one parameter value."""
    param_name: str
    param_value: Any
    terminal_challenges: int = 0
    food_ratio: float = 0.0
    events: int = 0
    wall_time_s: float = 0.0


class ParameterSweep:
    """Sweep parameters to find optimal generation ship configuration."""

    def sweep_crew_size(
        self, crew_range: list[int], years: int = 200, seed: int = 42
    ) -> list[SweepResult]:
        from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig
        results = []
        for crew in crew_range:
            t0 = time.time()
            cfg = GenerationShipConfig.breakthrough(seed=seed)
            cfg.crew_size = crew
            sim = GenerationShipSimulation(cfg)
            r = sim.run(years)
            results.append(SweepResult(
                param_name="crew_size", param_value=crew,
                terminal_challenges=r.challenges_terminal,
                food_ratio=r.final_food_production_ratio,
                events=r.total_events,
                wall_time_s=time.time() - t0,
            ))
        return results

    def sweep_velocity(
        self, velocity_range: list[float], years: int = 200, seed: int = 42
    ) -> list[SweepResult]:
        from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig
        results = []
        for v in velocity_range:
            t0 = time.time()
            cfg = GenerationShipConfig.breakthrough(seed=seed)
            cfg.velocity_c = v
            sim = GenerationShipSimulation(cfg)
            r = sim.run(years)
            results.append(SweepResult(
                param_name="velocity_c", param_value=v,
                terminal_challenges=r.challenges_terminal,
                food_ratio=r.final_food_production_ratio,
                events=r.total_events,
                wall_time_s=time.time() - t0,
            ))
        return results

    def sweep_mission_years(
        self, year_range: list[int], seed: int = 42
    ) -> list[SweepResult]:
        from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig
        results = []
        for yrs in year_range:
            t0 = time.time()
            cfg = GenerationShipConfig.breakthrough(seed=seed)
            sim = GenerationShipSimulation(cfg)
            r = sim.run(yrs)
            results.append(SweepResult(
                param_name="mission_years", param_value=yrs,
                terminal_challenges=r.challenges_terminal,
                food_ratio=r.final_food_production_ratio,
                events=r.total_events,
                wall_time_s=time.time() - t0,
            ))
        return results

    @staticmethod
    def format_results(results: list[SweepResult]) -> str:
        if not results:
            return "No results."
        param = results[0].param_name
        lines = [
            f"  Parameter Sweep: {param}",
            f"  {'─' * 65}",
            f"  {param:<15} {'Terminal':>10} {'Food%':>10} {'Events':>10} {'Time':>10}",
            f"  {'─' * 65}",
        ]
        for r in results:
            lines.append(
                f"  {str(r.param_value):<15} {r.terminal_challenges:>8}/6 "
                f"{r.food_ratio:>9.1%} {r.events:>10,} {r.wall_time_s:>9.2f}s"
            )
        return "\n".join(lines)
