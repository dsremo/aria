"""aiohttp authentication middleware + permission-required decorator.

Plugs the ship-wide identity layer into every request handled by
``aria.simulator.web_dashboard``.

Wire contract:
  - Login + healthz: open to anonymous (allow-list).
  - All other endpoints: require ``Authorization: Bearer <session_token>``.
  - Bearer token resolves to a verified ``Principal``, attached to
    ``request['principal']``.
  - Handlers protected by ``@require_permission("perm.name")`` get a
    pre-checked principal; on failure, a 403 with audit-logged reason.

Failure modes (Leveson / Anthropic safety panel):
  - Missing token → 401 (telemetry endpoints fall back to anonymous).
  - Bad/expired/revoked token → 401, log ``auth.session_invalid``.
  - Right session, wrong permission → 403, log ``auth.permission_denied``.
  - Tamper sentinel (signature failed) → 401 + tamper counter increment.

The middleware never reads the request body for auth — only headers —
so a giant malicious POST cannot bog down the auth path.

Implements §F-9 (principal-aware approval), §F-19 (session counter),
and the command lifecycle in `docs/FAILSAFE_ARCHITECTURE.md`.

Round-2 audit hardening (2026-04-27 R2):
  - Both auth + resolver middlewares now derive a client fingerprint
    from the request (NEW-CRIT-3) and pass it to ``touch()``, so the
    HIGH-6 client-binding actually fires.
  - Unmapped routes default to a sentinel deny-permission no role
    holds (NEW-HIGH-15).
  - In production (``is_production``), ``enforced=False`` refuses to
    boot (NEW-HIGH-16).
  - Route-perm middleware logs the ``deny_reason_code`` only — never
    role/reason text (NEW-HIGH-18).
"""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, Tuple

import structlog
from aiohttp import web

from aria.security.audit import log_event
from aria.security.auth_service import (
    get_auth_service,
    principal_from_session,
)
from aria.security.principals import (
    Principal,
    authorize,
)
from aria.security.session_store import (
    Session,
    fingerprint_ip,
    fingerprint_ua,
    get_session_store,
)

logger = structlog.get_logger()


# Sentinel permission used when a route is not in the explicit
# ``route_perms`` map.  Deliberately not granted to any role — boot-time
# checks should refuse to start production deployments that ship a
# route landing on this sentinel.
UNMAPPED_ROUTE_PERMISSION = "__route_unmapped__"


# ── Allow-list ────────────────────────────────────────────────────


# Endpoints that anonymous principals may reach. Everything else
# requires a Bearer token. Matched by exact prefix.
DEFAULT_ANONYMOUS_PREFIXES: Tuple[str, ...] = (
    "/healthz",
    "/readyz",
    "/api/auth/challenge",
    "/api/auth/login",
    # Static assets served by the dashboard.
    "/static/",
    "/favicon.ico",
    "/",                  # SPA index — page itself; API calls are gated
)


# Endpoints that fall back to anonymous on missing/expired token rather
# than 401. Strictly read-only telemetry — kept short on purpose.
TELEMETRY_FALLBACK_PREFIXES: Tuple[str, ...] = (
    # Empty by default — opt in via a per-route decorator instead.
)


def _path_in(prefixes: Iterable[str], path: str) -> bool:
    """Match an entry as exact path; or, if the entry ends with `/`
    and is longer than one char, as a true prefix. The lone `/` entry
    is treated as exact-match (the SPA index) so it doesn't accidentally
    match every URL."""
    for entry in prefixes:
        if len(entry) > 1 and entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def _client_fingerprint(request: web.Request) -> Tuple[str, str]:
    """Round-2 audit NEW-CRIT-3 — derive the IP + UA fingerprint that
    the session store needs to enforce client-binding.

    The IP we use here is ONLY for binding — it is intentionally NOT
    XFF-derived because the screener already runs that decision at the
    rate-limit layer (where trusted-proxy validation lives).  Using the
    raw socket peer here means an attacker who replays a token from a
    different machine will fail-closed, even when XFF is spoofable.
    """
    ip = request.remote or ""
    ua = request.headers.get("User-Agent", "") or ""
    return fingerprint_ip(ip), fingerprint_ua(ua)


# ── Middleware ────────────────────────────────────────────────────


def make_auth_middleware(
    *,
    anonymous_prefixes: Iterable[str] = DEFAULT_ANONYMOUS_PREFIXES,
    telemetry_fallback_prefixes: Iterable[str] = TELEMETRY_FALLBACK_PREFIXES,
) -> Callable[..., Awaitable[web.StreamResponse]]:
    """Build the aiohttp middleware. Override the prefix tuples in tests."""

    anon = tuple(anonymous_prefixes)
    fallback = tuple(telemetry_fallback_prefixes)

    @web.middleware
    async def auth_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        path = request.path or "/"

        # Allow-list: anonymous identity.
        if _path_in(anon, path):
            request["principal"] = Principal.anonymous()
            request["session"] = None
            return await handler(request)

        token = _extract_bearer_token(request)
        session = None
        principal: Optional[Principal] = None
        if token:
            ip_h, ua_h = _client_fingerprint(request)
            session = get_session_store().touch(
                token, ip_hash=ip_h, ua_hash=ua_h,
            )
            if session is not None:
                principal = principal_from_session(session)

        if principal is None:
            if _path_in(fallback, path):
                request["principal"] = Principal.anonymous()
                request["session"] = None
                return await handler(request)
            log_event(
                event_type="auth",
                identity="anonymous",
                action=f"GET/POST {path}",
                result="rejected",
                details={"reason": "no_or_invalid_session"},
            )
            return _unauthorized_response()

        request["principal"] = principal
        request["session"] = session
        return await handler(request)

    return auth_middleware


