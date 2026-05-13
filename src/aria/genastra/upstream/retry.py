"""Resilient HTTP client with circuit breaker, rate limiting, and retry."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from aria.genastra.upstream.circuit_breaker import CircuitBreaker, get_circuit_breaker
from aria.genastra.upstream.rate_limiter import TokenBucketRateLimiter, get_rate_limiter

logger = structlog.get_logger()


async def resilient_request(
    service: str,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    timeout_s: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Make an HTTP request with circuit breaker, rate limiting, and exponential backoff.

    Args:
        service: Service name (for circuit breaker + rate limiter lookup).
        method: HTTP method (GET, POST, etc.).
        url: Full URL.
        max_retries: Number of retries on transient errors.
        backoff_base: Base seconds for exponential backoff.
        timeout_s: Per-request timeout.
        **kwargs: Passed to httpx.AsyncClient.request().

    Returns:
        httpx.Response on success.

    Raises:
        UpstreamUnavailableError: Circuit breaker is open.
        httpx.HTTPStatusError: Non-retryable HTTP error.
    """
    breaker: CircuitBreaker = get_circuit_breaker(service)
    limiter: TokenBucketRateLimiter = get_rate_limiter(service)

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        breaker.check()
        await limiter.acquire()

        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.request(method, url, **kwargs)

            if response.status_code >= 500:
                # Server error — retry
                breaker.record_failure()
                last_exception = httpx.HTTPStatusError(
                    f"Server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
                if attempt < max_retries:
                    wait = backoff_base * (2 ** attempt)
                    logger.warning(
                        "upstream_retry",
                        service=service,
                        attempt=attempt + 1,
                        status=response.status_code,
                        wait_s=wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise last_exception

            if response.status_code == 429:
                # Rate limited by upstream — back off harder
                breaker.record_failure()
                wait = backoff_base * (2 ** (attempt + 1))
                logger.warning("upstream_rate_limited", service=service, wait_s=wait)
                if attempt < max_retries:
                    await asyncio.sleep(wait)
                    continue

            # Success (2xx, 3xx, 4xx non-429)
            breaker.record_success()
            return response

        except httpx.TimeoutException as exc:
            breaker.record_failure()
            last_exception = exc
            if attempt < max_retries:
                wait = backoff_base * (2 ** attempt)
                logger.warning(
                    "upstream_timeout",
                    service=service,
                    attempt=attempt + 1,
                    wait_s=wait,
                )
                await asyncio.sleep(wait)
                continue

        except httpx.ConnectError as exc:
            breaker.record_failure()
            last_exception = exc
            if attempt < max_retries:
                wait = backoff_base * (2 ** attempt)
                await asyncio.sleep(wait)
                continue

    # All retries exhausted
    raise last_exception or RuntimeError(f"Upstream {service} failed after {max_retries} retries")
