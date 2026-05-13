"""R111 — Speculative-execution hardening hints (Spectre/Meltdown class).

Threat: branch predictors leak data across security domains.  Spectre
v1/v2 (2018), L1TF (2018), MDS (2019), TAA / Reptar (2024).  Cloud
providers and OS vendors patch; ARIA's defence is to ensure the
mitigations are *on* and to refuse to start if the kernel reports them
disabled.

Defence: parse ``/sys/devices/system/cpu/vulnerabilities/*`` and
return the per-vuln status.  Boot check (paired with R48) refuses to
start in production if any vulnerability shows ``Vulnerable``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_VULN_DIR = Path("/sys/devices/system/cpu/vulnerabilities")


def cpu_vulnerability_status() -> Dict[str, str]:
    """Return ``{vuln_name: status_text}`` for every entry in
    ``/sys/devices/system/cpu/vulnerabilities/``."""
    out: Dict[str, str] = {}
    if not _VULN_DIR.is_dir():
        return out
    for p in _VULN_DIR.iterdir():
        try:
            out[p.name] = p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return out


def boot_check() -> Tuple[bool, list]:
    """Return ``(ok, issues_list)``.  ``ok`` is False if any
    speculative-exec mitigation reports ``Vulnerable``."""
    issues: list = []
    for name, status in cpu_vulnerability_status().items():
        if status.lower().startswith("vulnerable"):
            issues.append(f"{name}: {status}")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R111",
    name="speculative_exec",
    description="Spectre/Meltdown-class status parser + boot-check helper.",
))
