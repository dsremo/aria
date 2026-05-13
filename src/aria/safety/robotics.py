"""R41 §1.7 — robot capability tokens + E-stop watchdog + ISO/TS 15066
force limits + tool-ID attestation.

ARIA's constitution declares ``robotics_maintenance`` and
``robotics_eva`` as gated capabilities, but the codebase has had no
robot-specific safety surface.  This module supplies the four pieces
named in the R41 acceptance:

  1. **Capability token** — every motion command is bound to a
     short-lived token issued by an authorised principal.  The token
     names the robot, the motion class, the workspace envelope, and
     an expiry.  Actuators verify before moving.

  2. **Hardware E-stop watchdog** — heartbeat-driven dead-man.  A
     missed beat (> 100 ms by default) sends ``aria.actuator.estop``
     to all robotic actuators.  A real hardware E-stop button maps
     to the same kill path so a single source of truth covers both.

  3. **ISO/TS 15066 force-limit envelope** — collaborative-robot
     force/pressure limits per body-region table A-1.  The checker
     accepts a proposed motion + speed + body region and refuses
     anything that would exceed the published threshold.

  4. **Tool-ID attestation** — every tool change to a "dangerous"
     tool (cutting, drilling, welding) requires the operator's
     hardware key to sign the tool ID + timestamp.  Replay-defended
     by the per-action challenge ledger.

Reference:
    ISO 10218-1:2011 Robots and robotic devices §5.10 (E-stop);
    ISO/TS 15066:2016 §A "Power and force limits";
    AAMI TIR57:2016 — analogous medical-device pattern.
"""

from __future__ import annotations

import enum
import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ── Capability tokens ───────────────────────────────────────────


class MotionClass(str, enum.Enum):
    NAV     = "nav"          # base mobility, low force
    REACH   = "reach"        # arm reach, low payload
    GRIP    = "grip"         # gripper close, low force
    LIFT    = "lift"         # > 5 kg payload
    CUT     = "cut"          # cutting tools (dangerous)
    DRILL   = "drill"        # drilling (dangerous)
    WELD    = "weld"         # welding (dangerous + radiation)
    EVA     = "eva"          # any motion in EVA proximity


DANGEROUS_CLASSES = frozenset({
    MotionClass.CUT, MotionClass.DRILL, MotionClass.WELD,
})


@dataclass(frozen=True)
class WorkspaceEnvelope:
    """Axis-aligned bounding box in robot base frame (m)."""
    x_min_m: float
    x_max_m: float
    y_min_m: float
    y_max_m: float
    z_min_m: float
    z_max_m: float

    def contains(self, x: float, y: float, z: float) -> bool:
        return (
            self.x_min_m <= x <= self.x_max_m
            and self.y_min_m <= y <= self.y_max_m
            and self.z_min_m <= z <= self.z_max_m
        )


@dataclass(frozen=True)
class CapabilityToken:
    token_id: str
    robot_id: str
    motion_class: MotionClass
    envelope: WorkspaceEnvelope
    issued_at: float
    expires_at: float
    issuer_principal_id: str
    signature_hex: str       # Ed25519 over canonical fields

    def is_expired(self, now: Optional[float] = None) -> bool:
        return float(now or time.time()) >= self.expires_at


def _token_canonical_bytes(
    token_id: str, robot_id: str, motion_class: str,
    envelope: WorkspaceEnvelope, issued_at: float, expires_at: float,
    issuer: str,
) -> bytes:
    import json
    return json.dumps({
        "token_id": token_id,
        "robot_id": robot_id,
        "motion_class": motion_class,
        "envelope": [
            envelope.x_min_m, envelope.x_max_m,
            envelope.y_min_m, envelope.y_max_m,
            envelope.z_min_m, envelope.z_max_m,
        ],
        "issued_at": f"{issued_at:.6f}",
        "expires_at": f"{expires_at:.6f}",
        "issuer": issuer,
    }, sort_keys=True, separators=(",", ":")).encode()


