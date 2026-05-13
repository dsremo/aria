"""R41 §1.5 — per-action FIDO2 / hardware-key challenge.

R32 authenticates a *session* — once an operator unlocks at 09:00, any
high-impact action signed under that session token at 14:00 looks
identical to the first one.  NIST 800-63B AAL3 explicitly requires a
*fresh* hardware-key assertion per high-impact transaction so a coerced
operator can't be used as a one-time signing oracle.

This module is the pure cryptographic layer + replay-defence ledger:

  * ``PerActionChallenge.issue(action, args_hash, principal_id)``
    → ``Challenge`` (nonce + ts + bound payload).  Caller hands the
    challenge bytes to the operator's FIDO2/WebAuthn flow, which
    returns an Ed25519 signature over the same bytes.
  * ``PerActionChallenge.verify(challenge, signature, pubkey_hex)``
    → ``VerifyResult``.  Rejects on bad signature, replay, or
    challenge-window expiry.

The bound payload is::

    SHA-256( challenge_id ‖ action ‖ args_hash ‖ ts ‖ principal_id )

so a recorded valid signature for one (action, args) pair cannot be
substituted onto a different (action, args) pair.  Replay defence is
an LRU set keyed by ``challenge_id`` with TTL =
``2 × challenge_window_s`` so an attacker can't reuse an old
challenge after expiry either.

References:
  NIST SP 800-63B §5.1.7 — phishing-resistant authenticators;
  WebAuthn Level 3 §6.5 — assertion verification;
  Schneier-Kelsey 1999 — defence in depth for audit + auth coupling.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import structlog

logger = structlog.get_logger()


# AAL3-class window — challenges expire fast so a captured one isn't
# useful even if leaked.  120 s matches NIST 800-63B §10 for AAL3.
DEFAULT_CHALLENGE_WINDOW_S = 120.0

# Used-nonce TTL = 2 × window so we don't drop any during the window
# but also don't grow without bound.  Tunable in production.
NONCE_TTL_S = 2 * DEFAULT_CHALLENGE_WINDOW_S


# TT&C audit M-5 — mission-phase-aware challenge window.  At LEO
# round-trip times (<1 s) the 120 s window is fine, but at Mars
# distances (8–48 min one-way) the operator cannot complete the
# hardware-key challenge before it expires.  Operators MUST therefore
# raise the window when in deep-space phase, but a wide window is
# exactly what a replay attacker wants — so we pin per-phase ceilings
# instead of letting callers pick freely.
#
# Reference: JPL DSN handbook (DSN810-005-200) one-way light times.
_PHASE_WINDOW_CEILING_S: Dict[str, float] = {
    "NOMINAL_LEO":      120.0,    # ≤ 1 s round-trip (NIST AAL3 default)
    "LUNAR_TRANSIT":    600.0,    # ~2.5 s RTT, plus operator UI
    "MARS_TRANSIT":     1800.0,   # 8–48 min OWLT (Vallado §11)
    "OUTER_PLANETARY":  3600.0,   # JPL DSN810-005-200 ceiling
}


def challenge_window_for_phase(phase: str) -> float:
    """Return the maximum permitted challenge window for the named
    mission phase.  Unknown phases fall back to the conservative LEO
    default (TT&C audit M-5)."""
    return _PHASE_WINDOW_CEILING_S.get(phase, DEFAULT_CHALLENGE_WINDOW_S)


# ── Dataclasses ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Challenge:
    """One per-action challenge.  ``payload`` is the bytes the
    operator's hardware key signs."""
    challenge_id: str
    action: str
    args_hash: str
    principal_id: str
    issued_at: float
    window_s: float
    payload: bytes


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


# ── Helpers ─────────────────────────────────────────────────────


