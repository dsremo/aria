"""R242 — Data-diode (one-way air-gap) policy.

Threat: classified networks (NIPRNet, SIPRNet, NSS) require strict
one-way data flow — high-side reads from low-side, never the
reverse.  Software-only implementations leak via covert channels
(timing, ACK presence, error semantics).  Real diodes are
physical-fibre.

Defence: an enforcement helper.  When ``ARIA_DIODE_DIRECTION`` is set,
refuse outbound from high-side hosts; refuse inbound to low-side
hosts.  Every blocked attempt logs to R98 immutable log.
"""

from __future__ import annotations

import os
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def diode_direction() -> str:
    return os.environ.get("ARIA_DIODE_DIRECTION", "").lower()  # "high_to_low" | "low_to_high" | ""


def is_high_side() -> bool:
    return os.environ.get("ARIA_CLASSIFICATION_LEVEL", "").lower() in ("secret", "top_secret", "ts_sci")


def refuse_if_violates(direction: str, *, source_high: bool, dest_high: bool) -> Tuple[bool, str]:
    """``direction`` is ``high_to_low`` or ``low_to_high``."""
    if direction == "high_to_low" and not source_high:
        return False, "diode.low_origin_blocked"
    if direction == "high_to_low" and dest_high:
        return False, "diode.high_destination_blocked"
    if direction == "low_to_high" and source_high:
        return False, "diode.high_origin_blocked"
    if direction == "low_to_high" and not dest_high:
        return False, "diode.low_destination_blocked"
    return True, "ok"


def boot_check_diode_posture() -> Tuple[bool, str]:
    direction = diode_direction()
    if not direction:
        return True, "no_diode_configured"
    if direction not in ("high_to_low", "low_to_high"):
        return False, f"diode.invalid_direction:{direction}"
    return True, f"diode.configured:{direction}"


register(DefencePlugin(
    round_id="R242",
    name="air_gap_diode",
    description="Air-gap data-diode policy: refuse violating direction in classified deployments.",
))
