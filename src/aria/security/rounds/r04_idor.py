"""R4 — IDOR (Insecure Direct Object Reference).

Threat: handler receives a resource ID in path or body and looks it up
without verifying the caller's tenant owns it (``GET /v1/tenants/42``
returning data when the bearer is for tenant 7).  IDOR is the #1
OWASP API category and the root cause of the 2024 Dell unauth API
breach (49 M records).

Defence: a small dataclass that wraps each handler's tenant-scoped
lookup with a ``check_owns(principal, resource)`` call.  The plugin
itself doesn't fire on every request — instead it exposes the helper
that handler code uses, plus a request-id-correlated audit log entry
for any failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r04")


@dataclass
class _TenantBoundResource:
    resource_id: str
    owning_tenant: str


def check_owns(principal_tenant: str, resource: _TenantBoundResource) -> bool:
    """Return True iff ``principal_tenant`` owns ``resource``.

    Logs every failure so a hostile attempt to enumerate IDs across
    tenants stands out in the audit feed.
    """
    if not principal_tenant or not resource:
        return False
    if principal_tenant == resource.owning_tenant:
        return True
    logger.warning(
        "r04.idor_attempt principal=%s resource=%s owner=%s",
        principal_tenant, resource.resource_id, resource.owning_tenant,
    )
    return False


def make_resource(resource_id: str, owning_tenant: str) -> _TenantBoundResource:
    return _TenantBoundResource(resource_id=resource_id, owning_tenant=owning_tenant)


# Surface aliases for handler code: ``from aria.security.rounds.r04_idor import check_owns``


register(DefencePlugin(
    round_id="R4",
    name="idor_helper",
    description="Tenant-bound resource lookup helper + audit on cross-tenant attempt.",
))
