"""R112 — Kubernetes admission policy.

Threat: a hostile or misconfigured pod manifest reaches the cluster:
``hostNetwork: true``, ``privileged: true``, ``runAsUser: 0``, mounted
``hostPath: /``.  Banks + classified deployers gate every pod via OPA
Gatekeeper / Kyverno admission webhooks.

Defence: a Python-side validator that an admission webhook handler can
delegate to.  Returns ``{allowed, reasons}`` for a parsed pod spec.
Operators run this either as a sidecar webhook or as a CI gate on
helm chart rendering.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def review_pod_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return ``(allowed, reasons)``.  Conservative — refuses anything
    that doesn't pass the explicit allow-list."""
    reasons: List[str] = []
    if not isinstance(spec, dict):
        return False, ["spec_not_a_dict"]
    if spec.get("hostNetwork"):
        reasons.append("hostNetwork=true")
    if spec.get("hostPID"):
        reasons.append("hostPID=true")
    if spec.get("hostIPC"):
        reasons.append("hostIPC=true")
    sec_ctx = spec.get("securityContext") or {}
    if sec_ctx.get("runAsUser") == 0:
        reasons.append("runAsUser=0")
    if sec_ctx.get("runAsNonRoot") is False:
        reasons.append("runAsNonRoot=false")
    if sec_ctx.get("privileged"):
        reasons.append("privileged=true")
    if sec_ctx.get("allowPrivilegeEscalation"):
        reasons.append("allowPrivilegeEscalation=true")

    for v in spec.get("volumes") or []:
        if isinstance(v, dict) and "hostPath" in v:
            path = (v.get("hostPath") or {}).get("path", "")
            if path in ("/", "/etc", "/var", "/proc", "/sys"):
                reasons.append(f"hostPath={path}")

    for c in spec.get("containers") or []:
        cs = c.get("securityContext") or {}
        if cs.get("privileged"):
            reasons.append(f"container[{c.get('name','?')}].privileged")
        if cs.get("allowPrivilegeEscalation"):
            reasons.append(f"container[{c.get('name','?')}].allowPrivilegeEscalation")
        if not cs.get("readOnlyRootFilesystem"):
            reasons.append(f"container[{c.get('name','?')}].readOnlyRootFilesystem!=true")
        if cs.get("capabilities") and (cs["capabilities"].get("add") or []):
            reasons.append(f"container[{c.get('name','?')}].caps.add={cs['capabilities']['add']}")
        # Image must not be `:latest`
        img = c.get("image", "")
        if img.endswith(":latest") or ":" not in img.rsplit("/", 1)[-1]:
            reasons.append(f"container[{c.get('name','?')}].image_unpinned:{img}")

    return len(reasons) == 0, reasons


register(DefencePlugin(
    round_id="R112",
    name="k8s_admission",
    description="Pod-spec validator for OPA / Kyverno admission webhooks.",
))
