"""R218 — Safety-Instrumented System (SIS) air-gap enforcement.

Threat: TRITON 2017 attacked a Schneider Triconex SIS — the last-
line-of-defence that fires emergency shutdown.  Once the attacker
reached the SIS engineering workstation, they re-flashed the safety
PLC firmware.  The original network had a "soft" gap.

Defence: an enforcement helper — refuse any outbound network
operation from a host tagged ``sis=true`` regardless of destination;
refuse SIS firmware updates without two-person rule (R47).
"""

from __future__ import annotations

import os
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def is_sis_host() -> bool:
    return os.environ.get("ARIA_SIS_HOST", "").lower() in ("1", "true", "yes")


def refuse_outbound_if_sis(destination: str) -> Tuple[bool, str]:
    if is_sis_host():
        return False, f"sis.outbound_refused dest={destination}"
    return True, "non_sis"


def gate_sis_firmware_update(*, firmware_blob_sha256: str, two_person_token: str) -> Tuple[bool, str]:
    if not is_sis_host():
        return True, "non_sis"
    if not firmware_blob_sha256:
        return False, "sis.firmware_unhashed"
    try:
        from aria.security.rounds.r47_two_person_rule import verify_two_person_token
        if not verify_two_person_token(two_person_token, scope=f"sis_fw:{firmware_blob_sha256[:16]}"):
            return False, "sis.two_person_token_invalid"
    except ImportError:
        return False, "sis.r47_missing"
    return True, f"sis.fw_authorized sha={firmware_blob_sha256[:16]}…"


register(DefencePlugin(
    round_id="R218",
    name="sis_airgap",
    description="Safety-Instrumented System: refuse outbound + two-person firmware gate.",
))
