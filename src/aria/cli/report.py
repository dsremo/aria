"""ARIA CLI — Report commands.

Usage:
    aria report generate --mission-id <id> --format text|json|html
    aria report list
    aria report score --mission-id <id>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from aria.cli.formatting import (
    Color,
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
    """Register the 'report' service and its subcommands."""
    rpt_parser = subparsers.add_parser(
        "report",
        help="Generate and manage mission reports",
        description="Generate, list, and score mission reports.",
    )
    rpt_subs = rpt_parser.add_subparsers(dest="report_command")

    # --- report generate ---
    gen_p = rpt_subs.add_parser("generate", help="Generate a mission report")
    gen_p.add_argument("--mission-id", "-m", required=True, help="Mission identifier")
    gen_p.add_argument("--format", "-f", default="text",
                        choices=["text", "json", "html"],
                        help="Report format")

    # --- report list ---
    rpt_subs.add_parser("list", help="List available reports")

    # --- report score ---
    score_p = rpt_subs.add_parser("score", help="Show mission score")
    score_p.add_argument("--mission-id", "-m", required=True, help="Mission identifier")

    # --- report help ---
    rpt_subs.add_parser("help", help="Show report help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch report subcommands."""
    cmd = getattr(args, "report_command", None)
    if cmd == "generate":
        _cmd_generate(args)
    elif cmd == "list":
        _cmd_list(args)
    elif cmd == "score":
        _cmd_score(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown report command: {cmd}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  report generate
# ────────────────────────────────────────────────────────────────

def _cmd_generate(args: argparse.Namespace) -> None:
    """Generate a report from a saved mission JSON."""
    ctx = get_context()
    mission_id = args.mission_id
    fmt = args.format

    root = Path(__file__).resolve().parent.parent.parent.parent
    reports_dir = root / "reports"

    # Look for the mission JSON report
    json_path = reports_dir / f"{mission_id}_report.json"
    if not json_path.exists():
        # Try without _report suffix
        json_path = reports_dir / f"{mission_id}.json"

    if not json_path.exists():
        ctx.print(error(f"  No report data found for mission: {mission_id}"))
        ctx.print(dim(f"  Searched: {reports_dir}"))
        ctx.print(dim("  Run a simulation first: aria sim run --mission <type>"))
        sys.exit(1)

    import json as json_mod
    with open(json_path) as f:
        report_data = json_mod.load(f)

    if ctx.is_json:
        print_json(report_data)
        return

    if fmt == "json":
        print_json(report_data)
    elif fmt == "text":
        text_path = reports_dir / f"{mission_id}_report.txt"
        if text_path.exists():
            with open(text_path) as f:
                print(f.read())
        else:
            # Pretty-print from JSON
            print_header(f"Mission Report: {mission_id}")
            for k, v in report_data.items():
                if isinstance(v, dict):
                    print_subheader(k)
                    for sk, sv in v.items():
                        print_kv(sk, sv)
                else:
                    print_kv(k, v)
    elif fmt == "html":
        html_path = reports_dir / f"{mission_id}_report.html"
        if html_path.exists():
            ctx.print(info(f"  HTML report: {html_path}"))
        else:
            ctx.print(warning("  HTML report not available. Generating from JSON..."))
            # Minimal HTML generation
            html = _generate_html_from_json(report_data, mission_id)
            html_path = reports_dir / f"{mission_id}_report.html"
            with open(html_path, "w") as f:
                f.write(html)
            ctx.print(success(f"  Generated: {html_path}"))


def _generate_html_from_json(data: dict[str, Any], title: str) -> str:
    """Generate a minimal HTML report from JSON data."""
    import html as html_mod

    lines = [
        "<!DOCTYPE html>",
        "<html><head>",
        f"<title>ARIA Report: {html_mod.escape(title)}</title>",
        "<style>",
        "body { font-family: monospace; margin: 2em; background: #0a0a0a; color: #e0e0e0; }",
        "h1 { color: #00bcd4; } h2 { color: #4caf50; }",
        "table { border-collapse: collapse; margin: 1em 0; }",
        "td, th { padding: 4px 12px; border: 1px solid #333; }",
        "th { background: #1a1a2e; }",
        "</style>",
        "</head><body>",
        f"<h1>ARIA Mission Report: {html_mod.escape(title)}</h1>",
    ]

    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"<h2>{html_mod.escape(str(k))}</h2>")
            lines.append("<table>")
            for sk, sv in v.items():
                lines.append(f"<tr><th>{html_mod.escape(str(sk))}</th>"
                             f"<td>{html_mod.escape(str(sv))}</td></tr>")
            lines.append("</table>")
        elif isinstance(v, list):
            lines.append(f"<h2>{html_mod.escape(str(k))}</h2>")
            lines.append("<ul>")
            for item in v[:50]:
                lines.append(f"<li>{html_mod.escape(str(item))}</li>")
            lines.append("</ul>")
        else:
            lines.append(f"<p><strong>{html_mod.escape(str(k))}:</strong> "
                         f"{html_mod.escape(str(v))}</p>")

    lines.extend(["</body></html>"])
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
#  report list
# ────────────────────────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> None:
    """List available reports."""
    ctx = get_context()

    root = Path(__file__).resolve().parent.parent.parent.parent
    reports_dir = root / "reports"

    if not reports_dir.exists():
        if ctx.is_json:
            print_json({"reports": []})
        else:
            ctx.print(warning("  No reports directory found."))
            ctx.print(dim("  Run a simulation first: aria sim run --mission <type>"))
        return

    report_files = sorted(reports_dir.glob("*_report.*"))
    if not report_files:
        report_files = sorted(reports_dir.glob("*.json")) + sorted(reports_dir.glob("*.txt"))

    # Group by mission ID
    missions: dict[str, dict[str, Any]] = {}
    for f in report_files:
        name = f.stem
        # Strip _report suffix for grouping
        mission_id = name.replace("_report", "")
        if mission_id not in missions:
            missions[mission_id] = {"formats": [], "size_kb": 0}
        missions[mission_id]["formats"].append(f.suffix.lstrip("."))
        missions[mission_id]["size_kb"] += f.stat().st_size / 1024

    if ctx.is_json:
        print_json([
            {"mission_id": mid, "formats": info["formats"],
             "size_kb": round(info["size_kb"], 1)}
            for mid, info in missions.items()
        ])
        return

    if not missions:
        ctx.print(warning("  No reports found."))
        return

    print_header("Available Reports")
    rows = []
    for mid, info in sorted(missions.items()):
        fmts = ", ".join(info["formats"])
        rows.append([bold(mid), fmts, f"{info['size_kb']:.1f} KB"])
    print_table(["Mission ID", "Formats", "Size"], rows, col_widths=[30, 20, 12])


