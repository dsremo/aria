"""R115 — Container runtime drift detection.

Threat: an attacker who lands inside a running container modifies
binaries / libraries on the writable layer.  The image SHA-256 is
unchanged on disk but the running rootfs has drifted.  Banks +
classified deployers monitor file inotify on critical paths.

Defence: ``snapshot_paths(paths)`` records SHA-256 + mtime + size for a
list of paths at boot.  ``detect_drift()`` re-checks; any mismatch is
emitted as CRITICAL.  Pair with R45 read-only rootfs (writes refused)
+ R80 code-integrity (loaded modules) so the only path that survives is
``/proc`` and operator-mounted data dirs.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Snap:
    sha256: str
    mtime: float
    size: int


_SNAPS: Dict[str, _Snap] = {}
_LOCK = threading.Lock()


def snapshot_paths(paths: List[str]) -> int:
    n = 0
    with _LOCK:
        _SNAPS.clear()
        for p in paths:
            try:
                st = os.stat(p)
                if not os.path.isfile(p):
                    continue
                with open(p, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                _SNAPS[p] = _Snap(sha256=digest, mtime=st.st_mtime, size=st.st_size)
                n += 1
            except OSError:
                continue
    return n


def detect_drift() -> List[Tuple[str, str]]:
    """Return list of ``(path, reason)`` for any drifted file."""
    diffs: List[Tuple[str, str]] = []
    with _LOCK:
        snaps = dict(_SNAPS)
    for p, snap in snaps.items():
        try:
            st = os.stat(p)
            if st.st_size != snap.size:
                diffs.append((p, f"size {snap.size} -> {st.st_size}"))
                continue
            if abs(st.st_mtime - snap.mtime) > 1:
                diffs.append((p, f"mtime drift {snap.mtime:.0f} -> {st.st_mtime:.0f}"))
            with open(p, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            if actual != snap.sha256:
                diffs.append((p, "sha256_mismatch"))
        except OSError:
            diffs.append((p, "unreadable"))
    return diffs


_CRITICAL_PATHS = (
    "/etc/passwd", "/etc/shadow", "/etc/group",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssh/sshd_config",
    "/etc/sudoers",
    "/usr/bin/python3",
    "/bin/sh",
)


def snapshot_critical() -> int:
    return snapshot_paths(list(_CRITICAL_PATHS))


register(DefencePlugin(
    round_id="R115",
    name="runtime_drift",
    description="Boot snapshot + on-demand drift detection of critical paths.",
))
