"""ARIA CLI — Top-level command dispatcher.

Usage:
    aria <service> <command> [options]

Services:
    sim       Simulation commands (run, montecarlo, compare, generation-ship)
    system    System management (status, health, agents, benchmark, config)
    data      Data operations (import, replay, list, convert)
    report    Mission reports (generate, list, score)
    tools     External tool integration (basilisk, gmat, openmct, openc3)
    shield    Shield analysis (analyze, budget, erosion)
    crew      Crew simulation (lifecycle, ecosystem, genetics)
    mission   Mission persistence (list, show, delete)
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aria",
        description="ARIA — Autonomous Reasoning & Intelligence for Astronautics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Services:
  sim         Run spacecraft simulations
  system      System status and management
  data        Data import, replay, and conversion
  report      Mission report generation
  tools       External tool integration
  shield      Shield system analysis
  crew        Crew lifecycle simulation
  mission     Mission persistence (save/load)

Examples:
  aria sim run --mission leo-iss --agents
  aria sim montecarlo --runs 100 --years 200
  aria system status
  aria data list
  aria shield analyze --velocity 0.1
  aria crew lifecycle --years 200
  aria mission list
  aria mission show <id>
""",
    )

    parser.add_argument("--output", choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--version", action="version", version="ARIA 1.0.0")

    subparsers = parser.add_subparsers(dest="service", help="Service to use")

    # ── sim ──
    sim_parser = subparsers.add_parser("sim", help="Simulation commands")
    sim_sub = sim_parser.add_subparsers(dest="command")

    run_p = sim_sub.add_parser("run", help="Run a mission simulation")
    run_p.add_argument("--mission", "-m", default="leo-iss",
                       help="leo-iss, leo-sso, geo, interstellar")
    run_p.add_argument("--duration", "-d", type=float, help="Duration (seconds or years)")
    run_p.add_argument("--speed", "-s", type=float, default=0, help="Real-time multiplier")
    run_p.add_argument("--agents", action="store_true", help="Enable ARIA agents")
    run_p.add_argument("--dashboard", action="store_true", help="Enable telemetry dashboard")
    run_p.add_argument("--port", type=int, default=8080, help="Dashboard port")
    run_p.add_argument("--years", type=int, default=100, help="Interstellar years")
    run_p.add_argument("--crew", type=int, default=4, help="Crew size")
    run_p.add_argument("--altitude", type=float, help="Orbit altitude (km)")
    run_p.add_argument("--inclination", type=float, help="Orbit inclination (deg)")

    mc_p = sim_sub.add_parser("montecarlo", help="Monte Carlo mission analysis")
    mc_p.add_argument("--mission", "-m", default="interstellar")
    mc_p.add_argument("--runs", "-n", type=int, default=100)
    mc_p.add_argument("--years", type=int, default=200)
    mc_p.add_argument("--crew", type=int, default=4)

    cmp_p = sim_sub.add_parser("compare", help="Legacy vs Breakthrough comparison")
    cmp_p.add_argument("--years", type=int, default=200)
    cmp_p.add_argument("--seeds", type=int, default=10)

    gs_p = sim_sub.add_parser("generation-ship", help="Full generation ship simulation")
    gs_p.add_argument("--years", type=int, default=1000)
    gs_p.add_argument("--mode", choices=["legacy", "breakthrough"], default="breakthrough")

    # --- sim first-1000-days ---
    f1k_p = sim_sub.add_parser("first-1000-days", help="First 1000 days day-by-day simulation")
    f1k_p.add_argument("--crew", type=int, default=1000, help="Crew size")
    f1k_p.add_argument("--days", type=int, default=1000, help="Days to simulate")
    f1k_p.add_argument("--seed", type=int, default=42, help="Random seed")
    f1k_p.add_argument("--report", action="store_true", help="Print full mission report")

    sim_sub.add_parser("duration-sweep", help="Compare outcomes across mission durations")
    gs_p.add_argument("--crew", type=int, default=4)
    gs_p.add_argument("--seed", type=int, default=42)

    # --- sim target ---
    tgt_p = sim_sub.add_parser("target", help="Run simulation for a specific star target")
    tgt_p.add_argument("--star", type=str, default=None, help="Star target key (e.g. proxima_centauri)")
    tgt_p.add_argument("--list", action="store_true", dest="list_targets", help="List available star targets")
    tgt_p.add_argument("--crew", type=int, default=4, help="Crew size")
    tgt_p.add_argument("--seed", type=int, default=42, help="Random seed")
    tgt_p.add_argument("--mode", choices=["legacy", "breakthrough"], default="breakthrough", help="Tech mode")

    # --- sim target-sweep ---
    ts_p = sim_sub.add_parser("target-sweep", help="Compare outcomes across all nearby star targets")
    ts_p.add_argument("--max-distance", type=float, default=15.0, help="Max distance in light-years")
    ts_p.add_argument("--crew", type=int, default=4, help="Crew size")
    ts_p.add_argument("--seed", type=int, default=42, help="Random seed")
    ts_p.add_argument("--mode", choices=["legacy", "breakthrough"], default="breakthrough", help="Tech mode")

    # --- sim validate ---
    val_p = sim_sub.add_parser("validate", help="Run physics validation on a simulation")
    val_p.add_argument("--years", type=int, default=200, help="Simulation years to validate")
    val_p.add_argument("--seed", type=int, default=42, help="Random seed")

    # ── system ──
    sys_parser = subparsers.add_parser("system", help="System management")
    sys_sub = sys_parser.add_subparsers(dest="command")
    sys_sub.add_parser("status", help="System status")
    sys_sub.add_parser("health", help="Health check")
    sys_sub.add_parser("benchmark", help="Performance benchmarks")

    agents_p = sys_sub.add_parser("agents", help="Agent management")
    agents_p.add_argument("action", nargs="?", default="list", choices=["list", "status"])

    config_p = sys_sub.add_parser("config", help="Configuration")
    config_p.add_argument("action", nargs="?", default="show", choices=["show"])

    # ── data ──
    data_parser = subparsers.add_parser("data", help="Data operations")
    data_sub = data_parser.add_subparsers(dest="command")

    imp_p = data_sub.add_parser("import", help="Import external data")
    imp_p.add_argument("--source", required=True, choices=["noaa", "battery", "eden", "voyager"])
    imp_p.add_argument("--path", required=True, help="Path to data files")

    rep_p = data_sub.add_parser("replay", help="Replay data through ARIA")
    rep_p.add_argument("--source", required=True, choices=["noaa", "battery", "eden"])
    rep_p.add_argument("--file", required=True, help="Data file path")

    data_sub.add_parser("list", help="List available datasets")

    conv_p = data_sub.add_parser("convert", help="Convert data formats")
    conv_p.add_argument("--from-fmt", dest="from_fmt", required=True, choices=["netcdf", "mat"])
    conv_p.add_argument("--to-fmt", dest="to_fmt", required=True, choices=["csv"])
    conv_p.add_argument("--input", required=True, help="Input file")
    conv_p.add_argument("--output-dir", default=".", help="Output directory")

    # ── report ──
    report_parser = subparsers.add_parser("report", help="Mission reports")
    report_sub = report_parser.add_subparsers(dest="command")

    gen_p = report_sub.add_parser("generate", help="Generate mission report")
    gen_p.add_argument("--format", "-f", choices=["text", "json", "html"], default="text")
    gen_p.add_argument("--mission", default="last", help="Mission ID or 'last'")

    report_sub.add_parser("list", help="List available reports")

    # ── tools ──
    tools_parser = subparsers.add_parser("tools", help="External tool integration")
    tools_sub = tools_parser.add_subparsers(dest="command")

    bsk_p = tools_sub.add_parser("basilisk", help="Basilisk simulation")
    bsk_p.add_argument("action", choices=["run", "orbits", "status"])
    bsk_p.add_argument("--orbit", default="leo", help="Orbit preset")
    bsk_p.add_argument("--duration", type=float, default=5520, help="Duration (s)")

    tools_sub.add_parser("gmat", help="GMAT trajectory planning")
    tools_sub.add_parser("openmct", help="OpenMCT dashboard")
    tools_sub.add_parser("openc3", help="OpenC3 command & control")

    # ── shield ──
    shield_parser = subparsers.add_parser("shield", help="Shield system analysis")
    shield_sub = shield_parser.add_subparsers(dest="command")

    sa_p = shield_sub.add_parser("analyze", help="Analyze shield effectiveness")
    sa_p.add_argument("--velocity", type=float, default=0.1, help="Velocity (fraction of c)")
    sa_p.add_argument("--distance", type=float, default=100, help="Distance (ly)")

    shield_sub.add_parser("budget", help="Shield mass/power budget")

    ero_p = shield_sub.add_parser("erosion", help="Erosion analysis")
    ero_p.add_argument("--velocity", type=float, default=0.1)
    ero_p.add_argument("--material", default="carbon", choices=["carbon", "aluminum", "titanium"])

    # ── crew ──
    crew_parser = subparsers.add_parser("crew", help="Crew lifecycle simulation")
    crew_sub = crew_parser.add_subparsers(dest="command")

    lc_p = crew_sub.add_parser("lifecycle", help="Crew lifecycle simulation")
    lc_p.add_argument("--years", type=int, default=200)
    lc_p.add_argument("--initial-crew", type=int, default=100)

    eco_p = crew_sub.add_parser("ecosystem", help="Closed-loop ecosystem simulation")
    eco_p.add_argument("--years", type=int, default=500)

    gen_gp = crew_sub.add_parser("genetics", help="Genetic diversity analysis")
    gen_gp.add_argument("--population", type=int, default=50)
    gen_gp.add_argument("--years", type=int, default=300)

    # ── mission ──
    mission_parser = subparsers.add_parser("mission", help="Mission persistence")
    mission_sub = mission_parser.add_subparsers(dest="mission_command")

    mission_sub.add_parser("list", help="List saved missions")

    show_p = mission_sub.add_parser("show", help="Show mission details")
    show_p.add_argument("mission_id", help="Mission ID")

    del_p = mission_sub.add_parser("delete", help="Delete a mission")
    del_p.add_argument("mission_id", help="Mission ID")

    # ── test ──
    test_parser = subparsers.add_parser("test", help="Run tests and validation")
    test_sub = test_parser.add_subparsers(dest="command")
    test_sub.add_parser("quick", help="Quick validation (30s)")
    test_sub.add_parser("full", help="Full pytest suite")
    test_sub.add_parser("smoke", help="Smoke tests only")

    # ── analyze ──
    analyze_parser = subparsers.add_parser("analyze", help="Analysis tools")
    analyze_sub = analyze_parser.add_subparsers(dest="command")

    sw_p = analyze_sub.add_parser("sweep", help="Parameter sweep")
    sw_p.add_argument("--param", default="crew_size", choices=["crew_size", "velocity", "years"])
    sw_p.add_argument("--values", default="4,10,50", help="Comma-separated values")
    sw_p.add_argument("--years", type=int, default=100)

    analyze_sub.add_parser("diff", help="Compare two missions")
    analyze_sub.add_parser("batch", help="Run batch missions")

    return parser


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch to the appropriate command handler."""
    # Set global output context for all CLI modules
    try:
        from aria.cli.formatting import OutputContext, set_context
        output_fmt = getattr(args, "output", "text")
        verbose = getattr(args, "verbose", False)
        set_context(OutputContext(output_format=output_fmt, verbose=verbose))
    except (ImportError, TypeError):
        pass

    service_map = {
        "sim": "aria.cli.sim",
        "system": "aria.cli.system",
        "data": "aria.cli.data",
        "report": "aria.cli.report",
        "tools": "aria.cli.tools",
        "shield": "aria.cli.shield",
        "analyze": "aria.cli.analyze",
        "test": "aria.cli.test_runner",
        "crew": "aria.cli.crew",
        "mission": "aria.cli.mission",
    }

    module_name = service_map.get(args.service)
    if not module_name:
        build_parser().print_help()
        return

    import importlib
    mod = importlib.import_module(module_name)

    # Map args.command to what each module expects
    # Agent modules use {service}_command (e.g. sim_command), mine use command
    cmd = getattr(args, "command", None)
    service = args.service
    if cmd and not hasattr(args, f"{service}_command"):
        setattr(args, f"{service}_command", cmd)

    if hasattr(mod, "dispatch"):
        mod.dispatch(args)
    elif hasattr(mod, f"handle_{service}"):
        handler = getattr(mod, f"handle_{service}")
        output_json = getattr(args, "output", "text") == "json"
        handler(args, output_json)
    else:
        print(f"No handler for service: {service}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.service:
        parser.print_help()
        sys.exit(0)

    try:
        dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
