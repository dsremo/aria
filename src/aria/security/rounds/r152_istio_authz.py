"""R152 — Istio AuthorizationPolicy generator (zero-trust mesh).

Threat: a default-permissive service mesh treats every workload as
trusted once it gets a sidecar.  Compromise one pod and lateral move
to every service.  Capital One 2019 + Tesla 2018 both hinged on
default-allow inside the perimeter.

Defence: emit a default-deny ``AuthorizationPolicy`` for the namespace
and per-service ALLOW rules tied to SPIFFE identities.  Operator
applies the YAML to the cluster; rejects requests that don't carry an
SVID matching the named principal.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def deny_all_policy(namespace: str) -> str:
    return (
        "apiVersion: security.istio.io/v1\n"
        "kind: AuthorizationPolicy\n"
        "metadata:\n"
        f"  name: deny-all-{namespace}\n"
        f"  namespace: {namespace}\n"
        "spec: {}\n"          # empty spec = deny all
    )


def allow_from_principals(
    name: str, namespace: str, principals: Iterable[str], target_app: str,
) -> str:
    rules = "".join(
        f"  - from:\n    - source:\n        principals: [\"{p}\"]\n"
        for p in principals
    )
    return (
        "apiVersion: security.istio.io/v1\n"
        "kind: AuthorizationPolicy\n"
        f"metadata:\n  name: {name}\n  namespace: {namespace}\n"
        "spec:\n"
        f"  selector:\n    matchLabels:\n      app: {target_app}\n"
        "  action: ALLOW\n"
        "  rules:\n"
        + rules
    )


def lint_principals(principals: Iterable[str]) -> Tuple[bool, List[str]]:
    bad: List[str] = []
    for p in principals:
        if p == "*" or p.endswith("/*") or "cluster.local/ns/*/" in p:
            bad.append(f"wildcard_principal:{p}")
    return not bad, bad


register(DefencePlugin(
    round_id="R152",
    name="istio_authz",
    description="Default-deny + per-principal Istio AuthorizationPolicy generator.",
))
