"""R320 — Multi-region failover gate.

Threat: an active-passive deployment whose passive region was last
exercised six months ago will not actually fail over cleanly when
needed.  AWS US-EAST-1 outages 2017/2021/2024 reminded operators of
this every time.

Defence: per-region health + recency audit.  ``can_initiate_failover``
returns False if the target region's last successful drill is older
than the freshness window or if its data lag exceeds RPO.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class RegionState:
    region: str
    role: str                # "primary" | "secondary" | "tertiary"
    healthy: bool = True
    last_drill_at: float = 0.0
    last_drill_result: str = ""
    replication_lag_seconds: float = 0.0
    rpo_seconds: float = 60.0


def can_initiate_failover(
    target: RegionState,
    *,
    drill_freshness_seconds: float = 180 * 86_400.0,
    now: float = 0.0,
) -> Tuple[bool, str]:
    t = now or time.time()
    if target.role == "primary":
        return False, "failover.target_is_primary"
    if not target.healthy:
        return False, "failover.target_unhealthy"
    if target.last_drill_at == 0.0:
        return False, "failover.never_drilled"
    if target.last_drill_result != "pass":
        return False, f"failover.last_drill_failed:{target.last_drill_result}"
    if t - target.last_drill_at > drill_freshness_seconds:
        return False, f"failover.drill_stale age_days={int((t - target.last_drill_at) / 86_400)}"
    if target.replication_lag_seconds > target.rpo_seconds:
        return False, f"failover.rpo_breach lag={target.replication_lag_seconds:.0f}>{target.rpo_seconds:.0f}"
    return True, "ok"


def topology_audit(regions: Dict[str, RegionState]) -> Tuple[bool, list]:
    issues = []
    primaries = [r for r in regions.values() if r.role == "primary"]
    if len(primaries) != 1:
        issues.append(f"topology.primary_count:{len(primaries)}")
    if not any(r.role in ("secondary", "tertiary") for r in regions.values()):
        issues.append("topology.no_secondary")
    return not issues, issues


register(DefencePlugin(
    round_id="R320",
    name="multi_region_failover",
    description="Multi-region failover gate with drill-freshness + RPO check.",
))
