"""ARIA CLI — Crew lifecycle, ecosystem, and genetics commands."""

from __future__ import annotations

import argparse
import json
import time


def handle_crew(args: argparse.Namespace, output_json: bool = False) -> None:
    cmd = getattr(args, "command", None)
    if cmd == "lifecycle":
        _crew_lifecycle(args, output_json)
    elif cmd == "ecosystem":
        _crew_ecosystem(args, output_json)
    elif cmd == "genetics":
        _crew_genetics(args, output_json)
    else:
        print("Usage: aria crew <lifecycle|ecosystem|genetics>")


def _crew_lifecycle(args: argparse.Namespace, output_json: bool) -> None:
    from aria.simulation.crew_ecosystem import CrewEcosystemOrchestrator

    years = getattr(args, "years", 200)
    initial = getattr(args, "initial_crew", 100)

    print(f"\n  Crew Lifecycle Simulation: {years} years, {initial} initial crew\n")

    t0 = time.time()
    orch = CrewEcosystemOrchestrator(initial_crew_size=initial, seed=42)

    all_events = []
    for y in range(1, years + 1):
        result = orch.simulate_year(float(y))
        all_events.extend(result.get("events", []))

    dt = time.time() - t0
    pop = orch.lifecycle.state.total_alive

    data = {
        "years": years,
        "initial_crew": initial,
        "final_population": pop,
        "total_events": len(all_events),
        "wall_time_s": round(dt, 3),
    }

    if output_json:
        print(json.dumps(data, indent=2))
    else:
        print(f"  Final population: {pop}")
        print(f"  Events: {len(all_events)}")
        print(f"  Time: {dt:.3f}s")


def _crew_ecosystem(args: argparse.Namespace, output_json: bool) -> None:
    from aria.simulation.crew_ecosystem import ClosedLoopEcosystemSimulator

    years = getattr(args, "years", 500)

    print(f"\n  Closed-Loop Ecosystem: {years} years\n")

    t0 = time.time()
    eco = ClosedLoopEcosystemSimulator(seed=42)

    for y in range(1, years + 1):
        eco.simulate_year(float(y), population=4)

    dt = time.time() - t0
    elements = eco.state.elements_kg

    data = {
        "years": years,
        "elements_kg": {k: round(v, 2) for k, v in elements.items()},
        "wall_time_s": round(dt, 3),
    }

    if output_json:
        print(json.dumps(data, indent=2))
    else:
        print(f"  {'Element':<12} {'Remaining (kg)':>15}")
        print(f"  {'-'*28}")
        for elem, kg in sorted(elements.items(), key=lambda x: x[1]):
            bar = "█" * min(40, int(kg / 10))
            print(f"  {elem:<12} {kg:>12.1f}kg  {bar}")
        print(f"\n  Time: {dt:.3f}s")


def _crew_genetics(args: argparse.Namespace, output_json: bool) -> None:
    from aria.simulation.interstellar_challenges import GeneticDiversitySimulator

    pop = getattr(args, "population", 50)
    years = getattr(args, "years", 300)

    print(f"\n  Genetic Diversity: {pop} population, {years} years\n")

    t0 = time.time()
    sim = GeneticDiversitySimulator(initial_population=pop, seed=42)

    for y in range(1, years + 1):
        sim.simulate_year(float(y))

    dt = time.time() - t0
    g = sim.genetics

    data = {
        "years": years,
        "initial_population": pop,
        "final_population": g.population,
        "generation": g.generation,
        "inbreeding_F": round(g.inbreeding_coefficient, 4),
        "heterozygosity": round(g.heterozygosity, 4),
        "genetic_diseases": g.genetic_diseases,
        "frozen_embryos_remaining": g.frozen_embryos,
        "wall_time_s": round(dt, 3),
    }

    if output_json:
        print(json.dumps(data, indent=2))
    else:
        print(f"  Population:    {g.population}")
        print(f"  Generation:    {g.generation}")
        print(f"  Inbreeding F:  {g.inbreeding_coefficient:.4f}")
        print(f"  Heterozygosity:{g.heterozygosity:.4f}")
        print(f"  Diseases:      {g.genetic_diseases}")
        print(f"  Embryos left:  {g.frozen_embryos}")
        print(f"  Time:          {dt:.3f}s")
