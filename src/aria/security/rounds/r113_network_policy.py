"""R113 — Kubernetes NetworkPolicy generator.

Threat: a default-permissive cluster lets every pod reach every other
pod (and the kube-apiserver, the cloud metadata, the SQL DB).  The
2018 Tesla Kubernetes-mining incident relied on this exact gap.  Banks
+ defence deployers run deny-by-default NetworkPolicy.

Defence: a small generator that emits a deny-by-default + per-component
allow-list NetworkPolicy YAML for ARIA's deploy: screener, advisor,
the bus, the audit forwarder.  Operators apply the YAML directly.
"""

from __future__ import annotations

from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


_DEFAULT_DENY = """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: aria-default-deny
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
"""

_TEMPLATE_INGRESS = """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: aria-allow-{component}-ingress
spec:
  podSelector:
    matchLabels: {{ app: {component} }}
  policyTypes: [Ingress]
  ingress:
{ingress_rules}
"""

_TEMPLATE_EGRESS = """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: aria-allow-{component}-egress
spec:
  podSelector:
    matchLabels: {{ app: {component} }}
  policyTypes: [Egress]
  egress:
{egress_rules}
"""


def generate_default_deny() -> str:
    return _DEFAULT_DENY


def generate_component_policy(
    component: str,
    *,
    ingress_from_components: List[str] | None = None,
    ingress_ports: List[int] | None = None,
    egress_to_dns: bool = True,
    egress_to_components: List[str] | None = None,
    egress_ports: List[int] | None = None,
) -> Dict[str, str]:
    """Emit ingress + egress policy YAMLs for ``component``."""
    in_rules = []
    for f in ingress_from_components or []:
        in_rules.append(f"  - from:\n    - podSelector: {{ matchLabels: {{ app: {f} }} }}")
    if ingress_ports:
        ports = "\n      ".join(f"- {{ port: {p}, protocol: TCP }}" for p in ingress_ports)
        in_rules.append(f"    ports:\n      {ports}")

    eg_rules = []
    if egress_to_dns:
        eg_rules.append(
            "  - to:\n    - namespaceSelector: {{}}\n      podSelector: "
            "{ matchLabels: { k8s-app: kube-dns } }\n    "
            "ports:\n    - { port: 53, protocol: UDP }"
        )
    for t in egress_to_components or []:
        eg_rules.append(f"  - to:\n    - podSelector: {{ matchLabels: {{ app: {t} }} }}")
    if egress_ports:
        ports = "\n      ".join(f"- {{ port: {p}, protocol: TCP }}" for p in egress_ports)
        eg_rules.append(f"    ports:\n      {ports}")

    return {
        "ingress.yaml": _TEMPLATE_INGRESS.format(
            component=component, ingress_rules="\n".join(in_rules) or "  []",
        ),
        "egress.yaml": _TEMPLATE_EGRESS.format(
            component=component, egress_rules="\n".join(eg_rules) or "  []",
        ),
    }


register(DefencePlugin(
    round_id="R113",
    name="network_policy",
    description="Deny-by-default + per-component NetworkPolicy YAML generator.",
))
