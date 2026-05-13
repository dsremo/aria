"""ARIA CLI — Mission persistence commands.

Usage:
    aria mission list                    List all saved missions
    aria mission show <id>               Show details for a specific mission
    aria mission delete <id>             Delete a saved mission
"""

from __future__ import annotations

import argparse
import sys

from aria.cli.formatting import (
    Color,
    bold,
    colored,
    dim,
    error,
    get_context,
    print_header,
    print_json,
    print_kv,
    print_subheader,
    print_table,
    success,
    warning,
)


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch mission subcommands."""
    cmd = getattr(args, "mission_command", None)
    if cmd == "list":
        _cmd_list(args)
    elif cmd == "show":
        _cmd_show(args)
    elif cmd == "delete":
        _cmd_delete(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown mission command: {cmd}"))
        _cmd_help()
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  mission list
# ────────────────────────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> None:
    """List all saved missions."""
    ctx = get_context()
    from aria.persistence.mission_store import MissionStore

    store = MissionStore()
    try:
        missions = store.list_missions(limit=getattr(args, "limit", 50))

        if ctx.is_json:
            print_json([
                {
                    "id": m.id,
                    "name": m.name,
                    "type": m.mission_type,
                    "timestamp": m.timestamp,
                    "status": m.status,
                    "score": m.score,
                    "grade": m.grade,
                    "events": m.total_events,
                    "alerts": m.total_alerts,
                }
                for m in missions
            ])
            return

        if not missions:
            print(dim("  No saved missions found."))
            print(dim("  Run a simulation first: aria sim run --mission leo-iss"))
            return

        print_header(f"Saved Missions ({len(missions)})")

        rows = []
        for m in missions:
            status_str = (
                colored("OK", Color.BRIGHT_GREEN) if m.status == "success"
                else colored("FAIL", Color.BRIGHT_RED)
            )
            score_str = f"{m.score:.0f}" if m.score is not None else "-"
            grade_str = m.grade if m.grade else "-"
            ts_short = m.timestamp[:19].replace("T", " ")
            rows.append([
                m.id,
                m.name,
                m.mission_type,
                ts_short,
                status_str,
                score_str,
                grade_str,
            ])

        print_table(
            headers=["ID", "Name", "Type", "Date", "Status", "Score", "Grade"],
            rows=rows,
            col_widths=[14, 22, 14, 20, 8, 6, 6],
        )
    finally:
        store.close()


# ────────────────────────────────────────────────────────────────
#  mission show
# ────────────────────────────────────────────────────────────────

def _cmd_show(args: argparse.Namespace) -> None:
    """Show details for a specific mission."""
    ctx = get_context()
    from aria.persistence.mission_store import MissionStore

    mission_id = getattr(args, "mission_id", None)
    if not mission_id:
        print(error("Mission ID is required: aria mission show <id>"))
        sys.exit(1)

    store = MissionStore()
    try:
        record = store.load(mission_id)

        if record is None:
            print(error(f"Mission not found: {mission_id}"))
            sys.exit(1)

        if ctx.is_json:
            print_json({
                "id": record.id,
                "name": record.name,
                "type": record.mission_type,
                "timestamp": record.timestamp,
                "status": record.status,
                "score": record.score,
                "grade": record.grade,
                "duration_sim_s": record.duration_sim_s,
                "duration_wall_s": record.duration_wall_s,
                "total_frames": record.total_frames,
                "total_events": record.total_events,
                "total_alerts": record.total_alerts,
                "altitude_range_km": list(record.altitude_range_km),
                "velocity_range_m_s": list(record.velocity_range_m_s),
                "latitude_range_deg": list(record.latitude_range_deg),
                "eclipse_count": record.eclipse_count,
                "anomalies_detected": record.anomalies_detected,
                "severity_distribution": record.severity_distribution,
                "challenge_states": record.challenge_states,
                "terminal_challenges": record.terminal_challenges,
                "errors": record.errors,
            })
            return

        status_color = Color.BRIGHT_GREEN if record.status == "success" else Color.BRIGHT_RED
        print_header(f"Mission: {record.name}")
        print_kv("ID", record.id)
        print_kv("Type", record.mission_type)
        print_kv("Date", record.timestamp[:19].replace("T", " ") + " UTC")
        print_kv("Status", colored(record.status.upper(), status_color))

        if record.score is not None:
            grade_color = Color.BRIGHT_GREEN if record.score >= 70 else (
                Color.BRIGHT_YELLOW if record.score >= 50 else Color.BRIGHT_RED
            )
            print_kv("Score", colored(f"{record.score:.0f}/100 ({record.grade})", grade_color))

        print()
        print_subheader("Timing")
        print_kv("Sim duration", f"{record.duration_sim_s:.0f}s")
        print_kv("Wall time", f"{record.duration_wall_s:.2f}s")

        print()
        print_subheader("Telemetry")
        print_kv("Frames", f"{record.total_frames:,}")
        print_kv("Events", f"{record.total_events:,}")
        print_kv("Alerts", f"{record.total_alerts:,}")
        print_kv("Anomalies", f"{record.anomalies_detected:,}")
        print_kv("Eclipses", record.eclipse_count)

        if record.altitude_range_km != (0, 0):
            print()
            print_subheader("Orbit")
            print_kv("Altitude", f"{record.altitude_range_km[0]:.1f} - {record.altitude_range_km[1]:.1f} km")
            print_kv("Velocity", f"{record.velocity_range_m_s[0]:.0f} - {record.velocity_range_m_s[1]:.0f} m/s")
            print_kv("Latitude", f"{record.latitude_range_deg[0]:.1f} to {record.latitude_range_deg[1]:.1f} deg")

        if record.severity_distribution:
            print()
            print_subheader("Severity Distribution")
            for sev, count in sorted(record.severity_distribution.items()):
                print_kv(f"  {sev}", f"{count:,}")

        if record.challenge_states:
            print()
            print_subheader("Challenge States")
            for name, state in sorted(record.challenge_states.items()):
                state_color = Color.BRIGHT_RED if state == "terminal" else Color.BRIGHT_GREEN
                print_kv(f"  {name}", colored(state, state_color))
            print_kv("Terminal", f"{record.terminal_challenges}/6")

        if record.errors:
            print()
            print_subheader("Errors")
            for e in record.errors[:10]:
                print(f"  - {e}")

        print()
    finally:
        store.close()


# ────────────────────────────────────────────────────────────────
#  mission delete
# ────────────────────────────────────────────────────────────────

def _cmd_delete(args: argparse.Namespace) -> None:
    """Delete a saved mission."""
    ctx = get_context()
    from aria.persistence.mission_store import MissionStore

    mission_id = getattr(args, "mission_id", None)
    if not mission_id:
        print(error("Mission ID is required: aria mission delete <id>"))
        sys.exit(1)

    store = MissionStore()
    try:
        deleted = store.delete(mission_id)

        if ctx.is_json:
            print_json({"id": mission_id, "deleted": deleted})
            return

        if deleted:
            print(success(f"  Deleted mission {mission_id}"))
        else:
            print(error(f"  Mission not found: {mission_id}"))
            sys.exit(1)
    finally:
        store.close()


# ────────────────────────────────────────────────────────────────
#  mission help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show mission help."""
    print_header("ARIA Mission Persistence")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria mission list", "List all saved missions"],
            ["aria mission show <id>", "Show details for a specific mission"],
            ["aria mission delete <id>", "Delete a saved mission"],
        ],
        col_widths=[30, 50],
    )
    print(dim("  Missions are auto-saved after each simulation run."))
    print()
