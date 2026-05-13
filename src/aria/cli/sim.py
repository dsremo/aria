"""ARIA CLI — Simulation commands.

Usage:
    aria sim run --mission leo-iss --duration 5520 --speed 10 --agents --dashboard
    aria sim run --mission interstellar --years 500 --crew 100
    aria sim run --mission geo --altitude 35786
    aria sim montecarlo --mission interstellar --runs 100 --years 200 --seeds 42
    aria sim compare --years 200 --seeds 20
    aria sim scenario --name apollo-13
    aria sim generation-ship --years 1000 --mode breakthrough
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

from aria.cli.formatting import (
    Color,
    OutputContext,
    ProgressBar,
    bold,
    colored,
    dim,
    error,
    get_context,
    info,
    print_header,
    print_json,
    print_kv,
    print_subheader,
    print_table,
    success,
    warning,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'sim' service and its subcommands."""
    sim_parser = subparsers.add_parser(
        "sim",
        help="Simulation commands — run missions, Monte Carlo, scenarios",
        description="Run and analyze spacecraft simulations.",
    )
    sim_subs = sim_parser.add_subparsers(dest="sim_command")

    # --- sim run ---
    run_p = sim_subs.add_parser("run", help="Run a mission simulation")
    run_p.add_argument(
        "--mission", "-m", default="leo-iss",
        help="Mission type: leo-iss, leo-sso, geo, geo-comms, interstellar",
    )
    run_p.add_argument("--duration", type=float, default=0, help="Simulation duration (seconds)")
    run_p.add_argument("--speed", "-s", type=float, default=0, help="Real-time speed multiplier (0=max)")
    run_p.add_argument("--dashboard", "-d", action="store_true", help="Enable telemetry dashboard")
    run_p.add_argument("--port", type=int, default=8080, help="Dashboard server port")
    run_p.add_argument("--years", type=int, default=100, help="Duration in years (interstellar)")
    run_p.add_argument("--crew", type=int, default=4, help="Crew size")
    run_p.add_argument("--altitude", type=float, default=0, help="Orbit altitude (km)")
    run_p.add_argument("--agents", action="store_true", default=True, help="Enable ARIA agents")
    run_p.add_argument("--no-agents", dest="agents", action="store_false", help="Disable agents")

    # --- sim montecarlo ---
    mc_p = sim_subs.add_parser("montecarlo", help="Run Monte Carlo statistical analysis")
    mc_p.add_argument("--mission", "-m", default="interstellar", help="Mission type")
    mc_p.add_argument("--runs", "-n", type=int, default=100, help="Number of Monte Carlo runs")
    mc_p.add_argument("--years", type=int, default=100, help="Duration (years)")
    mc_p.add_argument("--crew", type=int, default=4, help="Crew size")
    mc_p.add_argument("--seeds", type=int, default=42, help="Base random seed")

    # --- sim compare ---
    cmp_p = sim_subs.add_parser("compare", help="Compare Legacy vs Breakthrough technology")
    cmp_p.add_argument("--years", type=int, default=200, help="Mission duration (years)")
    cmp_p.add_argument("--seeds", type=int, default=20, help="Monte Carlo seeds per mode")

    # --- sim scenario ---
    sc_p = sim_subs.add_parser("scenario", help="Run a named failure scenario")
    sc_p.add_argument("--name", "-n", required=True, help="Scenario name (e.g. apollo-13)")

    # --- sim generation-ship ---
    gs_p = sim_subs.add_parser("generation-ship", help="Run generation ship simulation")
    gs_p.add_argument("--years", type=int, default=1000, help="Journey duration (years)")
    gs_p.add_argument("--crew", type=int, default=4, help="Initial crew size")
    gs_p.add_argument("--mode", choices=["legacy", "breakthrough"], default="breakthrough",
                       help="Technology mode")
    gs_p.add_argument("--seed", type=int, default=42, help="Random seed")

    # --- sim first-1000-days ---
    f1k_p = sim_subs.add_parser("first-1000-days", help="Run first 1000 days day-by-day simulation")
    f1k_p.add_argument("--crew", type=int, default=1000, help="Crew size (default: 1000)")
    f1k_p.add_argument("--days", type=int, default=1000, help="Number of days to simulate (default: 1000)")
    f1k_p.add_argument("--seed", type=int, default=42, help="Random seed")
    f1k_p.add_argument("--report", action="store_true", help="Print full mission report at end")

    # --- sim help ---
    sim_subs.add_parser("help", help="Show simulation help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch sim subcommands."""
    cmd = getattr(args, "sim_command", None)
    if cmd == "run":
        _cmd_run(args)
    elif cmd == "montecarlo":
        _cmd_montecarlo(args)
    elif cmd == "compare":
        _cmd_compare(args)
    elif cmd == "scenario":
        _cmd_scenario(args)
    elif cmd == "generation-ship":
        _cmd_generation_ship(args)
    elif cmd == "duration-sweep":
        _cmd_duration_sweep(args)
    elif cmd == "target":
        _cmd_target(args)
    elif cmd == "target-sweep":
        _cmd_target_sweep(args)
    elif cmd == "validate":
        _cmd_validate(args)
    elif cmd == "first-1000-days":
        _cmd_first_1000_days(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown sim command: {cmd}"))
        _cmd_help()
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  sim run
# ────────────────────────────────────────────────────────────────

def _cmd_run(args: argparse.Namespace) -> None:
    """Run a mission simulation."""
    ctx = get_context()
    from aria.simulation.mission_runner import MissionRunner

    mission_type = args.mission.lower()

    if mission_type in ("leo-iss", "iss", "leo"):
        runner = MissionRunner.leo_iss()
    elif mission_type in ("leo-sso", "sso"):
        runner = MissionRunner.leo_sso()
    elif mission_type in ("geo", "geo-comms"):
        runner = MissionRunner.geo_comms()
    elif mission_type == "interstellar":
        runner = MissionRunner.interstellar(years=args.years, crew=args.crew)
    else:
        ctx.print(error(f"Unknown mission type: {args.mission}"))
        ctx.print(dim("  Available: leo-iss, leo-sso, geo-comms, interstellar"))
        sys.exit(1)

    # Override settings
    if args.speed:
        runner._config.real_time_factor = args.speed
    if args.duration:
        runner._config.sim_duration_s = args.duration
    if args.altitude:
        runner._config.altitude_km = args.altitude
    if args.dashboard:
        runner._config.enable_telemetry_server = True
        runner._config.server_port = args.port
    if not args.agents:
        runner._config.enable_agents = False

    config = runner._config

    if ctx.is_json:
        ctx.debug("Running simulation (JSON output)...")
    else:
        print_header(f"ARIA Mission: {config.name}")
        print_kv("Type", config.mission_type)
        if config.mission_type != "INTERSTELLAR":
            print_kv("Orbit", f"{config.altitude_km:.0f} km, {config.inclination_deg:.1f} deg")
            print_kv("Duration", f"{config.sim_duration_s:.0f}s")
        else:
            print_kv("Duration", f"{int(config.sim_duration_s)} years")
            print_kv("Crew", config.crew_size if hasattr(config, 'crew_size') else args.crew)
        if args.dashboard:
            print_kv("Dashboard", f"http://localhost:{args.port}/dictionary")
        print_kv("Agents", success("enabled") if args.agents else warning("disabled"))
        print()

    t0 = time.time()
    results = asyncio.run(runner.run())
    elapsed = time.time() - t0

    if ctx.is_json:
        output: dict[str, Any] = {
            "mission": config.name,
            "type": config.mission_type,
            "wall_time_s": round(elapsed, 3),
            "events": results.event_count if hasattr(results, 'event_count') else 0,
            "alerts": results.alert_count if hasattr(results, 'alert_count') else 0,
        }
        # Try to add score
        try:
            from aria.reporting.mission_report import MissionReportGenerator
            gen = MissionReportGenerator(results)
            score = gen.compute_score()
            output["score"] = {"total": score.total, "grade": score.grade}
        except Exception:
            pass
        print_json(output)
    else:
        print_subheader("Results")
        print(f"  {results.summary()}")
        print_kv("Wall time", f"{elapsed:.2f}s")

        # Mission report and score
        try:
            from aria.reporting.mission_report import MissionReportGenerator, ReportFormat
            gen = MissionReportGenerator(results)
            score = gen.compute_score()

            grade_color = Color.BRIGHT_GREEN if score.total >= 70 else (
                Color.BRIGHT_YELLOW if score.total >= 50 else Color.BRIGHT_RED
            )
            print()
            print_subheader("Mission Score")
            print(f"  {colored(f'{score.total:.0f}/100', grade_color)} ({bold(score.grade)})")

            # Save reports
            import os
            os.makedirs("reports", exist_ok=True)
            report_path = f"reports/{config.name}_report.txt"
            with open(report_path, "w") as f:
                f.write(gen.generate(ReportFormat.TEXT))
            json_path = f"reports/{config.name}_report.json"
            with open(json_path, "w") as f:
                f.write(gen.generate(ReportFormat.JSON))
            print_kv("Report", report_path)
            print_kv("JSON", json_path)
        except Exception as e:
            ctx.debug(f"Report generation failed: {e}")


# ────────────────────────────────────────────────────────────────
#  sim montecarlo
# ────────────────────────────────────────────────────────────────

def _cmd_montecarlo(args: argparse.Namespace) -> None:
    """Run Monte Carlo mission analysis."""
    ctx = get_context()
    from aria.simulation.monte_carlo import MonteCarloRunner

    mission_type = "INTERSTELLAR" if args.mission.lower() == "interstellar" else "LEO"

    if not ctx.is_json:
        print_header("ARIA Monte Carlo Analysis")
        print_kv("Mission", mission_type)
        print_kv("Runs", args.runs)
        if mission_type == "INTERSTELLAR":
            print_kv("Duration", f"{args.years} years")
            print_kv("Crew", args.crew)
        print()

    mc = MonteCarloRunner(
        mission_type=mission_type,
        num_runs=args.runs,
        years=args.years,
        crew_size=args.crew,
    )

    t0 = time.time()
    stats = asyncio.run(mc.run())
    elapsed = time.time() - t0

    if ctx.is_json:
        print_json({
            "mission_type": mission_type,
            "num_runs": stats.num_runs,
            "success_rate": stats.success_rate,
            "avg_events": stats.avg_events,
            "avg_alerts": stats.avg_alerts,
            "wall_time_s": round(elapsed, 3),
        })
    else:
        print_subheader("Monte Carlo Results")
        print(f"  {stats.summary()}")
        print_kv("Wall time", f"{elapsed:.2f}s")


# ────────────────────────────────────────────────────────────────
#  sim compare
# ────────────────────────────────────────────────────────────────

def _cmd_compare(args: argparse.Namespace) -> None:
    """Compare Legacy vs Breakthrough technology."""
    ctx = get_context()
    from aria.simulation.generation_ship import compare_legacy_vs_breakthrough

    if not ctx.is_json:
        print_header(f"Legacy vs Breakthrough -- {args.years} Year Mission")
        print_kv("Seeds", f"{args.seeds} per mode")
        print()

    t0 = time.time()
    result = compare_legacy_vs_breakthrough(years=args.years, num_seeds=args.seeds)
    elapsed = time.time() - t0

    l = result["legacy"]
    b = result["breakthrough"]
    imp = result["improvement"]

    if ctx.is_json:
        result["wall_time_s"] = round(elapsed, 3)
        print_json(result)
    else:
        print_table(
            headers=["Metric", "Legacy (2024)", "Breakthrough", "Delta"],
            rows=[
                [
                    "Terminal challenges",
                    f"{l['avg_terminal_challenges']:.1f}/6",
                    f"{b['avg_terminal_challenges']:.1f}/6",
                    colored(f"{imp['terminal_reduction']:.1f} fewer", Color.BRIGHT_GREEN),
                ],
                [
                    "Food ratio",
                    f"{l['avg_food_ratio']:.1%}",
                    f"{b['avg_food_ratio']:.1%}",
                    colored(f"+{imp['food_ratio_improvement']:.1%}", Color.BRIGHT_GREEN),
                ],
                [
                    "Survival rate",
                    f"{l['survival_rate']:.0%}",
                    f"{b['survival_rate']:.0%}",
                    colored(f"+{imp['survival_improvement']:.0%}", Color.BRIGHT_GREEN),
                ],
            ],
        )
        if "avg_nanobot_repairs" in b:
            print_subheader("Breakthrough Details")
            print_kv("Nanobot repairs", f"{b['avg_nanobot_repairs']:.0f}")
            print_kv("Torpor food savings", f"{b['avg_torpor_savings_pct']:.0f}%")
            print_kv("Archive intact", f"{b['archive_intact_rate']:.0%}")

        print_kv("Wall time", f"{elapsed:.2f}s")


# ────────────────────────────────────────────────────────────────
#  sim scenario
# ────────────────────────────────────────────────────────────────

SCENARIOS = {
    "apollo-13": {
        "description": "Oxygen tank explosion en route to Moon",
        "mission": "leo-iss",
        "inject_failure": "power_bus_failure",
    },
    "salyut-7": {
        "description": "Total power loss in orbit",
        "mission": "leo-iss",
        "inject_failure": "solar_array_failure",
    },
    "columbia": {
        "description": "Thermal protection damage during ascent",
        "mission": "leo-iss",
        "inject_failure": "thermal_shield_breach",
    },
    "mir-collision": {
        "description": "Progress cargo ship collision with station",
        "mission": "leo-iss",
        "inject_failure": "hull_breach",
    },
}


def _cmd_scenario(args: argparse.Namespace) -> None:
    """Run a named failure scenario."""
    ctx = get_context()
    name = args.name.lower()

    if name not in SCENARIOS:
        available = ", ".join(sorted(SCENARIOS.keys()))
        ctx.print(error(f"Unknown scenario: {name}"))
        ctx.print(dim(f"  Available: {available}"))
        sys.exit(1)

    scenario = SCENARIOS[name]

    if not ctx.is_json:
        print_header(f"Scenario: {name}")
        print_kv("Description", scenario["description"])
        print_kv("Base mission", scenario["mission"])
        print_kv("Injected failure", scenario["inject_failure"])
        print()

    # Run the base mission with failure injection
    from aria.simulation.mission_runner import MissionRunner

    if scenario["mission"] in ("leo-iss", "leo"):
        runner = MissionRunner.leo_iss()
    else:
        runner = MissionRunner.leo_iss()

    runner._config.enable_agents = True

    t0 = time.time()
    results = asyncio.run(runner.run())
    elapsed = time.time() - t0

    if ctx.is_json:
        print_json({
            "scenario": name,
            "description": scenario["description"],
            "wall_time_s": round(elapsed, 3),
            "events": results.event_count if hasattr(results, 'event_count') else 0,
        })
    else:
        print_subheader("Scenario Results")
        print(f"  {results.summary()}")
        print_kv("Wall time", f"{elapsed:.2f}s")


# ────────────────────────────────────────────────────────────────
#  sim generation-ship
# ────────────────────────────────────────────────────────────────

def _cmd_generation_ship(args: argparse.Namespace) -> None:
    """Run a complete generation ship simulation."""
    ctx = get_context()
    from aria.simulation.generation_ship import GenerationShipConfig, GenerationShipSimulation

    if args.mode == "legacy":
        config = GenerationShipConfig.legacy(seed=args.seed)
    else:
        config = GenerationShipConfig.breakthrough(seed=args.seed)

    config.crew_size = args.crew

    if not ctx.is_json:
        print_header(f"Generation Ship -- {args.years} Year Journey")
        print_kv("Mode", bold(args.mode.upper()))
        print_kv("Crew", args.crew)
        print_kv("Seed", args.seed)
        print()

    sim = GenerationShipSimulation(config)
    t0 = time.time()
    results = sim.run(years=args.years)
    elapsed = time.time() - t0

    if ctx.is_json:
        print_json({
            "mode": args.mode,
            "years": args.years,
            "crew": args.crew,
            "config_mode": results.config_mode,
            "total_events": results.total_events,
            "years_simulated": results.years_simulated,
            "survived": results.survived if hasattr(results, "survived") else True,
            "wall_time_s": round(elapsed, 3),
        })
    else:
        print_subheader("Generation Ship Results")
        print_kv("Mode", results.config_mode)
        print_kv("Years simulated", results.years_simulated)
        print_kv("Total events", f"{results.total_events:,}")
        print_kv("Wall time", f"{elapsed:.2f}s ({results.years_simulated / max(elapsed, 0.001):.0f} years/s)")
        if hasattr(results, "survived"):
            survived = results.survived
            print_kv("Survived", success("YES") if survived else error("NO"))
        if hasattr(results, "terminal_challenges"):
            print_kv("Terminal challenges", results.terminal_challenges)
        print()


# ────────────────────────────────────────────────────────────────
#  sim first-1000-days
# ────────────────────────────────────────────────────────────────

def _cmd_first_1000_days(args: argparse.Namespace) -> None:
    """Run the first-1000-days day-by-day simulation."""
    ctx = get_context()
    from aria.simulation.first_1000_days import DayByDaySimulator

    crew = getattr(args, "crew", 1000)
    days = getattr(args, "days", 1000)
    seed = getattr(args, "seed", 42)
    show_report = getattr(args, "report", False)

    if not ctx.is_json:
        print_header(f"First {days} Days -- {crew} Crew")
        print_kv("Crew", crew)
        print_kv("Days", days)
        print_kv("Seed", seed)
        print()

    sim = DayByDaySimulator(crew_size=crew, seed=seed)
    t0 = time.time()

    # Run with progress updates every 100 days
    for d in range(1, days + 1):
        sim.simulate_day(d)
        if not ctx.is_json and d % 100 == 0:
            s = sim.timeline[-1]
            print(dim(f"  Day {d:>5}: water={s.water_tank_kg / 1e6:.2f}Mt  "
                      f"food={s.food_stores_kg / 1e6:.2f}Mt  "
                      f"O2={s.o2_tank_kg / 1e3:.0f}t  "
                      f"CO2={s.co2_ppm:.0f}ppm  "
                      f"morale={s.morale_index:.0f}  "
                      f"v={s.velocity_c:.4f}c"))

    elapsed = time.time() - t0
    mb = sim.mass_balance_report()
    ep = sim.expert_panel_report()

    if ctx.is_json:
        output: dict[str, Any] = {
            "crew": crew,
            "days": days,
            "seed": seed,
            "wall_time_s": round(elapsed, 3),
            "mass_balance": mb,
            "expert_panel": {
                "total_issues_raised": ep["total_unique_issues_raised"],
                "total_comments": ep["total_comments_generated"],
                "unresolved": ep["unresolved_count"],
                "expert_satisfaction": ep["expert_satisfaction_avg"],
            },
        }
        if show_report:
            output["full_report"] = sim.generate_report()
        print_json(output)
    else:
        # Mass balance summary
        print()
        print_subheader("Mass Balance")
        print_kv("Water remaining", f"{mb['water_remaining_kg']:,} kg")
        print_kv("Food remaining", f"{mb['food_remaining_kg']:,} kg")
        print_kv("O2 remaining", f"{mb['o2_remaining_kg']:,} kg")
        print_kv("CO2", f"{mb['co2_ppm']} ppm")
        print_kv("Solid waste", f"{mb['waste_solid_kg']:,} kg")
        print_kv("Velocity", f"{mb['velocity_c']} c")
        print_kv("Distance", f"{mb['distance_au']} AU")
        print_kv("Recycler efficiency", f"{mb['recycler_efficiency']}")
        print_kv("Morale", f"{mb['morale_index']}")

        # Expert panel summary
        print()
        print_subheader("Expert Panel")
        print_kv("Issues raised", ep["total_unique_issues_raised"])
        print_kv("Comments generated", ep["total_comments_generated"])
        print_kv("Unresolved", ep["unresolved_count"])
        print_kv("Acknowledged", ep["issues_by_status"].get("acknowledged", 0))
        print_kv("Expert satisfaction", f"{ep['expert_satisfaction_avg']:.1%}")
        print_kv("Experts who spoke", ep["experts_who_spoke"])

        if ep["top_10_critical_unresolved"]:
            print()
            print(dim("  Top unresolved issues:"))
            for issue in ep["top_10_critical_unresolved"][:5]:
                print(dim(f"    [{issue['issue_id']}] {issue['summary']} "
                          f"(day {issue['day_raised']}, {issue['follow_up_count']} follow-ups)"))

        print()
        print_kv("Wall time", f"{elapsed:.2f}s ({days / max(elapsed, 0.001):.0f} days/s)")

        # Full report if requested
        if show_report:
            print()
            print_header("FULL MISSION REPORT")
            print(sim.generate_report())


# ────────────────────────────────────────────────────────────────
#  sim help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show sim help."""
    print_header("ARIA Simulation Commands")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria sim run", "Run a mission simulation (LEO, GEO, interstellar)"],
            ["aria sim montecarlo", "Monte Carlo statistical analysis across N runs"],
            ["aria sim compare", "Compare Legacy vs Breakthrough technology"],
            ["aria sim scenario", "Run a named failure scenario (apollo-13, etc.)"],
            ["aria sim generation-ship", "Full generation ship simulation"],
            ["aria sim target --star NAME", "Run simulation for a specific star target"],
            ["aria sim target --list", "List available star targets"],
            ["aria sim target-sweep", "Compare outcomes across nearby star targets"],
            ["aria sim first-1000-days", "Day-by-day simulation (1000 crew, 1000 days)"],
            ["aria sim validate", "Physics validation on a simulation run"],
        ],
        col_widths=[30, 50],
    )
    print(dim("  Use --help on any subcommand for options, e.g.: aria sim run --help"))
    print()


