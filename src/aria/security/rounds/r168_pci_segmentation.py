"""R168 — PCI-DSS scope-segmentation audit.

Threat: PCI-DSS scope creep — every system that *can* touch a primary
account number (PAN) is in scope.  An unsegmented network drags the
entire fleet into PCI; auditing 20K hosts is unaffordable, and any
non-CDE host with route-of-touch fails Req 1.2.

Defence: classify a host list into CDE / Connected / Out-of-scope
based on declared tags + observed flow data; refuse a deployment
that puts a non-segmented host in CDE.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def classify_scope(
    hosts: Dict[str, Dict[str, bool]],
    flows: Iterable[Tuple[str, str]],
) -> Dict[str, str]:
    """Each host has tags ``{"handles_pan": bool, "tagged_segmented": bool}``."""
    classification: Dict[str, str] = {}
    flow_set = {(a, b) for a, b in flows}
    for host, tags in hosts.items():
        if tags.get("handles_pan"):
            classification[host] = "CDE"
        else:
            connects = any(b == host or a == host for (a, b) in flow_set
                           if hosts.get(a, {}).get("handles_pan") or hosts.get(b, {}).get("handles_pan"))
            classification[host] = "Connected" if connects else "OutOfScope"
    return classification


def audit_segmentation(
    classification: Dict[str, str],
    segmented: Dict[str, bool],
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for host, scope in classification.items():
        if scope == "CDE" and not segmented.get(host, False):
            issues.append(f"unsegmented_cde_host:{host}")
        if scope == "Connected" and not segmented.get(host, False):
            issues.append(f"unsegmented_connected_host:{host}")
    return not issues, issues


register(DefencePlugin(
    round_id="R168",
    name="pci_segmentation",
    description="PCI-DSS scope classifier + unsegmented-CDE refusal.",
))
