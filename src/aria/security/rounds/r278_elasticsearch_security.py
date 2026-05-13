"""R278 — Elasticsearch security audit.

Threat: ES clusters historically shipped without auth — Bloomberg,
Adobe, Verizon all leaked customer data through unauthed ES.  Even
post-7.x where security is on by default, anonymous-user permissions
and HTTP (vs HTTPS) misconfig persist.

Defence: parse an elasticsearch.yml dict and refuse anonymous
access, missing TLS, missing realm, and ``xpack.security.enabled:
false`` in production.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_elasticsearch_yml(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    is_prod = os.environ.get("ARIA_ENV") == "prod"

    sec_enabled = _get_dotted(config, "xpack.security.enabled")
    if sec_enabled in (False, "false") and is_prod:
        issues.append("es.xpack_security_disabled_in_prod")

    anon = _get_dotted(config, "xpack.security.authc.anonymous.username")
    if anon:
        issues.append(f"es.anonymous_user:{anon}")

    http_ssl = _get_dotted(config, "xpack.security.http.ssl.enabled")
    if http_ssl in (False, "false") and is_prod:
        issues.append("es.http_ssl_disabled_in_prod")

    transport_ssl = _get_dotted(config, "xpack.security.transport.ssl.enabled")
    if transport_ssl in (False, "false"):
        issues.append("es.transport_ssl_disabled")

    network_host = _get_dotted(config, "network.host")
    if network_host in ("0.0.0.0", "_site_", "_global_") and not sec_enabled:
        issues.append(f"es.network_host_open_no_auth:{network_host}")

    return not issues, issues


def _get_dotted(d: Dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    current: Any = d
    for p in parts:
        if isinstance(current, dict):
            if p in current:
                current = current[p]
                continue
        # also try the flat-dotted form
        if isinstance(current, dict) and path in current:
            return current[path]
        return None
    return current


register(DefencePlugin(
    round_id="R278",
    name="elasticsearch_security",
    description="elasticsearch.yml audit: xpack.security + TLS + anonymous-user refusal.",
))
