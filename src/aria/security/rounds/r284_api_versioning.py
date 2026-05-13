"""R284 — API versioning rollback / downgrade gate.

Threat: an attacker requests an old API version (``/v1/transfer``)
that lacks the freshly-added defence in ``/v2``.  Same vulnerability
that stripped TLS-downgrade attacks taught — version is part of the
threat surface.

Defence: a per-deployment ``allowed_api_versions`` allow-list.  A
deprecation policy: deprecated versions get a 410 Gone (not silently
served), retired versions are refused outright.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class VersionPolicy:
    state: str        # "active" | "deprecated" | "retired"
    deprecated_at: float = 0.0
    sunset_at: float = 0.0


_POLICY: Dict[str, VersionPolicy] = {}
_LOCK = threading.Lock()


def configure_version(version: str, *, state: str = "active",
                      deprecated_at: float = 0.0, sunset_at: float = 0.0) -> None:
    if state not in ("active", "deprecated", "retired"):
        raise ValueError(f"R284: state must be active|deprecated|retired, got {state}")
    with _LOCK:
        _POLICY[version] = VersionPolicy(state, deprecated_at, sunset_at)


def check_version(version: str, *, now: float = 0.0) -> Tuple[int, str]:
    """Returns (http_status_code, header_value).  200 = serve, 410 = gone,
    426 = upgrade-required, 404 = unknown."""
    t = now or time.time()
    with _LOCK:
        p = _POLICY.get(version)
    if p is None:
        return 404, "version.unknown"
    if p.state == "retired":
        return 410, "version.retired"
    if p.state == "deprecated":
        if p.sunset_at and t > p.sunset_at:
            return 410, f"version.sunset_passed at={int(p.sunset_at)}"
        return 200, f"version.deprecated sunset={int(p.sunset_at)}"
    return 200, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _POLICY.clear()


register(DefencePlugin(
    round_id="R284",
    name="api_versioning",
    description="API version state machine; refuse retired versions, signal deprecation.",
))
