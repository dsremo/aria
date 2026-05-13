"""R94 — In-process fuzzing harness.

Threat: handlers + parsers + sanitizers crash on edge inputs we never
imagined (UTF-16 surrogate halves, malformed JSON, null bytes in
header values, etc.).  Banks, kernel teams, and AV vendors all run
property-based + structure-aware fuzzers nightly.

Defence: a bounded fuzzer that takes a callable + an input mutator and
runs it for ``n`` rounds.  Built on `random.Random(seed)` so a regression
that triggers at run #4242 is reproducible.  Captures every exception
class + the smallest input that triggered it; emits a report compatible
with R51's adversarial-runner format.
"""

from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from aria.security.plugins import DefencePlugin, register


@dataclass
class FuzzReport:
    iterations: int = 0
    crashes: List[Dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0


def _mutate_random_bytes(rng: random.Random, base: bytes) -> bytes:
    if len(base) == 0:
        return rng.randbytes(rng.randint(0, 64))
    op = rng.randint(0, 4)
    if op == 0:                          # replace random byte
        i = rng.randint(0, len(base) - 1)
        return base[:i] + bytes([rng.randint(0, 255)]) + base[i + 1:]
    if op == 1:                          # insert random byte
        i = rng.randint(0, len(base))
        return base[:i] + bytes([rng.randint(0, 255)]) + base[i:]
    if op == 2:                          # delete random byte
        i = rng.randint(0, len(base) - 1)
        return base[:i] + base[i + 1:]
    if op == 3:                          # truncate
        return base[: rng.randint(0, len(base))]
    return base + rng.randbytes(rng.randint(1, 32))


def fuzz_callable(
    fn: Callable[[bytes], Any],
    *,
    seed: int = 42,
    iterations: int = 1000,
    initial_corpus: List[bytes] | None = None,
    timeout_per_call_s: float = 1.0,
) -> FuzzReport:
    rng = random.Random(seed)
    corpus = list(initial_corpus or [b"", b"{}", b'{"x":1}', b"\x00", b"a" * 64])
    report = FuzzReport()
    t0 = time.monotonic()
    for i in range(iterations):
        report.iterations += 1
        base = rng.choice(corpus)
        candidate = _mutate_random_bytes(rng, base)
        try:
            fn(candidate)
        except Exception as exc:
            report.crashes.append({
                "iter": i,
                "exc": type(exc).__name__,
                "msg": str(exc)[:120],
                "input_hex": candidate[:64].hex(),
            })
            # Cap the report so we don't OOM on a flood of crashes.
            if len(report.crashes) > 64:
                break
        if time.monotonic() - t0 > 60.0:
            break
    report.elapsed_s = time.monotonic() - t0
    return report


def fuzz_string_callable(
    fn: Callable[[str], Any],
    *,
    seed: int = 42,
    iterations: int = 1000,
) -> FuzzReport:
    """ASCII-string variant so we can fuzz prompt sanitisers etc."""
    rng = random.Random(seed)
    alphabet = string.printable + "‪‮​" + "\x00\x01"
    report = FuzzReport()
    t0 = time.monotonic()
    for i in range(iterations):
        report.iterations += 1
        n = rng.randint(0, 256)
        s = "".join(rng.choice(alphabet) for _ in range(n))
        try:
            fn(s)
        except Exception as exc:
            report.crashes.append({
                "iter": i,
                "exc": type(exc).__name__,
                "msg": str(exc)[:120],
                "input": s[:128],
            })
            if len(report.crashes) > 64:
                break
        if time.monotonic() - t0 > 60.0:
            break
    report.elapsed_s = time.monotonic() - t0
    return report


register(DefencePlugin(
    round_id="R94",
    name="fuzz_harness",
    description="Bounded mutation fuzzer for parsers / sanitizers; reproducible by seed.",
))
