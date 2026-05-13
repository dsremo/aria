"""R79 — Anti-debugger / anti-attach detection (Linux).

Threat: an attacker with shell access to the deploy container attaches
gdb / strace / ptrace to dump in-memory secrets (decrypted master keys,
session tokens).  Bank stacks ship binaries that refuse to run when
ptrace-attached; ARIA can do the same on Linux via ``PR_SET_DUMPABLE`` +
``/proc/self/status TracerPid``.

Defence: ``deny_ptrace_attach()`` makes the process unattachable
(prctl).  ``is_being_traced()`` polls ``/proc/self/status`` and returns
True when ``TracerPid > 0``.  Operators wire this at boot for
production deployments.
"""

from __future__ import annotations

import ctypes
import os
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_PR_SET_DUMPABLE = 4
_PR_SET_TRACE_DENIED = 56            # not a real prctl; placeholder if needed


def deny_ptrace_attach() -> Tuple[bool, str]:
    """Make the process refuse ptrace attach (also disables core dumps)."""
    if os.name != "posix":
        return False, "non_posix"
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        # PR_SET_DUMPABLE = 0 → process unattachable + non-dumpable.
        rc = libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0)
        return rc == 0, "ok" if rc == 0 else f"rc={rc}"
    except Exception as exc:
        return False, f"exc:{exc}"


def is_being_traced() -> bool:
    """Read ``/proc/self/status`` for the TracerPid line."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("TracerPid:"):
                    return int(line.split(":", 1)[1].strip()) > 0
    except OSError:
        pass
    return False


register(DefencePlugin(
    round_id="R79",
    name="anti_debug",
    description="prctl(PR_SET_DUMPABLE,0) + TracerPid poll for ptrace detection.",
))
