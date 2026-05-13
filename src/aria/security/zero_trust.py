"""Zero-Trust Architecture for ARIA inter-service communication.

Principle: Never trust, always verify. Every inter-service call is
authenticated even if it comes from "inside" the ARIA process.

Why this matters for Mythos:
  Once Mythos gains a foothold in one component (e.g., through a sensor
  data injection), it can attempt lateral movement. Without zero-trust,
  an ARIA subsystem that trusts other ARIA subsystems creates a pivot
  point: compromise one, compromise all.

  With zero-trust, every call from PowerAgent to ECLSSAgent must carry
  a valid signed credential. Mythos cannot forge credentials without the
  private key, and cannot replay credentials (sequence numbers).

Service mesh:
  Each ARIA subsystem registers its identity with ServiceRegistry.
  All inter-service calls carry a ServiceToken (signed JWT-like structure).
  ZeroTrustVerifier validates every token before allowing the call.

Trust levels:
  INTERNAL:   ARIA agents running in the same process (highest)
  OPERATOR:   Human operators with a session token (medium)
  GROUND:     Ground control commands (medium)
  EXTERNAL:   Sensor data, external APIs (lowest — always sanitized)
  UNTRUSTED:  Unauthenticated / failed verification
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional, Set

import structlog

from aria.security.pqc import SignatureScheme, constant_time_compare

logger = structlog.get_logger()


class TrustLevel(IntEnum):
    UNTRUSTED = 0
    EXTERNAL = 1
    GROUND = 2
    OPERATOR = 3
    INTERNAL = 4


@dataclass
class ServiceToken:
    """Signed inter-service authentication token."""
    issuer: str          # Service name issuing this token
    audience: str        # Target service this token is valid for
    trust_level: int     # TrustLevel enum value
    issued_at: float
    expires_at: float
    nonce: str           # Random 128-bit nonce (replay prevention)
    signature: bytes     # Ed25519 signature over canonical payload

    def canonical_payload(self) -> bytes:
        d = {
            "issuer": self.issuer,
            "audience": self.audience,
            "trust_level": self.trust_level,
            "issued_at": f"{self.issued_at:.3f}",
            "expires_at": f"{self.expires_at:.3f}",
            "nonce": self.nonce,
        }
        return json.dumps(d, sort_keys=True).encode()


@dataclass
class ServiceIdentity:
    """Registered identity for an ARIA subsystem."""
    name: str
    trust_level: TrustLevel
    public_key: bytes
    private_key: bytes
    allowed_callers: Set[str]   # which services may call this one


class ServiceRegistry:
    """Manages registered service identities and cross-service trust policies.

    All ARIA agents register here at startup. The registry is the single
    source of truth for which service can call which other service.
    """

    def __init__(self) -> None:
        self._services: Dict[str, ServiceIdentity] = {}
        self._sig = SignatureScheme()
        self._used_nonces: Set[str] = set()  # replay detection
        self._nonce_expiry: Dict[str, float] = {}

    def register(
        self,
        name: str,
        trust_level: TrustLevel = TrustLevel.INTERNAL,
        allowed_callers: Optional[Set[str]] = None,
    ) -> ServiceIdentity:
        """Register a service identity and generate its key pair."""
        pub, priv = self._sig.generate()
        identity = ServiceIdentity(
            name=name,
            trust_level=trust_level,
            public_key=pub,
            private_key=priv,
            allowed_callers=allowed_callers or set(),
        )
        self._services[name] = identity
        logger.info("zero_trust.service_registered", service=name, trust=trust_level.name)
        return identity

    def issue_token(
        self,
        issuer_name: str,
        audience_name: str,
        ttl_s: float = 300.0,
    ) -> Optional[ServiceToken]:
        """Issue a signed token from issuer to audience (5-min TTL default)."""
        issuer = self._services.get(issuer_name)
        if issuer is None:
            logger.warning("zero_trust.unknown_issuer", issuer=issuer_name)
            return None

        import secrets as _sec
        nonce = _sec.token_hex(16)
        now = time.time()
        token = ServiceToken(
            issuer=issuer_name,
            audience=audience_name,
            trust_level=int(issuer.trust_level),
            issued_at=now,
            expires_at=now + ttl_s,
            nonce=nonce,
            signature=b"",
        )
        token.signature = SignatureScheme.sign(issuer.private_key, token.canonical_payload())
        return token

    def verify_token(self, token: ServiceToken, expected_audience: str) -> TrustLevel:
        """Verify token signature, expiry, replay, and audience match.

        Returns the token's TrustLevel on success, UNTRUSTED on any failure.
        """
        if token.audience != expected_audience:
            logger.warning(
                "zero_trust.audience_mismatch",
                expected=expected_audience,
                got=token.audience,
            )
            return TrustLevel.UNTRUSTED

        now = time.time()
        if now > token.expires_at:
            logger.warning("zero_trust.token_expired", issuer=token.issuer, age=now - token.expires_at)
            return TrustLevel.UNTRUSTED

        if token.issued_at > now + 10:
            logger.warning("zero_trust.token_from_future", issuer=token.issuer)
            return TrustLevel.UNTRUSTED

        if token.nonce in self._used_nonces:
            logger.warning("zero_trust.replay_detected", issuer=token.issuer, nonce=token.nonce[:8])
            return TrustLevel.UNTRUSTED
        self._used_nonces.add(token.nonce)
        self._nonce_expiry[token.nonce] = token.expires_at

        issuer = self._services.get(token.issuer)
        if issuer is None:
            logger.warning("zero_trust.unknown_issuer_on_verify", issuer=token.issuer)
            return TrustLevel.UNTRUSTED

        if not SignatureScheme.verify(issuer.public_key, token.canonical_payload(), token.signature):
            logger.warning("zero_trust.invalid_signature", issuer=token.issuer)
            return TrustLevel.UNTRUSTED

        return TrustLevel(token.trust_level)

    def is_call_authorized(
        self,
        caller: str,
        target: str,
        min_trust: TrustLevel = TrustLevel.INTERNAL,
    ) -> bool:
        """Policy check: can caller invoke target?"""
        target_svc = self._services.get(target)
        if target_svc is None:
            return False
        if target_svc.allowed_callers and caller not in target_svc.allowed_callers:
            logger.warning(
                "zero_trust.caller_not_allowed",
                caller=caller,
                target=target,
                allowed=list(target_svc.allowed_callers),
            )
            return False
        caller_svc = self._services.get(caller)
        if caller_svc is None:
            return False
        return caller_svc.trust_level >= min_trust

    def expire_nonces(self) -> None:
        """Purge expired nonces from replay cache (call periodically)."""
        now = time.time()
        expired = [n for n, exp in self._nonce_expiry.items() if exp < now]
        for n in expired:
            self._used_nonces.discard(n)
            del self._nonce_expiry[n]


class ZeroTrustGuard:
    """Per-service guard that wraps calls with token verification.

    Usage:
        guard = ZeroTrustGuard(registry, my_service_name)
        trust = guard.verify_incoming(token)
        if trust < TrustLevel.INTERNAL:
            raise PermissionError("Untrusted caller")
    """

    def __init__(self, registry: ServiceRegistry, service_name: str) -> None:
        self._registry = registry
        self._name = service_name

    def verify_incoming(self, token: ServiceToken) -> TrustLevel:
        """Verify an incoming service token. Returns trust level."""
        level = self._registry.verify_token(token, self._name)
        if level == TrustLevel.UNTRUSTED:
            logger.warning("zero_trust.access_denied", target=self._name, issuer=token.issuer)
        return level

    def make_token(self, target_service: str, ttl_s: float = 300.0) -> Optional[ServiceToken]:
        """Issue a token for calling another service."""
        return self._registry.issue_token(self._name, target_service, ttl_s)

    def require_trust(self, token: ServiceToken, min_level: TrustLevel) -> None:
        """Raise PermissionError if token doesn't meet minimum trust level."""
        level = self.verify_incoming(token)
        if level < min_level:
            raise PermissionError(
                f"Access denied: {token.issuer} → {self._name} "
                f"(got {level.name}, need {min_level.name})"
            )


# Module-level registry singleton
_registry: Optional[ServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry
