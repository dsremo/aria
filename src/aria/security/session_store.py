"""Opaque session token store — server-side, revocable, idle+absolute capped.

A session is created by ``AuthService.login`` and looked up by every
authenticated web request via ``auth_middleware``. The wire format is
an opaque 256-bit random hex string; the server keeps the principal
record in memory (and an append-only revocation log on disk that
stores ``sha256(token)`` only — round-2 audit NEW-HIGH-1).

Why opaque + server-side, not stateless JWT?
  - Revocation is O(1): a stolen tablet is revocable instantly.
  - The session payload (principal_id, role, duress flag) is private to
    the ship; the wire token reveals nothing about the principal.
  - JWT-style stateless tokens are tempting but force you to ship a
    revocation list anyway (per OAuth/OIDC review). Opaque + persistent
    revocation log is simpler and equivalent.

Lifetimes (ESTIMATE — tune per mission profile):
  - 4 h idle window:     re-auth if quiet for 4 h.
  - 12 h absolute window: hard cap regardless of activity.
  - 30 s grace on cached perms during auth-service degraded mode.

These match the human-factors panel's "don't re-prompt mid-emergency"
principle (Boeing 787 / Sidney Dekker style).

Implements §F-9 (principal-aware approval) and §F-19 (replay defence)
of FAILSAFE_ARCHITECTURE.md.

Round-2 audit hardening (2026-04-27 R2):
  - Token persisted to revocation log as ``sha256(token)`` only.
  - Revocation log entries trimmed to those still within their token
    expiry window on load (NEW-HIGH-3).
  - ``matches_client`` fails closed when the session has a bound
    fingerprint and the presented one is empty (NEW-HIGH-4).
  - Wall-clock fallback for ``last_seen_monotonic`` removed; every new
    session uses ``time.monotonic()`` (NEW-MED-1).
  - Fingerprint comparisons use ``hmac.compare_digest`` (NEW-MED-2).
  - F-19 monotonic counter persisted to disk (NEW-HIGH-5 / NEW-MED-22).
  - Revocation file written 0o600 (NEW-LOW-1).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import structlog

logger = structlog.get_logger()


# ── Lifetime constants ────────────────────────────────────────────


# 4 h idle, 12 h absolute. ESTIMATE — no published source; tuned to
# (a) avoid re-prompt during a 1-2h emergency window and (b) bound the
# stolen-tablet exposure window.
DEFAULT_IDLE_WINDOW_S = 4 * 3600.0
DEFAULT_ABSOLUTE_WINDOW_S = 12 * 3600.0
TOKEN_BYTES = 32   # 256-bit opaque token

# Round-3 audit R3-MED-1 / R3-MED-2 — cap the persistent-state maps so
# an attacker who can flood unique principal_ids cannot grow them
# without bound across restarts.
_MAX_PRINCIPAL_COUNTERS = 100_000
_MAX_REVOKED_ENTRIES = 1_000_000
# Round-3 audit R3-HIGH-4 — flush the counter file atomically, but only
# every N increments (or every WINDOW_S seconds) to bound IO cost.
_COUNTER_FLUSH_INTERVAL = 25
_COUNTER_FLUSH_INTERVAL_S = 5.0


def _hash_token(token: str) -> str:
    """Round-2 audit NEW-HIGH-1 — stable digest used as the on-disk
    identifier of a session token.  Plaintext tokens never touch
    persistent storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Session record ────────────────────────────────────────────────


