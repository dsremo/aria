"""R319 — Disaster-recovery RTO / RPO audit.

Threat: stated RTO (recovery time objective) + RPO (recovery point
objective) numbers without runbook + tested restore are aspirational.
Real DRs reveal that backups never actually restored, monitoring
masked corruption, runbooks were stale.

Defence: per-system DR descriptor with last-tested timestamp.
``audit_dr_state`` flags systems whose claimed RTO/RPO has not been
exercised within the operator-set freshness window.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class DRDescriptor:
    system: str
    rto_seconds: float
    rpo_seconds: float
    last_tested_at: float = 0.0
    last_test_result: str = ""        # "pass" | "fail" | ""
    runbook_url: str = ""


def audit_dr_state(
    descriptors: Dict[str, DRDescriptor],
    *,
    test_freshness_seconds: float = 90 * 86_400.0,
    now: float = 0.0,
) -> Tuple[bool, List[str]]:
    t = now or time.time()
    issues: List[str] = []
    for name, d in descriptors.items():
        if d.last_tested_at == 0.0:
            issues.append(f"dr.never_tested:{name}")
            continue
        if d.last_test_result != "pass":
            issues.append(f"dr.last_test_failed:{name}={d.last_test_result}")
        age = t - d.last_tested_at
        if age > test_freshness_seconds:
            issues.append(f"dr.stale:{name} age_days={int(age / 86_400)}")
        if not d.runbook_url:
            issues.append(f"dr.no_runbook:{name}")
        if d.rto_seconds <= 0 or d.rpo_seconds < 0:
            issues.append(f"dr.invalid_objectives:{name}")
    return not issues, issues


register(DefencePlugin(
    round_id="R319",
    name="dr_audit",
    description="Per-system DR RTO/RPO + last-tested freshness audit.",
))
