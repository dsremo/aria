"""R255 — Permissions-Policy (formerly Feature-Policy).

Threat: a vulnerable iframe or third-party widget that gains access
to camera, microphone, geolocation, USB, payment, or clipboard turns
into the surveillance backdoor of the host page.  Permissions-Policy
disables sensitive APIs by default.

Defence: a strict default Permissions-Policy header that turns off
the dangerous APIs unless explicitly enabled per origin.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_DENY = (
    "camera", "microphone", "geolocation", "usb", "payment",
    "clipboard-read", "clipboard-write", "magnetometer", "accelerometer",
    "gyroscope", "midi", "serial", "bluetooth", "hid", "fullscreen",
    "publickey-credentials-get", "screen-wake-lock", "window-management",
    "encrypted-media", "interest-cohort",
)


def strict_permissions_policy(allow_overrides: Dict[str, str] = None) -> str:
    allow_overrides = allow_overrides or {}
    parts: List[str] = []
    for feature in _DEFAULT_DENY:
        if feature in allow_overrides:
            parts.append(f"{feature}={allow_overrides[feature]}")
        else:
            parts.append(f"{feature}=()")
    return ", ".join(parts)


def audit_permissions_policy(header: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    h = (header or "").lower()
    if not h:
        return False, ["permissions.no_header"]
    for feature in ("camera", "microphone", "geolocation"):
        if feature not in h:
            issues.append(f"permissions.missing_directive:{feature}")
        elif f"{feature}=*" in h:
            issues.append(f"permissions.wildcard:{feature}")
    return not issues, issues


register(DefencePlugin(
    round_id="R255",
    name="permissions_policy",
    description="Strict default Permissions-Policy header + audit.",
))
