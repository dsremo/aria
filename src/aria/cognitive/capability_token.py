"""Capability tokens for LLM-bound tool calls.

Implements §F-6 of docs/FAILSAFE_ARCHITECTURE.md.

The LLM never holds a long-lived credential and never names a tool
directly. Instead, the planner mints a *capability token* per call:

  - which tool may be invoked,
  - which exact arguments are permitted (hashed),
  - within a tight time window (default 30 s),
  - signed by the planner's symmetric HMAC key.

The tool registry refuses to dispatch any call that does not
present a valid, unexpired, args-hash-matching token. Defeats:

  T-II-5  capability accumulation (LLM tries to grant itself tools)
  T-II-7  tool-chain abuse        (token's args_hash binds the call)
  T-VII-5 confused deputy         (agent forwards LLM's token, not
                                   its own authority)
  T-III-7 DSN command spoofing    (combined with auth signing on
                                   the wire)

HMAC-SHA-256 is used for signing. The signing key never leaves the
planner; tools verify against the same shared secret loaded from the
sealed manifest (when available) or a process-local random key
generated on boot. Long-running deployments rotate the key at every
restart, so a token leaked at second N expires at most 30 s later AND
is invalidated entirely on the next process boot.

Example flow:

    from aria.cognitive.capability_token import (
        get_token_minter, verify_token, ScopeMismatch
    )

    # Planner side: mint a tightly-scoped token before each tool call.
    token = get_token_minter().mint(
        tool="eps_get_power_budget",
        args={"include_history": False},
        ttl_s=30,
    )

    # Agent side: pass the token through to the tool registry.
    self._tools.invoke("eps_get_power_budget",
                       {"include_history": False, "_capability_token": token})

    # Tool side: registry validates before dispatching.
    verdict = verify_token(token, expected_tool="eps_get_power_budget",
                           args={"include_history": False})
    if not verdict.valid:
        raise ScopeMismatch(verdict.reason)
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, TYPE_CHECKING

import structlog

logger = structlog.get_logger()

if TYPE_CHECKING:
    from aria.core.types import AuthorityLevel
    from aria.security.principals import Principal


# ── Configuration ─────────────────────────────────────────────────


# Process-local secret if no shared key is configured. 32 bytes ⇒ 256-bit.
_DEFAULT_KEY = secrets.token_bytes(32)
DEFAULT_TTL_S = 30.0
MAX_TTL_S = 600.0          # 10 minutes — bound the longest token
MIN_TTL_S = 1.0


def _canonical_args(args: Mapping[str, Any]) -> bytes:
    """Stable JSON serialisation for arg-hashing."""
    # Drop the meta key carried by token-bearing requests so verify()
    # works on the same hash the minter computed.
    cleaned = {k: v for k, v in args.items() if k != "_capability_token"}
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()


def args_hash(args: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_args(args)).hexdigest()


# ── Token format ──────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityToken:
    """A signed capability token. Encoded as compact JSON for transit."""
    tool: str
    args_hash: str
    issued_at: float
    expires_at: float
    issuer: str
    nonce: str
    sig_hex: str

    def encode(self) -> str:
        return json.dumps({
            "t": self.tool,
            "h": self.args_hash,
            "i": round(self.issued_at, 3),
            "e": round(self.expires_at, 3),
            "is": self.issuer,
            "n": self.nonce,
            "s": self.sig_hex,
        }, separators=(",", ":"))

    @classmethod
    def decode(cls, encoded: str) -> "CapabilityToken":
        d = json.loads(encoded)
        return cls(
            tool=str(d.get("t", "")),
            args_hash=str(d.get("h", "")),
            issued_at=float(d.get("i", 0.0)),
            expires_at=float(d.get("e", 0.0)),
            issuer=str(d.get("is", "")),
            nonce=str(d.get("n", "")),
            sig_hex=str(d.get("s", "")),
        )

    def signing_payload(self) -> bytes:
        return f"{self.tool}|{self.args_hash}|{self.issued_at}|{self.expires_at}|{self.issuer}|{self.nonce}".encode()


class ScopeMismatch(RuntimeError):
    """Raised when a tool call presents a token that doesn't match."""


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    reason: str
    tool: str = ""


# ── Minter / verifier ─────────────────────────────────────────────


