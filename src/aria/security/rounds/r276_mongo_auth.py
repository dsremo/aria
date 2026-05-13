"""R276 — MongoDB authentication + bind-IP audit.

Threat: a MongoDB instance with ``bindIp: 0.0.0.0`` and no auth is the
classic data leak — millions of records exposed (Shodan: tens of
thousands at any time).  MongoDB pre-3.6 default was world-open.

Defence: parse a mongod config (YAML-shaped dict) and refuse open-
network bind without authorisation + TLS.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_mongod_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    net = config.get("net") or {}
    sec = config.get("security") or {}

    bind_ip = (net.get("bindIp") or "").strip()
    if "0.0.0.0" in bind_ip or "::" in bind_ip:
        if str(sec.get("authorization", "")).lower() != "enabled":
            issues.append("mongo.world_bind_no_auth")

    if str(sec.get("authorization", "")).lower() != "enabled":
        issues.append("mongo.authorization_disabled")

    tls = (net.get("tls") or {})
    if not tls.get("mode") or str(tls["mode"]).lower() in ("disabled", "allowtls"):
        issues.append(f"mongo.tls_mode_weak:{tls.get('mode', 'absent')}")

    if config.get("processManagement", {}).get("fork") and not sec.get("javascriptEnabled") is False:
        # explicit setting required to disable JS engine in prod
        pass     # advisory; we don't fail here

    if str(net.get("port", 27017)) == "27017" and "0.0.0.0" in bind_ip:
        issues.append("mongo.default_port_world_bind")

    return not issues, issues


register(DefencePlugin(
    round_id="R276",
    name="mongo_auth",
    description="MongoDB config audit: refuse world-bind + no-auth + weak TLS.",
))