class CapabilityTokenIssuer:
    """Holds an Ed25519 key + issues short-lived robot capability
    tokens.  Production wires this to the same key the attestation
    module uses; tests inject a synthetic key."""

    DEFAULT_TTL_S = 30.0

    def __init__(self, key_path: Optional[str] = None) -> None:
        from aria.security.attestation import (
            _default_key_path, _load_or_generate_key,
        )
        self._signer = _load_or_generate_key(
            key_path or _default_key_path()
        )

    @property
    def pubkey_hex(self) -> str:
        return self._signer.pubkey_hex

    def issue(
        self,
        robot_id: str,
        motion_class: MotionClass,
        envelope: WorkspaceEnvelope,
        issuer_principal_id: str,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> CapabilityToken:
        token_id = os.urandom(16).hex()
        issued_at = time.time()
        expires_at = issued_at + ttl_s
        blob = _token_canonical_bytes(
            token_id, robot_id, motion_class.value, envelope,
            issued_at, expires_at, issuer_principal_id,
        )
        sig = self._signer._priv.sign(blob).hex()
        return CapabilityToken(
            token_id=token_id, robot_id=robot_id,
            motion_class=motion_class, envelope=envelope,
            issued_at=issued_at, expires_at=expires_at,
            issuer_principal_id=issuer_principal_id,
            signature_hex=sig,
        )


def verify_capability_token(
    token: CapabilityToken,
    expected_pubkey_hex: str,
    now: Optional[float] = None,
) -> Tuple[bool, str]:
    """Verify token signature + expiry."""
    if token.is_expired(now):
        return False, "token expired"
    blob = _token_canonical_bytes(
        token.token_id, token.robot_id, token.motion_class.value,
        token.envelope, token.issued_at, token.expires_at,
        token.issuer_principal_id,
    )
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        pub = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(expected_pubkey_hex),
        )
        pub.verify(bytes.fromhex(token.signature_hex), blob)
    except Exception as exc:
        return False, f"signature invalid: {exc}"
    return True, "ok"


# ── ISO/TS 15066 force limits ──────────────────────────────────


# Quasi-static contact force limits (N) per body region — ISO/TS 15066:2016
# Table A.1.  Transient values are typically 2× quasi-static.
ISO_15066_FORCE_LIMITS_N: Dict[str, float] = {
    "skull_forehead":   130.0,
    "face":              65.0,
    "neck":             150.0,
    "neck_back":        145.0,
    "shoulder":         210.0,
    "chest":            140.0,
    "abdomen":          110.0,
    "pelvis":           180.0,
    "back":             210.0,
    "hand_finger":      135.0,
    "thigh":            220.0,
    "knee":             220.0,
    "lower_leg":        130.0,
    "instep":           220.0,
}


@dataclass(frozen=True)
class ForceCheckResult:
    ok: bool
    body_region: str
    proposed_n: float
    limit_n: float
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


def check_force_limit(
    body_region: str,
    proposed_force_n: float,
    transient: bool = False,
) -> ForceCheckResult:
    """Enforce ISO/TS 15066 §A force-limit envelope.

    ``transient`` doubles the limit per the standard's transient-vs-
    quasi-static distinction.  Anything above limit is rejected.
    """
    region = body_region.lower().strip()
    base = ISO_15066_FORCE_LIMITS_N.get(region)
    if base is None:
        return ForceCheckResult(
            ok=False, body_region=region,
            proposed_n=proposed_force_n, limit_n=0.0,
            reason=f"unknown body region '{region}'",
        )
    limit = 2.0 * base if transient else base
    if proposed_force_n > limit:
        return ForceCheckResult(
            ok=False, body_region=region,
            proposed_n=proposed_force_n, limit_n=limit,
            reason=(
                f"force {proposed_force_n:.1f} N exceeds "
                f"ISO/TS 15066 {'transient' if transient else 'quasi-static'} "
                f"limit {limit:.1f} N for {region}"
            ),
        )
    return ForceCheckResult(
        ok=True, body_region=region,
        proposed_n=proposed_force_n, limit_n=limit,
        reason="within envelope",
    )


