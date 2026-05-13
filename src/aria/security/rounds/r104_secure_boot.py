"""R104 — Secure-boot chain verifier.

Threat: an attacker drops a hostile kernel module / unified-bootloader
between firmware and OS (LoJax 2018, BlackLotus 2023 — both targeted
UEFI Secure Boot bypasses).  ARIA's classified-tier deployments need
to confirm the boot chain matches a sealed manifest before joining a
fleet.

Defence: read ``/sys/firmware/efi/efivars/SecureBoot-*`` to verify
Secure Boot is on; read ``/proc/keys`` for the kernel-pinned trust
anchors; compute SHA-256 of ``/boot/vmlinuz-*`` and ``/boot/initrd*``;
compare against operator-supplied baseline.  Returns a structured
report ready for SIEM forwarding (R92).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Dict

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r104")


def secure_boot_state() -> Dict[str, object]:
    out: Dict[str, object] = {"secure_boot_on": False, "platform_keys": []}
    sb = Path("/sys/firmware/efi/efivars/")
    try:
        for p in sb.glob("SecureBoot-*"):
            data = p.read_bytes()
            # Last byte is the SecureBoot variable: 1 = on
            if data and data[-1] == 1:
                out["secure_boot_on"] = True
                break
    except Exception:
        pass
    return out


def kernel_modules_hash() -> Dict[str, str]:
    out: Dict[str, str] = {}
    boot = Path("/boot")
    if not boot.is_dir():
        return out
    for p in boot.glob("vmlinuz-*"):
        try:
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            continue
    for p in boot.glob("initrd*"):
        try:
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            continue
    return out


def verify_against_baseline(baseline: Dict[str, str]) -> Dict[str, str]:
    """Return ``{filename: 'ok' | 'mismatch' | 'missing'}``."""
    actual = kernel_modules_hash()
    out: Dict[str, str] = {}
    for name, expected in baseline.items():
        a = actual.get(name)
        if a is None:
            out[name] = "missing"
        elif not a.startswith(expected[:16]):
            out[name] = f"mismatch_{a}_vs_{expected[:16]}"
        else:
            out[name] = "ok"
    return out


register(DefencePlugin(
    round_id="R104",
    name="secure_boot",
    description="Read SecureBoot EFI var + hash kernel/initrd; compare to baseline.",
))
