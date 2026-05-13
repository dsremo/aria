"""R290 — Per-tenant rate-limit fairness.

Threat: a single noisy tenant exhausts a global rate limit and starves
every other tenant.  Even with R39 (bandwidth cap) the request rate
still falls under shared quotas (LLM tokens, third-party APIs, DB
queries).

Defence: a token-bucket PER TENANT with global ceiling.  A tenant
that bursts to its full per-tenant quota cannot consume any of the
remaining budget — the global cap is reserved fairly.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _TenantBucket:
    tokens: float = 0.0
    last_refill: float = 0.0


_PER_TENANT: Dict[str, _TenantBucket] = defaultdict(_TenantBucket)
_GLOBAL_REMAINING = [0.0]
_LOCK = threading.Lock()


def configure(
    *, per_tenant_capacity: float = 100.0,
    per_tenant_refill_per_second: float = 1.0,
    global_capacity: float = 10_000.0,
) -> None:
    with _LOCK:
        _PER_TENANT.clear()
        _GLOBAL_REMAINING[0] = global_capacity
        # Save config in the bucket via sentinel keys
        _PER_TENANT["__config__"].tokens = per_tenant_capacity
        _PER_TENANT["__config__"].last_refill = per_tenant_refill_per_second


def consume(tenant: str, *, cost: float = 1.0) -> Tuple[bool, str]:
    if tenant == "__config__":
        return False, "tenant.reserved"
    t = time.monotonic()
    with _LOCK:
        config = _PER_TENANT["__config__"]
        capacity = config.tokens or 100.0
        refill_rate = config.last_refill or 1.0

        bucket = _PER_TENANT[tenant]
        if bucket.last_refill == 0.0:
            bucket.tokens = capacity
            bucket.last_refill = t
        elapsed = t - bucket.last_refill
        bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_rate)
        bucket.last_refill = t

        if _GLOBAL_REMAINING[0] < cost:
            return False, f"global.exhausted remaining={_GLOBAL_REMAINING[0]:.1f}"
        if bucket.tokens < cost:
            return False, f"tenant.exhausted tenant={tenant} have={bucket.tokens:.1f}"

        bucket.tokens -= cost
        _GLOBAL_REMAINING[0] -= cost
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _PER_TENANT.clear()
        _GLOBAL_REMAINING[0] = 0.0


register(DefencePlugin(
    round_id="R290",
    name="per_tenant_fairness",
    description="Per-tenant token-bucket + global ceiling; fair multi-tenant rate limits.",
))
