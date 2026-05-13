"""R208 — Side-channel template attack guard.

Threat: even constant-time crypto leaks via power, EM, and
microarchitectural side-channels (Mangard 2007, Kocher 1996).
Templates trained from one device generalise to siblings — Cloud
attacker with co-tenant access can recover keys.

Defence: a noise-injection wrapper that pads cryptographic operations
with randomized dummy work.  Won't make an algorithm constant-time
on its own — that's R109's job — but it widens the template-attack
distribution and forces more traces.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any, Callable

from aria.security.plugins import DefencePlugin, register


def jitter_call(fn: Callable[..., Any], *args, jitter_us: int = 100, **kwargs) -> Any:
    """Run ``fn`` with a randomised pre/post jitter in microseconds."""
    if jitter_us <= 0:
        return fn(*args, **kwargs)

    pre = secrets.randbelow(jitter_us)
    _busy(pre)
    out = fn(*args, **kwargs)
    post = secrets.randbelow(jitter_us)
    _busy(post)
    _decoy_load(secrets.randbelow(8) + 1)
    return out


def _busy(microseconds: int) -> None:
    if microseconds <= 0:
        return
    deadline = time.monotonic_ns() + microseconds * 1000
    while time.monotonic_ns() < deadline:
        os.urandom(16)


def _decoy_load(rounds: int) -> None:
    accumulator = 0
    for _ in range(rounds):
        accumulator ^= int.from_bytes(os.urandom(8), "big")


register(DefencePlugin(
    round_id="R208",
    name="template_attack_guard",
    description="Add randomised jitter + decoy work around crypto ops to widen side-channel templates.",
))
