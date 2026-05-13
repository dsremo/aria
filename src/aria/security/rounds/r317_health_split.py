"""R317 — Liveness vs readiness probe split.

Threat: a single ``/healthz`` endpoint that depends on every
downstream causes Kubernetes to kill+restart pods during a transient
outage of any single dependency — converting brownout into outage.

Defence: split into ``liveness`` (process can serve requests if
reachable) and ``readiness`` (process is ready to accept new
traffic, dependencies healthy).  Liveness must not depend on
external services.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Probe:
    name: str
    fn: Callable[[], Tuple[bool, str]]


_LIVENESS: List[_Probe] = []
_READINESS: List[_Probe] = []
_LOCK = threading.Lock()


def register_liveness(name: str, fn: Callable[[], Tuple[bool, str]]) -> None:
    with _LOCK:
        _LIVENESS.append(_Probe(name, fn))


def register_readiness(name: str, fn: Callable[[], Tuple[bool, str]]) -> None:
    with _LOCK:
        _READINESS.append(_Probe(name, fn))


def evaluate_liveness() -> Tuple[bool, List[str]]:
    return _evaluate(_LIVENESS)


def evaluate_readiness() -> Tuple[bool, List[str]]:
    return _evaluate(_READINESS)


def _evaluate(probes: List[_Probe]) -> Tuple[bool, List[str]]:
    with _LOCK:
        ps = list(probes)
    issues: List[str] = []
    for p in ps:
        try:
            ok, why = p.fn()
        except Exception as exc:
            ok, why = False, f"exc:{type(exc).__name__}"
        if not ok:
            issues.append(f"{p.name}:{why}")
    return not issues, issues


def reset_for_tests() -> None:
    with _LOCK:
        _LIVENESS.clear()
        _READINESS.clear()


register(DefencePlugin(
    round_id="R317",
    name="health_split",
    description="Liveness vs readiness probe split; liveness must not depend on externals.",
))
