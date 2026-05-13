from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aria.conjunction.data.celestrak_client import CelestrakClient, CelestrakError
from aria.conjunction.data.cross_source_delta import (
    CrossSourceDeltaDetector,
    SourceSnapshot,
    format_delta_human,
    parse_celestrak_response_to_snapshot,
)


def _gather_celestrak(groups: list[str]) -> list[SourceSnapshot]:
    client = CelestrakClient()
    snapshots: list[SourceSnapshot] = []
    for group in groups:
        try:
            response = client.fetch_group(group)
        except CelestrakError as exc:
            print(f"WARN: celestrak fetch failed for {group}: {exc}", file=sys.stderr)
            continue
        snapshot = parse_celestrak_response_to_snapshot(
            source=f"celestrak:{group}",
            raw_text=response.raw_text,
            fetched_at=datetime.fromtimestamp(response.fetched_at_s, tz=timezone.utc),
        )
        snapshots.append(snapshot)
    return snapshots


def _gather_offline(files: list[str]) -> list[SourceSnapshot]:
    snapshots: list[SourceSnapshot] = []
    for path in files:
        raw = Path(path).read_text(encoding="utf-8")
        source = f"file:{Path(path).name}"
        snapshots.append(parse_celestrak_response_to_snapshot(
            source=source, raw_text=raw,
        ))
    return snapshots


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-source catalogue delta detector. Pulls TLE data from "
            "multiple sources (Celestrak today; Space-Track / SatNOGS via "
            "their session clients), compares against a persistent baseline, "
            "and emits NEW / MISSING / MANEUVERING / SOURCE-DISAGREEMENT "
            "findings."
        ),
    )
    parser.add_argument(
        "--group", action="append", default=None,
        help=(
            "Celestrak GROUP to fetch (e.g. active, stations, weather, "
            "starlink). Pass multiple --group flags for multiple. Defaults "
            "to 'active'."
        ),
    )
    parser.add_argument(
        "--offline-tle-file", action="append", default=None,
        help=(
            "Local TLE file to use as a snapshot source instead of fetching "
            "from Celestrak. Pass multiple --offline-tle-file flags for "
            "multiple."
        ),
    )
    parser.add_argument(
        "--baseline-path", default=None,
        help="Override the baseline JSON path",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Treat the current snapshots as the new baseline",
    )
    parser.add_argument(
        "--json", dest="emit_json", action="store_true",
        help="Emit machine-readable JSON instead of human text",
    )
    args = parser.parse_args(argv)

    if args.offline_tle_file:
        snapshots = _gather_offline(args.offline_tle_file)
    else:
        groups = args.group or ["active"]
        snapshots = _gather_celestrak(groups)

    if not snapshots:
        print("ERROR: no snapshots gathered", file=sys.stderr)
        return 2

    baseline_path = (
        Path(args.baseline_path) if args.baseline_path
        else CrossSourceDeltaDetector().baseline_path
    )
    detector = CrossSourceDeltaDetector(baseline_path=baseline_path)
    delta = detector.compute(snapshots)

    if args.emit_json:
        print(json.dumps(delta.as_dict(), indent=2))
    else:
        print(format_delta_human(delta))

    if args.update_baseline:
        detector.write_baseline(snapshots)
        print(f"\n[baseline updated → {detector.baseline_path}]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
