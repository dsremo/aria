"""R292 — USB / removable-media block in classified environments.

Threat: Stuxnet, BadUSB, Manning's exfil all involved removable
media on classified networks.  IL-4 / IL-5 / TS networks ban USB
mass-storage; consumer endpoint policy in regulated industries
mirrors this.

Defence: an enforcement helper.  ``audit_usb_policy`` reads the host's
``/sys/bus/usb`` (when present) and flags mass-storage class devices
when ``ARIA_USB_POLICY=block``.  Best-effort only — the real control
is BIOS-level + endpoint EDR.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_usb_policy() -> Tuple[bool, List[str]]:
    issues: List[str] = []
    policy = os.environ.get("ARIA_USB_POLICY", "").lower()
    if policy != "block":
        return True, ["non_block_policy"]
    sysfs = Path("/sys/bus/usb/devices")
    if not sysfs.exists():
        return True, ["no_sysfs"]

    for dev in sysfs.iterdir():
        try:
            class_file = dev / "bDeviceClass"
            if not class_file.exists():
                continue
            class_hex = class_file.read_text().strip()
        except OSError:
            continue
        if class_hex == "08":
            issues.append(f"usb.mass_storage_attached:{dev.name}")

    return not issues, issues


def boot_check_usb_block() -> Tuple[bool, str]:
    if os.environ.get("ARIA_USB_POLICY") != "block":
        return True, "no_policy"
    ok, issues = audit_usb_policy()
    return ok, "ok" if ok else f"violations={len(issues)}"


register(DefencePlugin(
    round_id="R292",
    name="usb_block",
    description="USB mass-storage block check for classified deployments.",
))
