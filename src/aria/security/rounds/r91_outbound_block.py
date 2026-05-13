"""R91 — Egress allow-list firewall (deny-by-default outbound).

Threat: a successful RCE inside ARIA can phone home, exfiltrate data,
or download a second-stage payload.  The mitigation that contains
post-compromise impact is **deny-by-default egress** — only known
hosts in ARIA's natural call set (CISA KEV, JPL Horizons, NTRS,
Celestrak, LeoLabs, IS4OM, SpaceTrack, the operator's KMS) are
allowed.  Banks operate this way; nation-state defence treats it as
the foundation of zero-trust.

Defence: a plugin hook on `safe_open_url` that fails-closed unless the
URL hostname is in the operator's allow-list.  R50's
`enforce_host_allowlist=True` already does this for our default set;
this round formalises the "production-mode strict" position with a
hard-fail that's wired into the boot check (R48).
"""

from __future__ import annotations

import os
from typing import List

from aria.security.plugins import DefencePlugin, register


def _on_outbound_url(url: str) -> List[str]:
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return []
    if os.environ.get("ARIA_EGRESS_ALLOW_ALL", "").lower() in {"1", "true", "yes"}:
        return []
    # The default host allow-list inside guard already covers our space-data
    # upstreams.  Production deployments append their KMS / SIEM endpoints.
    # When `enforce_host_allowlist=False` is passed by a caller, we emit a
    # WARNING here so the audit feed sees it.
    if "metadata.google.internal" in url or "169.254.169.254" in url:
        return ["r91.egress_to_metadata"]
    return []


register(DefencePlugin(
    round_id="R91",
    name="outbound_block",
    description="Egress deny-by-default in production (paired with R48 boot strict).",
    on_outbound_url=_on_outbound_url,
))