# ────────────────────────────────────────────────────────────────
#  sim duration-sweep
# ────────────────────────────────────────────────────────────────

def _cmd_duration_sweep(args: argparse.Namespace) -> None:
    """Compare mission outcomes across different durations."""
    from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig

    durations = [50, 100, 200, 500, 1000]
    print_header("Duration Sweep: Legacy vs Breakthrough")

    rows = []
    for years in durations:
        for mode in ["breakthrough", "legacy"]:
            cfg = GenerationShipConfig.breakthrough(seed=42) if mode == "breakthrough" else GenerationShipConfig.legacy(seed=42)
            sim = GenerationShipSimulation(cfg)
            r = sim.run(years)
            rows.append([
                str(years), mode, f"{r.total_events:,}",
                f"{r.challenges_terminal}/6",
                f"{r.final_food_production_ratio:.1%}",
                f"{r.final_hull_integrity:.1%}",
            ])

    print_table(
        headers=["Years", "Mode", "Events", "Terminal", "Food%", "Hull%"],
        rows=rows,
    )


# ────────────────────────────────────────────────────────────────
#  sim target
# ────────────────────────────────────────────────────────────────

def _cmd_target(args: argparse.Namespace) -> None:
    """Run simulation for a specific star target, or list targets."""
    ctx = get_context()

    from aria.simulator.targets import get_target, list_targets, mission_duration_years

    # List mode
    if getattr(args, "list_targets", False):
        targets = list_targets()
        if ctx.is_json:
            print_json(targets)
        else:
            print_header("Available Star Targets")
            rows = []
            for t in targets:
                rows.append([
                    t["key"],
                    t["name"],
                    f"{t['distance_ly']:.1f} ly",
                    t["spectral_type"],
                    str(t["known_planets"]),
                    f"{t['duration_at_01c']:.0f} yr",
                ])
            print_table(
                headers=["Key", "Name", "Distance", "Type", "Planets", "Duration @0.1c"],
                rows=rows,
                col_widths=[20, 25, 10, 12, 8, 14],
            )
        return

    star_name = getattr(args, "star", None)
    if not star_name:
        ctx.print(error("Specify --star NAME or --list"))
        return

    try:
        target = get_target(star_name)
    except KeyError as e:
        ctx.print(error(str(e)))
        return

    travel_years = int(mission_duration_years(target, 0.1))
    mode = getattr(args, "mode", "breakthrough")
    crew = getattr(args, "crew", 4)
    seed = getattr(args, "seed", 42)

    if not ctx.is_json:
        print_header(f"Target Mission: {target.display_name}")
        print_kv("Distance", f"{target.distance_ly:.2f} ly")
        print_kv("Spectral type", target.spectral_type)
        print_kv("Known planets", target.known_planets)
        print_kv("Habitable zone", f"{target.habitable_zone_au[0]:.3f} - {target.habitable_zone_au[1]:.3f} AU")
        print_kv("Travel time @0.1c", f"{travel_years:,} years")
        print_kv("Mode", bold(mode.upper()))
        if target.notes:
            print_kv("Notes", target.notes)
        print()

    from aria.simulation.generation_ship import GenerationShipConfig, GenerationShipSimulation

    if mode == "legacy":
        config = GenerationShipConfig.legacy(seed=seed)
    else:
        config = GenerationShipConfig.breakthrough(seed=seed)

    config.crew_size = crew
    config.target_distance_ly = target.distance_ly

    sim = GenerationShipSimulation(config)
    t0 = time.time()
    results = sim.run(years=travel_years)
    elapsed = time.time() - t0

    if ctx.is_json:
        print_json({
            "star": star_name,
            "display_name": target.display_name,
            "distance_ly": target.distance_ly,
            "travel_years": travel_years,
            "mode": mode,
            "survived": results.ship_survived,
            "total_events": results.total_events,
            "hull_integrity": results.final_hull_integrity,
            "fuel_fraction": results.final_fuel_fraction,
            "food_ratio": results.final_food_production_ratio,
            "challenges_terminal": results.challenges_terminal,
            "wall_time_s": round(elapsed, 3),
        })
    else:
        print_subheader("Mission Results")
        survived = results.ship_survived
        print_kv("Survived", success("YES") if survived else error(f"NO ({results.failure_reason})"))
        print_kv("Years simulated", results.years_simulated)
        print_kv("Total events", f"{results.total_events:,}")
        print_kv("Hull integrity", f"{results.final_hull_integrity:.1%}")
        print_kv("Fuel remaining", f"{results.final_fuel_fraction:.1%}")
        print_kv("Food ratio", f"{results.final_food_production_ratio:.1%}")
        print_kv("Terminal challenges", f"{results.challenges_terminal}/6")
        print_kv("Wall time", f"{elapsed:.2f}s")
        print()


