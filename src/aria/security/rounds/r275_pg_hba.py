"""R275 — PostgreSQL pg_hba.conf hardening.

Threat: a permissive ``pg_hba.conf`` (host all all 0.0.0.0/0 trust)
exposes Postgres to the open internet without auth.  Shodan finds
~75K Postgres instances exposed at any time.

Defence: parse ``pg_hba.conf`` lines and refuse ``trust`` /
``password`` / wildcard ``all all`` 0.0.0.0/0 entries; require
``scram-sha-256`` for production.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_WEAK_METHODS = {"trust", "password", "ident"}
_OK_METHODS = {"scram-sha-256", "cert", "gss", "sspi", "peer"}


def audit_pg_hba(text: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    is_prod = os.environ.get("ARIA_ENV") == "prod"
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        # host db user [address] method  → method is last
        method = parts[-1].lower()
        if method in _WEAK_METHODS:
            issues.append(f"pg_hba.weak_method:{method} | {line}")
        if method == "md5" and is_prod:
            issues.append(f"pg_hba.md5_in_prod | {line}")
        if "0.0.0.0/0" in parts and method not in _OK_METHODS:
            issues.append(f"pg_hba.world_open | {line}")
        if parts[0].lower() == "host" and "all" in parts and parts.count("all") >= 2:
            if "0.0.0.0/0" in parts or "::/0" in parts:
                issues.append(f"pg_hba.all_all_world | {line}")
    return not issues, issues


register(DefencePlugin(
    round_id="R275",
    name="pg_hba",
    description="pg_hba.conf audit: refuse trust/password/world-open entries.",
))
