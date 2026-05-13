"""R289 — API-key vs OAuth boundary enforcement.

Threat: dual-auth APIs (accept either API key or OAuth bearer) end
up granting both, and a leaked API key bypasses OAuth's much stricter
scope + audit.  Slack 2024-class incidents.

Defence: per-route policy declaring exactly one auth class (api_key,
oauth, mtls, hybrid).  ``classify_request`` returns the auth class
detected; ``enforce`` returns the deny reason when policy mismatches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class RouteAuthPolicy:
    route: str
    allowed_auth: Tuple[str, ...]      # subset of ("api_key", "oauth", "mtls")


def classify_request(
    *, has_api_key: bool, has_oauth_bearer: bool, has_client_cert: bool,
) -> str:
    """Returns 'api_key' | 'oauth' | 'mtls' | 'mixed' | 'none'."""
    flags = sum([has_api_key, has_oauth_bearer, has_client_cert])
    if flags == 0:
        return "none"
    if flags > 1:
        return "mixed"
    if has_api_key:
        return "api_key"
    if has_oauth_bearer:
        return "oauth"
    return "mtls"


def enforce(policy: RouteAuthPolicy, classification: str) -> Tuple[bool, str]:
    if classification == "none":
        return False, "auth.no_credentials"
    if classification == "mixed":
        return False, "auth.mixed_credentials_refused"
    if classification not in policy.allowed_auth:
        return False, f"auth.class_not_allowed:{classification} allowed={','.join(policy.allowed_auth)}"
    return True, "ok"


register(DefencePlugin(
    round_id="R289",
    name="api_key_oauth",
    description="Per-route auth-class boundary; refuse mixed or out-of-policy credentials.",
))
