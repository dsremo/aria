"""R35 — Hash-flooding (algorithmic complexity attack on dict).

Threat: an attacker crafts a JSON body with thousands of keys that
all hash to the same bucket in Python's dict — every insert becomes
O(n) and the parser locks for minutes.  Original CCC 2011 disclosure;
PEP-456 (SipHash) hardened it; PYTHONHASHSEED=0 in CI / Docker builds
re-exposes the surface.

Defence: refuse if ``PYTHONHASHSEED`` is set to a fixed value at boot
unless the operator explicitly opts in.  Plus a JSON-key-count cap on
inbound bodies — 10 000 keys is well above legitimate API use.
"""

from __future__ import annotations

import json
import os
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_MAX_KEYS = 10_000


def _check_hash_seed() -> Tuple[bool, str]:
    seed = os.environ.get("PYTHONHASHSEED", "random")
    if seed.isdigit():
        if os.environ.get("ARIA_ALLOW_FIXED_HASH_SEED", "").lower() in {"1", "true", "yes"}:
            return True, ""
        return False, f"PYTHONHASHSEED={seed!r} is fixed; refuse to start"
    return True, ""


def boot_check_hash_seed() -> Tuple[bool, str]:
    return _check_hash_seed()


def _count_keys(obj, depth: int = 0) -> int:
    if depth > 32:
        return 0
    n = 0
    if isinstance(obj, dict):
        n += len(obj)
        for v in obj.values():
            n += _count_keys(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            n += _count_keys(v, depth + 1)
    return n


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or len(payload) > 4 * 1024 * 1024:
        return 0.0, ""
    try:
        obj = json.loads(payload)
    except Exception:
        return 0.0, ""
    keys = _count_keys(obj)
    if keys > _DEFAULT_MAX_KEYS:
        return 0.9, f"r35.hash_flood keys={keys}"
    if keys > _DEFAULT_MAX_KEYS // 2:
        return 0.5, f"r35.hash_flood keys={keys}"
    return 0.0, ""


register(DefencePlugin(
    round_id="R35",
    name="hash_flooding",
    description="Refuse JSON bodies > 10 000 keys; refuse fixed PYTHONHASHSEED.",
    on_score=_on_score,
))
