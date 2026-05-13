"""R117 — Linux namespace isolation enforcer.

Threat: a containerised process that shares the host PID, network, or
mount namespace can pivot to host resources.  Docker default is OK;
``--pid=host`` / ``--net=host`` / ``--ipc=host`` all break the
boundary and are the #1 finding on container-security audits.

Defence: a runtime self-check that ARIA is in its own PID + net + IPC
namespace; raises if not, in production mode.  Reads
``/proc/self/ns/{pid,net,ipc,uts,mnt,user,cgroup}`` and compares to
PID 1's namespace inode — different inodes mean we're isolated.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_NS_KINDS = ("pid", "net", "ipc", "uts", "mnt", "user", "cgroup")


def _read_ns(pid: str, kind: str) -> str:
    try:
        return os.readlink(f"/proc/{pid}/ns/{kind}")
    except OSError:
        return ""


def isolation_status() -> Dict[str, bool]:
    """Return ``{kind: isolated_bool}``.  ``isolated_bool == True`` iff
    our namespace inode differs from PID 1's inode."""
    out: Dict[str, bool] = {}
    for k in _NS_KINDS:
        ours = _read_ns("self", k)
        host = _read_ns("1", k)
        if not ours or not host:
            out[k] = True               # we can't tell — assume OK
            continue
        out[k] = ours != host
    return out


def boot_check() -> Tuple[bool, List[str]]:
    """In production, refuse to start without PID + net + IPC isolation."""
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return True, []
    issues: List[str] = []
    s = isolation_status()
    for required in ("pid", "net", "ipc"):
        if not s.get(required, True):
            issues.append(f"{required}_namespace_shared_with_host")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R117",
    name="namespace_isolation",
    description="Refuse production start with shared host PID/net/IPC namespaces.",
))
