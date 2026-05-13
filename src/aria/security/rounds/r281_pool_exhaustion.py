"""R281 — DB connection pool exhaustion guard.

Threat: a single misbehaving caller can hold every connection in the
pool and starve all other tenants.  Goes beyond rate-limiting because
the pool is a shared resource — DoS without high request rate.

Defence: a per-principal connection counter + soft cap.  ``acquire``
returns False when the principal's share would exceed ``max_per_principal``;
the request gracefully degrades (queue / 429) instead of starving the
pool.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _PoolState:
    in_use: int = 0
    last_acquired: float = 0.0


_POOL: Dict[str, _PoolState] = defaultdict(_PoolState)
_LOCK = threading.Lock()
_DEFAULT_MAX_PER_PRINCIPAL = 10
_DEFAULT_TOTAL_POOL = 100


def acquire(
    principal: str,
    *,
    max_per_principal: int = _DEFAULT_MAX_PER_PRINCIPAL,
    total_pool_size: int = _DEFAULT_TOTAL_POOL,
) -> Tuple[bool, str]:
    with _LOCK:
        total_in_use = sum(s.in_use for s in _POOL.values())
        if total_in_use >= total_pool_size:
            return False, f"pool.total_full {total_in_use}/{total_pool_size}"
        principal_state = _POOL[principal]
        if principal_state.in_use >= max_per_principal:
            return False, f"pool.principal_full principal={principal} {principal_state.in_use}/{max_per_principal}"
        principal_state.in_use += 1
        principal_state.last_acquired = time.time()
    return True, "ok"


def release(principal: str) -> None:
    with _LOCK:
        s = _POOL.get(principal)
        if s and s.in_use > 0:
            s.in_use -= 1


def snapshot() -> Dict[str, int]:
    with _LOCK:
        return {k: s.in_use for k, s in _POOL.items()}


def reset_for_tests() -> None:
    with _LOCK:
        _POOL.clear()


register(DefencePlugin(
    round_id="R281",
    name="pool_exhaustion",
    description="DB connection pool fairness guard: per-principal cap + total ceiling.",
))
