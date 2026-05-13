"""Circuit breaker for external API calls.

States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing recovery)

Used for: NASA OSDR, MAST, HITRAN, AlphaFold EBI, UniProt, ESM Atlas.
These are government/academic APIs with no SLA — the system must degrade
gracefully when they hang or return errors.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from aria.genastra.core._compat import StrEnum
from aria.genastra.core.constants import (
    UPSTREAM_CIRCUIT_BREAKER_FAILURES,
    UPSTREAM_CIRCUIT_BREAKER_RECOVERY_S,
    UPSTREAM_CIRCUIT_BREAKER_TIMEOUT_S,
)
from aria.genastra.core.exceptions import UpstreamUnavailableError

logger = structlog.get_logger()


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-service circuit breaker with configurable thresholds."""

    def __init__(
        self,
        service: str,
        failure_threshold: int = UPSTREAM_CIRCUIT_BREAKER_FAILURES,
        recovery_timeout_s: float = UPSTREAM_CIRCUIT_BREAKER_RECOVERY_S,
        request_timeout_s: float = UPSTREAM_CIRCUIT_BREAKER_TIMEOUT_S,
    ) -> None:
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.request_timeout_s = request_timeout_s

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._success_count_half_open = 0
        # P1-E9 (Bhatt): asyncio.gather on multiple upstream APIs (MAST + HITRAN)
        # creates concurrent coroutines that call record_failure() simultaneously.
        # Plain attribute mutation is NOT atomic in asyncio — a context switch
        # between read-modify-write steps corrupts _failure_count and _state.
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Read current state, transitioning OPEN→HALF_OPEN if recovery timeout elapsed.

        Note: this property is intentionally NOT lock-guarded because it is
        read-only for callers (check() uses it). State *mutations* are guarded
        in record_success / record_failure / reset via the asyncio.Lock.
        """
        if self._state == CircuitState.OPEN:  # noqa: SIM102
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout_s:
                self._state = CircuitState.HALF_OPEN
                self._success_count_half_open = 0
                logger.info("circuit_breaker_half_open", service=self.service)
        return self._state

    def check(self) -> None:
        """Check if a request is allowed. Raises UpstreamUnavailableError if circuit is open."""
        if self.state == CircuitState.OPEN:
            raise UpstreamUnavailableError(self.service)

    async def record_success(self) -> None:
        """Record a successful call (async-safe)."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count_half_open += 1
                if self._success_count_half_open >= 2:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("circuit_breaker_closed", service=self.service)
            else:
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self) -> None:
        """Record a failed call (async-safe)."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open trips back to open
                self._state = CircuitState.OPEN
                logger.warning("circuit_breaker_reopened", service=self.service)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_tripped",
                    service=self.service,
                    failure_count=self._failure_count,
                )

    async def reset(self) -> None:
        """Manually reset the circuit breaker (async-safe)."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count_half_open = 0
        logger.info("circuit_breaker_reset", service=self.service)


# ── Global registry ────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(service: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a named service."""
    if service not in _breakers:
        _breakers[service] = CircuitBreaker(service)
    return _breakers[service]
