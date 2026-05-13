"""Authentication service — challenge / login / logout for ship principals.

Implements the entry point of the command lifecycle described in
`docs/FAILSAFE_ARCHITECTURE.md` §F-9 and the identity model in
`src/aria/security/principals.py`.

Login flow (for crew / captain / maintainer with hardware key):

  1. Client: GET /api/auth/challenge?principal_id=<id>
     Server returns a 32-byte random nonce + expires_at (30 s window).

  2. Client signs ``challenge_payload(nonce, principal_id, expires_at)``
     with the hardware token's Ed25519 private key.

  3. Client: POST /api/auth/login
     {principal_id, nonce, signature_hex,
      duress_token (optional), recall_token (optional)}.
     Server verifies the signature against the principal's pinned
     public key (sealed roster), checks expiry / nonce one-shot, and
     issues a session.

  4. Subsequent requests: Authorization: Bearer <session_token>.

Anti-features:
  * Per-IP login throttling lives in ``security/rate_limiter.py``.
  * Per-(IP, principal_id) challenge-issue throttling here too
    (round-2 audit NEW-HIGH-14) so a flood cannot grow the in-memory
    challenge table without bound.
  * Replay defence: nonce is one-shot, server-side, 30 s window.
  * Duress: a different `duress_token` triggers `Session.duress=True`
    which the role-store caps at SENSOR_ONLY.
  * No password fallback — hardware key is mandatory for human roles.

Implements §F-1 (sealed root of trust), §F-9 (principal-aware actions),
§F-19 (per-session monotonic counter).

Round-2 audit hardening (2026-04-27 R2):
  - ``login`` accepts optional ``client_ip`` + ``client_ua``; passes
    fingerprints to ``SessionStore.create`` so HIGH-6 actually fires
    (NEW-CRIT-3).
  - ``logout`` returns the same shape regardless of token validity
    (NEW-HIGH-13 — token-validity oracle closed).
  - ``issue_challenge`` per-IP and per-principal rate-limited
    (NEW-HIGH-14).
  - Pubkey fingerprint is stamped into the new session so a key
    rotation invalidates outstanding sessions (NEW-MED-15).
"""

from __future__ import annotations

import collections
import hashlib
import os
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

import structlog

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from aria.security.principals import (
    Principal,
    get_principal_store,
)
from aria.security.session_store import (
    Session,
    SessionStore,
    fingerprint_ip,
    fingerprint_ua,
    get_session_store,
)

logger = structlog.get_logger()


# ── Constants ─────────────────────────────────────────────────────


# Challenge nonce TTL — 30 s. ESTIMATE: long enough for a deliberate
# ship-side login (network round-trip + biometric prompt), short enough
# that a stolen challenge is useless before the attacker can sign it.
CHALLENGE_TTL_S = 30.0
NONCE_BYTES = 32

# Round-2 audit NEW-HIGH-14 — per-IP challenge issuance ceiling.
# Keeps the in-memory ``_challenges`` table bounded under flood.
_CHALLENGE_RATE_PER_IP_PER_MIN = 30
_CHALLENGE_RATE_PER_PRINCIPAL_PER_MIN = 30
_MAX_OUTSTANDING_CHALLENGES = 50_000
# Round-3 audit R3-HIGH-1 — bound the issue-rate dicts so an attacker
# rotating principal_id strings cannot grow them without bound.
_MAX_RATE_LIMITER_KEYS = 100_000


# ── Challenge ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Challenge:
    nonce: str
    principal_id: str
    expires_at: float

    def signing_payload(self) -> bytes:
        return f"{self.nonce}|{self.principal_id}|{self.expires_at}".encode()


def challenge_payload(nonce: str, principal_id: str, expires_at: float) -> bytes:
    """Public helper so a client can compute the same payload to sign."""
    return Challenge(nonce=nonce, principal_id=principal_id,
                     expires_at=expires_at).signing_payload()


# ── Errors ────────────────────────────────────────────────────────


