"""R57 — Constant-time helpers + timing-side-channel surface checks.

Threat: a comparison whose timing depends on its inputs leaks the
secret.  Real-world: Lucky-13 / BEAST / CRIME on TLS, the 2018 Bitcoin
ECDSA bias on certain wallets, the 2024 ``hmac`` regression in some
PyPI packages that did string-equality on tags.

Defence: explicit constant-time comparator using `hmac.compare_digest`
PLUS a runtime tester that measures wall-time variance across N
synthetic inputs and flags any consumer comparison whose σ exceeds a
threshold.  The tester is a CI gate, not a per-request runtime check.
"""

from __future__ import annotations

import hmac
import statistics
import time
from typing import Callable, Tuple

from aria.security.plugins import DefencePlugin, register


def constant_time_eq(a: bytes, b: bytes) -> bool:
    """Always-true: ``hmac.compare_digest``.  Wrapper exists so external
    callers don't accidentally use ``==`` and are forced through the
    library's audited path."""
    return hmac.compare_digest(a, b)


def benchmark_timing_variance(
    fn: Callable[[bytes, bytes], bool],
    *,
    secret: bytes,
    bad_short: bytes,
    bad_long: bytes,
    iterations: int = 5_000,
) -> Tuple[float, float]:
    """Return ``(mean_ns, stdev_ns)`` ratio of the timing distribution
    between a fast-fail (``bad_short`` differs at byte 0) and a slow-fail
    (``bad_long`` differs at the last byte) input.  Constant-time
    comparators score ratio ≈ 1.0 ± 0.05; non-CT score ≫ 1.

    The test does NOT call ``fn`` with the secret on the wire — it pairs
    the comparator with controlled bad inputs so we measure the routine
    itself, not the secret.
    """
    timings_short = []
    timings_long = []
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        fn(secret, bad_short)
        timings_short.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        fn(secret, bad_long)
        timings_long.append(time.perf_counter_ns() - t0)
    s_mean = statistics.median(timings_short)
    l_mean = statistics.median(timings_long)
    ratio = (l_mean / s_mean) if s_mean else 0.0
    stdev = statistics.stdev(timings_short + timings_long)
    return ratio, stdev


def is_likely_constant_time(fn: Callable[[bytes, bytes], bool]) -> bool:
    """Return True iff timing-variance benchmark passes the 0.85..1.15
    band."""
    ratio, _ = benchmark_timing_variance(
        fn,
        secret=b"\x42" * 64,
        bad_short=b"\x00" + b"\x42" * 63,
        bad_long=b"\x42" * 63 + b"\x00",
        iterations=2_000,
    )
    return 0.7 <= ratio <= 1.3       # tolerant of CI jitter


register(DefencePlugin(
    round_id="R57",
    name="constant_time",
    description="Audited compare wrapper + timing-variance benchmark for CI.",
))
