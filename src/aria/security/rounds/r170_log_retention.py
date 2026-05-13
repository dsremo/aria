"""R170 — Audit-log retention policy enforcement.

Threat: audit logs deleted before regulatory minimums (PCI: 1 year,
HIPAA: 6 years, SOC 2: contract-defined) destroy forensic evidence
and trigger Notification.  Conversely, logs kept *too* long under
GDPR violate the storage-limitation principle.

Defence: a policy struct + ``enforce_retention`` that walks a
log-store iterator and emits keep / archive / delete decisions per
artefact class.  Pairs with R98 immutable log seal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class RetentionPolicy:
    rules: Dict[str, int] = field(default_factory=lambda: {
        "auth":           86_400 * 365 * 1,    # PCI 10.7
        "audit":          86_400 * 365 * 6,    # HIPAA / SOC2
        "access":         86_400 * 365 * 1,
        "system":         86_400 * 90,
        "debug":          86_400 * 30,
    })
    grace_seconds: int = 86_400


def enforce_retention(
    artefacts: Iterable[Tuple[str, str, float]],   # (id, class, ts)
    policy: RetentionPolicy,
    *,
    now: float = 0.0,
) -> Tuple[List[str], List[str]]:
    keep: List[str] = []
    delete: List[str] = []
    t = now or time.time()
    for aid, kind, ts in artefacts:
        max_age = policy.rules.get(kind, 86_400 * 30)
        age = t - ts
        if age <= max_age + policy.grace_seconds:
            keep.append(aid)
        else:
            delete.append(aid)
    return keep, delete


register(DefencePlugin(
    round_id="R170",
    name="log_retention",
    description="Retention policy enforcement: PCI/HIPAA/SOC2 minimums + GDPR ceiling.",
))