class TokenMinter:
    """Per-process token issuer.

    ``key`` defaults to a process-local random secret; pass an explicit
    key in tests / when the verifier runs in a separate process so the
    HMAC matches.
    """

    # R32: tier name → permission name. Stable mapping; constitution
    # enforcement keys off the permission name.
    _TIER_PERM = {
        "SENSOR_ONLY":   "mint_token.sensor_only",
        "ROUTINE":       "mint_token.routine",
        "SUPERVISED":    "mint_token.supervised",
        "CONSENT":       "mint_token.consent",
        "ADVISORY":      "mint_token.advisory",
        "CAPTAIN_ONLY":  "mint_token.captain_only",
    }

    def __init__(
        self,
        key: Optional[bytes] = None,
        issuer: str = "planner",
    ) -> None:
        self._key = key or _DEFAULT_KEY
        self._issuer = issuer
        # Bounded set of recently-issued nonces — defends against
        # replay-after-expiry by the same token (small extra belt).
        self._seen_nonces: set[str] = set()
        self._lock = threading.Lock()

    def _enforce_mint_rbac(
        self,
        *,
        tool: str,
        tool_authority: Optional["AuthorityLevel"],
        principal: "Principal",
    ) -> None:
        """R32: refuse mints that violate role-based limits.

        Two layers:
          1. Hard cap: agent role NEVER mints CONSENT-or-higher.
          2. Soft check: if tool_authority is supplied, the principal
             must hold the matching ``mint_token.<tier>`` permission.

        Raises ScopeMismatch on refusal.
        """
        # Layer 1: agent hard cap.
        if principal.role == "agent" and tool_authority is not None:
            from aria.core.types import AuthorityLevel
            if tool_authority.value >= AuthorityLevel.CONSENT.value:
                raise ScopeMismatch(
                    f"agent role cannot mint {tool_authority.name} token "
                    f"for tool '{tool}' (R32 hard cap)",
                )
        # Layer 2: explicit permission table.
        if tool_authority is not None:
            from aria.security.principals import authorize
            perm = self._TIER_PERM.get(tool_authority.name)
            if perm is None:
                raise ScopeMismatch(
                    f"unknown tool authority {tool_authority!r}",
                )
            decision = authorize(principal, perm)
            if not decision.allow:
                raise ScopeMismatch(
                    f"role '{principal.role}' lacks {perm} for tool '{tool}': "
                    f"{decision.reason}",
                )

    def mint(
        self,
        tool: str,
        args: Mapping[str, Any],
        *,
        ttl_s: float = DEFAULT_TTL_S,
        tool_authority: Optional["AuthorityLevel"] = None,
        requesting_principal: Optional["Principal"] = None,
    ) -> str:
        """Mint a capability token. Returns the encoded form.

        Note: timestamps are rounded to 3 decimals so that encode →
        decode → verify recomputes the same signing payload as mint.

        R32 RBAC: when ``requesting_principal`` is provided we enforce
        the role's mint permissions:

          - Agent role NEVER mints CONSENT-or-higher tokens, regardless
            of any other permission. This is the AI-self-elevation
            firewall (T-V-1, W-2 in THREAT_MODEL.md).
          - The principal's role must hold the permission
            ``mint_token.<tier>`` corresponding to ``tool_authority``.

        Raises ``ScopeMismatch`` on RBAC failure.
        """
        if requesting_principal is not None:
            self._enforce_mint_rbac(
                tool=tool,
                tool_authority=tool_authority,
                principal=requesting_principal,
            )
        else:
            # Wiring audit Pass 3 (F1.14) — without a principal the
            # RBAC hard-cap (Agent never mints CONSENT-or-higher) is
            # silently bypassed. Production deploys must thread the
            # principal through the engine; we refuse to mint
            # CONSENT-tier-or-higher tokens without one rather than
            # let the bypass go silent.  Lower-tier tokens are still
            # allowed because the legacy "no-principal" path is the
            # only thing the engine has wired today.
            tier = tool_authority
            if tier is not None:
                tier_name = getattr(tier, "name", str(tier)).upper()
                # AuthorityLevel order: SENSOR_ONLY=0, ROUTINE=1,
                # SUPERVISED=2, CONSENT=3, ADVISORY=4, CAPTAIN_ONLY=5.
                # "CONSENT-or-higher" = the top three tiers; those
                # MUST carry an explicit principal so the AI self-
                # elevation firewall fires.
                if tier_name in ("CONSENT", "ADVISORY", "CAPTAIN_ONLY"):
                    logger.error(
                        "capability_token.mint_consent_tier_no_principal",
                        tool=tool,
                        tier=tier_name,
                        impact="refusing CONSENT-or-higher mint without a "
                               "requesting_principal — Agent self-elevation "
                               "firewall would otherwise be bypassed",
                    )
                    raise ScopeMismatch(
                        f"capability_token.mint refused: tool={tool!r} "
                        f"tier={tier_name} requires requesting_principal"
                    )
            logger.debug(
                "capability_token.mint_no_principal",
                tool=tool,
                note="legacy path; production deploys should thread "
                     "the requesting principal through the engine",
            )
        # Stamp the issuer with the principal_id when given so audit
        # logs attribute the mint to a specific identity, not "planner".
        issuer = (f"{requesting_principal.role}:{requesting_principal.principal_id}"
                  if requesting_principal is not None else self._issuer)
        ttl = max(MIN_TTL_S, min(MAX_TTL_S, float(ttl_s)))
        now = round(time.time(), 3)
        token = CapabilityToken(
            tool=str(tool),
            args_hash=args_hash(args),
            issued_at=now,
            expires_at=round(now + ttl, 3),
            issuer=issuer,
            nonce=secrets.token_hex(16),
            sig_hex="",
        )
        sig = hmac.new(self._key, token.signing_payload(),
                       hashlib.sha256).hexdigest()
        signed = CapabilityToken(
            tool=token.tool, args_hash=token.args_hash,
            issued_at=token.issued_at, expires_at=token.expires_at,
            issuer=token.issuer, nonce=token.nonce, sig_hex=sig,
        )
        with self._lock:
            # Bound the seen-nonces set so it can't grow forever.
            if len(self._seen_nonces) > 4096:
                self._seen_nonces = set(list(self._seen_nonces)[-2048:])
            self._seen_nonces.add(signed.nonce)
        return signed.encode()


