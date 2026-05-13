"""R206 — Post-quantum SSH key-exchange preference.

Threat: long-running SSH tunnels into bastions are recorded by
adversaries today and replayed against future CRQCs.  OpenSSH 9.0+
ships ``sntrup761x25519-sha512`` as a hybrid PQ KEX.

Defence: an audit that parses an sshd_config / ssh_config string,
returns the configured KEX preference, and refuses launches that
don't put a hybrid PQ KEX first.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_PQ_HYBRID_KEX = (
    "sntrup761x25519-sha512",
    "mlkem768x25519-sha256",
    "mlkem1024nistp384-sha384",
)


def audit_ssh_kex_line(line: str) -> Tuple[bool, List[str]]:
    """Returns ``(ok, issues)``.  ``line`` is a ``KexAlgorithms``
    config line (``KexAlgorithms a,b,c`` or just ``a,b,c``)."""
    issues: List[str] = []
    raw = line.strip()
    m = re.search(r"KexAlgorithms\s+(\S.+)$", raw, re.IGNORECASE)
    kexes = m.group(1) if m else raw
    parts = [k.strip() for k in kexes.split(",") if k.strip()]
    if not parts:
        return False, ["ssh.kex_empty"]
    first = parts[0]
    if first not in _PQ_HYBRID_KEX:
        issues.append(f"ssh.first_kex_not_pq:{first}")
    if "diffie-hellman-group1-sha1" in parts:
        issues.append("ssh.dh_group1_sha1")
    if "diffie-hellman-group14-sha1" in parts:
        issues.append("ssh.dh_group14_sha1")
    return not issues, issues


def recommended_kex_line() -> str:
    return ("KexAlgorithms " + ",".join(_PQ_HYBRID_KEX) +
            ",curve25519-sha256,curve25519-sha256@libssh.org")


def boot_check_local_sshd(*, path: str = "/etc/ssh/sshd_config") -> Tuple[bool, List[str]]:
    """Audit MED-14 — read the on-host sshd_config (best effort) and run
    the audit; returns ``(ok, issues)`` so operators can wire this into
    a boot-time gate.  Soft-passes outside ``ARIA_ENV=prod``."""
    import os
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return True, ["sshd_config_unreadable"]
    if os.environ.get("ARIA_ENV", "").lower() != "prod":
        return True, ["non_prod"]
    line = ""
    for raw in text.splitlines():
        s = raw.strip()
        if s.lower().startswith("kexalgorithms"):
            line = s
            break
    if not line:
        return False, ["sshd.no_kex_directive"]
    return audit_ssh_kex_line(line)


register(DefencePlugin(
    round_id="R206",
    name="pq_ssh",
    description="OpenSSH KexAlgorithms audit: refuse launches without hybrid PQ KEX first.",
))