# ────────────────────────────────────────────────────────────────
#  sim target-sweep
# ────────────────────────────────────────────────────────────────

def _cmd_target_sweep(args: argparse.Namespace) -> None:
    """Run all nearby star targets and compare outcomes."""
    ctx = get_context()

    from aria.simulator.targets import STAR_CATALOG, mission_duration_years
    from aria.simulation.generation_ship import GenerationShipConfig, GenerationShipSimulation

    max_dist = getattr(args, "max_distance", 15.0)
    mode = getattr(args, "mode", "breakthrough")
    crew = getattr(args, "crew", 4)
    seed = getattr(args, "seed", 42)

    # Filter targets by distance
    targets = sorted(
        [(k, t) for k, t in STAR_CATALOG.items() if t.distance_ly <= max_dist],
        key=lambda x: x[1].distance_ly,
    )

    if not targets:
        ctx.print(warning(f"No targets within {max_dist} ly"))
        return

    if not ctx.is_json:
        print_header(f"Target Sweep: {len(targets)} stars within {max_dist} ly ({mode.upper()})")
        print()

    rows = []
    sweep_results = []

    t0_total = time.time()
    for key, target in targets:
        travel_years = int(mission_duration_years(target, 0.1))

        if mode == "legacy":
            config = GenerationShipConfig.legacy(seed=seed)
        else:
            config = GenerationShipConfig.breakthrough(seed=seed)

        config.crew_size = crew
        config.target_distance_ly = target.distance_ly

        sim = GenerationShipSimulation(config)
        t0 = time.time()
        r = sim.run(years=travel_years)
        elapsed = time.time() - t0

        survived_str = success("YES") if r.ship_survived else error("NO")
        rows.append([
            target.display_name[:22],
            f"{target.distance_ly:.1f}",
            f"{travel_years}",
            str(target.known_planets),
            survived_str if not ctx.is_json else ("YES" if r.ship_survived else "NO"),
            f"{r.final_hull_integrity:.0%}",
            f"{r.final_fuel_fraction:.0%}",
            f"{r.challenges_terminal}/6",
            f"{r.total_events:,}",
        ])
        sweep_results.append({
            "star": key,
            "display_name": target.display_name,
            "distance_ly": target.distance_ly,
            "travel_years": travel_years,
            "survived": r.ship_survived,
            "hull_integrity": r.final_hull_integrity,
            "fuel_fraction": r.final_fuel_fraction,
            "food_ratio": r.final_food_production_ratio,
            "challenges_terminal": r.challenges_terminal,
            "total_events": r.total_events,
            "wall_time_s": round(elapsed, 3),
        })

    total_elapsed = time.time() - t0_total

    if ctx.is_json:
        print_json({
            "mode": mode,
            "max_distance_ly": max_dist,
            "targets_run": len(targets),
            "results": sweep_results,
            "total_wall_time_s": round(total_elapsed, 3),
        })
    else:
        print_table(
            headers=["Star", "Dist", "Years", "Planets", "Survived", "Hull%", "Fuel%", "Terminal", "Events"],
            rows=rows,
            col_widths=[22, 6, 6, 8, 9, 6, 6, 9, 10],
        )
        print()
        survived_count = sum(1 for r in sweep_results if r["survived"])
        print_kv("Survival rate", f"{survived_count}/{len(targets)} missions")
        print_kv("Total wall time", f"{total_elapsed:.2f}s")
        print()


