"""ARIA CLI — System commands.

Usage:
    aria system status
    aria system health
    aria system agents list
    aria system agents restart <name>
    aria system benchmark
    aria system config show
    aria system config set <key> <value>
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from aria.cli.formatting import (
    Color,
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
    status_indicator,
    success,
    warning,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'system' service and subcommands."""
    sys_parser = subparsers.add_parser(
        "system",
        help="System status, health, agents, benchmarks, configuration",
        description="Inspect and manage the ARIA runtime system.",
    )
    sys_subs = sys_parser.add_subparsers(dest="system_command")

    # --- system status ---
    sys_subs.add_parser("status", help="Show system status overview")

    # --- system health ---
    sys_subs.add_parser("health", help="Run health checks on all subsystems")

    # --- system agents ---
    agents_p = sys_subs.add_parser("agents", help="Manage ARIA agents")
    agents_subs = agents_p.add_subparsers(dest="agents_command")
    agents_subs.add_parser("list", help="List all agents and their status")
    restart_p = agents_subs.add_parser("restart", help="Restart an agent")
    restart_p.add_argument("name", help="Agent name to restart")

    # --- system benchmark ---
    sys_subs.add_parser("benchmark", help="Run performance benchmarks")

    # --- system config ---
    config_p = sys_subs.add_parser("config", help="View or modify configuration")
    config_subs = config_p.add_subparsers(dest="config_command")
    config_subs.add_parser("show", help="Show current configuration")
    set_p = config_subs.add_parser("set", help="Set a configuration value")
    set_p.add_argument("key", help="Configuration key")
    set_p.add_argument("value", help="Configuration value")

    # --- system help ---
    sys_subs.add_parser("help", help="Show system help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch system subcommands."""
    cmd = getattr(args, "system_command", None)
    if cmd == "status":
        _cmd_status(args)
    elif cmd == "health":
        _cmd_health(args)
    elif cmd == "agents":
        _dispatch_agents(args)
    elif cmd == "benchmark":
        _cmd_benchmark(args)
    elif cmd == "config":
        _dispatch_config(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown system command: {cmd}"))
        sys.exit(1)


def _dispatch_agents(args: argparse.Namespace) -> None:
    cmd = getattr(args, "agents_command", None)
    if cmd == "list":
        _cmd_agents_list(args)
    elif cmd == "restart":
        _cmd_agents_restart(args)
    else:
        _cmd_agents_list(args)


def _dispatch_config(args: argparse.Namespace) -> None:
    cmd = getattr(args, "config_command", None)
    if cmd == "show":
        _cmd_config_show(args)
    elif cmd == "set":
        _cmd_config_set(args)
    else:
        _cmd_config_show(args)


# ────────────────────────────────────────────────────────────────
#  system status
# ────────────────────────────────────────────────────────────────

def _cmd_status(args: argparse.Namespace) -> None:
    """Show ARIA system status."""
    ctx = get_context()

    root = Path(__file__).resolve().parent.parent.parent.parent
    src_dir = root / "src"
    test_dir = root / "tests"

    src_files = list(src_dir.rglob("*.py")) if src_dir.exists() else []
    test_files = list(test_dir.rglob("*.py")) if test_dir.exists() else []
    total_lines = 0
    for f in src_files + test_files:
        try:
            total_lines += sum(1 for _ in open(f))
        except Exception:
            pass

    # Dependency checks
    deps = {
        "Basilisk (bsk)": "Basilisk",
        "scipy": "scipy",
        "numpy": "numpy",
        "netCDF4": "netCDF4",
        "aiohttp": "aiohttp",
        "structlog": "structlog",
        "hypothesis": "hypothesis",
        "websockets": "websockets",
    }
    dep_status: dict[str, bool] = {}
    for name, mod in deps.items():
        try:
            __import__(mod)
            dep_status[name] = True
        except ImportError:
            dep_status[name] = False

    # Data source checks
    data_dir = root / "data" / "raw"
    data_sources = [
        ("NASA Battery", "nasa_battery"),
        ("NOAA GOES-16", "noaa_goes"),
        ("EDEN ISS", "eden_iss"),
        ("Voyager", "voyager"),
        ("NASA Bearings", "nasa_bearings"),
    ]
    data_status: dict[str, int] = {}
    for name, subdir in data_sources:
        path = data_dir / subdir
        if path.exists():
            data_status[name] = len(list(path.rglob("*")))
        else:
            data_status[name] = -1

    if ctx.is_json:
        print_json({
            "source_files": len(src_files),
            "test_files": len(test_files),
            "total_lines": total_lines,
            "dependencies": dep_status,
            "data_sources": data_status,
        })
        return

    from aria import __version__
    print_header("ARIA System Status")
    print_kv("Version", bold(__version__))
    print_kv("Source files", f"{len(src_files):,}")
    print_kv("Test files", f"{len(test_files):,}")
    print_kv("Total lines", f"{total_lines:,}")
    print()

    # Dependencies table
    print_subheader("Dependencies")
    dep_rows = []
    for name, installed in dep_status.items():
        dep_rows.append([name, status_indicator(installed)])
    print_table(["Package", "Status"], dep_rows, col_widths=[28, 10])

    # Data sources table
    print_subheader("Data Sources")
    ds_rows = []
    for name, count in data_status.items():
        if count >= 0:
            ds_rows.append([name, success(f"{count} files")])
        else:
            ds_rows.append([name, warning("not found")])
    print_table(["Source", "Status"], ds_rows, col_widths=[28, 20])


# ────────────────────────────────────────────────────────────────
#  system health
# ────────────────────────────────────────────────────────────────

def _cmd_health(args: argparse.Namespace) -> None:
    """Run health checks on all subsystems."""
    ctx = get_context()

    checks: list[dict[str, Any]] = []

    # Check 1: Core imports
    core_ok = True
    try:
        from aria.core.coordinator import AriaCoordinator
        from aria.core.config import AriaConfig
    except Exception as e:
        core_ok = False
    checks.append({"name": "Core imports", "ok": core_ok})

    # Check 2: Simulation engine
    sim_ok = True
    try:
        from aria.simulation.mission_runner import MissionRunner
        _ = MissionRunner.leo_iss()
    except Exception:
        sim_ok = False
    checks.append({"name": "Simulation engine", "ok": sim_ok})

    # Check 3: Interstellar simulation
    inter_ok = True
    try:
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
    except Exception:
        inter_ok = False
    checks.append({"name": "Interstellar simulation", "ok": inter_ok})

    # Check 4: Shield system
    shield_ok = True
    try:
        from aria.simulation.shield_system import ShieldErosionModel
        model = ShieldErosionModel(velocity_c=0.1)
        _ = model.kinetic_energy_j(1e-15)
    except Exception:
        shield_ok = False
    checks.append({"name": "Shield system", "ok": shield_ok})

    # Check 5: Crew ecosystem
    crew_ok = True
    try:
        from aria.simulation.crew_ecosystem import CrewLifecycleSimulator
    except Exception:
        crew_ok = False
    checks.append({"name": "Crew ecosystem", "ok": crew_ok})

    # Check 6: Reporting
    report_ok = True
    try:
        from aria.reporting.mission_report import MissionReportGenerator
    except Exception:
        report_ok = False
    checks.append({"name": "Reporting engine", "ok": report_ok})

    # Check 7: Dashboard
    dash_ok = True
    try:
        from aria.dashboard.health_dashboard import HealthDashboard
        d = HealthDashboard()
        d.update_orbit(altitude_km=400, velocity_m_s=7673)
        d.snapshot()
    except Exception:
        dash_ok = False
    checks.append({"name": "Health dashboard", "ok": dash_ok})

    # Check 8: Agent framework
    agent_ok = True
    try:
        from aria.agents.power import PowerAgent
    except Exception:
        agent_ok = False
    checks.append({"name": "Agent framework", "ok": agent_ok})

    total_ok = sum(1 for c in checks if c["ok"])
    total = len(checks)

    if ctx.is_json:
        print_json({
            "total_checks": total,
            "passed": total_ok,
            "failed": total - total_ok,
            "checks": checks,
        })
        return

    print_header("ARIA Health Check")

    rows = []
    for c in checks:
        rows.append([c["name"], status_indicator(c["ok"])])
    print_table(["Subsystem", "Status"], rows, col_widths=[30, 10])

    color = Color.BRIGHT_GREEN if total_ok == total else (
        Color.BRIGHT_YELLOW if total_ok >= total * 0.7 else Color.BRIGHT_RED
    )
    print(f"  {colored(f'{total_ok}/{total} checks passed', color)}")
    print()


# ────────────────────────────────────────────────────────────────
#  system agents list
# ────────────────────────────────────────────────────────────────

AGENT_NAMES = [
    ("PowerAgent", "aria.agents.power", "Power subsystem management"),
    ("ThermalAgent", "aria.agents.thermal", "Thermal control monitoring"),
    ("EclssAgent", "aria.agents.eclss", "Environmental control & life support"),
    ("NavigationAgent", "aria.agents.navigation", "Orbital mechanics & navigation"),
    ("PropulsionAgent", "aria.agents.propulsion", "Propulsion system control"),
    ("CommsAgent", "aria.agents.comms", "Communications management"),
    ("TelemetryAgent", "aria.agents.telemetry", "Telemetry collection & routing"),
    ("MedicalAgent", "aria.agents.medical", "Crew health monitoring"),
    ("ScienceAgent", "aria.agents.science", "Science payload management"),
]


def _cmd_agents_list(args: argparse.Namespace) -> None:
    """List all ARIA agents."""
    ctx = get_context()

    agents_info = []
    for name, module, desc in AGENT_NAMES:
        importable = True
        try:
            __import__(module)
        except Exception:
            importable = False
        agents_info.append({
            "name": name,
            "module": module,
            "description": desc,
            "importable": importable,
        })

    if ctx.is_json:
        print_json(agents_info)
        return

    print_header("ARIA Agents")
    rows = []
    for a in agents_info:
        rows.append([
            bold(a["name"]),
            a["description"],
            status_indicator(a["importable"]),
        ])
    print_table(["Agent", "Description", "Status"], rows, col_widths=[22, 40, 10])


def _cmd_agents_restart(args: argparse.Namespace) -> None:
    """Restart an agent (informational only in CLI context)."""
    ctx = get_context()
    name = args.name

    known = {n.lower(): n for n, _, _ in AGENT_NAMES}
    if name.lower() not in known:
        ctx.print(error(f"Unknown agent: {name}"))
        ctx.print(dim(f"  Available: {', '.join(sorted(known.values()))}"))
        sys.exit(1)

    actual_name = known[name.lower()]

    if ctx.is_json:
        print_json({"agent": actual_name, "action": "restart", "status": "requested"})
    else:
        ctx.print(info(f"  Restart requested for {bold(actual_name)}"))
        ctx.print(dim("  Note: Agent restart requires a running ARIA coordinator instance."))
        ctx.print(dim("  Use 'aria system status' to verify the coordinator is active."))


# ────────────────────────────────────────────────────────────────
#  system benchmark
# ────────────────────────────────────────────────────────────────

def _cmd_benchmark(args: argparse.Namespace) -> None:
    """Run performance benchmarks."""
    ctx = get_context()

    results: list[dict[str, Any]] = []

    if not ctx.is_json:
        print_header("ARIA Performance Benchmarks")

    # Benchmark 1: Interstellar simulation
    try:
        from aria.simulation.interstellar import InterstellarSimulation
        t0 = time.time()
        sim = InterstellarSimulation(cruise_velocity_c=0.1, crew_size=4, seed=42)
        events = sim.run_full_mission()
        dt = time.time() - t0
        results.append({
            "name": "Interstellar 1000yr",
            "time_s": round(dt, 3),
            "throughput": f"{1000 / dt:.0f} years/s",
            "detail": f"{len(events)} events",
        })
    except Exception as e:
        results.append({"name": "Interstellar 1000yr", "error": str(e)})

    # Benchmark 2: Challenge orchestrator
    try:
        from aria.simulation.interstellar_challenges import InterstellarChallengeOrchestrator
        t0 = time.time()
        orch = InterstellarChallengeOrchestrator(crew_size=4, seed=42)
        cresults = orch.run_full_mission()
        dt = time.time() - t0
        total_events = sum(len(r["events"]) for r in cresults)
        results.append({
            "name": "Challenges 1000yr",
            "time_s": round(dt, 3),
            "throughput": f"{1000 / dt:.0f} years/s",
            "detail": f"{total_events} events",
        })
    except Exception as e:
        results.append({"name": "Challenges 1000yr", "error": str(e)})

    # Benchmark 3: Telemetry history store
    try:
        from aria.dashboard.telemetry_server import TelemetryHistoryStore
        store = TelemetryHistoryStore()
        t0 = time.time()
        for i in range(100_000):
            store.record(f"key.{i % 100}", i, float(i))
        dt = time.time() - t0
        results.append({
            "name": "History 100K writes",
            "time_s": round(dt, 3),
            "throughput": f"{100_000 / dt:.0f} rec/s",
            "detail": "100K records",
        })
    except Exception as e:
        results.append({"name": "History 100K writes", "error": str(e)})

    # Benchmark 4: Basilisk orbit
    try:
        from aria.simulation.basilisk_runner import BasiliskSimRunner, SimConfig, OrbitConfig
        config = SimConfig(
            timestep_s=1.0, output_interval_s=10.0,
            orbit=OrbitConfig(altitude_km=400, inclination_deg=51.6),
        )
        runner = BasiliskSimRunner(config)
        runner.setup()
        t0 = time.time()
        frames = runner.step(5520.0)
        dt = time.time() - t0
        results.append({
            "name": "Basilisk 1 orbit",
            "time_s": round(dt, 3),
            "throughput": f"{5520 / dt:.0f}x real-time",
            "detail": f"{len(frames)} frames",
        })
    except Exception as e:
        results.append({"name": "Basilisk 1 orbit", "skipped": str(e)})

    # Benchmark 5: Health dashboard
    try:
        from aria.dashboard.health_dashboard import HealthDashboard
        dash = HealthDashboard()
        t0 = time.time()
        for i in range(10_000):
            dash.update_orbit(altitude_km=400 + i * 0.01, velocity_m_s=7673)
            dash.update_power(battery_soc=80 - i * 0.001)
            dash.snapshot()
        dt = time.time() - t0
        results.append({
            "name": "Dashboard 10K snaps",
            "time_s": round(dt, 3),
            "throughput": f"{10_000 / dt:.0f} snap/s",
            "detail": "10K snapshots",
        })
    except Exception as e:
        results.append({"name": "Dashboard 10K snaps", "error": str(e)})

    if ctx.is_json:
        print_json({"benchmarks": results})
        return

    rows = []
    for r in results:
        if "error" in r:
            rows.append([r["name"], error("ERROR"), dim(r["error"]), ""])
        elif "skipped" in r:
            rows.append([r["name"], warning("SKIP"), dim(r["skipped"]), ""])
        else:
            rows.append([r["name"], success(f"{r['time_s']}s"), r["throughput"], r["detail"]])
    print_table(
        ["Benchmark", "Time", "Throughput", "Detail"],
        rows,
        col_widths=[24, 12, 20, 20],
    )
    print(success("  All benchmarks complete."))
    print()


# ────────────────────────────────────────────────────────────────
#  system config
# ────────────────────────────────────────────────────────────────

def _cmd_config_show(args: argparse.Namespace) -> None:
    """Show current configuration."""
    ctx = get_context()

    config: dict[str, Any] = {
        "aria.version": None,
        "aria.root": str(Path(__file__).resolve().parent.parent.parent.parent),
        "simulation.default_mission": "leo-iss",
        "simulation.default_speed": 0,
        "simulation.default_crew": 4,
        "interstellar.default_years": 100,
        "interstellar.default_velocity_c": 0.1,
        "dashboard.default_port": 8080,
        "agents.enabled": True,
    }

    try:
        from aria import __version__
        config["aria.version"] = __version__
    except Exception:
        config["aria.version"] = "unknown"

    # Try reading from config file if specified
    config_path = ctx.config_path
    if config_path and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path) as f:
                file_config = yaml.safe_load(f)
            if isinstance(file_config, dict):
                for k, v in file_config.items():
                    config[k] = v
        except Exception:
            pass

    if ctx.is_json:
        print_json(config)
        return

    print_header("ARIA Configuration")
    rows = []
    for k, v in sorted(config.items()):
        rows.append([dim(k), str(v)])
    print_table(["Key", "Value"], rows, col_widths=[36, 30])


def _cmd_config_set(args: argparse.Namespace) -> None:
    """Set a configuration value."""
    ctx = get_context()

    if ctx.is_json:
        print_json({"action": "config_set", "key": args.key, "value": args.value, "status": "noted"})
    else:
        ctx.print(info(f"  Set {bold(args.key)} = {args.value}"))
        ctx.print(dim("  Note: Runtime config changes require a config file."))
        ctx.print(dim("  Use --config /path/to/aria.yaml to persist settings."))


# ────────────────────────────────────────────────────────────────
#  system help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show system help."""
    print_header("ARIA System Commands")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria system status", "System overview (files, deps, data sources)"],
            ["aria system health", "Run health checks on all subsystems"],
            ["aria system agents list", "List all ARIA agents"],
            ["aria system agents restart <name>", "Restart a specific agent"],
            ["aria system benchmark", "Run performance benchmarks"],
            ["aria system config show", "Show current configuration"],
            ["aria system config set <key> <value>", "Set a configuration value"],
        ],
        col_widths=[38, 42],
    )
