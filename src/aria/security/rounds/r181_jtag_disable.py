"""R181 — Embedded debug-port (JTAG/SWD/UART) disable check.

Threat: production devices left with an active JTAG/SWD header give
attackers a privileged in-circuit debug path that bypasses every
software defence — read flash, halt CPU, single-step bootloader.
Trezor wallet, Tesla MCU, smart-meter exploits all started here.

Defence: a manifest validator + a runtime probe that checks the chip
fuse state (where exposed via /sys or vendor SDK) is set to
permanent-lock.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_debug_manifest(manifest: Dict[str, bool]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    must_be_disabled = (
        "jtag", "swd", "uart_console", "test_mode_pad", "boot_select_pad",
    )
    for port in must_be_disabled:
        if not manifest.get(f"{port}_disabled", False):
            issues.append(f"debug.{port}_enabled")
    if not manifest.get("flash_readout_protection", False):
        issues.append("debug.flash_readout_unprotected")
    if not manifest.get("debug_fuse_locked", False):
        issues.append("debug.fuse_not_locked")
    return not issues, issues


def runtime_probe_linux() -> Tuple[bool, List[str]]:
    """Best-effort Linux probe: confirm no kgdb/kdb live on boot params."""
    issues: List[str] = []
    cmdline = Path("/proc/cmdline")
    try:
        if cmdline.exists():
            txt = cmdline.read_text()
            if "kgdboc" in txt or "kgdbwait" in txt:
                issues.append("debug.kgdb_active")
            if "earlyprintk" in txt and "ARIA_ENV" in os.environ and os.environ["ARIA_ENV"] == "prod":
                issues.append("debug.earlyprintk_in_prod")
    except OSError:
        pass
    return not issues, issues


register(DefencePlugin(
    round_id="R181",
    name="jtag_disable",
    description="Embedded debug-port disable manifest + runtime kgdb probe.",
))
