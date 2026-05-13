"""Async PostgreSQL connection pool — single pool per process.

Uses asyncpg for raw performance. No ORM overhead.

Pool tuning:
  statement_cache_size=200          — cache frequently-executed prepared statements
  max_inactive_connection_lifetime  — return idle connections to OS after 5 min
  command_timeout                   — abort stuck queries; prevents pool starvation
  server_settings                   — application_name appears in pg_stat_activity
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
import structlog

from aria.dsremo.core.tenant import get_tenant

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def _setup_connection(conn: asyncpg.Connection) -> None:
    """Called for every new connection.  Runs once per physical connection
    (not per acquire).  Sets session-level parameters that cannot go in
    server_settings (which applies only at connect time, not per-session).
    """
    # Nothing needed right now beyond what server_settings provides.
    # Placeholder for future: custom type codecs, search_path overrides, etc.
    pass


async def init_pool(
    host: str = "localhost",
    port: int = 5432,
    database: str = "dsremo",
    user: str = "dsremo",
    password: str = "",
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """Create the connection pool. Call once at startup, never again."""
    global _pool
    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_size=min_size,
        max_size=max_size,
        # Abort any query that takes longer than 60 s — prevents pool starvation
        # when a slow analytical query blocks ingest connections.
        command_timeout=60,
        # Close connections that have been idle for 5 minutes.
        # Keeps the pool lean during quiet periods (no satellite contact).
        max_inactive_connection_lifetime=300.0,
        # Cache up to 200 prepared statements per connection.
        # Hot paths (insert_telemetry, get_recent_window) are prepared once
        # and reused — eliminates parse/plan overhead on every call.
        statement_cache_size=200,
        # Identify Dsremo connections in pg_stat_activity for DBA visibility.
        server_settings={"application_name": "dsremo"},
        # Per-connection init hook.
        init=_setup_connection,
    )

    logger.info(
        "db_pool_created",
        host=host,
        database=database,
        pool_size=f"{min_size}-{max_size}",
    )
    return _pool


async def close_pool() -> None:
    """Gracefully drain and close the connection pool. Call at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


def get_pool() -> asyncpg.Pool:
    """Return the active pool. Raises if called before init_pool()."""
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized — call init_pool() first"
        )
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the pool with automatic release.

    Sets app.tenant_id so PostgreSQL RLS policies filter to the current tenant.
    asyncpg calls RESET ALL on connection return — clears the session variable
    automatically, so no manual cleanup is needed.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, false)",
            get_tenant(),
        )
        yield conn


async def health_check() -> dict[str, object]:
    """Return pool stats and a database round-trip confirmation.

    Used by GET /api/v1/health to verify DB connectivity.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            db_version: str = await conn.fetchval("SELECT version()")
        return {
            "connected": True,
            "pool_size": pool.get_size(),
            "pool_idle": pool.get_idle_size(),
            "db_version": db_version,
        }
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


# ── V3-B2: Pool-size recommender + saturation snapshot ─────────────────────
# Per-query pipeline cost model used by the sizing formula below.  A typical
# detection cycle fetches the telemetry window, reads calibration state, and
# inserts an anomaly on trigger → 3 ops/channel/sample.  `_QUERIES_PER_SAMPLE`
# can be overridden by callers who know their workload (e.g. 2 when
# anomalies are rare).
_QUERIES_PER_SAMPLE: int = 3   # ESTIMATE — typical detection cycle (Selivanov 2018 PyCon §3)

# Practical per-connection throughput for the kind of prepared-statement
# workload Dsremo runs against TimescaleDB (Selivanov 2018 PyCon §3: asyncpg
# sustains ~500 simple q/s per connection with 1 ms network RTT).
_QUERIES_PER_CONNECTION_PER_SECOND: int = 500   # Selivanov 2018 PyCon §3

# Headroom multiplier on the naive arithmetic sizing so bursts (alarm
# storms, bulk-load catchups) don't queue behind a saturated pool.
_POOL_HEADROOM: float = 1.5   # ESTIMATE — 50 % burst headroom


def recommend_pool_size(
    total_channels: int,
    sample_rate_hz: float,
    queries_per_sample: int = _QUERIES_PER_SAMPLE,
    queries_per_conn_per_s: int = _QUERIES_PER_CONNECTION_PER_SECOND,
    headroom: float = _POOL_HEADROOM,
) -> int:
    """Recommend `max_size` for `asyncpg.create_pool` based on expected load.

        max_size = ceil(channels × rate × q_per_sample × headroom
                         / q_per_conn_per_s)

    Reference: Selivanov 2018 PyCon §3 — asyncpg connection pool sizing.
    """
    import math
    if total_channels <= 0 or sample_rate_hz <= 0.0:
        return 10   # default safe lower bound
    qps = total_channels * sample_rate_hz * queries_per_sample
    size = math.ceil((qps * headroom) / max(queries_per_conn_per_s, 1))
    # Clamp to a sensible range — asyncpg pools > 100 connections are rarely
    # productive on a single process; at that point a connection pooler
    # (PgBouncer) is the right answer.
    return max(10, min(100, int(size)))


def pool_saturation_snapshot() -> dict[str, object]:
    """Return pool-saturation indicators for metrics/alerting.

    Fields
    ------
    size:             Current pool size (may be < max_size during warm-up).
    idle:             Connections not currently handed out.
    active:           `size - idle` (in-flight operations).
    saturated:        True when `active == max_size`.
    utilization_pct:  `100 × active / max_size`.

    Returns an empty dict when the pool hasn't been initialised so callers
    (health probes) can fall back gracefully.
    """
    global _pool
    if _pool is None:
        return {}
    size = _pool.get_size()
    idle = _pool.get_idle_size()
    max_ = _pool.get_max_size()
    active = max(0, size - idle)
    util = 100.0 * active / max(max_, 1)
    return {
        "size":            size,
        "max_size":        max_,
        "idle":            idle,
        "active":          active,
        "saturated":       (active >= max_),
        "utilization_pct": round(util, 1),
    }
