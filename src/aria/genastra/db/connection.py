"""Database and Redis connection management.

Follows the same asyncpg pool pattern as the Telemetry Detection project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import asyncpg
    import redis.asyncio as aioredis

logger = structlog.get_logger()

_pool: asyncpg.Pool | None = None
_redis: aioredis.Redis | None = None


async def init_db(dsn: str, min_size: int = 5, max_size: int = 20) -> asyncpg.Pool:
    """Initialize the asyncpg connection pool."""
    import asyncpg as _asyncpg

    global _pool
    _pool = await _asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size)
    logger.info("db_pool_initialized", min_size=min_size, max_size=max_size)
    return _pool


async def close_db() -> None:
    """Close the database connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


def get_pool() -> asyncpg.Pool:
    """Get the database connection pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return _pool


async def init_redis(url: str = "redis://localhost:6379/0") -> aioredis.Redis:
    """Initialize the Redis connection."""
    import redis.asyncio as aioredis

    global _redis
    _redis = aioredis.from_url(url, decode_responses=True)
    await _redis.ping()
    logger.info("redis_initialized", url=url)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("redis_closed")


def get_redis() -> aioredis.Redis | None:
    """Get the Redis connection, or None if not initialized."""
    return _redis
