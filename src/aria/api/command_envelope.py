"""Command-envelope authentication for the ARIA HTTP/WS command path.

TT&C audit C-1, C-2, C-3, C-4 — closes the unauthenticated bypass that
let any reachable client publish to ``aria.captain.query`` with no
counter / nonce / signature.

A command envelope is four request headers:

    X-ARIA-Counter:    monotonic per-issuer integer (>= 1)
    X-ARIA-Nonce:      random hex/base64 string, ≥ 16 chars
    X-ARIA-Timestamp:  POSIX seconds (signed window: stale OR future-dated rejected)
    X-ARIA-Signature:  hex(HMAC-SHA-256(secret, f"{counter}|{nonce}|{timestamp}|{body}"))

The body is bound into the signature so a captured envelope cannot be
re-used with a different payload.  ``ReplayGuard.accept`` is consulted
against ``(source=<bearer-issuer>, seq=counter, nonce=nonce)`` to
reject replays whose seq is not strictly monotonic.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


# Sensor-fusion / TT&C audit — clock skew bound matches CommandAuthenticator
# (auth.py:_MAX_CLOCK_SKEW_S).  Future-dated commands past this skew are
# rejected exactly like stale commands.
_MAX_CLOCK_SKEW_S = 30.0    # s — auth.py default

# Maximum freshness window for envelopes.  Smaller than the
# CommandAuthenticator default (3600 s) because the HTTP path has no
# DSN-light-time round-trip — anything older than 5 minutes is suspect.
DEFAULT_MAX_ENVELOPE_AGE_S = 300.0   # s — 5-minute freshness window

# Minimum nonce length must match ReplayGuard's contract
# (replay_guard.py:107 — ``len(nonce) < 16`` ⇒ "missing_nonce").
_MIN_NONCE_LEN = 16


@dataclass(frozen=True)
class EnvelopeVerdict:
    accepted: bool
    issuer: str = ""
    counter: int = 0
    nonce: str = ""
    reason: str = ""


def parse_and_verify(
    headers: dict[str, str],
    body: bytes,
    secret: bytes,
    *,
    bearer_issuer: str,
    max_age_s: float = DEFAULT_MAX_ENVELOPE_AGE_S,
) -> EnvelopeVerdict:
    """Parse ``X-ARIA-*`` headers and verify signature + freshness.

    The caller is responsible for the *replay* check — feed the
    returned ``(issuer, counter, nonce)`` into
    ``ReplayGuard.accept`` to enforce monotonic-seq + nonce-window
    semantics.  Splitting the responsibilities keeps this module pure
    (no I/O) so it stays unit-testable.
    """
    counter_raw = headers.get("x-aria-counter")
    nonce = headers.get("x-aria-nonce") or ""
    ts_raw = headers.get("x-aria-timestamp")
    signature = headers.get("x-aria-signature") or ""

    if not counter_raw or not nonce or not ts_raw or not signature:
        return EnvelopeVerdict(False, reason="envelope_missing")

    try:
        counter = int(counter_raw)
    except (TypeError, ValueError):
        return EnvelopeVerdict(False, reason="counter_not_integer")
    if counter <= 0:
        return EnvelopeVerdict(False, reason="counter_non_positive")

    if len(nonce) < _MIN_NONCE_LEN:
        return EnvelopeVerdict(False, reason="nonce_too_short")

    try:
        timestamp = float(ts_raw)
    except (TypeError, ValueError):
        return EnvelopeVerdict(False, reason="timestamp_not_numeric")

    wall_now = time.time()
    age = wall_now - timestamp
    if age > max_age_s:
        return EnvelopeVerdict(False, reason="stale")
    if age < -_MAX_CLOCK_SKEW_S:
        return EnvelopeVerdict(False, reason="future_dated")

    # Canonical signature material — counter|nonce|timestamp|body.
    # ``timestamp`` is restored to its on-the-wire string so trailing
    # zeros in 1700000000.0 vs 1700000000 don't desync the signature.
    body_hex = hashlib.sha256(body).hexdigest()
    canonical = f"{counter}|{nonce}|{ts_raw}|{body_hex}".encode("utf-8")
    expected = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return EnvelopeVerdict(False, reason="signature_mismatch")

    return EnvelopeVerdict(
        accepted=True,
        issuer=bearer_issuer,
        counter=counter,
        nonce=nonce,
    )


def sign_envelope(
    secret: bytes,
    counter: int,
    nonce: str,
    timestamp_s: float,
    body: bytes,
) -> dict[str, str]:
    """Construct the four headers a client should send.  Test/utility helper."""
    body_hex = hashlib.sha256(body).hexdigest()
    ts = str(timestamp_s)
    canonical = f"{counter}|{nonce}|{ts}|{body_hex}".encode("utf-8")
    sig = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    return {
        "X-ARIA-Counter": str(counter),
        "X-ARIA-Nonce": nonce,
        "X-ARIA-Timestamp": ts,
        "X-ARIA-Signature": sig,
    }
