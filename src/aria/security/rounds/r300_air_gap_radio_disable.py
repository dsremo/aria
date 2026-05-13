"""R300 — Air-gap radio-egress disable.

Threat: even an air-gapped host can leak via cellular modem, Wi-Fi,
Bluetooth, or NFC radios — Stuxnet's exfil hop, AirHopper (2014), or
modern smart-NIC backdoors.  Classified facilities physically remove
or RF-shield radios.

Defence: an enforcement helper that reads the host's RF-kill state
and refuses to start in air-gap mode unless every radio is hardware-
killed.  Soft-fails on non-Linux.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def read_rfkill_state() -> List[Tuple[str, str, str]]:
    """Returns list of (name, type, state) tuples from /sys/class/rfkill/."""
    out: List[Tuple[str, str, str]] = []
    base = Path("/sys/class/rfkill")
    if not base.exists():
        return out
    for entry in base.iterdir():
        try:
            name = (entry / "name").read_text().strip()
            kind = (entry / "type").read_text().strip()
            soft = (entry / "soft").read_text().strip()
            hard = (entry / "hard").read_text().strip()
        except OSError:
            continue
        state = "blocked_hard" if hard == "1" else (
            "blocked_soft" if soft == "1" else "unblocked"
        )
        out.append((name, kind, state))
    return out


def boot_check_air_gap() -> Tuple[bool, List[str]]:
    if os.environ.get("ARIA_AIR_GAP", "").lower() not in ("1", "true", "yes"):
        return True, ["non_air_gap"]
    states = read_rfkill_state()
    issues: List[str] = []
    if not states:
        issues.append("airgap.rfkill_unavailable")
    for name, kind, state in states:
        if state != "blocked_hard":
            issues.append(f"airgap.radio_active name={name} type={kind} state={state}")
    return not issues, issues


register(DefencePlugin(
    round_id="R300",
    name="air_gap_radio_disable",
    description="Air-gap mode: refuse start unless every radio is hardware-killed.",
))
