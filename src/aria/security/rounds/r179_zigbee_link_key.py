"""R179 — Zigbee link-key rotation policy.

Threat: Zigbee 3.0 networks ship with the well-known global trust
center link key (5A6967426565416C6C69616E63653039) for
out-of-the-box joining.  Many vendors never rotate after install;
any captured packet during join lets an attacker decrypt subsequent
network traffic.

Defence: an audit helper that flags use of the well-known key,
checks rotation age, and recommends per-device install-codes.
"""

from __future__ import annotations

import time
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_WELL_KNOWN_TC_KEY = bytes.fromhex("5A6967426565416C6C69616E63653039")


def audit_zigbee_state(
    *,
    current_tc_key: bytes,
    last_rotation_ts: float,
    install_code_used: bool,
    now: float = 0.0,
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if current_tc_key == _WELL_KNOWN_TC_KEY:
        issues.append("zigbee.well_known_tc_link_key")
    if len(current_tc_key) != 16:
        issues.append(f"zigbee.tc_key_wrong_length:{len(current_tc_key)}")
    age = (now or time.time()) - last_rotation_ts
    if age > 86_400 * 365:
        issues.append(f"zigbee.tc_key_rotation_age_days:{int(age / 86400)}")
    if not install_code_used:
        issues.append("zigbee.no_install_code")
    return not issues, issues


def is_well_known_key(k: bytes) -> bool:
    return k == _WELL_KNOWN_TC_KEY


register(DefencePlugin(
    round_id="R179",
    name="zigbee_link_key",
    description="Zigbee TC link-key audit: refuse well-known key, enforce rotation.",
))
