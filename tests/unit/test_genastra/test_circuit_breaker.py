"""Tests for the circuit breaker."""

from __future__ import annotations

import pytest

from aria.genastra.core.exceptions import UpstreamUnavailableError
from aria.genastra.upstream.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout_s=9999)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_raises_unavailable(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999)
        await cb.record_failure()
        with pytest.raises(UpstreamUnavailableError, match="test"):
            cb.check()

    @pytest.mark.asyncio
    async def test_success_decrements_failure_count(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()
        await cb.record_failure()
        # Should still be closed (2 failures, not 3)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_after_recovery(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0)
        await cb.record_failure()
        # With recovery_timeout=0, state check immediately transitions to half-open
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_closes_after_successes(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0)
        await cb.record_failure()
        _ = cb.state  # trigger half-open
        await cb.record_success()
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999)
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await cb.reset()
        assert cb.state == CircuitState.CLOSED