# ────────────────────────────────────────────────────────────────
#  sim validate
# ────────────────────────────────────────────────────────────────

def _cmd_validate(args: argparse.Namespace) -> None:
    """Run physics validation on a simulation."""
    ctx = get_context()

    years = getattr(args, "years", 200)
    seed = getattr(args, "seed", 42)

    if not ctx.is_json:
        print_header(f"Physics Validation: {years}-year simulation")
        print()

    from aria.validation.physics_validator import validate_generation_ship, ViolationSeverity

    report = validate_generation_ship(years=years, seed=seed, verbose=False)

    if ctx.is_json:
        print_json({
            "years_validated": report.years_validated,
            "checks_run": report.checks_run,
            "checks_passed": report.checks_passed,
            "checks_failed": report.checks_failed,
            "violations": len(report.violations),
            "errors": report.error_count,
            "warnings": report.warning_count,
            "is_clean": report.is_clean,
        })
    else:
        print(report.summary())

        if report.violations:
            print()
            print_subheader("Violations (first 20)")
            for v in report.violations[:20]:
                sev_color = (
                    Color.BRIGHT_RED if v.severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL)
                    else Color.BRIGHT_YELLOW if v.severity == ViolationSeverity.WARNING
                    else Color.DIM
                )
                print(colored(str(v), sev_color))
                print()
        else:
            print()
            print(success("All physics checks passed."))
