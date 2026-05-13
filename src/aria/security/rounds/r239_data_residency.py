"""R239 — Data residency enforcement (EU / US / IN / SG).

Threat: data subject to EU GDPR (or India DPDP, or China PIPL, or
Russia 242-FZ) must remain within the legal jurisdiction.  A single
mis-routed write to an out-of-region replica is a notifiable breach.

Defence: per-tenant residency policy + ``check_destination``
returning ALLOW / BLOCK + reason.  The policy maps tenant → list of
allowed region codes; any other destination is refused.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_TENANT_ALLOWED_REGIONS: Dict[str, Set[str]] = {}
_LOCK = threading.Lock()


def configure_tenant(tenant_id: str, allowed_regions: List[str]) -> None:
    with _LOCK:
        _TENANT_ALLOWED_REGIONS[tenant_id] = {r.upper() for r in allowed_regions}


def check_destination(tenant_id: str, destination_region: str) -> Tuple[bool, str]:
    with _LOCK:
        allowed = _TENANT_ALLOWED_REGIONS.get(tenant_id)
    if allowed is None:
        return False, f"residency.tenant_unconfigured:{tenant_id}"
    if destination_region.upper() not in allowed:
        return False, f"residency.violation tenant={tenant_id} dst={destination_region} allowed={','.join(sorted(allowed))}"
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _TENANT_ALLOWED_REGIONS.clear()


register(DefencePlugin(
    round_id="R239",
    name="data_residency",
    description="Per-tenant data-residency allow-list (GDPR / DPDP / PIPL / 242-FZ).",
))
