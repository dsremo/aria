"""R157 — VPC / subnet microsegmentation audit.

Threat: a flat VPC where the web tier can reach the database tier
directly, the DB can reach the internet, and dev VPCs peer to prod.
Lateral movement post-foothold is trivial.

Defence: a topology validator that takes a list of allowed (src, dst)
pairs and a list of observed flows, and reports any flow that isn't
in the allow-list.  Pairs with R131 VPC flow logs.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def diff_flows(
    allowed: Iterable[Tuple[str, str]],
    observed: Iterable[Tuple[str, str]],
) -> Tuple[bool, List[str]]:
    allow_set = {(a, b) for a, b in allowed}
    violations: List[str] = []
    for src, dst in observed:
        if (src, dst) not in allow_set:
            violations.append(f"unauthorized_flow {src}->{dst}")
    return not violations, violations


def boot_check_segmentation(
    allowed: Iterable[Tuple[str, str]],
    observed: Iterable[Tuple[str, str]],
) -> Tuple[bool, List[str]]:
    """Refuse to start if any unauthorized flow is observed in prod."""
    return diff_flows(allowed, observed)


register(DefencePlugin(
    round_id="R157",
    name="microsegmentation",
    description="VPC/subnet flow allow-list audit; refuses out-of-policy flows.",
))
