"""R257 — Cross-Origin-Opener / Embedder-Policy hardening.

Threat: shared-array-buffer + high-resolution timers reopened the
Spectre / Meltdown side-channel in browsers.  Cross-origin isolation
(COOP same-origin + COEP require-corp) is the modern mitigation that
re-enables those APIs only for sites that explicitly opt in.

Defence: emit the strict header pair; audit the response and refuse
sites that need shared array buffers without isolation.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def strict_isolation_headers() -> Dict[str, str]:
    return {
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def audit_isolation(headers: Dict[str, str], *, requires_isolation: bool = False) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    norm = {k.lower(): v for k, v in (headers or {}).items()}

    coop = (norm.get("cross-origin-opener-policy") or "").lower()
    coep = (norm.get("cross-origin-embedder-policy") or "").lower()

    if requires_isolation:
        if coop != "same-origin":
            issues.append(f"isolation.coop_not_same_origin:{coop or 'absent'}")
        if coep not in ("require-corp", "credentialless"):
            issues.append(f"isolation.coep_not_strict:{coep or 'absent'}")
    elif coop and coop == "unsafe-none":
        issues.append("isolation.coop_unsafe_none")
    return not issues, issues


register(DefencePlugin(
    round_id="R257",
    name="coop_coep",
    description="Cross-origin isolation header pair (COOP same-origin + COEP require-corp).",
))