# ────────────────────────────────────────────────────────────────
#  report score
# ────────────────────────────────────────────────────────────────

def _cmd_score(args: argparse.Namespace) -> None:
    """Show mission score from a saved report."""
    ctx = get_context()
    mission_id = args.mission_id

    root = Path(__file__).resolve().parent.parent.parent.parent
    reports_dir = root / "reports"
    json_path = reports_dir / f"{mission_id}_report.json"

    if not json_path.exists():
        json_path = reports_dir / f"{mission_id}.json"

    if not json_path.exists():
        ctx.print(error(f"  No report data found for mission: {mission_id}"))
        sys.exit(1)

    import json as json_mod
    with open(json_path) as f:
        data = json_mod.load(f)

    score_data = data.get("score", data.get("mission_score", {}))
    total = score_data.get("total", 0) if isinstance(score_data, dict) else 0
    grade = score_data.get("grade", "N/A") if isinstance(score_data, dict) else "N/A"

    if ctx.is_json:
        print_json({"mission_id": mission_id, "score": score_data})
        return

    print_header(f"Mission Score: {mission_id}")

    grade_color = Color.BRIGHT_GREEN if total >= 70 else (
        Color.BRIGHT_YELLOW if total >= 50 else Color.BRIGHT_RED
    )
    print(f"  {colored(f'{total:.0f}/100', grade_color)} ({bold(str(grade))})")
    print()

    if isinstance(score_data, dict):
        rows = []
        for k, v in score_data.items():
            if k not in ("total", "grade", "weights"):
                rows.append([k.replace("_", " ").title(), f"{v:.1f}" if isinstance(v, (int, float)) else str(v)])
        if rows:
            print_subheader("Score Breakdown")
            print_table(["Component", "Score"], rows, col_widths=[30, 12])


# ────────────────────────────────────────────────────────────────
#  report help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show report help."""
    print_header("ARIA Report Commands")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria report generate --mission-id <id>", "Generate a mission report"],
            ["aria report list", "List available reports"],
            ["aria report score --mission-id <id>", "Show mission score"],
        ],
        col_widths=[42, 34],
    )
    print(dim("  Report formats: text, json, html"))
    print()
