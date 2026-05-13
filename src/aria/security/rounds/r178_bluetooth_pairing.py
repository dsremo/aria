"""R178 — Bluetooth Low Energy pairing audit.

Threat: BLE pairing in Just-Works mode is unauthenticated and trivial
to MITM.  Many medical / fitness / lock devices ship Just-Works to
ease the consumer flow and never disable it.

Defence: classify a pairing-method string and refuse Just-Works on
any device classified as security-sensitive.  Recommend Numeric
Comparison (LE Secure Connections) for sensitive channels.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_SAFE = ("numeric_comparison", "passkey_entry", "out_of_band")
_INSECURE = ("just_works", "legacy_pairing")


def audit_pairing_method(
    method: str,
    *,
    is_sensitive: bool = True,
) -> Tuple[bool, List[str]]:
    method_l = (method or "").lower().replace("-", "_").replace(" ", "_")
    issues: List[str] = []
    if method_l in _INSECURE:
        if is_sensitive:
            issues.append(f"bt.insecure_pairing_on_sensitive_device:{method_l}")
        else:
            issues.append(f"bt.insecure_pairing:{method_l}")
    elif method_l not in _SAFE and method_l:
        issues.append(f"bt.unknown_pairing_method:{method_l}")
    if not method:
        issues.append("bt.no_pairing_method_declared")
    return not issues, issues


register(DefencePlugin(
    round_id="R178",
    name="bluetooth_pairing",
    description="BLE pairing-method classifier; refuse Just-Works for sensitive devices.",
))
