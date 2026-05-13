"""ARIA CLI — External tools integration commands.

Usage:
    aria tools basilisk run --orbit leo --duration 5520
    aria tools basilisk orbits
    aria tools gmat plan --from earth --to mars
    aria tools openmct start --port 8080
    aria tools openc3 status
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from aria.cli.formatting import (
    bold,
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


# ────────────────────────────────────────────────────────────────
#  ORBIT PRESETS
# ────────────────────────────────────────────────────────────────

ORBIT_PRESETS = {
    "leo": {"altitude_km": 400, "inclination_deg": 51.6, "name": "Low Earth Orbit (ISS)"},
    "leo-sso": {"altitude_km": 600, "inclination_deg": 97.8, "name": "Sun-Synchronous Orbit"},
    "meo": {"altitude_km": 20200, "inclination_deg": 55.0, "name": "Medium Earth Orbit (GPS)"},
    "geo": {"altitude_km": 35786, "inclination_deg": 0.0, "name": "Geostationary Orbit"},
    "heo": {"altitude_km": 39852, "inclination_deg": 63.4, "name": "Highly Elliptical Orbit (Molniya)"},
    "lunar": {"altitude_km": 384400, "inclination_deg": 5.1, "name": "Lunar Transfer Orbit"},
}


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'tools' service and its subcommands."""
    tools_parser = subparsers.add_parser(
        "tools",
        help="External tool integrations (Basilisk, GMAT, OpenMCT, OpenC3)",
        description="Interface with external spacecraft simulation and operations tools.",
    )
    tools_subs = tools_parser.add_subparsers(dest="tools_command")

    # --- tools basilisk ---
    bsk_p = tools_subs.add_parser("basilisk", help="Basilisk spacecraft simulation")
    bsk_subs = bsk_p.add_subparsers(dest="basilisk_command")

    run_p = bsk_subs.add_parser("run", help="Run a Basilisk simulation")
    run_p.add_argument("--orbit", "-o", default="leo",
                        choices=list(ORBIT_PRESETS.keys()),
                        help="Orbit preset")
    run_p.add_argument("--duration", "-d", type=float, default=5520, help="Duration (seconds)")
    run_p.add_argument("--timestep", type=float, default=1.0, help="Timestep (seconds)")

    bsk_subs.add_parser("orbits", help="List available orbit presets")

    # --- tools gmat ---
    gmat_p = tools_subs.add_parser("gmat", help="GMAT trajectory planning")
    gmat_subs = gmat_p.add_subparsers(dest="gmat_command")

    plan_p = gmat_subs.add_parser("plan", help="Plan a trajectory")
    plan_p.add_argument("--from", dest="from_body", default="earth", help="Departure body")
    plan_p.add_argument("--to", dest="to_body", default="mars", help="Arrival body")
    plan_p.add_argument("--launch-date", help="Launch date (YYYY-MM-DD)")

    # --- tools openmct ---
    mct_p = tools_subs.add_parser("openmct", help="OpenMCT telemetry visualization")
    mct_subs = mct_p.add_subparsers(dest="openmct_command")

    start_p = mct_subs.add_parser("start", help="Start OpenMCT server")
    start_p.add_argument("--port", "-p", type=int, default=8080, help="Server port")

    # --- tools openc3 ---
    c3_p = tools_subs.add_parser("openc3", help="OpenC3 command & control")
    c3_subs = c3_p.add_subparsers(dest="openc3_command")
    c3_subs.add_parser("status", help="Show OpenC3 status")

    # --- tools help ---
    tools_subs.add_parser("help", help="Show tools help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch tools subcommands."""
    cmd = getattr(args, "tools_command", None)
    if cmd == "basilisk":
        _dispatch_basilisk(args)
    elif cmd == "gmat":
        _dispatch_gmat(args)
    elif cmd == "openmct":
        _dispatch_openmct(args)
    elif cmd == "openc3":
        _dispatch_openc3(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown tools command: {cmd}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  Basilisk
# ────────────────────────────────────────────────────────────────

def _dispatch_basilisk(args: argparse.Namespace) -> None:
    cmd = getattr(args, "basilisk_command", None)
    if cmd == "run":
        _cmd_basilisk_run(args)
    elif cmd == "orbits":
        _cmd_basilisk_orbits(args)
    else:
        _cmd_basilisk_orbits(args)


def _cmd_basilisk_run(args: argparse.Namespace) -> None:
    """Run a Basilisk spacecraft simulation."""
    ctx = get_context()
    orbit_name = args.orbit
    preset = ORBIT_PRESETS[orbit_name]
    duration = args.duration

    if not ctx.is_json:
        print_header(f"Basilisk Simulation: {preset['name']}")
        print_kv("Orbit", orbit_name)
        print_kv("Altitude", f"{preset['altitude_km']:.0f} km")
        print_kv("Inclination", f"{preset['inclination_deg']:.1f} deg")
        print_kv("Duration", f"{duration:.0f}s")
        print()

    try:
        from aria.simulation.basilisk_runner import (
            BasiliskSimRunner, SimConfig, OrbitConfig, BASILISK_AVAILABLE,
        )

        if not BASILISK_AVAILABLE:
            if ctx.is_json:
                print_json({"status": "error", "error": "Basilisk not installed"})
            else:
                ctx.print(warning("  Basilisk not installed. Install with: pip install bsk"))
            sys.exit(1)

        config = SimConfig(
            timestep_s=args.timestep,
            output_interval_s=10.0,
            orbit=OrbitConfig(
                altitude_km=preset["altitude_km"],
                inclination_deg=preset["inclination_deg"],
            ),
        )
        runner = BasiliskSimRunner(config)
        runner.setup()

        t0 = time.time()
        frames = runner.step(duration)
        elapsed = time.time() - t0

        if ctx.is_json:
            print_json({
                "orbit": orbit_name,
                "duration_s": duration,
                "frames": len(frames),
                "realtime_factor": round(duration / elapsed, 1),
                "wall_time_s": round(elapsed, 3),
            })
        else:
            print_subheader("Simulation Complete")
            print_kv("Frames", len(frames))
            print_kv("Real-time factor", f"{duration / elapsed:.0f}x")
            print_kv("Wall time", f"{elapsed:.3f}s")

    except ImportError:
        if ctx.is_json:
            print_json({"status": "error", "error": "Basilisk not installed"})
        else:
            ctx.print(warning("  Basilisk not installed. Install with: pip install bsk"))
        sys.exit(1)
    except Exception as e:
        if ctx.is_json:
            print_json({"status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  Basilisk simulation failed: {e}"))
        sys.exit(1)


def _cmd_basilisk_orbits(args: argparse.Namespace) -> None:
    """List available orbit presets."""
    ctx = get_context()

    if ctx.is_json:
        print_json(ORBIT_PRESETS)
        return

    print_header("Basilisk Orbit Presets")
    rows = []
    for key, preset in ORBIT_PRESETS.items():
        rows.append([
            bold(key),
            preset["name"],
            f"{preset['altitude_km']:,.0f} km",
            f"{preset['inclination_deg']:.1f} deg",
        ])
    print_table(
        ["Key", "Name", "Altitude", "Inclination"],
        rows,
        col_widths=[12, 34, 14, 14],
    )


# ────────────────────────────────────────────────────────────────
#  GMAT
# ────────────────────────────────────────────────────────────────

def _dispatch_gmat(args: argparse.Namespace) -> None:
    cmd = getattr(args, "gmat_command", None)
    if cmd == "plan":
        _cmd_gmat_plan(args)
    else:
        ctx = get_context()
        if not ctx.is_json:
            print_header("GMAT Commands")
            print(dim("  aria tools gmat plan --from earth --to mars"))
        print()


def _cmd_gmat_plan(args: argparse.Namespace) -> None:
    """Plan a trajectory using GMAT bridge."""
    ctx = get_context()
    from_body = args.from_body
    to_body = args.to_body

    if not ctx.is_json:
        print_header(f"GMAT Trajectory: {from_body.title()} -> {to_body.title()}")

    # Use the GMAT bridge if available.
    # Wiring audit Pass 4 (F10.5) — fixed four signature errors:
    # (1) class is `GmatBridge`, not `GMATBridge`;
    # (2) the high-level method is `plan_trajectory(MissionConfig)`,
    #     not `plan_transfer(from_body, to_body)`;
    # (3) the result is a `GmatTrajectory` object exposing
    #     `to_dict()` / metadata, not a dict;
    # (4) all four were swallowed by a broad except so users saw
    #     "GMAT bridge not configured" forever even with GMAT installed.
    try:
        from aria.integrations.gmat_bridge import GmatBridge, MissionConfig
        bridge = GmatBridge()
        config = MissionConfig(
            name=f"cli_{from_body}_to_{to_body}",
        )
        trajectory = bridge.plan_trajectory(config, execute=False)
        result = (
            trajectory.to_dict()
            if hasattr(trajectory, "to_dict")
            else {"trajectory": str(trajectory)}
        )

        if ctx.is_json:
            print_json(result)
        else:
            if isinstance(result, dict):
                for k, v in result.items():
                    print_kv(k, v)
    except ImportError:
        # Provide informational output
        if ctx.is_json:
            print_json({
                "from": from_body,
                "to": to_body,
                "status": "gmat_not_configured",
                "message": "GMAT bridge not available. Install GMAT and configure the bridge.",
            })
        else:
            ctx.print(warning("  GMAT bridge not configured."))
            ctx.print(dim("  Install GMAT R2022a+ and set GMAT_ROOT environment variable."))
    except Exception as e:
        if ctx.is_json:
            print_json({"status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  GMAT planning failed: {e}"))


# ────────────────────────────────────────────────────────────────
#  OpenMCT
# ────────────────────────────────────────────────────────────────

def _dispatch_openmct(args: argparse.Namespace) -> None:
    cmd = getattr(args, "openmct_command", None)
    if cmd == "start":
        _cmd_openmct_start(args)
    else:
        ctx = get_context()
        if not ctx.is_json:
            print_header("OpenMCT Commands")
            print(dim("  aria tools openmct start --port 8080"))
        print()


def _cmd_openmct_start(args: argparse.Namespace) -> None:
    """Start OpenMCT telemetry server."""
    ctx = get_context()
    port = args.port

    if ctx.is_json:
        print_json({"action": "start_openmct", "port": port, "status": "starting"})
    else:
        print_header("OpenMCT Telemetry Server")
        print_kv("Port", port)
        ctx.print(info(f"  Starting telemetry server on http://localhost:{port}"))

    try:
        from aria.dashboard.telemetry_server import TelemetryServer
        server = TelemetryServer(port=port)
        if ctx.is_json:
            print_json({"status": "running", "port": port})
        else:
            ctx.print(success(f"  Telemetry server running at http://localhost:{port}"))
            ctx.print(dim("  Press Ctrl+C to stop."))
        import asyncio
        asyncio.run(server.start())
    except ImportError:
        if ctx.is_json:
            print_json({"status": "error", "error": "Telemetry server module not available"})
        else:
            ctx.print(warning("  Telemetry server module not available."))
    except KeyboardInterrupt:
        ctx.print(info("\n  Telemetry server stopped."))
    except Exception as e:
        if ctx.is_json:
            print_json({"status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  Server error: {e}"))


# ────────────────────────────────────────────────────────────────
#  OpenC3
# ────────────────────────────────────────────────────────────────

def _dispatch_openc3(args: argparse.Namespace) -> None:
    cmd = getattr(args, "openc3_command", None)
    if cmd == "status":
        _cmd_openc3_status(args)
    else:
        ctx = get_context()
        if not ctx.is_json:
            print_header("OpenC3 Commands")
            print(dim("  aria tools openc3 status"))
        print()


def _cmd_openc3_status(args: argparse.Namespace) -> None:
    """Show OpenC3 status."""
    ctx = get_context()

    # Wiring audit Pass 4 (F10.5) — fixed three signature errors:
    # (1) `OpenC3Bridge(bus, config?)` takes a required bus argument;
    #     CLI now constructs a transient MessageBus for the snapshot;
    # (2) the accessor is `bridge.stats` (property), not
    #     `bridge.status()` (method);
    # (3) all three errors were swallowed by a broad except so users
    #     saw "Server error: __init__() missing argument" on every
    #     invocation.
    try:
        from aria.bus.message_bus import MessageBus
        from aria.integrations.openc3_bridge import OpenC3Bridge, OpenC3Config
        bridge = OpenC3Bridge(MessageBus(), OpenC3Config(mock_mode=True))
        status = bridge.stats

        if ctx.is_json:
            print_json(status)
        else:
            print_header("OpenC3 Status")
            if isinstance(status, dict):
                for k, v in status.items():
                    print_kv(k, v)
            else:
                print(f"  {status}")
    except ImportError:
        if ctx.is_json:
            print_json({"status": "not_configured", "message": "OpenC3 bridge not available"})
        else:
            print_header("OpenC3 Status")
            ctx.print(warning("  OpenC3 bridge not configured."))
            ctx.print(dim("  Install OpenC3 and configure the bridge."))
    except Exception as e:
        if ctx.is_json:
            print_json({"status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  OpenC3 error: {e}"))


# ────────────────────────────────────────────────────────────────
#  tools help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show tools help."""
    print_header("ARIA External Tools")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria tools basilisk run", "Run Basilisk spacecraft simulation"],
            ["aria tools basilisk orbits", "List orbit presets"],
            ["aria tools gmat plan", "Plan a trajectory with GMAT"],
            ["aria tools openmct start", "Start OpenMCT telemetry server"],
            ["aria tools openc3 status", "Show OpenC3 connection status"],
        ],
        col_widths=[32, 40],
    )
