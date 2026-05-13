"""R84 — SYN-flood mitigation (TCP layer).

Threat: a SYN flood saturates the kernel SYN backlog, denying real
clients a half-open slot.  Linux's SYN cookies (``net.ipv4.tcp_syncookies=1``)
are the canonical mitigation; many cloud VMs ship with it on, but
custom kernels / containers can regress.

Defence: a runtime check that the kernel has SYN cookies enabled +
emits a recommended sysctl snippet for operators.  ARIA itself runs
above the TCP layer, so this round is a *config gate* — fails the
boot check (R48) when production-mode + SYN cookies off.
"""

from __future__ import annotations

import os
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def syn_cookies_enabled() -> bool:
    try:
        with open("/proc/sys/net/ipv4/tcp_syncookies") as f:
            return int(f.read().strip()) >= 1
    except OSError:
        return False


def boot_check() -> Tuple[bool, str]:
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return True, ""
    if not syn_cookies_enabled():
        return False, "SYN cookies disabled (net.ipv4.tcp_syncookies != 1)"
    return True, ""


_SYSCTL_RECOMMENDED = """\
# R84 — SYN-flood mitigation kernel knobs
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_synack_retries = 3
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.tcp_abort_on_overflow = 0
"""


def sysctl_recommended() -> str:
    return _SYSCTL_RECOMMENDED


register(DefencePlugin(
    round_id="R84",
    name="syn_flood",
    description="Boot check for SYN cookies; emit recommended sysctl snippet.",
))
