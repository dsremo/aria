"""R194 — File-Integrity Monitor (Tripwire-class).

Threat: an attacker plants a rootkit, swaps /usr/bin/ssh, edits
/etc/passwd or a cron job — and persists for months unnoticed.  FIM
catches modifications by hashing and comparing.  R115 covered the
container-runtime variant; this one is the host equivalent.

Defence: ``capture_baseline`` SHA-256s a list of critical paths;
``detect_changes`` compares a fresh capture and reports add/modify/
remove.  Persistent baseline is opaque-bytes JSON for trivial sealing
into R98 immutable logs.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/sshd_config",
    "/etc/cron.d",
    "/usr/bin/ssh",
    "/usr/bin/sudo",
    "/usr/bin/python3",
    "/usr/sbin/sshd",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return ""


def capture_baseline(paths: Iterable[str] = ()) -> Dict[str, str]:
    targets = list(paths) or _DEFAULT_PATHS
    out: Dict[str, str] = {}
    for p in targets:
        path = Path(p)
        if path.is_file():
            digest = _sha256_file(path)
            if digest:
                out[str(path)] = digest
        elif path.is_dir():
            for sub in path.rglob("*"):
                if sub.is_file():
                    digest = _sha256_file(sub)
                    if digest:
                        out[str(sub)] = digest
    return out


def detect_changes(baseline: Dict[str, str], current: Dict[str, str]) -> Tuple[bool, List[str]]:
    changes: List[str] = []
    for p, d in baseline.items():
        c = current.get(p)
        if c is None:
            changes.append(f"removed:{p}")
        elif c != d:
            changes.append(f"modified:{p}")
    for p in current:
        if p not in baseline:
            changes.append(f"added:{p}")
    return not changes, changes


def serialise(baseline: Dict[str, str]) -> bytes:
    return json.dumps(baseline, sort_keys=True).encode("utf-8")


register(DefencePlugin(
    round_id="R194",
    name="fim",
    description="Host file-integrity monitor: SHA-256 baseline + drift detector.",
))
