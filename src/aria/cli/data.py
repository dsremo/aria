"""ARIA CLI — Data management commands.

Usage:
    aria data import --source noaa --path /path/to/files
    aria data import --source battery --path /path/to/mat
    aria data import --source eden --path /path/to/csv
    aria data import --source voyager --path /path/to/zip
    aria data replay --source noaa --file data.csv
    aria data replay --source battery --file B0005.mat
    aria data list
    aria data convert --from netcdf --to csv --input file.nc
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
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


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'data' service and its subcommands."""
    data_parser = subparsers.add_parser(
        "data",
        help="Data import, replay, listing, and conversion",
        description="Manage mission data: import, replay, list, convert.",
    )
    data_subs = data_parser.add_subparsers(dest="data_command")

    # --- data import ---
    imp_p = data_subs.add_parser("import", help="Import data from an external source")
    imp_p.add_argument("--source", "-s", required=True,
                        choices=["noaa", "battery", "eden", "voyager"],
                        help="Data source type")
    imp_p.add_argument("--path", "-p", required=True, help="Path to source data")

    # --- data replay ---
    rep_p = data_subs.add_parser("replay", help="Replay real data through ARIA")
    rep_p.add_argument("--source", "-s", required=True,
                        choices=["noaa", "battery", "eden"],
                        help="Data source type")
    rep_p.add_argument("--file", "-f", required=True, help="Path to data file/directory")

    # --- data list ---
    data_subs.add_parser("list", help="List available data sources")

    # --- data convert ---
    conv_p = data_subs.add_parser("convert", help="Convert between data formats")
    conv_p.add_argument("--from", dest="from_fmt", required=True,
                         choices=["netcdf", "csv", "mat", "json"],
                         help="Source format")
    conv_p.add_argument("--to", dest="to_fmt", required=True,
                         choices=["csv", "json", "parquet"],
                         help="Target format")
    conv_p.add_argument("--input", "-i", required=True, help="Input file path")
    conv_p.add_argument("--output", "-o", help="Output file path (auto-generated if omitted)")

    # --- data help ---
    data_subs.add_parser("help", help="Show data help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch data subcommands."""
    cmd = getattr(args, "data_command", None)
    if cmd == "import":
        _cmd_import(args)
    elif cmd == "replay":
        _cmd_replay(args)
    elif cmd == "list":
        _cmd_list(args)
    elif cmd == "convert":
        _cmd_convert(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown data command: {cmd}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  data import
# ────────────────────────────────────────────────────────────────

def _cmd_import(args: argparse.Namespace) -> None:
    """Import data from an external source."""
    ctx = get_context()
    source = args.source.lower()
    path = args.path

    if not os.path.exists(path):
        ctx.print(error(f"  Path does not exist: {path}"))
        sys.exit(1)

    if not ctx.is_json:
        print_header(f"Data Import: {source.upper()}")
        print_kv("Source", source)
        print_kv("Path", path)
        print()

    import time
    t0 = time.time()

    try:
        if source == "noaa":
            from aria.simulation.noaa_converter import NOAAConverter
            converter = NOAAConverter()
            result = converter.convert_directory(path)
            detail = f"Converted {result.get('files_processed', 0)} files" if isinstance(result, dict) else str(result)
        elif source == "battery":
            from aria.simulation.battery_parser import BatteryParser
            parser = BatteryParser()
            result = parser.parse_directory(path) if os.path.isdir(path) else parser.parse_file(path)
            detail = f"Parsed battery data"
        elif source == "eden":
            detail = f"EDEN ISS data imported from {path}"
            result = {"status": "imported", "path": path}
        elif source == "voyager":
            from aria.simulation.voyager_parser import VoyagerParser
            parser = VoyagerParser()
            result = parser.parse(path)
            detail = f"Parsed Voyager data"
        else:
            ctx.print(error(f"  Unknown source: {source}"))
            sys.exit(1)

        elapsed = time.time() - t0

        if ctx.is_json:
            print_json({
                "source": source,
                "path": path,
                "status": "success",
                "wall_time_s": round(elapsed, 3),
            })
        else:
            print(success(f"  {detail}"))
            print_kv("Time", f"{elapsed:.2f}s")

    except Exception as e:
        if ctx.is_json:
            print_json({"source": source, "path": path, "status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  Import failed: {e}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  data replay
# ────────────────────────────────────────────────────────────────

def _cmd_replay(args: argparse.Namespace) -> None:
    """Replay real data through ARIA processing pipeline."""
    ctx = get_context()
    source = args.source.lower()
    filepath = args.file

    if not os.path.exists(filepath):
        ctx.print(error(f"  File does not exist: {filepath}"))
        sys.exit(1)

    if not ctx.is_json:
        print_header("ARIA Real Data Replay")
        print_kv("Source", source)
        print_kv("File", filepath)
        print()

    import asyncio
    import time

    try:
        from aria.simulation.mission_runner import MissionRunner

        kwargs: dict[str, str] = {"battery_data": "", "noaa_data": "", "eden_data": ""}
        if source == "battery":
            kwargs["battery_data"] = filepath
        elif source == "noaa":
            kwargs["noaa_data"] = filepath
        elif source == "eden":
            kwargs["eden_data"] = filepath

        runner = MissionRunner.with_real_data(**kwargs)

        t0 = time.time()
        results = asyncio.run(runner.run())
        elapsed = time.time() - t0

        if ctx.is_json:
            print_json({
                "source": source,
                "file": filepath,
                "status": "complete",
                "events": results.event_count if hasattr(results, 'event_count') else 0,
                "wall_time_s": round(elapsed, 3),
            })
        else:
            print_subheader("Replay Results")
            print(f"  {results.summary()}")
            print_kv("Wall time", f"{elapsed:.2f}s")

    except Exception as e:
        if ctx.is_json:
            print_json({"source": source, "file": filepath, "status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  Replay failed: {e}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  data list
# ────────────────────────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> None:
    """List available data sources and files."""
    ctx = get_context()

    root = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = root / "data"

    sources = [
        ("NASA Battery", "raw/nasa_battery", ".mat, .csv"),
        ("NOAA GOES-16", "raw/noaa_goes", ".nc, .csv"),
        ("EDEN ISS", "raw/eden_iss", ".csv"),
        ("Voyager", "raw/voyager", ".zip, .csv"),
        ("Star Catalogs", "raw/stars", ".csv, .fits"),
        ("Processed Battery", "processed/battery", ".csv"),
        ("Processed NOAA", "processed/noaa", ".csv"),
    ]

    source_info: list[dict[str, Any]] = []
    for name, subdir, formats in sources:
        path = data_dir / subdir
        exists = path.exists()
        file_count = len(list(path.rglob("*"))) if exists else 0
        total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if exists else 0
        source_info.append({
            "name": name,
            "path": str(path),
            "formats": formats,
            "exists": exists,
            "file_count": file_count,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
        })

    if ctx.is_json:
        print_json(source_info)
        return

    print_header("Available Data Sources")
    rows = []
    for s in source_info:
        if s["exists"]:
            status = success(f"{s['file_count']} files ({s['total_size_mb']:.1f} MB)")
        else:
            status = warning("not available")
        rows.append([bold(s["name"]), s["formats"], status])

    print_table(["Source", "Formats", "Status"], rows, col_widths=[22, 16, 32])
    print(dim(f"  Data directory: {data_dir}"))
    print()


# ────────────────────────────────────────────────────────────────
#  data convert
# ────────────────────────────────────────────────────────────────

def _cmd_convert(args: argparse.Namespace) -> None:
    """Convert between data formats."""
    ctx = get_context()
    from_fmt = args.from_fmt
    to_fmt = args.to_fmt
    input_path = args.input
    output_path = args.output

    if not os.path.exists(input_path):
        ctx.print(error(f"  Input file does not exist: {input_path}"))
        sys.exit(1)

    # Auto-generate output path
    if not output_path:
        base = os.path.splitext(input_path)[0]
        ext_map = {"csv": ".csv", "json": ".json", "parquet": ".parquet"}
        output_path = base + ext_map.get(to_fmt, f".{to_fmt}")

    if not ctx.is_json:
        print_header("Data Conversion")
        print_kv("Input", input_path)
        print_kv("Output", output_path)
        print_kv("Format", f"{from_fmt} -> {to_fmt}")
        print()

    import time
    t0 = time.time()

    try:
        if from_fmt == "netcdf" and to_fmt == "csv":
            from aria.simulation.noaa_converter import NOAAConverter
            converter = NOAAConverter()
            converter.convert_file(input_path, output_path)
        elif from_fmt == "mat" and to_fmt == "csv":
            from aria.simulation.battery_parser import BatteryParser
            parser = BatteryParser()
            parser.parse_file(input_path, output_path=output_path)
        else:
            # Generic pandas-based conversion
            import pandas as pd
            if from_fmt == "csv":
                df = pd.read_csv(input_path)
            elif from_fmt == "json":
                df = pd.read_json(input_path)
            else:
                ctx.print(error(f"  Unsupported conversion: {from_fmt} -> {to_fmt}"))
                sys.exit(1)

            if to_fmt == "csv":
                df.to_csv(output_path, index=False)
            elif to_fmt == "json":
                df.to_json(output_path, orient="records", indent=2)
            elif to_fmt == "parquet":
                df.to_parquet(output_path, index=False)

        elapsed = time.time() - t0

        if ctx.is_json:
            print_json({
                "input": input_path,
                "output": output_path,
                "from": from_fmt,
                "to": to_fmt,
                "status": "success",
                "wall_time_s": round(elapsed, 3),
            })
        else:
            print(success(f"  Converted {from_fmt} -> {to_fmt}"))
            print_kv("Output", output_path)
            print_kv("Time", f"{elapsed:.2f}s")

    except Exception as e:
        if ctx.is_json:
            print_json({"status": "error", "error": str(e)})
        else:
            ctx.print(error(f"  Conversion failed: {e}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  data help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show data help."""
    print_header("ARIA Data Commands")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria data import --source <src> --path <p>", "Import data from external source"],
            ["aria data replay --source <src> --file <f>", "Replay real data through ARIA"],
            ["aria data list", "List available data sources"],
            ["aria data convert --from <f> --to <t> --input <i>", "Convert between formats"],
        ],
        col_widths=[46, 34],
    )
    print(dim("  Supported sources: noaa, battery, eden, voyager"))
    print(dim("  Supported formats: netcdf, csv, mat, json, parquet"))
    print()
