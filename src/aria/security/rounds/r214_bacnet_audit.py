"""R214 — BACnet building-automation auth audit.

Threat: BACnet/IP networks in HVAC, lighting, fire-suppression are
near-universally unauthenticated.  Attackers pivot through smart-
building protocols to reach corporate IT (Target 2013 HVAC pivot).
BACnet/SC (Secure Connect) was added in 2019 but adoption is sparse.

Defence: refuse BACnet/IP without BACnet/SC TLS wrapper in
production; flag write-property operations on life-safety objects
(fire panel, HVAC override).
"""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_LIFE_SAFETY_OBJECTS = {"fire_panel", "smoke_detector", "egress_door", "emergency_exit"}


def audit_bacnet_op(
    *, service: str, object_type: str, object_id: int = 0,
    via_bacnet_sc: bool = False,
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not via_bacnet_sc and os.environ.get("ARIA_ENV") == "prod":
        issues.append("bacnet.cleartext_in_prod")
    if service.lower() in ("writeproperty", "writepropertymultiple", "atomicwrite"):
        if object_type.lower() in _LIFE_SAFETY_OBJECTS:
            issues.append(f"bacnet.write_life_safety:{object_type}")
    if service.lower() in ("reinitializedevice", "deviceattribute"):
        issues.append(f"bacnet.privileged_service:{service}")
    return not issues, issues


def recommend_bacnet_sc() -> str:
    return ("Migrate to BACnet/SC: WebSocket+TLS 1.2, X.509 device "
            "certs, hub-and-spoke topology with VPLS isolation.")


register(DefencePlugin(
    round_id="R214",
    name="bacnet_audit",
    description="BACnet/IP audit; refuse cleartext + flag life-safety writes.",
))