class AuthError(RuntimeError):
    """Login refused. The reason string is auditable; do not return it
    to the wire — return a fixed-shape "auth refused" so an attacker
    cannot probe for valid principal_ids."""


class ChallengeRateLimited(AuthError):
    """Anonymous flood detected on /api/auth/challenge."""


# ── Service ──────────────────────────────────────────────────────


def _pubkey_fingerprint(pubkey_hex: str) -> str:
    """Round-3 audit R3-CRIT-3 — raises on bad/missing pubkey so a
    silently-empty fingerprint cannot let ``principal_from_session``
    fail-open after a key rotation."""
    if not pubkey_hex:
        raise ValueError("pubkey_missing")
    try:
        return hashlib.sha256(bytes.fromhex(pubkey_hex)).hexdigest()[:32]
    except ValueError as exc:
        raise ValueError("pubkey_not_hex") from exc


class AuthService:
    """Stateless wrapper over PrincipalStore + SessionStore + a tiny
    nonce table. The nonce table is in-memory; a process restart
    invalidates outstanding challenges (acceptable — short TTL)."""

    def __init__(self, sessions: Optional[SessionStore] = None) -> None:
        # Wiring audit Pass 3 (F13.6) — production deploys MUST set
        # ARIA_RUNTIME_DIR so SessionStore's revocation list and
        # session counters land in the operator-managed runtime
        # directory rather than the package-rel default (which is
        # often shared across dev runs and could leak revocation
        # state from one deploy to another).
        if (
            sessions is None
            and os.environ.get("ARIA_ENVIRONMENT", "development") == "production"
            and not os.environ.get("ARIA_RUNTIME_DIR", "").strip()
        ):
            logger.critical(
                "auth_service.production_runtime_dir_missing",
                impact="SessionStore would persist revocation state to the "
                       "package-rel default directory; production deploys "
                       "must set ARIA_RUNTIME_DIR — refusing to start",
            )
            raise RuntimeError(
                "AuthService refuses to construct a default SessionStore "
                "in production (set ARIA_RUNTIME_DIR)"
            )

        # NOTE: explicit ``is not None`` — SessionStore defines
        # ``__len__`` so an empty store is falsy under
        # ``sessions or get_session_store()``.
        self._sessions = sessions if sessions is not None else get_session_store()
        self._lock = threading.RLock()
        # nonce -> (principal_id, expires_at)
        self._challenges: Dict[str, Tuple[str, float]] = {}
        # Round-3 audit R3-HIGH-1 — LRU `OrderedDict` so flooding with
        # rotating IPs / principal_id strings cannot grow the dict
        # past ``_MAX_RATE_LIMITER_KEYS``.
        self._issue_by_ip: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._issue_by_pid: "OrderedDict[str, Deque[float]]" = OrderedDict()

    # ── Challenge ────────────────────────────────────────────────

    def issue_challenge(
        self,
        principal_id: str,
        *,
        client_ip: str = "",
    ) -> Challenge:
        """Mint a fresh nonce for the named principal.

        Always returns a Challenge — even for unknown principals — so
        that an attacker probing principal_ids cannot distinguish valid
        from invalid by timing or response shape. The login step is
        where we actually validate the principal exists.

        Round-2 audit NEW-HIGH-14 — per-IP and per-principal rate
        limits are enforced; if either bucket is full, raise
        ``ChallengeRateLimited`` so the HTTP layer can return 429.
        """
        nonce = secrets.token_hex(NONCE_BYTES)
        exp = time.time() + CHALLENGE_TTL_S
        with self._lock:
            self._gc_challenges_locked()
            if not self._allow_issue_locked(client_ip, principal_id):
                raise ChallengeRateLimited(
                    "challenge_rate_limited",
                )
            if len(self._challenges) >= _MAX_OUTSTANDING_CHALLENGES:
                # Flood is severe enough that even per-bucket limits are
                # not draining fast enough; refuse to allocate.
                raise ChallengeRateLimited("challenge_table_full")
            self._challenges[nonce] = (principal_id, exp)
        return Challenge(nonce=nonce, principal_id=principal_id,
                         expires_at=exp)

    @staticmethod
    def _evict_oldest(d: OrderedDict, max_size: int) -> None:
        while len(d) >= max_size:
            d.popitem(last=False)

    def _allow_issue_locked(self, client_ip: str, principal_id: str) -> bool:
        """Round-3 audit R3-HIGH-1 — both LRU dicts are size-capped so
        flooding with rotating identifiers can't grow memory."""
        now = time.time()
        if client_ip:
            q = self._issue_by_ip.get(client_ip)
            if q is None:
                self._evict_oldest(self._issue_by_ip, _MAX_RATE_LIMITER_KEYS)
                q = collections.deque()
                self._issue_by_ip[client_ip] = q
            while q and now - q[0] > 60.0:
                q.popleft()
            self._issue_by_ip.move_to_end(client_ip)
            if len(q) >= _CHALLENGE_RATE_PER_IP_PER_MIN:
                return False
            q.append(now)
        q2 = self._issue_by_pid.get(principal_id)
        if q2 is None:
            self._evict_oldest(self._issue_by_pid, _MAX_RATE_LIMITER_KEYS)
            q2 = collections.deque()
            self._issue_by_pid[principal_id] = q2
        while q2 and now - q2[0] > 60.0:
            q2.popleft()
        self._issue_by_pid.move_to_end(principal_id)
        if len(q2) >= _CHALLENGE_RATE_PER_PRINCIPAL_PER_MIN:
            return False
        q2.append(now)
        return True

    def _gc_challenges_locked(self) -> None:
        now = time.time()
        expired = [n for n, (_, e) in self._challenges.items() if e < now]
        for n in expired:
            self._challenges.pop(n, None)

    def _consume_challenge(self, nonce: str, principal_id: str,
                           ) -> Optional[Challenge]:
        """Pop the matching challenge if it's still valid; else None.

        One-shot semantics: even a *valid* challenge can be used at
        most once. Replay impossible.
        """
        with self._lock:
            entry = self._challenges.pop(nonce, None)
        if entry is None:
            return None
        bound_pid, exp = entry
        if bound_pid != principal_id:
            return None
        if time.time() > exp:
            return None
        return Challenge(nonce=nonce, principal_id=principal_id,
                         expires_at=exp)

    # ── Login ────────────────────────────────────────────────────

    def login(
        self,
        principal_id: str,
        nonce: str,
        signature_hex: str,
        *,
        duress: bool = False,
        client_ip: str = "",
        client_ua: str = "",
    ) -> Session:
        """Verify the signed challenge and issue a session.

        Raises AuthError on any failure. The reason is logged but only
        a generic 'auth refused' should be returned to the client.

        Round-2 audit NEW-CRIT-3 — ``client_ip`` and ``client_ua`` are
        hashed and stored on the Session so subsequent requests are
        bound to the originating client.

        Round-2 audit NEW-MED-15 — the principal's current pubkey
        fingerprint is stamped onto the session so a key rotation
        invalidates the outstanding session.
        """
        # 1. Consume the challenge (one-shot + bound to principal_id).
        ch = self._consume_challenge(nonce, principal_id)
        if ch is None:
            logger.warning("auth.challenge_invalid", principal_id=principal_id)
            raise AuthError("challenge invalid or expired")

        # 2. Look up the principal.
        store = get_principal_store()
        principal = store.get(principal_id)
        if principal is None:
            logger.warning("auth.unknown_principal", principal_id=principal_id)
            raise AuthError("unknown principal")
        if principal.is_expired():
            logger.warning("auth.expired_cert", principal_id=principal_id)
            raise AuthError("principal certificate expired")
        if not principal.pubkey_hex:
            logger.error("auth.principal_no_pubkey", principal_id=principal_id)
            raise AuthError("principal has no signing key")

        # 3. Verify Ed25519 signature on the challenge payload.
        try:
            sig = bytes.fromhex(signature_hex)
        except ValueError:
            raise AuthError("signature not hex")
        try:
            pub = Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(principal.pubkey_hex),
            )
            pub.verify(sig, ch.signing_payload())
        except (InvalidSignature, ValueError) as exc:
            logger.warning("auth.signature_invalid",
                           principal_id=principal_id, error=str(exc))
            raise AuthError("signature invalid") from exc

        # 4. Issue session — bound to client + key fingerprint.
        # Round-3 audit R3-CRIT-3 — _pubkey_fingerprint raises if the
        # principal's pubkey is missing or malformed; we catch and
        # refuse the login rather than silently issue a session with
        # an empty fingerprint.
        try:
            pubkey_fp = _pubkey_fingerprint(principal.pubkey_hex)
        except ValueError as exc:
            logger.error("auth.principal_pubkey_unparseable",
                         principal_id=principal.principal_id, reason=str(exc))
            raise AuthError("principal pubkey unparseable") from exc
        s = self._sessions.create(
            principal_id=principal.principal_id,
            role=principal.role,
            duress=duress,
            client_ip_hash=fingerprint_ip(client_ip),
            client_ua_hash=fingerprint_ua(client_ua),
            pubkey_fingerprint=pubkey_fp,
        )
        logger.info("auth.login_ok",
                    principal_id=principal.principal_id,
                    role=principal.role, duress=duress)
        # R35: write an audit entry so every successful login is on
        # the hash-chained log + carries the request's trace_id.
        try:
            from aria.security.audit import log_event
            log_event(
                event_type="auth",
                identity=principal.principal_id,
                action="login",
                result="accepted",
                details={"role": principal.role, "duress": duress},
                severity="warning" if duress else "info",
                source="auth_service",
            )
        except Exception:
            pass
        return s

    # ── Logout ───────────────────────────────────────────────────

    def logout(self, session_token: str) -> None:
        """Round-2 audit NEW-HIGH-13 — return value intentionally void
        so callers cannot accidentally surface a token-validity oracle
        to the wire.  The actual revocation outcome is in the audit
        log only.
        """
        existed = self._sessions.revoke(session_token, reason="logout")
        if existed:
            logger.info("auth.logout_ok")
        else:
            logger.info("auth.logout_no_active_session")