@dataclass(frozen=True)
class Session:
    token: str
    principal_id: str
    role: str
    created_at: float
    last_seen_at: float
    expires_at: float          # absolute hard cap
    idle_window_s: float
    duress: bool
    command_counter: int = 0   # per-session monotonic; F-19
    # HIGH-6 — bind the session to the originating client so a leaked
    # token cannot be replayed from another machine.
    client_ip_hash: str = ""
    client_ua_hash: str = ""
    # MED-2 — idle-check uses the monotonic clock so a wall-clock jump
    # (NTP skew, DST, user setting clock back) cannot extend or revoke
    # the session.  ``time.monotonic()`` is monotone non-decreasing.
    last_seen_monotonic: float = 0.0
    # Round-2 NEW-MED-15 — pin the principal's pubkey at session-mint
    # time so a key-rotation invalidates outstanding sessions.
    pubkey_fingerprint: str = ""

    def is_expired(self, now: Optional[float] = None,
                   now_monotonic: Optional[float] = None) -> bool:
        n = now if now is not None else time.time()
        if n > self.expires_at:
            return True
        nm = now_monotonic if now_monotonic is not None else time.monotonic()
        # Round-2 NEW-MED-1 — sessions WITHOUT a monotonic stamp are
        # treated as already-expired so legacy sessions cannot survive
        # an upgrade and bypass clock-jump protection.
        if self.last_seen_monotonic <= 0:
            return True
        if (nm - self.last_seen_monotonic) > self.idle_window_s:
            return True
        return False

    def matches_client(self, *, ip_hash: str = "", ua_hash: str = "") -> bool:
        """HIGH-6 + round-2 NEW-HIGH-4 — refuse a session presented from
        a different client.  Once a session has a bound fingerprint,
        presenting an empty fingerprint also rejects (no header-strip
        bypass).  Comparisons constant-time (NEW-MED-2)."""
        if self.client_ip_hash:
            if not ip_hash:
                return False
            if not hmac.compare_digest(self.client_ip_hash, ip_hash):
                return False
        if self.client_ua_hash:
            if not ua_hash:
                return False
            if not hmac.compare_digest(self.client_ua_hash, ua_hash):
                return False
        return True


@dataclass(frozen=True)
class SessionTouchResult:
    session: Session
    expired: bool


# ── Store ─────────────────────────────────────────────────────────


