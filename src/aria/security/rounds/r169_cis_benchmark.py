"""R169 — CIS Linux Benchmark Level 1 spot-check.

Threat: an unhardened Linux host has dozens of misconfigurations any
attacker post-foothold can chain (sticky bits, world-writable cron,
weak ssh ciphers).  CIS Benchmarks codify the baseline; without an
automated check, drift is invisible.

Defence: spot-check a curated subset of CIS Linux Level 1 controls
that are cheap to verify in-process: kernel params, file modes, SSH
config, cron permissions.  Return non-compliant items.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def check_cis_level1() -> Tuple[bool, List[str]]:
    issues: List[str] = []

    # 1.1.1.x  — protocol modules disabled (best-effort: file presence)
    for mod in ("cramfs", "freevxfs", "jffs2", "hfs", "hfsplus", "udf"):
        try:
            with open(f"/proc/modules") as fh:
                if mod in fh.read():
                    issues.append(f"cis.kmod_loaded:{mod}")
        except OSError:
            break

    # 5.2.x  — sshd config (no PermitRootLogin yes, no Protocol 1)
    sshd = Path("/etc/ssh/sshd_config")
    if sshd.exists():
        try:
            txt = sshd.read_text(errors="ignore")
        except OSError:
            txt = ""
        for needle, label in (
            ("PermitRootLogin yes", "cis.sshd_root_login"),
            ("PermitEmptyPasswords yes", "cis.sshd_empty_password"),
            ("Protocol 1", "cis.sshd_protocol_1"),
        ):
            if needle.lower() in txt.lower():
                issues.append(label)

    # 1.5.1  — /etc/passwd 0644
    p = Path("/etc/passwd")
    if p.exists():
        m = p.stat().st_mode
        if m & (stat.S_IWGRP | stat.S_IWOTH):
            issues.append("cis.passwd_world_writable")

    # 5.1.x  — /etc/cron.d, /etc/cron.daily, /etc/crontab not world-writable
    for cron in ("/etc/crontab", "/etc/cron.d", "/etc/cron.daily"):
        cp = Path(cron)
        if cp.exists():
            m = cp.stat().st_mode
            if m & stat.S_IWOTH:
                issues.append(f"cis.world_writable:{cron}")

    # 1.7.1  — banner exists
    if not Path("/etc/issue.net").exists():
        issues.append("cis.issue_net_missing")

    return not issues, issues


def boot_check() -> Tuple[bool, List[str]]:
    if os.environ.get("ARIA_ENV") != "prod":
        return True, ["non_prod"]
    return check_cis_level1()


register(DefencePlugin(
    round_id="R169",
    name="cis_benchmark",
    description="CIS Linux Benchmark Level 1 spot-check (sshd, cron, passwd, kmods).",
))
