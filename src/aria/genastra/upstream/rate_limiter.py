"""Token-bucket rate limiter for upstream API calls.

Per-service limits to avoid being banned by government/academic APIs.
NASA OSDR: ~60 req/min (undocumented). MAST: 10 req/s (documented).
"""

from __future__ import annotations

import asyncio
import time

import structlog

logger = structlog.get_logger()


class TokenBucketRateLimiter:
    """Async-safe token bucket rate limiter.

    Refills `rate` tokens per second, up to `capacity` max.
    `acquire()` blocks until a token is available.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 30.0) -> None:
        """Wait until a token is available. Raises TimeoutError if `timeout` exceeded."""
        deadline = time.monotonic() + timeout

        async with self._lock:
            self._refill()

            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Rate limiter timeout — upstream too slow")
                await asyncio.sleep(min(wait, remaining))
                self._refill()

            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now


# ── Pre-configured limiters for known upstream services ────────────

_limiters: dict[str, TokenBucketRateLimiter] = {}

# Service rate limits (conservative)
_DEFAULTS: dict[str, tuple[float, int]] = {
    "nasa_osdr": (1.0, 5),       # 1 req/s, burst 5
    "mast": (5.0, 10),            # 5 req/s, burst 10
    "hitran": (2.0, 5),           # 2 req/s, burst 5
    "alphafold_ebi": (5.0, 10),   # 5 req/s, burst 10
    "uniprot": (5.0, 10),         # 5 req/s, burst 10
    "esm_atlas": (3.0, 5),        # 3 req/s, burst 5
    "rcsb_pdb": (5.0, 10),        # 5 req/s, burst 10
}


def get_rate_limiter(service: str) -> TokenBucketRateLimiter:
    """Get or create a rate limiter for a named service."""
    if service not in _limiters:
        rate, capacity = _DEFAULTS.get(service, (2.0, 5))
        _limiters[service] = TokenBucketRateLimiter(rate, capacity)
    return _limiters[service]