class SessionStore:
    """Process-wide session table with persistent revocation log.

    The active table is in memory (sessions are short-lived and a ship
    has dozens, not millions, of operators). The revocation log is
    persisted so a session token leaked at second N stays revoked across
    restarts until it would have naturally expired.
    """

    REVOKED_FILENAME = "sessions_revoked.jsonl"
    COUNTER_FILENAME = "session_counters.json"

    def __init__(
        self,
        runtime_dir: Optional[Path] = None,
        idle_window_s: float = DEFAULT_IDLE_WINDOW_S,
        absolute_window_s: float = DEFAULT_ABSOLUTE_WINDOW_S,
    ) -> None:
        env = os.environ.get("ARIA_RUNTIME_DIR")
        if runtime_dir is None and env:
            runtime_dir = Path(env).resolve()
        if runtime_dir is None:
            here = Path(__file__).resolve()
            runtime_dir = (here.parents[3] / "data" / "runtime").resolve()
        self._runtime_dir = runtime_dir
        self._idle = float(idle_window_s)
        self._absolute = float(absolute_window_s)
        self._lock = threading.RLock()
        self._sessions: Dict[str, Session] = {}
        # Revoked store: sha256(token) -> expiry_epoch.  Trimmed on load
        # so the file size doesn't grow without bound (NEW-HIGH-3).
        self._revoked: Dict[str, float] = self._load_revoked()
        # Persistent F-19 monotonic counter per principal so a process
        # restart cannot reset replay defence (NEW-HIGH-5).
        self._principal_counters: Dict[str, int] = self._load_counters()
        # Round-3 audit R3-HIGH-4 — coalesced counter persistence.
        self._counter_writes_pending = 0
        self._counter_last_flush = time.time()

    # ── Lifecycle ────────────────────────────────────────────────

    def create(
        self,
        principal_id: str,
        role: str,
        *,
        duress: bool = False,
        idle_window_s: Optional[float] = None,
        absolute_window_s: Optional[float] = None,
        client_ip_hash: str = "",
        client_ua_hash: str = "",
        pubkey_fingerprint: str = "",
    ) -> Session:
        idle = float(idle_window_s) if idle_window_s is not None else self._idle
        absolute = (float(absolute_window_s)
                    if absolute_window_s is not None else self._absolute)
        # Duress sessions have 30 s absolute lifetime — caller is forced to
        # re-auth quickly so an attacker holding a duress code can't keep
        # quiet exfiltrating telemetry.
        # 30 s — no published source; matches the duress-traffic alert
        # window in W-4 of THREAT_MODEL.md.
        if duress:
            absolute = min(absolute, 30.0)
            idle = min(idle, 30.0)
        token = secrets.token_hex(TOKEN_BYTES)
        now = time.time()
        nm = time.monotonic()
        # Round-2 NEW-HIGH-5 — if a persistent counter exists for this
        # principal, start the session above it.
        starting_counter = self._principal_counters.get(principal_id, 0)
        s = Session(
            token=token,
            principal_id=principal_id,
            role=role,
            created_at=now,
            last_seen_at=now,
            last_seen_monotonic=nm,
            expires_at=now + absolute,
            idle_window_s=idle,
            duress=duress,
            client_ip_hash=client_ip_hash,
            client_ua_hash=client_ua_hash,
            pubkey_fingerprint=pubkey_fingerprint,
            command_counter=starting_counter,
        )
        with self._lock:
            self._sessions[token] = s
        logger.info("session.created",
                    principal_id=principal_id, role=role, duress=duress,
                    expires_in_s=round(absolute, 1))
        return s

    def get(self, token: str, *, ip_hash: str = "", ua_hash: str = "") -> Optional[Session]:
        # HIGH-13 — entire critical section in a single atomic block.
        with self._lock:
            if _hash_token(token) in self._revoked:
                return None
            s = self._sessions.get(token)
            if s is None:
                return None
            if s.is_expired():
                self._sessions.pop(token, None)
                return None
            if not s.matches_client(ip_hash=ip_hash, ua_hash=ua_hash):
                return None
            return s

    def touch(self, token: str, *, ip_hash: str = "", ua_hash: str = "") -> Optional[Session]:
        """Update last_seen on an active session.  Returns the refreshed
        Session, or None if expired/unknown/wrong-client.

        HIGH-6 — refuses sessions presented from a different client.
        HIGH-13 — single atomic check-and-update inside ``self._lock``.
        MED-2  — last_seen_monotonic uses the monotonic clock.
        Round-2 NEW-HIGH-4 — fail-closed on empty fingerprint when bound.
        """
        now = time.time()
        nm = time.monotonic()
        with self._lock:
            if _hash_token(token) in self._revoked:
                return None
            s = self._sessions.get(token)
            if s is None:
                return None
            if s.is_expired(now, nm):
                self._sessions.pop(token, None)
                return None
            if not s.matches_client(ip_hash=ip_hash, ua_hash=ua_hash):
                logger.warning("session.client_fingerprint_mismatch",
                               principal_id=s.principal_id)
                return None
            refreshed = Session(
                token=s.token, principal_id=s.principal_id, role=s.role,
                created_at=s.created_at, last_seen_at=now,
                last_seen_monotonic=nm,
                expires_at=s.expires_at, idle_window_s=s.idle_window_s,
                duress=s.duress, command_counter=s.command_counter,
                # Upgrade legacy sessions: bind first observed client.
                client_ip_hash=s.client_ip_hash or ip_hash,
                client_ua_hash=s.client_ua_hash or ua_hash,
                pubkey_fingerprint=s.pubkey_fingerprint,
            )
            self._sessions[token] = refreshed
            return refreshed

    def increment_counter(self, token: str) -> Optional[int]:
        """F-19: per-session monotonic counter on every command.
        Returns the new counter, or None if session is gone.

        Round-2 NEW-HIGH-5 — also persisted per-principal so a process
        restart cannot reset replay defence."""
        with self._lock:
            if _hash_token(token) in self._revoked:
                return None
            s = self._sessions.get(token)
            if s is None or s.is_expired():
                return None
            new_counter = s.command_counter + 1
            self._sessions[token] = Session(
                token=s.token, principal_id=s.principal_id, role=s.role,
                created_at=s.created_at, last_seen_at=s.last_seen_at,
                last_seen_monotonic=s.last_seen_monotonic,
                expires_at=s.expires_at, idle_window_s=s.idle_window_s,
                duress=s.duress, command_counter=new_counter,
                client_ip_hash=s.client_ip_hash, client_ua_hash=s.client_ua_hash,
                pubkey_fingerprint=s.pubkey_fingerprint,
            )
            # Round-3 audit R3-MED-1 — bounded principal-counter map.
            if (s.principal_id not in self._principal_counters
                    and len(self._principal_counters) >= _MAX_PRINCIPAL_COUNTERS):
                # Drop the smallest-value entry — replay defence still
                # holds for actively-used principals.
                victim = min(self._principal_counters,
                             key=self._principal_counters.get)
                self._principal_counters.pop(victim, None)
            self._principal_counters[s.principal_id] = max(
                self._principal_counters.get(s.principal_id, 0), new_counter,
            )
            # Round-3 audit R3-HIGH-4 — coalesce file writes.
            self._counter_writes_pending += 1
            now_s = time.time()
            if (self._counter_writes_pending >= _COUNTER_FLUSH_INTERVAL
                    or now_s - self._counter_last_flush >= _COUNTER_FLUSH_INTERVAL_S):
                self._persist_counters_locked()
                self._counter_writes_pending = 0
                self._counter_last_flush = now_s
            return new_counter

    def revoke(self, token: str, *, reason: str = "logout") -> bool:
        """Revoke a session.  Returns True if the token was active.

        Callers must NOT echo the boolean back to the wire — see the
        round-2 audit NEW-HIGH-13: that creates a token-validity oracle.
        Use the wrapper in ``auth_service.logout`` which returns a fixed
        shape regardless.
        """
        with self._lock:
            existed = token in self._sessions
            existing = self._sessions.pop(token, None)
            expiry = existing.expires_at if existing else (time.time() + self._absolute)
            self._revoked[_hash_token(token)] = expiry
        self._append_revoked(token, reason, expires_at=expiry)
        if existed:
            logger.info("session.revoked", reason=reason)
        return existed

    def revoke_duress_for_principal(self, principal_id: str) -> int:
        """Audit MED-4 — explicit ``all clear`` path for the duress flow.
        Revokes only the principal's *duress* sessions; non-duress
        sessions are untouched so an operator recovering from a coerced
        login keeps their normal access.
        """
        with self._lock:
            tokens = [
                (t, s.expires_at) for t, s in self._sessions.items()
                if s.principal_id == principal_id and s.duress
            ]
            for t, expiry in tokens:
                self._sessions.pop(t, None)
                self._revoked[_hash_token(t)] = expiry
        for t, expiry in tokens:
            self._append_revoked(t, "duress_clear", expires_at=expiry)
        if tokens:
            logger.warning("session.duress_cleared",
                           principal_id=principal_id, count=len(tokens))
        return len(tokens)

    def revoke_all_for_principal(self, principal_id: str,
                                 *, reason: str = "captain.revoke") -> int:
        with self._lock:
            tokens = [(t, s.expires_at) for t, s in self._sessions.items()
                      if s.principal_id == principal_id]
            for t, expiry in tokens:
                self._sessions.pop(t, None)
                self._revoked[_hash_token(t)] = expiry
        for t, expiry in tokens:
            self._append_revoked(t, reason, expires_at=expiry)
        if tokens:
            logger.warning("session.principal_revoked",
                           principal_id=principal_id, count=len(tokens),
                           reason=reason)
        return len(tokens)

    def gc(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [t for t, s in self._sessions.items() if s.is_expired(now)]
            for t in expired:
                self._sessions.pop(t, None)
            # Trim revocation entries whose tokens have already expired.
            stale = [h for h, exp in self._revoked.items() if exp < now]
            for h in stale:
                self._revoked.pop(h, None)
        return len(expired)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ── Revocation persistence ──────────────────────────────────

    def _load_revoked(self) -> Dict[str, float]:
        """Round-3 audit R3-MED-2 — capped at ``_MAX_REVOKED_ENTRIES``
        so a truly enormous file (a long-running deployment, or an
        attacker who can flood logout) cannot OOM the process at boot.
        Older entries are dropped first."""
        path = self._runtime_dir / self.REVOKED_FILENAME
        out: Dict[str, float] = {}
        if not path.is_file():
            return out
        now = time.time()
        bad_lines = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        bad_lines += 1
                        continue
                    h = d.get("token_hash") or d.get("token")
                    if not h:
                        continue
                    # Legacy entries stored raw tokens; accept by hashing
                    # them on the way in.  Future writes use token_hash.
                    if "token_hash" not in d and "token" in d:
                        h = _hash_token(str(d["token"]))
                    expires_at = float(d.get("expires_at", now + self._absolute))
                    if expires_at < now:
                        continue
                    out[str(h)] = expires_at
                    if len(out) > _MAX_REVOKED_ENTRIES:
                        # Evict the entry with the earliest expiry —
                        # i.e. the one closest to falling off anyway.
                        victim = min(out, key=out.get)
                        out.pop(victim, None)
        except OSError as exc:
            logger.warning("session.revoked_load_failed", error=str(exc))
        if bad_lines:
            logger.warning("session.revoked_load_bad_lines", count=bad_lines)
        return out

    def _append_revoked(self, token: str, reason: str,
                        *, expires_at: float) -> None:
        try:
            self._runtime_dir.mkdir(parents=True, exist_ok=True)
            path = self._runtime_dir / self.REVOKED_FILENAME
            existed = path.exists()
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "token_hash": _hash_token(token),
                    "reason": reason,
                    "expires_at": expires_at,
                    "ts": time.time(),
                }) + "\n")
            if not existed:
                try:
                    os.chmod(path, 0o600)   # NEW-LOW-1
                except OSError:
                    pass
        except OSError as exc:
            logger.error("session.revoked_persist_failed", error=str(exc))

    # ── Per-principal counter persistence (NEW-HIGH-5) ────────

    def _load_counters(self) -> Dict[str, int]:
        path = self._runtime_dir / self.COUNTER_FILENAME
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return {str(k): int(v) for k, v in d.items()}
        except Exception as exc:
            logger.warning("session.counter_load_failed", error=str(exc))
            return {}

    def _persist_counters_locked(self) -> None:
        """Round-3 audit R3-HIGH-4 — atomic write with fsync so a crash
        between rename and durability doesn't roll the counter back."""
        path = self._runtime_dir / self.COUNTER_FILENAME
        try:
            self._runtime_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._principal_counters, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            # fsync the directory so the rename is durable too.
            try:
                dir_fd = os.open(str(self._runtime_dir), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("session.counter_persist_failed", error=str(exc))

    def flush_counters(self) -> None:
        """Force-persist any buffered counter increments.  Call from
        a graceful-shutdown handler."""
        with self._lock:
            self._persist_counters_locked()
            self._counter_writes_pending = 0
            self._counter_last_flush = time.time()


# ── Singleton ─────────────────────────────────────────────────────


_INSTANCE: Optional[SessionStore] = None
_LOCK = threading.RLock()


def get_session_store() -> SessionStore:
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = SessionStore()
    return _INSTANCE


def reset_for_test(runtime_dir: Optional[Path] = None) -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = SessionStore(runtime_dir=runtime_dir)


# ── Helpers exported for use by middleware/auth_service ──────────


def fingerprint_ip(ip: str) -> str:
    """Stable hash for an IP — 16 hex chars (64-bit) is plenty for
    fingerprinting without exposing the raw address in logs."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def fingerprint_ua(ua: str) -> str:
    """Stable hash for a User-Agent string."""
    if not ua:
        return ""
    return hashlib.sha256(ua.encode("utf-8")).hexdigest()[:16]
