from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

_MIN_NONCE_LEN = 16
_MAX_FRAME_BYTES = 8192
_MAX_CLOCK_SKEW_S = 30.0
DEFAULT_MAX_FRAME_AGE_S = 60.0


@dataclass(frozen=True)
class HalFrame:
    counter: int
    nonce: str
    timestamp_s: float
    command: str
    params: dict[str, Any] = field(default_factory=dict)
    issuer: str = "aria"

    def canonical_body(self) -> bytes:
        payload = {
            "command": self.command,
            "params": self.params,
            "issuer": self.issuer,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class HalReply:
    counter: int
    accepted: bool
    detail: str
    state_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrameVerdict:
    accepted: bool
    frame: Optional[HalFrame] = None
    reason: str = ""


def _hmac_hex(secret: bytes, blob: bytes) -> str:
    return hmac.new(secret, blob, hashlib.sha256).hexdigest()


def sign_frame(secret: bytes, frame: HalFrame) -> bytes:
    body = frame.canonical_body()
    body_hex = hashlib.sha256(body).hexdigest()
    ts_str = repr(frame.timestamp_s)
    canonical = f"{frame.counter}|{frame.nonce}|{ts_str}|{body_hex}".encode("utf-8")
    sig = _hmac_hex(secret, canonical)
    envelope = {
        "v": 1,
        "counter": frame.counter,
        "nonce": frame.nonce,
        "timestamp": ts_str,
        "issuer": frame.issuer,
        "command": frame.command,
        "params": frame.params,
        "signature": sig,
    }
    raw = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    if len(raw) > _MAX_FRAME_BYTES:
        raise ValueError(f"frame too large: {len(raw)} > {_MAX_FRAME_BYTES}")
    return raw


def parse_and_verify_frame(
    raw: bytes,
    secret: bytes,
    *,
    max_age_s: float = DEFAULT_MAX_FRAME_AGE_S,
    now_s: Optional[float] = None,
) -> FrameVerdict:
    if not raw:
        return FrameVerdict(False, reason="empty_frame")
    if len(raw) > _MAX_FRAME_BYTES:
        return FrameVerdict(False, reason="frame_oversize")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return FrameVerdict(False, reason="json_decode_error")
    if not isinstance(envelope, dict):
        return FrameVerdict(False, reason="not_an_object")
    if envelope.get("v") != 1:
        return FrameVerdict(False, reason="version_mismatch")

    counter_raw = envelope.get("counter")
    nonce = envelope.get("nonce")
    ts_str = envelope.get("timestamp")
    issuer = envelope.get("issuer") or "aria"
    command = envelope.get("command")
    params = envelope.get("params") or {}
    signature = envelope.get("signature")

    if not isinstance(counter_raw, int) or counter_raw <= 0:
        return FrameVerdict(False, reason="counter_invalid")
    if not isinstance(nonce, str) or len(nonce) < _MIN_NONCE_LEN:
        return FrameVerdict(False, reason="nonce_too_short")
    if not isinstance(ts_str, str):
        return FrameVerdict(False, reason="timestamp_not_string")
    if not isinstance(command, str) or not command:
        return FrameVerdict(False, reason="command_missing")
    if not isinstance(params, dict):
        return FrameVerdict(False, reason="params_not_object")
    if not isinstance(signature, str) or not signature:
        return FrameVerdict(False, reason="signature_missing")
    try:
        timestamp = float(ts_str)
    except (TypeError, ValueError):
        return FrameVerdict(False, reason="timestamp_not_numeric")

    wall_now = now_s if now_s is not None else time.time()
    age = wall_now - timestamp
    if age > max_age_s:
        return FrameVerdict(False, reason="stale")
    if age < -_MAX_CLOCK_SKEW_S:
        return FrameVerdict(False, reason="future_dated")

    frame = HalFrame(
        counter=counter_raw,
        nonce=nonce,
        timestamp_s=timestamp,
        command=command,
        params=dict(params),
        issuer=str(issuer),
    )
    body_hex = hashlib.sha256(frame.canonical_body()).hexdigest()
    canonical = f"{frame.counter}|{frame.nonce}|{ts_str}|{body_hex}".encode("utf-8")
    expected = _hmac_hex(secret, canonical)
    if not hmac.compare_digest(signature, expected):
        return FrameVerdict(False, reason="signature_mismatch")

    return FrameVerdict(True, frame=frame)


def fresh_nonce() -> str:
    return secrets.token_hex(16)
