"""R215 — OPC-UA security policy audit.

Threat: OPC-UA is the modern industrial protocol (OPC Foundation
spec) but the SecurityPolicy field is configurable from ``None`` up
to ``Basic256Sha256``.  Many vendors ship ``None`` as default; the
attacker-on-LAN bypass is one config-screen wide.

Defence: validate the chosen SecurityPolicy + MessageSecurityMode;
refuse ``None`` in production; flag ``Basic128Rsa15`` (deprecated
2018).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEPRECATED = {
    "http://opcfoundation.org/UA/SecurityPolicy#Basic128Rsa15",
    "http://opcfoundation.org/UA/SecurityPolicy#Basic256",
}

_ALLOWED = {
    "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
    "http://opcfoundation.org/UA/SecurityPolicy#Aes128_Sha256_RsaOaep",
    "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss",
}


def audit_opcua_endpoint(endpoint: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    policy = endpoint.get("securityPolicyUri") or ""
    mode = endpoint.get("securityMode") or "None"

    if policy.endswith("#None") or mode == "None":
        if os.environ.get("ARIA_ENV") == "prod":
            issues.append("opcua.policy_none_in_prod")

    if policy in _DEPRECATED:
        issues.append(f"opcua.deprecated_policy:{policy.rsplit('#', 1)[-1]}")

    if mode not in ("None", "Sign", "SignAndEncrypt"):
        issues.append(f"opcua.invalid_mode:{mode}")

    if mode == "Sign" and os.environ.get("ARIA_ENV") == "prod":
        issues.append("opcua.sign_only_in_prod")     # production needs SignAndEncrypt

    if policy and policy not in _ALLOWED and not policy.endswith("#None"):
        issues.append(f"opcua.unrecognised_policy:{policy.rsplit('#', 1)[-1]}")

    return not issues, issues


register(DefencePlugin(
    round_id="R215",
    name="opcua_security",
    description="OPC-UA SecurityPolicy + MessageSecurityMode audit; refuse None in prod.",
))