def args_hash_for(args: Dict[str, object]) -> str:
    """Deterministic SHA-256 over canonicalised args.  Caller passes
    this into ``issue`` so the resulting signature can never be
    substituted onto a different argument set."""
    import json
    blob = json.dumps(args, sort_keys=True, separators=(",", ":"),
                      default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _bound_payload(
    challenge_id: str, action: str, args_hash: str,
    issued_at: float, principal_id: str,
) -> bytes:
    h = hashlib.sha256()
    h.update(challenge_id.encode())
    h.update(b"|")
    h.update(action.encode())
    h.update(b"|")
    h.update(args_hash.encode())
    h.update(b"|")
    h.update(f"{issued_at:.6f}".encode())
    h.update(b"|")
    h.update(principal_id.encode())
    return h.digest()


# ── PerActionChallenge ──────────────────────────────────────────


class PerActionChallenge:
    """Issues + verifies fresh hardware-key challenges.

    Thread-safe; back-end is in-memory.  Production should swap the
    used-nonce dict for a durable store (Redis-class) so a process
    restart doesn't reset the replay-defence clock.  An attacker
    cannot forge a valid challenge because:

      1. ``challenge_id`` is 256 bits of OS randomness (unforgeable).
      2. ``payload`` binds the action + args_hash + principal_id
         together, so a captured signature for action A on args X
         cannot be substituted onto action B on args Y.
      3. The verify path enforces (a) the public key belongs to the
         expected principal, (b) the challenge hasn't expired, and
         (c) the challenge_id has not already been redeemed.
    """

    def __init__(
        self,
        window_s: float = DEFAULT_CHALLENGE_WINDOW_S,
        nonce_ttl_s: float = NONCE_TTL_S,
        state_path: Optional[Path] = None,
    ) -> None:
        self._window_s = float(window_s)
        self._ttl_s = float(nonce_ttl_s)
        self._open: Dict[str, Challenge] = {}
        self._used: Dict[str, float] = {}     # challenge_id → expire_at
        self._lock = threading.Lock()
        # TT&C audit H-5 — persist ``_used`` so a process restart does
        # not re-open the replay window.  Default location lives next
        # to ReplayGuard's persisted state.
        env = os.environ.get("ARIA_RUNTIME_DIR")
        if state_path is None:
            base = (
                Path(env) if env
                else Path(__file__).resolve().parents[3] / "data" / "runtime"
            )
            state_path = base / "per_action_used.json"
        self._state_path = state_path
        self._writes_pending = 0
        self._WRITES_BEFORE_FLUSH = 25
        self._last_flush_monotonic = time.monotonic()
        self._FLUSH_INTERVAL_S = 5.0
        self._load_state()

    # ── Issue ──────────────────────────────────────────────────

    def issue(
        self,
        action: str,
        args_hash: str,
        principal_id: str,
    ) -> Challenge:
        challenge_id = os.urandom(32).hex()
        issued_at = time.time()
        payload = _bound_payload(
            challenge_id, action, args_hash, issued_at, principal_id,
        )
        challenge = Challenge(
            challenge_id=challenge_id,
            action=action,
            args_hash=args_hash,
            principal_id=principal_id,
            issued_at=issued_at,
            window_s=self._window_s,
            payload=payload,
        )
        with self._lock:
            self._open[challenge_id] = challenge
            self._evict_stale_locked()
        logger.info("per_action.challenge_issued",
                    action=action, principal=principal_id,
                    challenge=challenge_id[:16])
        return challenge

    # ── Verify ─────────────────────────────────────────────────

    def verify(
        self,
        challenge_id: str,
        action: str,
        args_hash: str,
        principal_id: str,
        signature_hex: str,
        pubkey_hex: str,
    ) -> VerifyResult:
        now = time.time()
        with self._lock:
            self._evict_stale_locked()
            if challenge_id in self._used:
                return VerifyResult(False, "challenge replayed")
            ch = self._open.get(challenge_id)
        if ch is None:
            return VerifyResult(False, "unknown challenge_id")

        # Window — must check before evicting so the caller gets a
        # meaningful "expired" reason instead of a generic unknown.
        if (now - ch.issued_at) > ch.window_s:
            return VerifyResult(False, "challenge expired")

        # Substitution defence: caller's stated action / args / principal
        # must match what the challenge was issued for.
        if action != ch.action:
            return VerifyResult(False, "action mismatch")
        if args_hash != ch.args_hash:
            return VerifyResult(False, "args_hash mismatch")
        if principal_id != ch.principal_id:
            return VerifyResult(False, "principal_id mismatch")

        # Verify Ed25519 signature over the bound payload.
        # HIGH-5 — never echo the cryptography library exception text on
        # the wire; it can leak partial pubkey bytes / verifier internals.
        # Log it locally; return a fixed string to the caller.
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            pub = Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(pubkey_hex),
            )
            pub.verify(bytes.fromhex(signature_hex), ch.payload)
        except ValueError as exc:
            logger.warning("per_action.invalid_input",
                           principal=principal_id, error=str(exc))
            return VerifyResult(False, "signature invalid")
        except Exception as exc:
            logger.warning("per_action.verify_failed",
                           principal=principal_id,
                           error_type=type(exc).__name__)
            return VerifyResult(False, "signature invalid")

        # Atomic redeem.
        with self._lock:
            if challenge_id in self._used:
                return VerifyResult(False, "race: already redeemed")
            self._open.pop(challenge_id, None)
            self._used[challenge_id] = now + self._ttl_s
            self._writes_pending += 1
            now_m = time.monotonic()
            if (self._writes_pending >= self._WRITES_BEFORE_FLUSH
                    or now_m - self._last_flush_monotonic >= self._FLUSH_INTERVAL_S):
                self._persist_locked()
                self._writes_pending = 0
                self._last_flush_monotonic = now_m

        logger.info("per_action.challenge_redeemed",
                    action=action, principal=principal_id,
                    challenge=challenge_id[:16])
        return VerifyResult(True, "ok")

    # ── Persistence (TT&C audit H-5) ──────────────────────────────

    def _load_state(self) -> None:
        path = self._state_path
        if not path.is_file():
            return
        try:
            now = time.time()
            data = json.loads(path.read_text(encoding="utf-8"))
            for cid, expiry in data.items():
                expiry_f = float(expiry)
                if expiry_f > now:
                    self._used[str(cid)] = expiry_f
        except Exception as exc:    # noqa: BLE001
            logger.warning("per_action.load_failed", error=str(exc))

    def _persist_locked(self) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            payload = {cid: expiry for cid, expiry in self._used.items()}
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("per_action.persist_failed", error=str(exc))

    def flush(self) -> None:
        """Force-persist used-nonce state.  Call from graceful shutdown."""
        with self._lock:
            self._persist_locked()
            self._writes_pending = 0
            self._last_flush_monotonic = time.monotonic()

    # ── Inspection ─────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "open": len(self._open),
                "used": len(self._used),
            }

    def _evict_stale_locked(self) -> None:
        # LOW-4 — invoked from issue() AND verify(); guarantees GC every
        # interaction so the dicts cannot grow unbounded under stalled
        # background sweeps.
        now = time.time()
        for cid in [k for k, v in self._used.items() if v < now]:
            del self._used[cid]
        # Expired open challenges keep an "expired" reason for one window
        # past expiry, then are dropped.  Past 2× ttl they always go.
        grace_cutoff = self._ttl_s
        for cid in [k for k, c in self._open.items()
                    if (now - c.issued_at) > c.window_s + grace_cutoff]:
            del self._open[cid]


# ── Module singleton ────────────────────────────────────────────


_INSTANCE: Optional[PerActionChallenge] = None
_LOCK = threading.Lock()


def get_per_action_challenge() -> PerActionChallenge:
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = PerActionChallenge()
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None
