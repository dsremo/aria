"""R219 — Industrial protocol whitelist enforcement.

Threat: an OT segment that allows arbitrary L4 protocols becomes a
pivot lane.  Any rogue tool that speaks SSH, RDP, SMB, HTTPS finds
its way in once one host is owned.  The Purdue model only works if
the firewalls between zones strictly whitelist OT protocols.

Defence: a per-zone protocol whitelist + ``audit_zone_traffic`` that
drops any flow whose L4-port + protocol pair isn't on the explicit
allow list.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_WHITELIST: Dict[str, Set[Tuple[int, str]]] = {
    "L2_basic_control":  {(502, "tcp"), (44818, "tcp"), (2222, "udp"),    # Modbus, EthernetIP
                          (4840, "tcp")},                                  # OPC-UA
    "L1_local_io":       {(502, "tcp"), (47808, "udp")},                   # BACnet
    "L3_operations":     {(443, "tcp"), (4840, "tcp"), (502, "tcp")},
    "L3_5_dmz":          {(443, "tcp"), (514, "udp")},                     # syslog
}


def audit_zone_traffic(
    zone: str,
    flows: Iterable[Tuple[int, str, str, str]],    # (port, proto, src, dst)
    *,
    custom_whitelist: Dict[str, Set[Tuple[int, str]]] = None,
) -> Tuple[bool, List[str]]:
    wl = (custom_whitelist or _DEFAULT_WHITELIST).get(zone, set())
    if not wl:
        return False, [f"zone.unknown:{zone}"]
    issues: List[str] = []
    for port, proto, src, dst in flows:
        if (int(port), proto.lower()) not in wl:
            issues.append(f"zone={zone} blocked {src}->{dst}:{port}/{proto}")
    return not issues, issues


register(DefencePlugin(
    round_id="R219",
    name="protocol_whitelist",
    description="Per-zone OT protocol/port whitelist enforcement.",
))
