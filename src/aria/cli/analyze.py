"""ARIA CLI — Analysis commands (sweep, diff, batch)."""

from __future__ import annotations

import argparse
import json


def handle_analyze(args: argparse.Namespace, output_json: bool = False) -> None:
    cmd = getattr(args, "command", None)
    if cmd == "sweep":
        _sweep(args, output_json)
    elif cmd == "diff":
        _diff(args, output_json)
    elif cmd == "batch":
        _batch(args, output_json)
    else:
        print("Usage: aria analyze <sweep|diff|batch>")


def _sweep(args: argparse.Namespace, output_json: bool) -> None:
    from aria.analysis.parameter_sweep import ParameterSweep

    param = getattr(args, "param", "crew_size")
    values = getattr(args, "values", "4,10,50")
    years = getattr(args, "years", 100)

    sweep = ParameterSweep()

    if param == "crew_size":
        vals = [int(v) for v in values.split(",")]
        results = sweep.sweep_crew_size(crew_range=vals, years=years)
    elif param == "velocity":
        vals = [float(v) for v in values.split(",")]
        results = sweep.sweep_velocity(velocity_range=vals, years=years)
    elif param == "years":
        vals = [int(v) for v in values.split(",")]
        results = sweep.sweep_mission_years(year_range=vals)
    else:
        print(f"Unknown parameter: {param}")
        return

    if output_json:
        print(json.dumps([{
            "param": r.param_name, "value": r.param_value,
            "terminal": r.terminal_challenges, "food_ratio": r.food_ratio,
            "events": r.events, "time_s": r.wall_time_s,
        } for r in results], indent=2))
    else:
        print(ParameterSweep.format_results(results))


def _diff(args: argparse.Namespace, output_json: bool) -> None:
    print("  Mission diff requires two mission IDs. Use: aria analyze diff --a <id> --b <id>")


def _batch(args: argparse.Namespace, output_json: bool) -> None:
    print("  Batch runner. Use: aria analyze batch --config <yaml>")
