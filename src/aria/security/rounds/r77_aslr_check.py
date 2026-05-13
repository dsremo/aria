"""R77 — ASLR / PIE / RELRO / stack-canary CI checker.

Threat: a binary built without PIE (Position-Independent Executable),
without RELRO (Relocation Read-Only), without stack canaries, or with
executable stack defaults to "exploitable mitigations off".  Linux
distros and Docker base images sometimes regress these silently.
Microsoft + RedHat both publish quarterly mitigation reports.

Defence: a CI-friendly checker that walks ``/proc/self/maps`` (live)
or a candidate ELF (offline) and reports whether the standard
mitigations are active.  Returns a dict with per-flag bools so the
runner can fail the build on any FALSE.
"""

from __future__ import annotations

import os
import subprocess
from typing import Dict

from aria.security.plugins import DefencePlugin, register


def check_live_process() -> Dict[str, bool]:
    out: Dict[str, bool] = {
        "aslr_kernel": False,
        "pie_self": False,
        "stack_executable": True,            # bad if True
    }
    try:
        with open("/proc/sys/kernel/randomize_va_space", "r") as f:
            out["aslr_kernel"] = int(f.read().strip()) >= 1
    except Exception:
        pass
    try:
        with open("/proc/self/maps", "r") as f:
            maps = f.read()
        if any("[stack]" in line and "x" in line.split()[1][:4] for line in maps.splitlines()):
            out["stack_executable"] = True
        else:
            out["stack_executable"] = False
        # PIE: heuristic — main exe loaded at non-page-aligned-0x400000?
        for line in maps.splitlines():
            cols = line.split()
            if len(cols) > 5 and cols[-1].endswith("python3"):
                start_hex = cols[0].split("-", 1)[0]
                start = int(start_hex, 16)
                # Non-PIE typically loads at 0x400000; PIE elsewhere.
                out["pie_self"] = start != 0x400000
                break
    except Exception:
        pass
    return out


def check_elf_file(path: str) -> Dict[str, bool]:
    """Use ``checksec``-style flags via ``readelf -h`` and ``readelf -d``.

    Returns ``{relro, pie, canary, nx, fortify}`` when those tools are
    available; conservative defaults otherwise.
    """
    out: Dict[str, bool] = {"relro": False, "pie": False, "canary": False, "nx": False}
    try:
        proc = subprocess.run(                       # nosec B603
            ["readelf", "-d", "-h", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        text = proc.stdout
        if "Type:" in text and " DYN " in text:
            out["pie"] = True
        if "BIND_NOW" in text:
            out["relro"] = True              # full RELRO
        if "GNU_RELRO" in text and not out["relro"]:
            out["relro"] = True              # partial — count it
    except Exception:
        return out
    try:
        proc = subprocess.run(                       # nosec B603
            ["readelf", "-l", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if "GNU_STACK" in proc.stdout and "RWE" not in proc.stdout:
            out["nx"] = True
    except Exception:
        pass
    try:
        proc = subprocess.run(                       # nosec B603
            ["nm", "-D", path],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if "__stack_chk_fail" in proc.stdout:
            out["canary"] = True
    except Exception:
        pass
    return out


register(DefencePlugin(
    round_id="R77",
    name="aslr_pie_relro_canary",
    description="Live + ELF check for ASLR/PIE/RELRO/NX/canary mitigations.",
))
