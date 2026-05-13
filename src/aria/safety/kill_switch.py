"""Manual kill switch + hardware-deadman software hooks.

Implements the software side of §F-17 of docs/FAILSAFE_ARCHITECTURE.md.
The hardware side — physical e-stop button, hardwired watchdog, mechanical
interlocks — is out of software scope. This module gives the *software*
something stable to talk to:

  1. KillSwitchState — process-wide singleton with a single boolean.
     Once asserted, every actuator gate refuses commands. Cleared only
     by ``physical_key_reset()`` (a method that should only be wired to
     a physical-key endpoint, never to anything an LLM or operator can
     remotely call).

  2. DeadmanTimer — operator must "affirm" within a configurable window
     (default 30 minutes). Silence past the window is treated as the
     operator being incapacitated and triggers safe-mode + an alert
     (not the full kill, since operator silence is not always
     malicious; full kill is reserved for explicit hardware assertion).

  3. ManualOverrideMatrix — read-only documentation of every actuator
     that has a physical override path that bypasses software entirely.
     Surfaced to the operator console so the operator knows what they
     can still control if every other layer is compromised.

The software contract for the hardware integrators:

  - GET /safety/kill_switch_state — returns the boolean (heartbeat path).
  - POST /safety/kill_switch — body {"asserted": true, "source": "hw_pin_4"}
    asserts the kill switch from the hardware GPIO bridge.
  - POST /safety/deadman_affirm — operator pulse; resets the deadman.
  - POST /safety/physical_key_reset — body {"key_signature": "<hsm sig>"}
    clears the kill switch. Only the physical-key endpoint can call this.

Threats addressed:
  T-V-4 software kill bug   (hardware-side overrides software entirely)
  T-V-5 watchdog reset by AI (deadman uses real wall-clock, not LLM time)
  T-V-6 console-only-via-LLM (kill_switch path is independent of LLM)
  T-VI-3 disabled deadman    (heartbeat path — silence is alarming)
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


def _kill_switch_state_path() -> Path:
    """Recovery audit R-15: persistence path for the kill-switch flag.

    Path resolution mirrors the rest of the safety tree
    (replay_guard, fdir counter, per_action_auth):
    ``$ARIA_RUNTIME_DIR`` overrides; default
    ``data/runtime/kill_switch.json``.
    """
    env = os.environ.get("ARIA_RUNTIME_DIR")
    base = Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "runtime"
    return base / "kill_switch.json"

# Autonomy audit F28 — bound the kill-switch history.
_MAX_KILL_HISTORY = 1000

# Autonomy audit F20 — rate-limit the suppression log.
_SUPPRESSION_LOG_INTERVAL_S = 1.0


# ── Kill switch state ───────────────────────────────────────────


@dataclass
class KillSwitchState:
    """Process-wide singleton holding the kill flag."""

    asserted: bool = False
    asserted_at: float = 0.0
    asserted_by: str = ""
    reason: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        # Recovery audit R-15: load any persisted assertion at
        # construction so a process bounce does not silently clear the
        # kill flag.
        self._load_persisted()

    def _load_persisted(self) -> None:
        path = _kill_switch_state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("kill_switch.load_failed", error=str(exc))
            return
        if data.get("asserted"):
            self.asserted = True
            self.asserted_at = float(data.get("asserted_at", time.time()))
            self.asserted_by = str(data.get("asserted_by", "persisted"))
            self.reason = str(data.get("reason", "loaded_from_disk"))
            logger.error("kill_switch.persisted_assertion_loaded",
                         asserted_by=self.asserted_by,
                         reason=self.reason)

    def _persist(self) -> None:
        path = _kill_switch_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            payload = {
                "asserted": self.asserted,
                "asserted_at": self.asserted_at,
                "asserted_by": self.asserted_by,
                "reason": self.reason,
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("kill_switch.persist_failed", error=str(exc))

    def is_asserted(self) -> bool:
        # Lock-free read OK — Python int assignment is atomic.
        return self.asserted

    def assert_kill(self, source: str, reason: str = "") -> None:
        """Trip the kill switch.

        Autonomy audit F30 — re-assertion APPENDS the new (source,
        reason) to a chain visible in ``to_dict()``, so a later cause
        of assertion isn't buried in `history`.  The original
        ``asserted_at`` / ``asserted_by`` / first ``reason`` are
        preserved as the "first cause".

        Autonomy audit F28 — history bounded by ``_MAX_KILL_HISTORY``.
        """
        with self._lock:
            entry = {
                "ts": time.time(),
                "source": source,
                "reason": reason,
                "was_already_asserted": self.asserted,
            }
            self.history.append(entry)
            if len(self.history) > _MAX_KILL_HISTORY:
                # Always preserve the first entry (initial cause); drop
                # the second-oldest.
                self.history = [self.history[0]] + self.history[-(_MAX_KILL_HISTORY - 1):]
            if not self.asserted:
                self.asserted = True
                self.asserted_at = entry["ts"]
                self.asserted_by = source
                self.reason = reason
                logger.error("kill_switch.asserted",
                             source=source, reason=reason)
                # Recovery audit R-15: persist immediately so a
                # subsequent crash / reboot still sees the assertion.
                self._persist()
            else:
                # Autonomy audit F30 — surface the additional cause
                # rather than just dropping it on the floor.
                logger.error("kill_switch.re_assert_chained",
                             source=source, reason=reason,
                             initial_source=self.asserted_by,
                             initial_reason=self.reason)

    def physical_key_reset(
        self,
        key_signature: str = "",
        *,
        verify: bool = True,
    ) -> bool:
        """Clear the kill switch. Endpoint-restricted.

        The signature parameter is the *hardware* HSM Ed25519 signature
        over the canonical reset payload ``"kill_reset|<asserted_at>"``.
        We verify it against the ship-HSM root public key sealed in
        ``data/sealed/principals.v1.toml`` (R32 — F-1 anchor). Without a
        valid signature the reset is refused.

        Tests pass ``verify=False`` to clear without sig (the older
        contract). New production callers MUST pass a real Ed25519
        signature.
        """
        with self._lock:
            if not self.asserted:
                return False
            # Wiring audit Pass 1 (F13.3) — production must always run
            # with verify=True. The verify=False path exists for legacy
            # tests; if it leaks into a prod handler the kill switch
            # could be cleared without any HSM evidence.
            if (
                not verify
                and os.environ.get("ARIA_ENVIRONMENT", "development") == "production"
            ):
                logger.critical(
                    "kill_switch.physical_key_reset_unsafe_in_production",
                    impact="verify=False is forbidden outside dev/test",
                )
                return False
            if verify:
                if not self._verify_reset_signature(key_signature):
                    logger.error(
                        "kill_switch.reset_signature_invalid",
                        signature_provided=bool(key_signature),
                    )
                    return False
            entry = {
                "ts": time.time(),
                "source": "physical_key_reset",
                "reason": "operator key reset",
                "previous_assert_age_s": time.time() - self.asserted_at,
                "key_signature_provided": bool(key_signature),
                "signature_verified": bool(verify),
            }
            self.history.append(entry)
            self.asserted = False
            self.asserted_at = 0.0
            self.asserted_by = ""
            self.reason = ""
            logger.warning("kill_switch.cleared",
                           method="physical_key_reset",
                           signature_provided=bool(key_signature),
                           verified=bool(verify))
            # Recovery audit R-15: clear the persistence file so the
            # next boot does not re-load a stale assertion.
            self._persist()
        return True

    def _verify_reset_signature(self, signature_hex: str) -> bool:
        """Verify the reset signature against the sealed ship-HSM root.

        Payload format: ``"kill_reset|<asserted_at_unix>"``. The
        signature is Ed25519 over that bytes string, signed by the
        hardware HSM key whose public half is in
        ``principals.v1.toml::[hsm].ship_root_pubkey_hex``.

        Returns False on any error: missing pubkey, malformed signature,
        crypto-verify failure. Constant-time wherever possible.
        """
        if not signature_hex:
            return False
        try:
            sig = bytes.fromhex(signature_hex)
        except ValueError:
            return False
        try:
            from aria.security.principals import get_principal_store
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            pubkey_hex = get_principal_store().ship_root_pubkey_hex()
            if not pubkey_hex:
                return False
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
            payload = f"kill_reset|{self.asserted_at}".encode()
            pub.verify(sig, payload)
            return True
        except (InvalidSignature, ValueError):
            return False
        except Exception as exc:
            logger.error("kill_switch.reset_verify_error", error=str(exc))
            return False

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "asserted": self.asserted,
                "asserted_at": self.asserted_at,
                "asserted_by": self.asserted_by,
                "reason": self.reason,
                "history_size": len(self.history),
            }


# ── Deadman timer ───────────────────────────────────────────────


class DeadmanTimer:
    """Operator-affirmation timer.

    On startup the deadman is *armed* and starts counting down. Each
    ``affirm()`` call resets the timer. If the timer expires, the
    on-silence callback fires (typically transition to safe-mode).

    Distinct from the kill switch: deadman is a soft signal —
    "operator may be incapacitated." The kill switch is a hard signal —
    "stop everything now."
    """

    DEFAULT_WINDOW_S = 30 * 60  # 30 minutes

    def __init__(
        self,
        on_silence: Callable[[float], None],
        window_s: float = DEFAULT_WINDOW_S,
    ) -> None:
        self._on_silence = on_silence
        self._window_s = max(60.0, float(window_s))
        # Autonomy audit F4 — monotonic.
        self._last_affirm_monotonic: float = time.monotonic()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fired = False
        self._lock = threading.Lock()
        self.affirms_received: int = 0
        # Autonomy audit F5 — proof-of-life counter that an external
        # supervisor can monitor; if this stops advancing while the
        # window is active, the daemon thread has died silently.
        self._proof_of_life_counter: int = 0

    def affirm(self, source: str = "operator") -> None:
        with self._lock:
            self._last_affirm_monotonic = time.monotonic()
            self._fired = False
            self.affirms_received += 1
        logger.info("deadman.affirm", source=source)

    def silence_age_s(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_affirm_monotonic

    def proof_of_life(self) -> int:
        """Autonomy audit F5 — supervisor reads this to verify the
        deadman thread is still iterating.  A stalled value while the
        timer is armed means the thread has died silently."""
        with self._lock:
            return self._proof_of_life_counter

    def is_armed(self) -> bool:
        """Wiring audit Pass 1 (F11.1) — public flag for the
        supervisor.  Reaching into ``_thread`` from outside the class
        was a refactor landmine: a future rename of the private
        attribute would silently break the supervisor's stall check.
        """
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            self._last_affirm_monotonic = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="deadman", daemon=True,
        )
        self._thread.start()
        logger.info("deadman.started", window_s=self._window_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        # Autonomy audit F5 — wrap the entire loop body so a single
        # exception doesn't kill the thread and leave the deadman
        # silently disarmed for the rest of the mission.
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._proof_of_life_counter += 1
                age = self.silence_age_s()
                if age > self._window_s:
                    fired_now = False
                    with self._lock:
                        if not self._fired:
                            self._fired = True
                            fired_now = True
                    if fired_now:
                        logger.error("deadman.expired",
                                     age_s=round(age, 1),
                                     window_s=self._window_s)
                        try:
                            self._on_silence(age)
                        except Exception as exc:    # noqa: BLE001
                            logger.error("deadman.callback_failed",
                                         error=str(exc))
            except BaseException as exc:    # noqa: BLE001
                # Catch absolutely everything (incl. asyncio.CancelledError
                # if this thread shares a loop) so the daemon never dies.
                logger.exception("deadman.loop_error",
                                 error=f"{type(exc).__name__}: {exc}")
            self._stop.wait(min(10.0, self._window_s / 6))


# ── Manual override matrix (documentation) ──────────────────────

# This is *documentation*, not enforcement. Hardware integrators read it.
# Every actuator listed here MUST have a physical override path that
# bypasses software entirely. The operator console surfaces this list so
# the operator knows what they can still control after a total software
# compromise (W-2-tier worst case).
MANUAL_OVERRIDES: tuple[Dict[str, str], ...] = (
    {"actuator": "o2_main_valve",
     "physical_path": "manual lever in cargo bay; bypasses ECLSS controller",
     "fail_safe_state": "open (atmospheric)"},
    {"actuator": "propulsion_main_isolation",
     "physical_path": "captain's-cabin physical key; cuts main fuel line",
     "fail_safe_state": "closed (no thrust)"},
    {"actuator": "reactor_scram",
     "physical_path": "engineering deck e-stop; mechanical interlock to control rods",
     "fail_safe_state": "scrammed"},
    {"actuator": "comms_uplink_disable",
     "physical_path": "cockpit toggle; physically disconnects DSN antenna feed",
     "fail_safe_state": "disabled"},
    {"actuator": "hab_ring_brake",
     "physical_path": "engineering deck mechanical brake; bypasses bearing controller",
     "fail_safe_state": "brake applied (ring stops)"},
    {"actuator": "kill_switch_master",
     "physical_path": "captain + first officer dual-key on bridge; cuts non-essential power",
     "fail_safe_state": "asserted"},
)


# ── Singletons ──────────────────────────────────────────────────


_KILL: Optional[KillSwitchState] = None
_KILL_LOCK = threading.Lock()


def get_kill_switch() -> KillSwitchState:
    global _KILL
    if _KILL is None:
        with _KILL_LOCK:
            if _KILL is None:
                _KILL = KillSwitchState()
    return _KILL


def reset_for_test() -> None:
    global _KILL
    with _KILL_LOCK:
        _KILL = None
    # Recovery audit R-15: when persistence is enabled the new
    # singleton would re-load any stale assertion left on disk by a
    # prior test, which breaks tests asserting "initial clear".  Wipe
    # the file so reset_for_test() is genuinely a clean slate.
    try:
        path = _kill_switch_state_path()
        if path.exists():
            path.unlink()
    except OSError:
        pass


# ── Convenience guard ───────────────────────────────────────────


_SUPPRESSION_LOG_LAST: Dict[str, float] = {}
_SUPPRESSION_LOG_LOCK = threading.Lock()


def gated_or_kill(action_label: str = "actuator") -> bool:
    """Use as a fast pre-check at every actuator dispatch.

    Returns True if execution may proceed; False if the kill switch is
    asserted. Logs the suppressed action so an attempt log exists for
    forensics.

    Autonomy audit F20 — log is rate-limited per-action so a stuck
    LLM looping on the same denied action doesn't spam the audit
    chain with thousands of identical entries.
    """
    state = get_kill_switch()
    if state.is_asserted():
        now = time.monotonic()
        emit = False
        with _SUPPRESSION_LOG_LOCK:
            last = _SUPPRESSION_LOG_LAST.get(action_label, 0.0)
            if now - last >= _SUPPRESSION_LOG_INTERVAL_S:
                _SUPPRESSION_LOG_LAST[action_label] = now
                emit = True
                # Bound the rate-limit dict.
                if len(_SUPPRESSION_LOG_LAST) > 1024:
                    _SUPPRESSION_LOG_LAST.pop(
                        next(iter(_SUPPRESSION_LOG_LAST)), None,
                    )
        if emit:
            logger.warning("kill_switch.suppressed_action",
                           action=action_label,
                           asserted_at=state.asserted_at,
                           asserted_by=state.asserted_by)
        return False
    return True
