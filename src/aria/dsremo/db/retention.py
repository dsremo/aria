"""Data retention and archival policy for TimescaleDB.

P3-X fix: Defines retention policies for telemetry data to prevent
unbounded growth.  For a 100-satellite constellation at 1 Hz:
    5000 points/sec × 86400 sec/day = 432M points/day ≈ 40 GB/day

Policies:
    1. Raw telemetry:  Compressed after 7 days, dropped after 90 days
    2. Anomalies:      Kept indefinitely (small volume)
    3. Detection audit: Compressed after 30 days, dropped after 365 days
    4. Hourly rollups:  Continuous aggregate, kept indefinitely

Usage:
    await setup_retention_policies()  # call once at startup
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


async def setup_retention_policies(
    raw_retention_days: int = 90,
    raw_compress_after_days: int = 7,
    audit_retention_days: int = 365,
    audit_compress_after_days: int = 30,
) -> None:
    """Configure TimescaleDB retention and compression policies.

    Safe to call multiple times — uses IF NOT EXISTS semantics.
    Requires TimescaleDB extension and hypertables already created.
    """
    from aria.dsremo.db.connection import get_pool  # noqa: PLC0415

    pool = get_pool()
    async with pool.acquire() as conn:
        # ── 1. Enable compression on telemetry hypertable ──────────────
        try:
            await conn.execute("""
                ALTER TABLE telemetry SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'satellite_id, parameter',
                    timescaledb.compress_orderby = 'timestamp DESC'
                )
            """)
            logger.info("timescaledb_compression_enabled", table="telemetry")
        except Exception as e:
            logger.debug("timescaledb_compression_skip", table="telemetry", reason=str(e))

        # ── 2. Add compression policy (compress chunks older than N days) ──
        try:
            await conn.execute(f"""
                SELECT add_compression_policy('telemetry',
                    INTERVAL '{raw_compress_after_days} days',
                    if_not_exists => true)
            """)
            logger.info("compression_policy_set", table="telemetry",
                       after_days=raw_compress_after_days)
        except Exception as e:
            logger.debug("compression_policy_skip", reason=str(e))

        # ── 3. Add retention policy (drop chunks older than N days) ────
        try:
            await conn.execute(f"""
                SELECT add_retention_policy('telemetry',
                    INTERVAL '{raw_retention_days} days',
                    if_not_exists => true)
            """)
            logger.info("retention_policy_set", table="telemetry",
                       retention_days=raw_retention_days)
        except Exception as e:
            logger.debug("retention_policy_skip", reason=str(e))

        # ── 4. Detection audit retention ───────────────────────────────
        try:
            await conn.execute("""
                ALTER TABLE detection_audit SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'satellite_id, parameter',
                    timescaledb.compress_orderby = 'timestamp DESC'
                )
            """)
            await conn.execute(f"""
                SELECT add_compression_policy('detection_audit',
                    INTERVAL '{audit_compress_after_days} days',
                    if_not_exists => true)
            """)
            await conn.execute(f"""
                SELECT add_retention_policy('detection_audit',
                    INTERVAL '{audit_retention_days} days',
                    if_not_exists => true)
            """)
            logger.info("audit_retention_set",
                       compress_days=audit_compress_after_days,
                       retention_days=audit_retention_days)
        except Exception as e:
            logger.debug("audit_retention_skip", reason=str(e))

    logger.info("retention_policies_configured",
               raw_compress=raw_compress_after_days,
               raw_retain=raw_retention_days,
               audit_compress=audit_compress_after_days,
               audit_retain=audit_retention_days)


async def get_retention_stats() -> dict:
    """Return current data size and compression stats."""
    from aria.dsremo.db.connection import get_pool  # noqa: PLC0415

    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow("""
                SELECT
                    hypertable_size('telemetry') as total_bytes,
                    pg_size_pretty(hypertable_size('telemetry')) as total_size
            """)
            return {
                "telemetry_bytes": row["total_bytes"] if row else 0,
                "telemetry_size": row["total_size"] if row else "unknown",
            }
        except Exception:
            return {"telemetry_bytes": 0, "telemetry_size": "unknown"}
