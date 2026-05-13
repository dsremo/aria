"""ARIA Security — layered defense from human to quantum-scale adversaries.

Layer 1 — Basic human attacks:
    CommandAuthenticator, InputSanitizer,
    CanaryRegistry (URL honeypots, scanner signature detection),
    PerIPRateLimiter (in `aria.api.per_ip_rate_limiter`)

Layer 2 — Skilled attackers (MITM, replay, credential stuffing):
    CommandAuthenticator (HMAC + monotonic counter + time window),
    SecureChannel (X25519 key exchange + AES-256-GCM),
    AuditLog (tamper-evident hash chain),
    PerIPRateLimiter (sliding window + exponential backoff,
    persisted across restart per Pass 7 F5.3)

Layer 3 — Mythos-class AI (autonomous exploit chaining, 80% success rate):
    AnomalyDetector (CUSUM velocity, Shannon entropy, Poisson regularity),
    CanaryRegistry (honeypot endpoints triggered by auto-scanners),
    ZeroTrustGuard (every inter-service call signed + verified),
    ToolResultSanitizer (prevents prompt injection via telemetry data)

Layer 4 — Quantum adversaries:
    HybridKEM (X25519 + MLKEM-768 when available; SHA3-256 KDF),
    SymmetricEncryptor (AES-256-GCM; quantum-safe per NIST SP 800-131B),
    SignatureScheme (Ed25519; upgrade path to ML-DSA documented),
    AuditLog (SHA-256 hash chain; 128-bit quantum security via Grover's bound)
"""

from aria.security.anomaly import AnomalyDetector, AnomalySignal
from aria.security.audit import (
    AuditLog,
    AuditEntry,
    get_audit_log,
    log_event,
    verify_at_boot as verify_audit_at_boot,
)
from aria.security.audit_bus_mirror import (
    AuditBusMirror,
    DEFAULT_ALWAYS_AUDIT_PREFIXES,
    DEFAULT_ALWAYS_AUDIT_SUBSTRINGS,
    get_audit_bus_mirror,
    start_audit_bus_mirror,
)
from aria.security.trace_context import (
    current_trace_id,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
    trace_scope,
)
from aria.security.auth import CommandAuthenticator, AuthResult, CommandCredential
from aria.security.canary import CanaryRegistry, CanaryHit, HoneypotResponder, get_default_registry
from aria.security.pqc import (
    HybridKEM,
    SignatureScheme,
    SymmetricEncryptor,
    SecureChannel,
    generate_session_key,
    constant_time_compare,
)
from aria.security.auth_service import (
    AuthError,
    AuthService,
    Challenge,
    challenge_payload,
    get_auth_service,
    principal_from_session,
)
from aria.security.middleware import (
    DEFAULT_ANONYMOUS_PREFIXES,
    RoutePermMap,
    get_request_principal,
    make_auth_middleware,
    make_principal_resolver_middleware,
    make_route_permission_middleware,
    make_trace_middleware,
    require_permission,
)
from aria.security.principals import (
    Principal,
    Role,
    Decision,
    AuthorityCeiling,
    TrustTier,
    authorize,
    trust_tier_for,
    authority_ceiling_for,
    authority_rank,
    get_principal_store,
    get_role_store,
)
from aria.security.session_store import (
    Session,
    SessionStore,
    get_session_store,
)
# aria.security.rate_limiter deleted Pass 3 F14.15c — duplicated
# aria.api.per_ip_rate_limiter (the actually-used limiter, hardened in
# Pass 7 F5.3 with persistence + LRU-skip-blocked).
from aria.security.sanitizer import InputSanitizer, ToolResultSanitizer, SanitizeResult
from aria.security.zero_trust import (
    TrustLevel,
    ServiceRegistry,
    ServiceToken,
    ZeroTrustGuard,
    get_registry,
)
from aria.security.guard import (
    BootCheckResult,
    ContentTypeRejected,
    GuardError,
    HardenConfig,
    JSONTooDeep,
    PickleBlocked,
    ResponseTooLarge,
    SSRFBlocked,
    XMLDisallowed,
    ZipUnsafe,
    harden_aiohttp_app,
    make_body_size_middleware,
    make_method_guard_middleware,
    make_request_id_middleware,
    make_security_headers_middleware,
    mfa_admin_check,
    runtime_check_environment,
    safe_json_loads,
    safe_open_url,
    safe_pickle_block,
    safe_xml_fromstring,
    safe_xml_parse,
    safe_yaml_load,
    safe_zip_extract,
    safe_zip_open,
    sanitise_for_log,
    validate_outbound_url,
)

__all__ = [
    # Layer 1
    "CommandAuthenticator", "AuthResult", "CommandCredential",
    "InputSanitizer", "ToolResultSanitizer", "SanitizeResult",
    # RateLimiter / RateLimitResult / TarpitMiddleware removed Pass 3
    # F14.15c (use aria.api.per_ip_rate_limiter.PerIPRateLimiter).
    "CanaryRegistry", "CanaryHit", "HoneypotResponder", "get_default_registry",
    # Layer 2-3
    "AuditLog", "AuditEntry", "get_audit_log", "log_event",
    "verify_audit_at_boot",
    "AuditBusMirror", "get_audit_bus_mirror", "start_audit_bus_mirror",
    "DEFAULT_ALWAYS_AUDIT_PREFIXES", "DEFAULT_ALWAYS_AUDIT_SUBSTRINGS",
    # R35 trace_id propagation
    "current_trace_id", "new_trace_id", "trace_scope",
    "set_trace_id", "reset_trace_id",
    "AnomalyDetector", "AnomalySignal",
    "TrustLevel", "ServiceRegistry", "ServiceToken", "ZeroTrustGuard", "get_registry",
    # Layer 4
    "HybridKEM", "SignatureScheme", "SymmetricEncryptor", "SecureChannel",
    "generate_session_key", "constant_time_compare",
    # Identity / RBAC (R32)
    "Principal", "Role", "Decision", "AuthorityCeiling", "TrustTier",
    "authorize", "trust_tier_for", "authority_ceiling_for", "authority_rank",
    "get_principal_store", "get_role_store",
    # Sessions + auth service (R32 Phase 2)
    "Session", "SessionStore", "get_session_store",
    "AuthService", "AuthError", "Challenge", "challenge_payload",
    "get_auth_service", "principal_from_session",
    # aiohttp middleware
    "make_auth_middleware", "require_permission", "get_request_principal",
    "make_principal_resolver_middleware", "make_route_permission_middleware",
    "make_trace_middleware",
    "RoutePermMap", "DEFAULT_ANONYMOUS_PREFIXES",
    # R50 guard library
    "GuardError", "SSRFBlocked", "ResponseTooLarge", "ContentTypeRejected",
    "XMLDisallowed", "JSONTooDeep", "ZipUnsafe", "PickleBlocked",
    "validate_outbound_url", "safe_open_url",
    "safe_xml_fromstring", "safe_xml_parse",
    "safe_json_loads", "safe_zip_extract", "safe_zip_open",
    "safe_pickle_block", "safe_yaml_load",
    "sanitise_for_log", "mfa_admin_check",
    "make_security_headers_middleware", "make_body_size_middleware",
    "make_method_guard_middleware", "make_request_id_middleware",
    "HardenConfig", "harden_aiohttp_app",
    "BootCheckResult", "runtime_check_environment",
]