def _extract_bearer_token(request: web.Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[len("Bearer "):].strip() or None


def _unauthorized_response() -> web.Response:
    return web.json_response(
        {"error": "unauthorized", "message": "valid session required"},
        status=401,
    )


def _forbidden_response(reason: str = "permission denied") -> web.Response:
    return web.json_response(
        {"error": "forbidden", "message": reason},
        status=403,
    )


def _reason_to_code(reason: str) -> str:
    """Map a human-readable authorisation deny reason to a stable code so
    the audit log records the failure class without leaking the role-
    permission graph (audit MED-1)."""
    r = (reason or "").lower()
    if "expired" in r:
        return "PRINCIPAL_EXPIRED"
    if "duress" in r:
        return "DURESS_REJECTED"
    if "permission" in r or "missing" in r or "no_role" in r:
        return "PERMISSION_MISSING"
    if "anonymous" in r:
        return "ANONYMOUS"
    if "tamper" in r:
        return "TAMPERED_PRINCIPAL"
    if "unmapped" in r:
        return "ROUTE_UNMAPPED"
    return "DENIED_OTHER"


# ── Decorator ─────────────────────────────────────────────────────


def require_permission(
    permission: str,
) -> Callable[
    [Callable[[web.Request], Awaitable[web.StreamResponse]]],
    Callable[[web.Request], Awaitable[web.StreamResponse]],
]:
    """Wrap a handler so it only runs when the request's principal
    holds ``permission``. Audited on both grant and deny.

    Usage::

        @require_permission("approval.sign")
        async def handle_safety_approve(request): ...
    """

    def decorator(
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> Callable[[web.Request], Awaitable[web.StreamResponse]]:

        @functools.wraps(handler)
        async def wrapped(request: web.Request) -> web.StreamResponse:
            principal: Principal = request.get(  # type: ignore[assignment]
                "principal", Principal.anonymous(),
            )
            decision = authorize(principal, permission)
            if not decision.allow:
                # MED-1 — log a stable category code (deny_reason_code), not the
                # human reason text or the principal's role; doing so leaked role
                # privilege metadata into the audit chain and enabled attacker
                # reconnaissance over time.
                log_event(
                    event_type="authz",
                    identity=principal.principal_id,
                    action=f"{permission} on {request.path}",
                    result="denied",
                    details={"deny_reason_code": _reason_to_code(decision.reason)},
                )
                return _forbidden_response("permission denied")
            log_event(
                event_type="authz",
                identity=principal.principal_id,
                action=f"{permission} on {request.path}",
                result="granted",
                details={},
            )
            return await handler(request)

        return wrapped

    return decorator


# ── R35 trace_id middleware ──────────────────────────────────────


def make_trace_middleware(
    *,
    header_name: str = "X-Trace-Id",
) -> Callable[..., Awaitable[web.StreamResponse]]:
    """Read ``X-Trace-Id`` from the incoming request (or mint a fresh
    one if absent), install it into the TraceContext for the duration
    of the handler, and echo it on the response so the client can
    correlate.

    Mount BEFORE the principal resolver so every audit entry written
    by downstream middleware (auth, authz, log_event in handlers)
    automatically inherits the trace id.

    Round-2 audit NEW-MED-11 — exceptions raised inside the handler
    are converted to a stable ``{"error": "internal"}`` response so
    the default aiohttp error pages can't leak details.
    """

    @web.middleware
    async def trace_mw(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        from aria.security.trace_context import (
            new_trace_id, set_trace_id, reset_trace_id,
        )
        incoming = (request.headers.get(header_name) or "").strip()
        # Defence: reject obviously-bogus values so an attacker can't
        # poison the audit log with a controlled correlation key.
        # Format: ``trc_`` + 16 hex chars (ARIA-mint) OR upstream
        # OpenTelemetry trace-id (32 hex chars).  Audit LOW-5: explicit
        # branching (no ambiguous boolean order-of-precedence trap).
        if not incoming:
            accepted = False
        elif incoming.startswith("trc_"):
            accepted = (len(incoming) == 4 + 16
                        and all(c in "0123456789abcdef" for c in incoming[4:]))
        elif len(incoming) == 32:
            accepted = all(c in "0123456789abcdef" for c in incoming)
        else:
            accepted = False
        trace_id = incoming if accepted else new_trace_id()
        token = set_trace_id(trace_id)
        request["trace_id"] = trace_id
        try:
            response = await handler(request)
        except web.HTTPException:
            reset_trace_id(token)
            raise
        except Exception as exc:    # noqa: BLE001
            reset_trace_id(token)
            logger.exception("trace_mw.handler_exception",
                             trace_id=trace_id, exc_type=type(exc).__name__)
            return web.json_response(
                {"error": "internal", "trace_id": trace_id}, status=500,
            )
        try:
            response.headers[header_name] = trace_id
        except Exception:
            pass
        reset_trace_id(token)
        return response

    return trace_mw


# ── Soft principal resolver (for the live dashboard) ─────────────


def make_principal_resolver_middleware(
) -> Callable[..., Awaitable[web.StreamResponse]]:
    """Resolve Bearer → Principal and ALWAYS attach to ``request``.

    Unlike ``make_auth_middleware``, this never 401s on its own —
    missing or invalid tokens yield ``Principal.anonymous()``. The
    permission gate (``make_route_permission_middleware`` or per-handler
    ``@require_permission``) does the actual access control.

    Use this on the live dashboard so handlers can always read
    ``request['principal']`` without conditional plumbing.

    Round-2 audit NEW-CRIT-3 — passes the client fingerprint to
    ``touch()`` so HIGH-6 binding actually fires.
    """

    @web.middleware
    async def resolver(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        token = _extract_bearer_token(request)
        principal: Optional[Principal] = None
        session: Optional[Session] = None
        if token:
            ip_h, ua_h = _client_fingerprint(request)
            session = get_session_store().touch(
                token, ip_hash=ip_h, ua_hash=ua_h,
            )
            if session is not None:
                principal = principal_from_session(session)
        if principal is None:
            principal = Principal.anonymous()
        request["principal"] = principal
        request["session"] = session
        return await handler(request)

    return resolver


# ── Route-permission middleware ──────────────────────────────────


# Public alias for the lookup table — keys are (METHOD, canonical_path).
RoutePermMap = Mapping[Tuple[str, str], str]


def make_route_permission_middleware(
    route_perms: RoutePermMap,
    *,
    enforced: bool = True,
    default_get_perm: str = UNMAPPED_ROUTE_PERMISSION,
    default_mutating_perm: str = UNMAPPED_ROUTE_PERMISSION,
    anonymous_paths: Iterable[str] = DEFAULT_ANONYMOUS_PREFIXES,
) -> Callable[..., Awaitable[web.StreamResponse]]:
    """Permission-gate every handler by route lookup.

    ``route_perms`` maps (HTTP method, canonical path) to a permission
    name. Canonical path = the registered route pattern, e.g.
    ``/api/snapshot/{year}`` (not the resolved ``/api/snapshot/2042``).

    Round-2 audit NEW-HIGH-15 — both default permissions default to a
    sentinel string no role holds.  Any unmapped route therefore
    deny-by-default.  Operators must explicitly override the defaults
    if they want a permissive default (strongly discouraged).

    Round-2 audit NEW-HIGH-16 — production deploys must set
    ``enforced=True``.  ``is_production() and not enforced`` raises at
    construction time.

    Round-2 audit NEW-HIGH-18 — deny logs the stable code only, never
    the raw role/reason text.
    """
    from aria.security.env import is_production
    if is_production() and not enforced:
        raise RuntimeError(
            "middleware.route_perm.enforced_required — production deploys "
            "must run with enforced=True; refuse to start with auth disabled"
        )

    anon = tuple(anonymous_paths)

    @web.middleware
    async def gate(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        path = request.path or "/"
        if _path_in(anon, path):
            return await handler(request)
        if not enforced:
            return await handler(request)
        principal: Principal = request.get(  # type: ignore[assignment]
            "principal", Principal.anonymous(),
        )
        # Look up permission by route pattern when available, else by
        # resolved path (handles add_static and similar).
        canonical = path
        match = request.match_info.route
        if match is not None:
            res = match.resource
            if res is not None:
                canonical = res.canonical
        key = (request.method.upper(), canonical)
        perm = route_perms.get(key)
        if perm is None:
            if request.method.upper() in ("GET", "HEAD"):
                perm = default_get_perm
            else:
                perm = default_mutating_perm
        decision = authorize(principal, perm)
        if not decision.allow:
            # NEW-HIGH-18 — stable code only; no role / reason text.
            log_event(
                event_type="authz",
                identity=principal.principal_id,
                action=f"{perm} on {request.method} {canonical}",
                result="denied",
                details={"deny_reason_code": _reason_to_code(decision.reason)},
            )
            if principal.role == "anonymous":
                return _unauthorized_response()
            return _forbidden_response("permission denied")
        return await handler(request)

    return gate


# ── Helpers for handlers ──────────────────────────────────────────


def get_request_principal(request: web.Request) -> Principal:
    """Return the Principal attached by the resolver middleware.
    Defaults to anonymous if (somehow) missing."""
    p = request.get("principal")
    if isinstance(p, Principal):
        return p
    return Principal.anonymous()
