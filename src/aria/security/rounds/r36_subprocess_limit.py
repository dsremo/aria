"""R36 — Subprocess fork-bomb / spawn flood.

Threat: a handler invokes ``subprocess.run`` once per request.  If the
attacker can force concurrent invocations (or chain via a recursive
endpoint), the OS process table exhausts and ARIA itself becomes
unresponsive.

Defence: a process-wide semaphore + per-call ``ulimit``-style budget.
``spawn_subprocess(args)`` is a thin wrapper around ``subprocess.run``
that:
  * acquires a semaphore (default 8 concurrent children)
  * sets ``preexec_fn`` to drop the child to a small RLIMIT_NPROC
    + RLIMIT_AS so a misbehaving child can't fork-bomb
  * enforces a default 30-s wall-clock timeout
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import List, Optional

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r36")
_SEM = threading.Semaphore(int(os.environ.get("ARIA_SUBPROCESS_PARALLELISM", "8")))


def _drop_limits() -> None:
    """Restrict the child via POSIX rlimits.  No-op on Windows."""
    try:
        import resource as _r
        # 64 max processes per child (no fork-bomb)
        _r.setrlimit(_r.RLIMIT_NPROC, (64, 64))
        # 1 GiB virtual address space cap
        _r.setrlimit(_r.RLIMIT_AS, (1 << 30, 1 << 30))
        # 60 s CPU time
        _r.setrlimit(_r.RLIMIT_CPU, (60, 60))
    except Exception:
        pass


def spawn_subprocess(
    args: List[str],
    *,
    timeout_s: float = 30.0,
    capture_output: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run ``args`` (no shell) under the resource cap + concurrency
    semaphore.  Raises ``TimeoutExpired`` on hang."""
    if not isinstance(args, (list, tuple)) or not args:
        raise ValueError("args must be a non-empty list of strings")
    acquired = _SEM.acquire(timeout=10.0)
    if not acquired:
        raise RuntimeError("R36.subprocess_flood: parallelism budget exhausted")
    try:
        return subprocess.run(            # nosec B603 (args list, not shell)
            args,
            timeout=timeout_s,
            capture_output=capture_output,
            check=check,
            preexec_fn=_drop_limits if os.name == "posix" else None,
            shell=False,
        )
    finally:
        _SEM.release()


register(DefencePlugin(
    round_id="R36",
    name="subprocess_limit",
    description="spawn_subprocess wraps subprocess.run with semaphore + rlimits.",
))
