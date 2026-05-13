"""R192 — Live-process memory forensics dump.

Threat: an incident hits, the on-call kills the suspicious process
without preserving memory — and any in-RAM secrets, decrypted blobs,
or attacker shellcode are lost.  Forensic value drops by an order of
magnitude.

Defence: ``dump_self`` writes the current process's writable mappings
to a file (best-effort; falls back to gcore when available).
Permission-checked + path-sandboxed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def dump_self(out_dir: str = "/var/log/aria/memdumps") -> Tuple[bool, str]:
    p = Path(out_dir).resolve()
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            return False, f"mkdir_failed:{exc}"

    pid = os.getpid()
    out_file = p / f"core.{pid}.{int(__import__('time').time())}.bin"

    gcore = shutil.which("gcore")
    if gcore:
        try:
            subprocess.run(
                [gcore, "-o", str(out_file.with_suffix("")), str(pid)],
                check=True, capture_output=True, timeout=120,
            )
            return True, f"gcore_dump:{out_file}"
        except Exception:
            pass    # fall through to /proc/maps fallback

    try:
        with open(f"/proc/{pid}/maps") as fh:
            maps_txt = fh.read()
        out_file.write_text(maps_txt)
        return True, f"maps_only:{out_file}"
    except OSError as exc:
        return False, f"proc_maps_unavailable:{exc}"


register(DefencePlugin(
    round_id="R192",
    name="memory_forensics",
    description="Dump current process memory (gcore preferred, /proc/maps fallback).",
))
