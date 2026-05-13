"""R312 — Chaos-injection harness.

Threat: production code paths only exercised under failure are tested
exclusively *during* failure.  Outages reveal latent bugs that chaos
testing would have caught — the Netflix Chaos Monkey thesis.

Defence: a controlled fault-injection harness.  ``maybe_inject``
returns whether to inject a fault for the current call based on a
configured probability + scope label, audited so post-incident
reviews can correlate.
"""

from __future__ import annotations

import os
import random
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _ChaosConfig:
    enabled: bool = False
    probability: float = 0.0
    scopes: Dict[str, float] = None


_CONFIG = _ChaosConfig(scopes={})
_INJECTIONS: Dict[str, int] = defaultdict(int)
_LOCK = threading.Lock()


def configure(*, enabled: bool = False, probability: float = 0.0,
              scope_overrides: Dict[str, float] = None) -> None:
    if os.environ.get("ARIA_ENV") == "prod" and not os.environ.get("ARIA_CHAOS_ALLOWED_PROD"):
        return
    with _LOCK:
        _CONFIG.enabled = enabled
        _CONFIG.probability = max(0.0, min(1.0, probability))
        _CONFIG.scopes = dict(scope_overrides or {})
        _INJECTIONS.clear()


def maybe_inject(scope: str = "default") -> Tuple[bool, str]:
    with _LOCK:
        if not _CONFIG.enabled:
            return False, "disabled"
        prob = _CONFIG.scopes.get(scope, _CONFIG.probability)
    if prob <= 0.0:
        return False, "no_prob"
    if random.random() >= prob:
        return False, "not_selected"
    with _LOCK:
        _INJECTIONS[scope] += 1
        count = _INJECTIONS[scope]
    return True, f"injected scope={scope} count={count}"


def stats() -> Dict[str, int]:
    with _LOCK:
        return dict(_INJECTIONS)


def reset_for_tests() -> None:
    with _LOCK:
        _CONFIG.enabled = False
        _CONFIG.probability = 0.0
        _CONFIG.scopes = {}
        _INJECTIONS.clear()


register(DefencePlugin(
    round_id="R312",
    name="chaos_injection",
    description="Controlled fault-injection harness with per-scope probability + audit.",
))
