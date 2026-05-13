"""R195 — Active deception (decoy file + canary tokens).

Threat: a stealthy attacker post-foothold reads sensitive files and
exfils.  Without active deception there is no detection trigger
between "foothold" and "data leaves the perimeter".

Defence: place decoy files in attractive paths (~/.aws/credentials.bak,
/var/backups/db.sql.bak) whose content is a uniquely-tagged honey
token; ``audit_for_reads`` checks atime / inotify events and trips
on any access.  Pairs with R51 honeypot mesh.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def make_decoy(path: str, *, tag_prefix: str = "ARIA_DECOY") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(8).hex()
    tag = f"{tag_prefix}-{salt}"
    payload = (
        "[default]\n"
        f"# {tag}\n"
        "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
    )
    p.write_text(payload)
    try:
        os.chmod(p, 0o400)
    except OSError:
        pass
    return tag


def audit_for_reads(decoys: Dict[str, float]) -> Tuple[bool, List[str]]:
    """``decoys`` is a dict ``{path: baseline_atime}``.  Returns
    ``(clean, list_of_accessed)``."""
    accessed: List[str] = []
    for path, baseline_atime in decoys.items():
        p = Path(path)
        if not p.exists():
            accessed.append(f"removed:{path}")
            continue
        try:
            cur = p.stat().st_atime
            if cur > baseline_atime + 1.0:
                accessed.append(f"read:{path}@{cur:.0f}")
        except OSError:
            continue
    return not accessed, accessed


def hash_decoy(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


register(DefencePlugin(
    round_id="R195",
    name="active_deception",
    description="Decoy credential files + atime-based read detection.",
))
