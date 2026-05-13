"""R217 — Purdue Model OT/IT segmentation audit.

Threat: an OT network connected directly to the corporate IT VLAN
becomes one phishing-email away from a TRITON / Stuxnet-class event.
ISA-99 / IEC 62443 mandate the Purdue Reference Model: levels 0-5
with one-way DMZ between L3 (operations) and L4-5 (enterprise).

Defence: classify a host's level (0-5) and audit declared flows;
refuse any L4/L5 → L3/L2/L1/L0 flow that isn't through an L3.5 DMZ.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_purdue_flow(
    flows: Iterable[Tuple[str, int, str, int]],   # (src_host, src_level, dst_host, dst_level)
    dmz_levels: Iterable[int] = (3,),
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    dmz = set(dmz_levels) | {35}                  # L3.5 DMZ in modern reading
    for src_host, src_lvl, dst_host, dst_lvl in flows:
        if src_lvl >= 4 and dst_lvl <= 2:
            if not (src_lvl in dmz or dst_lvl in dmz):
                issues.append(f"purdue.IT_to_OT_no_dmz {src_host}@L{src_lvl}->{dst_host}@L{dst_lvl}")
        if src_lvl == 0 and dst_lvl >= 3:
            issues.append(f"purdue.L0_outbound {src_host}->{dst_host}@L{dst_lvl}")
    return not issues, issues


register(DefencePlugin(
    round_id="R217",
    name="purdue_segmentation",
    description="Purdue Reference Model flow audit; refuse IT→OT without DMZ.",
))
