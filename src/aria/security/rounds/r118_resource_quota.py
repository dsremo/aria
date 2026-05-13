"""R118 — Per-process resource quota enforcement (cgroups + rlimits).

Threat: a memory-bomb or fork-bomb inside the worker drags the whole
host down.  K8s mitigates via PodSpec ``resources.limits``; on bare
metal we use ``setrlimit``.  Banks ship with both belts buckled.

Defence: ``apply_quotas()`` calls ``setrlimit`` with operator-supplied
caps for AS (virtual mem), NPROC, NOFILE, CPU.  Refuses to *raise*
limits (only lower).  Boot check refuses production start when limits
are infinite.
"""

from __future__ import annotations

import os
import resource
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_LIMITS = {
    resource.RLIMIT_AS: (4 * 1024 * 1024 * 1024, 4 * 1024 * 1024 * 1024),  # 4 GiB
    resource.RLIMIT_NPROC: (256, 256),
    resource.RLIMIT_NOFILE: (4096, 4096),
    resource.RLIMIT_CPU: (3600, 3600),                       # 1 h CPU per worker
    resource.RLIMIT_FSIZE: (1 * 1024 * 1024 * 1024, 1 * 1024 * 1024 * 1024),
}


def apply_quotas(*, overrides: Dict[int, Tuple[int, int]] | None = None) -> Dict[str, str]:
    """Apply rlimits.  Returns ``{rlimit_name: outcome}`` for the audit log."""
    out: Dict[str, str] = {}
    target = dict(_DEFAULT_LIMITS)
    if overrides:
        target.update(overrides)
    for k, (soft, hard) in target.items():
        try:
            cur_soft, cur_hard = resource.getrlimit(k)
            # Refuse to RAISE — only lower hard caps.
            if cur_hard != resource.RLIM_INFINITY and hard > cur_hard:
                out[str(k)] = f"refused_raise cur={cur_hard} req={hard}"
                continue
            resource.setrlimit(k, (min(soft, cur_soft if cur_soft != resource.RLIM_INFINITY else soft),
                                   min(hard, cur_hard if cur_hard != resource.RLIM_INFINITY else hard)))
            out[str(k)] = "applied"
        except (ValueError, OSError) as exc:
            out[str(k)] = f"failed:{exc}"
    return out


def boot_check() -> Tuple[bool, list]:
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return True, []
    issues: list = []
    for k in (resource.RLIMIT_AS, resource.RLIMIT_NPROC, resource.RLIMIT_NOFILE):
        soft, hard = resource.getrlimit(k)
        if soft == resource.RLIM_INFINITY or hard == resource.RLIM_INFINITY:
            issues.append(f"rlimit_{k}_infinite")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R118",
    name="resource_quota",
    description="setrlimit caps + boot-check refusing infinite rlimits in prod.",
))