# ── E-Stop watchdog ────────────────────────────────────────────


class EStopWatchdog:
    """Heartbeat-driven dead-man watchdog.  Robotic actuator subscribes
    to ``aria.actuator.estop`` — emitted on missed heartbeat.

    100 ms grace matches the ISO 10218-1 §5.10 "stop category 0"
    target for emergency motion arrest.
    """

    DEFAULT_GRACE_MS = 100.0

    def __init__(
        self,
        publish_fn: Callable[[str, Dict[str, Any]], None],
        grace_ms: float = DEFAULT_GRACE_MS,
        robot_id: str = "primary",
    ) -> None:
        self._publish = publish_fn
        self._grace_s = float(grace_ms) / 1000.0
        self._robot_id = robot_id
        self._last_beat: Optional[float] = None
        self._fired = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def heartbeat(self, ts: Optional[float] = None) -> None:
        with self._lock:
            self._last_beat = float(ts if ts is not None else time.time())
            self._fired = False

    def silence_age_s(self, now: Optional[float] = None) -> float:
        with self._lock:
            if self._last_beat is None:
                return float("inf")
            return float(now if now is not None else time.time()) - self._last_beat

    def check(self, now: Optional[float] = None) -> bool:
        """Return True if we just fired the E-stop on this call."""
        age = self.silence_age_s(now)
        if age <= self._grace_s:
            return False
        with self._lock:
            if self._fired:
                return False
            self._fired = True
        try:
            self._publish("aria.actuator.estop", {
                "robot_id": self._robot_id,
                "reason": f"heartbeat silence {age*1000:.1f} ms > {self._grace_s*1000:.1f} ms",
                "ts": float(now or time.time()),
            })
        except Exception as exc:
            logger.error("robotics.estop_publish_failed", error=str(exc))
        logger.error("robotics.estop_fired", robot=self._robot_id,
                     age_ms=round(age * 1000, 2),
                     grace_ms=self._grace_s * 1000)
        return True

    def trip_now(self, reason: str = "manual") -> None:
        """Fire the E-stop synchronously — used when a hardware E-stop
        button is depressed (the GPIO handler calls this)."""
        try:
            self._publish("aria.actuator.estop", {
                "robot_id": self._robot_id,
                "reason": f"manual: {reason}",
                "ts": time.time(),
            })
        except Exception as exc:
            logger.error("robotics.estop_publish_failed", error=str(exc))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"estop-{self._robot_id}", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        # Poll at 10× the grace window so we react inside the budget.
        sleep_s = max(self._grace_s / 10.0, 0.005)
        while not self._stop.is_set():
            self.check()
            self._stop.wait(sleep_s)


# ── Tool-ID attestation ────────────────────────────────────────


@dataclass(frozen=True)
class ToolID:
    tool_id: str
    is_dangerous: bool
    name: str = ""


def tool_id_args_hash(tool: ToolID) -> str:
    """SHA-256 over a ToolID for use with the per-action challenge."""
    h = hashlib.sha256()
    h.update(tool.tool_id.encode())
    h.update(b"|")
    h.update(b"D" if tool.is_dangerous else b"S")
    h.update(b"|")
    h.update(tool.name.encode())
    return h.hexdigest()


def require_tool_id_signature(
    challenge_module,
    tool: ToolID,
    principal_id: str,
    signature_hex: str,
    pubkey_hex: str,
    challenge_id: str,
) -> Tuple[bool, str]:
    """Wrap the per-action challenge for a tool change.  Caller must
    have already issued a challenge via challenge_module.issue() with
    ``args_hash = tool_id_args_hash(tool)``."""
    args_hash = tool_id_args_hash(tool)
    result = challenge_module.verify(
        challenge_id=challenge_id,
        action="robot_tool_change",
        args_hash=args_hash,
        principal_id=principal_id,
        signature_hex=signature_hex,
        pubkey_hex=pubkey_hex,
    )
    return result.ok, result.reason
