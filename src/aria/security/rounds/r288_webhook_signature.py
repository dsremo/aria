"""R288 — Webhook signature verification.

Threat: webhook receivers (Stripe, GitHub, Slack, custom) often lack
strict signature checks — accepting POSTs from anyone, allowing any
attacker to inject events that look authentic.  Stripe 2019 disclosed
such mis-implementations.

Defence: a per-source signing secret + ``verify_webhook`` enforcing
``X-Signature: t=<ts>,v1=<hmac>`` shape with constant-time compare,
± 5 minute timestamp skew, and replay-window dedup.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import deque
from typing import Deque, Tuple

from aria.security.plugins import DefencePlugin, register


_RECENT: Deque[Tuple[float, str]] = deque(maxlen=4096)
_LOCK = threading.Lock()
_REPLAY_WINDOW = 300.0


def make_signature(payload: bytes, secret: bytes, *, ts: float = 0.0) -> str:
    t = int(ts or time.time())
    body_to_sign = f"{t}.".encode() + (payload or b"")
    sig = hmac.new(secret, body_to_sign, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def verify_webhook(
    payload: bytes,
    header_value: str,
    secret: bytes,
    *,
    skew_seconds: float = _REPLAY_WINDOW,
    now: float = 0.0,
) -> Tuple[bool, str]:
    t = now or time.time()
    if not header_value or not secret:
        return False, "webhook.empty_header_or_secret"
    parts = dict(p.split("=", 1) for p in header_value.split(",") if "=" in p)
    ts_str = parts.get("t", "")
    sig = parts.get("v1", "")
    if not ts_str.isdigit() or not sig:
        return False, "webhook.malformed_header"
    ts = int(ts_str)
    if abs(t - ts) > skew_seconds:
        return False, f"webhook.timestamp_skew:{int(t - ts)}s"

    expected = hmac.new(secret, f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False, "webhook.signature_mismatch"

    with _LOCK:
        # Trim entries older than replay window
        while _RECENT and t - _RECENT[0][0] > _REPLAY_WINDOW:
            _RECENT.popleft()
        seen = any(s == sig for _, s in _RECENT)
        if seen:
            return False, "webhook.replay"
        _RECENT.append((t, sig))
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _RECENT.clear()


register(DefencePlugin(
    round_id="R288",
    name="webhook_signature",
    description="Webhook HMAC-SHA-256 signature verifier with skew + replay window.",
))
