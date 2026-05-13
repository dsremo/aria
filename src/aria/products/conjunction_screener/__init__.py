"""ARIA Conjunction Screener as a Service.

A minimal HTTPS API that smallsat operators can call to screen one
or more of their satellites against a TLE catalog they supply.
ARIA never centrally hoards 18-SDS data — operators bring their
own TLEs / SpaceTrack credentials — which keeps the legal posture
clean and the service stateless.

Endpoints:

  POST /v1/screen           — screen one primary against a list of
                              secondaries; return TCA + miss + Pc
                              + risk classification per pair.
  POST /v1/auth/spacetrack  — operator authenticates with their own
                              SpaceTrack credentials; ARIA pulls the
                              full active LEO catalog on their behalf
                              and runs the screen.
  GET  /v1/healthz          — liveness + version probe.
  GET  /v1/version          — ARIA + ARIA-Screener semver.

Auth model: operators send a per-tenant API key (HMAC-shared
secret) in the `X-ARIA-Token` header.  Rate limits per tenant.

Out of scope for this minimum viable product:
  * Multi-tenant database
  * Stripe / billing integration
  * WebSocket streaming
  * Manoeuvre planning (separate endpoint family in v2)
"""

from aria.products.conjunction_screener.service import (
    ConjunctionScreenerService,
    ScreenRequest,
    ScreenResponse,
    ScreenResult,
    create_app,
)
from aria.products.conjunction_screener.tenants import (
    Tenant,
    TenantStore,
    default_db_path,
)

__all__ = [
    "ConjunctionScreenerService",
    "ScreenRequest",
    "ScreenResponse",
    "ScreenResult",
    "create_app",
    "Tenant",
    "TenantStore",
    "default_db_path",
]
