"""R277 — Redis ACL + protected-mode audit.

Threat: Redis pre-6.0 had no per-user ACLs — anyone with network
access could ``CONFIG SET dir`` to /var/spool/cron and write a cron
job (CVE-2015-4335 chain).  Even with ACLs, a default-allow user
``default`` undoes the model.

Defence: parse a Redis config and an ACL file, refuse ``protected-
mode no``, ``bind 0.0.0.0`` without ``requirepass``, and ACL entries
that grant ``+@all`` on the ``default`` user.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_redis_conf(text: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    is_prod = os.environ.get("ARIA_ENV") == "prod"
    config_lines = [l.strip() for l in (text or "").splitlines() if l.strip() and not l.strip().startswith("#")]
    config = {}
    for line in config_lines:
        parts = line.split(None, 1)
        if len(parts) == 2:
            config[parts[0].lower()] = parts[1].strip()

    if config.get("protected-mode", "yes").lower() == "no":
        issues.append("redis.protected_mode_off")

    bind = config.get("bind", "127.0.0.1")
    if ("0.0.0.0" in bind or "::" in bind) and not config.get("requirepass") and not config.get("aclfile"):
        issues.append("redis.world_bind_no_auth")

    if not config.get("requirepass") and is_prod and not config.get("aclfile"):
        issues.append("redis.no_auth_in_prod")

    if config.get("rename-command", "").upper().endswith("CONFIG ''"):
        pass     # disabling CONFIG is fine

    if config.get("user", "").lower().startswith("default on nopass"):
        issues.append("redis.default_user_nopass")

    return not issues, issues


def audit_acl_file(text: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if not parts or parts[0].lower() != "user":
            continue
        if len(parts) >= 2 and parts[1].lower() == "default":
            joined = " ".join(parts).lower()
            if "+@all" in joined and "nopass" in joined:
                issues.append("redis.acl_default_all_nopass")
            elif "nopass" in joined and "off" not in joined:
                issues.append("redis.acl_default_nopass_on")
    return not issues, issues


register(DefencePlugin(
    round_id="R277",
    name="redis_acl",
    description="Redis config + ACL audit: refuse protected-mode off + world-bind without auth.",
))
