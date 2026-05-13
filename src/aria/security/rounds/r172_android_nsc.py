"""R172 — Android Network Security Config audit.

Threat: an Android app with cleartextTrafficPermitted=true or a
trust-store including user-installed CAs can be MITM'd by any
malicious sysadmin or hostile network.  Found in 36% of top-100 apps
(NowSecure 2023).

Defence: parse a network_security_config.xml string and audit the
posture: refuse cleartext to non-localhost domains, require pin-set
for production domains, refuse user-CA trust on release builds.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_nsc(xml_text: str, *, is_release: bool = True) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    text = xml_text or ""

    if re.search(r'cleartextTrafficPermitted\s*=\s*"true"', text):
        issues.append("nsc.cleartext_permitted")

    if is_release and re.search(r'<certificates\s+src\s*=\s*"user"', text, re.IGNORECASE):
        issues.append("nsc.user_ca_trusted_on_release")

    if "<pin-set" not in text and is_release:
        issues.append("nsc.no_pin_set_on_release")

    if re.search(r'<base-config[^>]*cleartextTrafficPermitted\s*=\s*"true"', text):
        issues.append("nsc.base_cleartext_permitted")

    return not issues, issues


def make_strict_nsc(domain: str, pin_sha256_b64: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<network-security-config>\n'
        '  <base-config cleartextTrafficPermitted="false">\n'
        '    <trust-anchors><certificates src="system"/></trust-anchors>\n'
        '  </base-config>\n'
        f'  <domain-config>\n    <domain includeSubdomains="true">{domain}</domain>\n'
        '    <pin-set expiration="2099-01-01">\n'
        f'      <pin digest="SHA-256">{pin_sha256_b64}</pin>\n'
        '    </pin-set>\n  </domain-config>\n'
        '</network-security-config>\n'
    )


register(DefencePlugin(
    round_id="R172",
    name="android_nsc",
    description="Android Network Security Config audit + strict template emitter.",
))
