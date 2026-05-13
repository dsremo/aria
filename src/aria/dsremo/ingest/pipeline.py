"""Shared pipeline utilities for analyze_*.py scripts.

Eliminates the 11-line DB-init block and Phase 1/2 boilerplate that was
copy-pasted verbatim across every analysis script.

Usage (in any analyze_*.py)::

    async def main(...):
        async with db_context() as cfg:
            connector = MyConnector(...)
            print_run_header("My Source", Satellite=sat_id, Resolution="5-min")

            with phase("Phase 1: Bulk Load"):
                totals = await connector.bulk_load_to_db(...)
                print(f"  {sum(totals.values()):,} rows, {len(totals)} channels")

            with phase("Phase 2: Streaming Detection"):
                results = await run_bulk_detection(...)
                print(f"  {sum(len(v) for v in results.values())} anomalies")

            print_detection_report(results, title="...")
"""

from __future__ import annotations

import contextlib
import copy
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_HEADER_WIDTH = 65


@contextlib.asynccontextmanager
async def db_context(
    cfg_path: Path = Path("configs/dsremo.yaml"),
    *,
    cooldown_hours: int | None = None,
):
    """Async context manager: load config, init DB pool + detectors, close on exit.

    Args:
        cfg_path:       Path to dsremo.yaml (default: ``configs/dsremo.yaml``).
        cooldown_hours: Override ``detection.alert_cooldown_hours`` in config
                        without mutating the on-disk file.  Useful for historical
                        datasets (e.g. ESA spans 13 years → 1440 h cooldown).

    Yields:
        The (possibly modified) config dict so callers can read it if needed.
    """
    # Local imports keep this module importable without a running DB (tests).
    from aria.dsremo.core.config import load_config
    from aria.dsremo.db import connection as db_connection
    from aria.dsremo.detection.detector import init_detectors

    cfg: dict[str, Any] = load_config(cfg_path)

    if cooldown_hours is not None:
        cfg = copy.deepcopy(cfg)
        cfg.setdefault("detection", {})["alert_cooldown_hours"] = cooldown_hours

    db = cfg.get("database", {})
    await db_connection.init_pool(
        host=db.get("host", "localhost"),
        port=db.get("port", 5432),
        database=db.get("name", "dsremo"),
        user=db.get("user", "dsremo"),
        password=db.get("password", ""),
        min_size=2,
        max_size=4,
    )
    init_detectors(cfg)
    logger.info("pipeline_db_ready", host=db.get("host", "localhost"))

    try:
        yield cfg
    finally:
        await db_connection.close_pool()
        logger.info("pipeline_db_closed")


@contextlib.contextmanager
def phase(label: str, *, width: int = _HEADER_WIDTH) -> Iterator[None]:
    """Sync context manager: print a phase header banner and elapsed time on exit.

    Example output::

        ── Phase 1: Bulk Load ──────────────────────────────────────
          ... caller prints summary here ...
          (─── 3.2s)
    """
    pad = max(0, width - len(label) - 4)
    print(f"\n── {label} {'─' * pad}")
    t = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - t
        print(f"  ({'─' * 3} {elapsed:.1f}s)")


def print_run_header(title: str, **pairs: str) -> None:
    """Print a consistent banner with key-value metadata rows.

    Args:
        title:  Main title line (e.g. ``"SatNOGS Network — Production Benchmark"``).
        **pairs: Arbitrary key=value rows printed below the title.
                 Underscore in key is replaced with space and capitalised.

    Example::

        print_run_header(
            "CSV Telemetry — Dsremo",
            File="telemetry.csv",
            Satellite="MYSAT-1",
            Resolution="5-min",
        )
    """
    print("\n" + "=" * _HEADER_WIDTH)
    print(title)
    print("=" * _HEADER_WIDTH)
    for key, val in pairs.items():
        label = key.replace("_", " ").capitalize()
        print(f"  {label:<16}: {val}")
    print()
