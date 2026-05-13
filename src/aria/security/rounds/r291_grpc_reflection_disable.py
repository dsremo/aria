"""R291 — gRPC reflection disable in production.

Threat: gRPC reflection (reflection.v1alpha.ServerReflection) is the
default convenience that lets clients discover all service methods.
In production it leaks the API surface to anyone who can reach the
gRPC port — feeding fuzzers and exploit kits.

Defence: ``boot_check_reflection_disabled`` reads ARIA_GRPC_REFLECTION
and refuses launch in prod if it's enabled; ``audit_server_descriptor``
walks declared services and flags reflection registrations.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_REFLECTION_SERVICES = {
    "grpc.reflection.v1alpha.ServerReflection",
    "grpc.reflection.v1.ServerReflection",
}


def boot_check_reflection_disabled() -> Tuple[bool, str]:
    if os.environ.get("ARIA_ENV") != "prod":
        return True, "non_prod"
    if os.environ.get("ARIA_GRPC_REFLECTION", "false").lower() in ("1", "true", "yes"):
        return False, "grpc.reflection_enabled_in_prod"
    return True, "ok"


def audit_server_descriptor(declared_services: Iterable[str]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    is_prod = os.environ.get("ARIA_ENV") == "prod"
    services = list(declared_services)
    for s in services:
        if s in _REFLECTION_SERVICES and is_prod:
            issues.append(f"grpc.reflection_in_prod:{s}")
    return not issues, issues


register(DefencePlugin(
    round_id="R291",
    name="grpc_reflection_disable",
    description="Refuse gRPC reflection in prod; audit declared services.",
))
