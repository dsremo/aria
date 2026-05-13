"""R120 — Pod Security Standards (PSS) compliance check.

Threat: a pod that doesn't meet K8s PSS Restricted profile is by
default a privilege escalation vector.  PSS is the upstream
replacement for the now-deprecated PodSecurityPolicy.  Banks +
financial regulators all require Restricted profile.

Defence: ``check_pss(spec)`` — extends R112 admission with the
formal PSS Restricted policy.  Returns ``{profile_passing, profile_max,
violations}`` so the operator's CI tells them exactly which policy
they're meeting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from aria.security.plugins import DefencePlugin, register


@dataclass
class PSSResult:
    passes_baseline: bool
    passes_restricted: bool
    violations: List[str]


def check_pss(pod_spec: Dict[str, Any]) -> PSSResult:
    violations: List[str] = []

    # Baseline checks (subset)
    sec_ctx = pod_spec.get("securityContext") or {}
    if pod_spec.get("hostNetwork"):
        violations.append("baseline:hostNetwork")
    if pod_spec.get("hostPID"):
        violations.append("baseline:hostPID")
    if pod_spec.get("hostIPC"):
        violations.append("baseline:hostIPC")

    for c in pod_spec.get("containers") or []:
        cs = c.get("securityContext") or {}
        if cs.get("privileged"):
            violations.append(f"baseline:container[{c.get('name','?')}].privileged")
        if cs.get("allowPrivilegeEscalation"):
            violations.append(f"baseline:container[{c.get('name','?')}].allowPrivilegeEscalation")
        # Capabilities — baseline forbids these few
        added = (cs.get("capabilities") or {}).get("add") or []
        for cap in added:
            if cap not in ("NET_BIND_SERVICE",):
                violations.append(f"baseline:cap[{cap}]_added")

    baseline_pass = not violations

    # Restricted checks (stricter)
    restricted_extra: List[str] = []
    if not sec_ctx.get("runAsNonRoot", False):
        restricted_extra.append("restricted:pod.runAsNonRoot!=true")
    if (sec_ctx.get("seccompProfile") or {}).get("type") not in ("RuntimeDefault", "Localhost"):
        restricted_extra.append("restricted:pod.seccompProfile.type")
    for c in pod_spec.get("containers") or []:
        cs = c.get("securityContext") or {}
        if cs.get("allowPrivilegeEscalation") is None or cs.get("allowPrivilegeEscalation"):
            restricted_extra.append(f"restricted:container[{c.get('name','?')}].allowPrivilegeEscalation")
        if not cs.get("readOnlyRootFilesystem"):
            restricted_extra.append(f"restricted:container[{c.get('name','?')}].readOnlyRootFilesystem")
        caps = (cs.get("capabilities") or {})
        if "ALL" not in (caps.get("drop") or []):
            restricted_extra.append(f"restricted:container[{c.get('name','?')}].caps.drop!=ALL")

    restricted_pass = baseline_pass and not restricted_extra
    violations.extend(restricted_extra)
    return PSSResult(
        passes_baseline=baseline_pass,
        passes_restricted=restricted_pass,
        violations=violations,
    )


register(DefencePlugin(
    round_id="R120",
    name="pod_security_standard",
    description="Kubernetes PSS Baseline + Restricted compliance check.",
))
