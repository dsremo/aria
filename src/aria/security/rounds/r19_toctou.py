"""R19 — TOCTOU (time-of-check / time-of-use).

Threat: ARIA checks ``os.path.exists(path) and is_safe_path(path)``,
then opens the file.  Between the check and the open, an attacker
swaps the file for a symlink to ``/etc/passwd``.  CWE-367.  Recently
abused: SimpleHelp file-server (CVE-2024-57728).

Defence: an ``open_locked_path(p, mode)`` helper that uses
``os.open(p, O_NOFOLLOW | O_CLOEXEC)`` then re-stat-checks the
inode + device after open to detect symlink swaps.  Also exposes
``inside_dir(path, root)`` that resolves both with ``Path.resolve()``
to a canonical absolute form before the relative_to check.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def inside_dir(target: str, root: str) -> bool:
    """True iff ``target`` (after symlink resolution) sits inside ``root``."""
    try:
        t = Path(target).resolve(strict=False)
        r = Path(root).resolve(strict=True)
        t.relative_to(r)
        return True
    except Exception:
        return False


def open_locked_read(path: str) -> Tuple[int, os.stat_result]:
    """Open ``path`` read-only with O_NOFOLLOW; verify inode/device are
    stable after open.  Returns ``(fd, stat)`` — caller closes the fd.
    Raises ``OSError`` on any TOCTOU symptom.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        # Verify the path on disk is still the same inode + device.
        try:
            disk = os.stat(path)
        except OSError:
            os.close(fd)
            raise
        if (disk.st_ino, disk.st_dev) != (st.st_ino, st.st_dev):
            os.close(fd)
            raise OSError(f"R19.toctou: path {path!r} changed inode/device after open")
        return fd, st
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise


register(DefencePlugin(
    round_id="R19",
    name="toctou",
    description="open_locked_read + inside_dir helpers for atomic file lookup.",
))
