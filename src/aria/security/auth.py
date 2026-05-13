"""Command Authentication — multi-factor auth for spacecraft commands.

Three factors (every one mandatory for the wire path; only the
process-private internal channel may bypass and only with a
process-bound HMAC handshake):

  1. Identity verification (who is issuing the command — derived from
     the verified session, NOT from a caller-supplied string).
  2. Command counter (replay protection — must be > previous).
  3. Time window (command freshness — bounded skew, no abs()).

For Captain commands: identity verified via session token, issuer is
re-derived server-side from the session record.

For ground commands: Ed25519 / HMAC signature on (command_data) +
counter + bounded time window.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger()


# Defaults that are well-known and therefore refused at construction
# time when the operator forgets to inject a strong secret.
_BANNED_SHARED_SECRETS = {
    "aria-default-secret", "aria-dev-secret", "default", "secret",
    "changeme", "admin", "password", "test", "dev", "",
}
# Minimum entropy floor for the shared secret (UTF-8 byte length).
# 32 bytes = 256-bit; matches HMAC-SHA-256 block half.
_SHARED_SECRET_MIN_BYTES = 32

# Bound the in-memory tables so an attacker who can vary the issuer
# string or flood sessions cannot exhaust process memory (round-2
# audit NEW-HIGH-2).
_MAX_ACTIVE_SESSIONS = 100_000
_MAX_TRACKED_ISSUERS = 100_000

# Maximum clock skew tolerated for ground-mint timestamps (round-2
# audit NEW-CRIT-6).  ``time.time() - timestamp`` is signed; future
# values past this skew are rejected exactly like stale ones.
_MAX_CLOCK_SKEW_S = 30.0

# Internal-channel HMAC handshake: the agent runner mints this token at
# process start and must present it on every internal command.  It is
# never serialised to disk or to the wire (round-2 audit NEW-CRIT-1).
#
# Round-3 audit R3-CRIT-1 / R3-CRIT-2 — the mint API is one-shot.  Any
# subsequent caller that wants to verify gets the token through the
# verification API only; they cannot retrieve the bytes themselves.
# Tests (and only tests) reset via ``reset_internal_channel_token_for_test``.
_INTERNAL_CHANNEL_TOKEN: Optional[bytes] = None
_INTERNAL_CHANNEL_MINTED: bool = False
_INTERNAL_CHANNEL_LOCK = threading.RLock()


def mint_internal_channel_token() -> bytes:
    """Mint the process-only internal-channel token.  EXACTLY ONCE per
    process — subsequent calls raise ``RuntimeError``.  The caller is
    responsible for handing the bytes to the trusted internal agent
    runner; nobody else should ever see them.

    Round-3 audit R3-CRIT-1 / R3-CRIT-2 — making this one-shot means a
    later code path (debug endpoint, sandboxed Python, deserialiser
    that round-trips into this module) cannot retrieve the token by
    calling the function: it has already been consumed.

    Verification of an inbound credential's token is done with
    :func:`verify_internal_channel_token`, which returns a bool only.
    """
    global _INTERNAL_CHANNEL_TOKEN, _INTERNAL_CHANNEL_MINTED
    with _INTERNAL_CHANNEL_LOCK:
        if _INTERNAL_CHANNEL_MINTED:
            raise RuntimeError(
                "auth.internal_channel_already_minted — "
                "mint_internal_channel_token() may be called at most once "
                "per process"
            )
        _INTERNAL_CHANNEL_TOKEN = secrets.token_bytes(32)
        _INTERNAL_CHANNEL_MINTED = True
        return _INTERNAL_CHANNEL_TOKEN


def verify_internal_channel_token(presented: bytes) -> bool:
    """Constant-time check against the minted token.  Returns ``False``
    if no token has been minted yet (so an attacker who submits empty
    bytes before the agent runner boots is rejected) — and ``False``
    on mismatch.  Never returns the token bytes."""
    with _INTERNAL_CHANNEL_LOCK:
        expected = _INTERNAL_CHANNEL_TOKEN
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented, expected)


def reset_internal_channel_token_for_test() -> None:
    """Tests-only — reset the singleton so each test starts fresh."""
    global _INTERNAL_CHANNEL_TOKEN, _INTERNAL_CHANNEL_MINTED
    with _INTERNAL_CHANNEL_LOCK:
        _INTERNAL_CHANNEL_TOKEN = None
        _INTERNAL_CHANNEL_MINTED = False


def _reset_after_fork_in_child() -> None:
    """Autonomy audit F6 — invalidate the parent's token in the child
    process so a pre-fork worker model (gunicorn / uvicorn ``--workers``)
    cannot leak the parent's token across worker boundaries.  Each
    worker's ``post_fork`` hook calls ``mint_internal_channel_token()``
    afresh."""
    global _INTERNAL_CHANNEL_TOKEN, _INTERNAL_CHANNEL_MINTED
    with _INTERNAL_CHANNEL_LOCK:
        _INTERNAL_CHANNEL_TOKEN = None
        _INTERNAL_CHANNEL_MINTED = False


# Register the child-side reset hook once at module import time.  No-op
# on platforms that don't support it.
try:
    os.register_at_fork(after_in_child=_reset_after_fork_in_child)
except (AttributeError, OSError):
    pass


class AuthResult(Enum):
    ACCEPTED = "accepted"
    REJECTED_IDENTITY = "rejected_identity"
    REJECTED_REPLAY = "rejected_replay"
    REJECTED_EXPIRED = "rejected_expired"
    REJECTED_SIGNATURE = "rejected_signature"


@dataclass
class CommandCredential:
    """Credential attached to a command.

    NOTE: the ``issuer`` field is informational only — the
    authenticator re-derives the authoritative issuer from the
    verified session token (round-2 audit NEW-CRIT-2).  Do not use
    ``credential.issuer`` to make trust decisions in callers; ask
    the authenticator instead.
    """

    issuer: str  # informational; bound to session at create_session time
    session_token: str = ""
    command_counter: int = 0
    timestamp: float = 0.0
    signature: str = ""  # HMAC for now; Ed25519 in production
    # round-2 NEW-CRIT-1: trusted internal agents present this token to
    # bypass the wire-auth path.  Not serialised; in-process only.
    internal_channel_token: bytes = b""


class CommandAuthenticator:
    """Authenticates commands before execution.

    Prevents:
      - Replay attacks (mandatory monotonic counter).
      - Stale / future-dated commands (signed time window with bounded skew).
      - Unauthorised access (session validation; issuer is bound to session).
      - Tampered commands (HMAC signature, mandatory).
      - Free-form issuer spoofing (issuer derived from session, not header).
      - Memory exhaustion (bounded LRU dicts).
    """

    def __init__(
        self,
        shared_secret: str | None = None,
        max_command_age_s: float = 3600,    # 1 h replay window for ground-mint clocks (R8)
        max_clock_skew_s: float = _MAX_CLOCK_SKEW_S,
        max_active_sessions: int = _MAX_ACTIVE_SESSIONS,
        max_tracked_issuers: int = _MAX_TRACKED_ISSUERS,
    ) -> None:
        secret = shared_secret if shared_secret is not None else os.environ.get(
            "ARIA_CONSOLE_SECRET", ""
        )
        if (not secret) or secret.strip().lower() in _BANNED_SHARED_SECRETS:
            raise RuntimeError(
                "auth.shared_secret_missing — set ARIA_CONSOLE_SECRET to a "
                f"random string of at least {_SHARED_SECRET_MIN_BYTES} bytes "
                "(secrets.token_urlsafe(32))"
            )
        if len(secret.encode("utf-8")) < _SHARED_SECRET_MIN_BYTES:
            raise RuntimeError(
                f"auth.shared_secret_weak — must be ≥ {_SHARED_SECRET_MIN_BYTES} bytes"
            )
        self._secret = secret.encode("utf-8")
        self._max_age = max_command_age_s
        self._max_skew = max_clock_skew_s
        self._max_sessions = max_active_sessions
        self._max_issuers = max_tracked_issuers
        self._lock = threading.RLock()
        # OrderedDict-based LRU: oldest entry evicted on overflow.  Bounds
        # memory under issuer / session-token spam (NEW-HIGH-2).
        self._last_counter: "OrderedDict[str, int]" = OrderedDict()
        # token -> (expiry, issuer); issuer is server-derived (NEW-CRIT-2).
        self._active_sessions: "OrderedDict[str, tuple[float, str]]" = OrderedDict()

    # ── Session lifecycle ───────────────────────────────────────

    def create_session(self, issuer: str, duration_s: float = 86400) -> str:
        """Create an authenticated session for a user.

        Token is 256-bit OS-RNG output (URL-safe).  The store binds the
        token to ``issuer`` server-side so a presented credential cannot
        spoof a different issuer (round-2 audit NEW-CRIT-2).
        """
        if not issuer or "agent:" in issuer.lower():
            # Reject the legacy "agent:" namespace — internal agents
            # use ``internal_channel_token`` (NEW-CRIT-1), not sessions.
            raise ValueError(
                "auth.create_session.invalid_issuer — internal agents "
                "must not be given session tokens"
            )
        token = secrets.token_urlsafe(32)
        expiry = time.time() + duration_s
        with self._lock:
            self._evict_oldest_locked(self._active_sessions, self._max_sessions)
            self._active_sessions[token] = (expiry, issuer)
        logger.info("auth.session_created", issuer=issuer)
        return token

    def revoke_session(self, token: str) -> None:
        with self._lock:
            self._active_sessions.pop(token, None)

    @staticmethod
    def _evict_oldest_locked(d: OrderedDict, max_size: int) -> None:
        while len(d) >= max_size:
            d.popitem(last=False)

    # ── Authentication ──────────────────────────────────────────

    def authenticate(
        self,
        credential: CommandCredential,
        command_data: str = "",
    ) -> AuthResult:
        """Authenticate a command.

        Wire-path requires every factor: bound session, counter > last,
        timestamp within bounded skew, signature over command_data.

        Internal-channel fast-path (round-2 audit NEW-CRIT-1) requires a
        process-only HMAC token and is never accepted via free-form
        ``issuer`` strings.
        """
        # Internal-channel fast-path: trusted in-process agents present
        # the bytes minted by ``mint_internal_channel_token``.  The
        # comparison is constant-time and the token bytes never leave
        # the auth module (round-3 R3-CRIT-2).
        if credential.internal_channel_token:
            if verify_internal_channel_token(credential.internal_channel_token):
                return AuthResult.ACCEPTED
            logger.warning("auth.internal_token_mismatch")
            return AuthResult.REJECTED_IDENTITY

        # Factor 1 — Session must resolve.  Issuer is re-derived from
        # the session record; the credential's ``issuer`` field is
        # informational only.
        if not credential.session_token:
            logger.warning("auth.missing_session")
            return AuthResult.REJECTED_IDENTITY
        with self._lock:
            entry = self._active_sessions.get(credential.session_token)
            if entry is None:
                logger.warning("auth.invalid_session")
                return AuthResult.REJECTED_IDENTITY
            expiry, bound_issuer = entry
            if time.time() > expiry:
                logger.warning("auth.expired_session", issuer=bound_issuer)
                self._active_sessions.pop(credential.session_token, None)
                return AuthResult.REJECTED_EXPIRED
            # Move to MRU position.
            self._active_sessions.move_to_end(credential.session_token)
        issuer = bound_issuer

        # Factor 2 — Mandatory monotonic counter.  ``counter <= 0`` is
        # always rejected (round-2 audit NEW-CRIT-5).
        if credential.command_counter <= 0:
            logger.warning("auth.counter_missing", issuer=issuer)
            return AuthResult.REJECTED_REPLAY
        with self._lock:
            last = self._last_counter.get(issuer, 0)
            if credential.command_counter <= last:
                logger.warning(
                    "auth.replay_detected",
                    issuer=issuer,
                    counter=credential.command_counter,
                    last=last,
                )
                return AuthResult.REJECTED_REPLAY
            self._evict_oldest_locked(self._last_counter, self._max_issuers)
            self._last_counter[issuer] = credential.command_counter
            self._last_counter.move_to_end(issuer)

        # Factor 3 — Mandatory timestamp.  Signed window: stale and
        # future-dated both rejected (round-2 audit NEW-CRIT-6).
        if credential.timestamp <= 0:
            logger.warning("auth.timestamp_missing", issuer=issuer)
            return AuthResult.REJECTED_EXPIRED
        age = time.time() - credential.timestamp
        if age > self._max_age:
            logger.warning("auth.command_stale", issuer=issuer, age_s=age)
            return AuthResult.REJECTED_EXPIRED
        if age < -self._max_skew:
            logger.warning("auth.command_future_dated", issuer=issuer, age_s=age)
            return AuthResult.REJECTED_EXPIRED

        # Factor 4 — Mandatory signature.  Empty command_data still
        # requires a signature over the empty string.  An empty
        # signature is always rejected (round-2 audit NEW-CRIT-5).
        if not credential.signature:
            logger.warning("auth.missing_signature", issuer=issuer)
            return AuthResult.REJECTED_SIGNATURE
        expected = hmac.new(
            self._secret,
            command_data.encode(),
            hashlib.sha256,
        ).hexdigest()    # full 256-bit; truncation removed (audit MED-3)
        if not hmac.compare_digest(credential.signature, expected):
            logger.warning("auth.signature_mismatch", issuer=issuer)
            return AuthResult.REJECTED_SIGNATURE

        logger.debug("auth.accepted", issuer=issuer)
        return AuthResult.ACCEPTED

    def issuer_for_session(self, token: str) -> Optional[str]:
        """Return the server-bound issuer for a session token, or None.

        Callers must use this to resolve issuer authority — never trust
        a wire-supplied ``credential.issuer`` field.
        """
        with self._lock:
            entry = self._active_sessions.get(token)
            if entry is None:
                return None
            expiry, issuer = entry
            if time.time() > expiry:
                self._active_sessions.pop(token, None)
                return None
            return issuer

    def sign_command(self, command_data: str) -> str:
        """Sign a command (for testing / ground simulation)."""
        return hmac.new(
            self._secret,
            command_data.encode(),
            hashlib.sha256,
        ).hexdigest()    # full 256-bit (audit MED-3)