class TokenVerifier:
    """Per-process token verifier."""

    def __init__(
        self,
        key: Optional[bytes] = None,
        clock_skew_s: float = 5.0,
    ) -> None:
        self._key = key or _DEFAULT_KEY
        self._clock_skew_s = max(0.0, float(clock_skew_s))
        # Per-tool one-shot nonce blocklist (short-lived, capped).
        self._used_nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def verify(
        self,
        encoded: str,
        *,
        expected_tool: str,
        args: Mapping[str, Any],
    ) -> VerifyResult:
        """Validate a capability token presented at the tool boundary."""
        try:
            token = CapabilityToken.decode(encoded)
        except Exception as exc:
            return VerifyResult(False, f"undecodable: {exc}")
        # Tool match.
        if token.tool != str(expected_tool):
            return VerifyResult(False, f"tool mismatch: token={token.tool} expected={expected_tool}",
                                token.tool)
        # Arg hash match.
        h = args_hash(args)
        if not hmac.compare_digest(h, token.args_hash):
            return VerifyResult(False, "args_hash mismatch", token.tool)
        # Expiry — allow a small forward skew to handle multi-process clocks.
        now = time.time()
        if now > token.expires_at + self._clock_skew_s:
            return VerifyResult(False, "expired", token.tool)
        if now + self._clock_skew_s < token.issued_at:
            return VerifyResult(False, "issued_at in the future", token.tool)
        # Signature — constant-time compare.
        expected_sig = hmac.new(
            self._key, token.signing_payload(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, token.sig_hex):
            return VerifyResult(False, "signature invalid", token.tool)
        # One-shot nonce — same token cannot be reused.
        with self._lock:
            # Prune expired nonces lazily to bound memory.
            expired = [n for n, t in self._used_nonces.items() if t < now]
            for n in expired:
                self._used_nonces.pop(n, None)
            if token.nonce in self._used_nonces:
                return VerifyResult(False, "nonce already used", token.tool)
            self._used_nonces[token.nonce] = token.expires_at + self._clock_skew_s
        return VerifyResult(True, "ok", token.tool)


# ── Singletons ────────────────────────────────────────────────────


_MINTER: Optional[TokenMinter] = None
_VERIFIER: Optional[TokenVerifier] = None
_LOCK = threading.Lock()


def get_token_minter() -> TokenMinter:
    global _MINTER
    if _MINTER is None:
        with _LOCK:
            if _MINTER is None:
                _MINTER = TokenMinter()
    return _MINTER


def get_token_verifier() -> TokenVerifier:
    global _VERIFIER
    if _VERIFIER is None:
        with _LOCK:
            if _VERIFIER is None:
                # Same key as minter for in-process verification. In a
                # multi-process deployment, both load the key from the
                # sealed manifest's key slot.
                _VERIFIER = TokenVerifier(key=get_token_minter()._key)
    return _VERIFIER


def reset_for_test() -> None:
    """Drop singletons + force a new ephemeral key. For tests only."""
    global _MINTER, _VERIFIER, _DEFAULT_KEY
    with _LOCK:
        _DEFAULT_KEY = secrets.token_bytes(32)
        _MINTER = None
        _VERIFIER = None


def verify_token(encoded: str, *, expected_tool: str,
                 args: Mapping[str, Any]) -> VerifyResult:
    """Convenience module-level verify."""
    return get_token_verifier().verify(
        encoded, expected_tool=expected_tool, args=args,
    )