# ── Singleton ────────────────────────────────────────────────────


_INSTANCE: Optional[AuthService] = None
_LOCK = threading.RLock()


def get_auth_service() -> AuthService:
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = AuthService()
    return _INSTANCE


def reset_for_test(sessions: Optional[SessionStore] = None) -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = AuthService(sessions=sessions)


# ── Helpers for resolving a session into a Principal ─────────────


def principal_from_session(s: Session) -> Optional[Principal]:
    """Re-fetch the verified Principal from the store using the
    session's principal_id. Re-fetch (don't cache) so role changes /
    revocations take effect mid-session.

    Round-2 audit NEW-MED-15 — if the session pinned a pubkey
    fingerprint and the principal's current pubkey fingerprint differs,
    treat the session as no longer valid (a key rotation).
    """
    if s is None:
        return None
    store = get_principal_store()
    p = store.get(s.principal_id)
    if p is None:
        return None
    # Round-3 audit R3-CRIT-3 — if the session has a pinned
    # fingerprint we MUST be able to recompute one for the live
    # principal; an empty live fingerprint (bad/missing pubkey) is
    # fail-closed, not fail-open.
    if s.pubkey_fingerprint:
        try:
            live_fp = _pubkey_fingerprint(p.pubkey_hex)
        except ValueError:
            logger.warning("auth.session_pubkey_unparseable",
                           principal_id=s.principal_id)
            return None
        if live_fp != s.pubkey_fingerprint:
            logger.warning("auth.session_pubkey_rotated",
                           principal_id=s.principal_id)
            return None
    if s.duress:
        # Stamp the duress flag onto the live Principal so authorize()
        # downgrades it.
        return Principal(
            principal_id=p.principal_id, role=p.role,
            pubkey_hex=p.pubkey_hex, display_name=p.display_name,
            created_at=p.created_at, expires_at=p.expires_at,
            duress=True,
        )
    return p
