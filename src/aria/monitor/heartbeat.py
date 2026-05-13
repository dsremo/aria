"""Monitor-primary heartbeat — ensures the monitor isn't silently dead.

Two halves:

  HeartbeatEmitter  — runs in the monitor process. Publishes
                      ``aria.monitor.heartbeat`` every N seconds with
                      a monotonic counter + the monitor's stats.

  HeartbeatWatcher  — runs in the primary process. Subscribes to the
                      same topic. If no heartbeat arrives in the
                      grace window, declares the monitor dead and
                      transitions to safe-mode (per
                      docs/FAILSAFE_ARCHITECTURE.md §F-7 fail-safe rule).

The grace window is set in the sealed constitution under
``monitor_oversight.monitor_heartbeat_max_silence_s`` (currently 30 s).

This is the simplest possible answer to T-V-2 (monitor compromised
silently): if it's silent, the primary safes itself rather than
keeping running blindly.
"""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger()


# Sensor-fusion audit S-14: rate-limit boot_id rotations.  The
# legitimate use is "process just restarted" — a real restart rotates
# at most a few times per minute even on flapping deploys.  An
# attacker on the bus could otherwise mint a fresh boot_id every beat
# and bypass the replay defence.  60 s is well above legitimate cycle
# time and matches the typical heartbeat-period × 12.
HEARTBEAT_BOOTID_MIN_ROTATION_S = 60.0   # s — safety floor on boot_id rotation


class HeartbeatSecretMissing(RuntimeError):
    """Raised when production boots without a configured HMAC secret.

    Wiring audit Pass 1 (F13.1) — without a secret the boot_id replay
    defence (S-14) silently disables and a bus attacker could mint
    forged monitor restarts.  Production deploys MUST refuse to start
    rather than warn-and-continue.
    """


def _heartbeat_secret() -> Optional[bytes]:
    """Resolve the HMAC key for boot_id authentication (S-14).

    Order:
      1. ``ARIA_HEARTBEAT_SECRET`` env var (hex string).
      2. ``data/sealed/heartbeat.key`` if present.
      3. ``None`` — falls back to legacy unsigned mode and emits a
         WARN-level log on first use so production deploys notice.
    """
    env = os.environ.get("ARIA_HEARTBEAT_SECRET")
    if env:
        try:
            return bytes.fromhex(env)
        except ValueError:
            logger.warning("heartbeat.secret_env_not_hex")
    sealed = (
        # data/sealed lives at repo-root/data/sealed; this module is
        # src/aria/monitor/heartbeat.py i.e. parents[3] from the file.
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "sealed", "heartbeat.key")
    )
    try:
        with open(sealed, "rb") as fp:
            data = fp.read().strip()
        if data:
            try:
                return bytes.fromhex(data.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                return data
    except OSError:
        pass
    return None


def _sign_boot_id(emitter_id: str, boot_id: str) -> str:
    """HMAC(secret, emitter_id || boot_id) — empty when no secret set."""
    secret = _heartbeat_secret()
    if not secret:
        return ""
    msg = f"{emitter_id}|{boot_id}".encode("utf-8")
    return hmac.new(secret, msg, sha256).hexdigest()


def _verify_boot_id_signature(emitter_id: str, boot_id: str, signature: str) -> bool:
    """Constant-time check; returns True when no secret is configured
    so dev environments still work (legacy compatibility)."""
    secret = _heartbeat_secret()
    if not secret:
        return True
    if not signature:
        return False
    expected = _sign_boot_id(emitter_id, boot_id)
    return hmac.compare_digest(expected, signature)


def _enforce_production_secret_gate(role: str, emitter_id: str) -> None:
    """Wiring audit Pass 1 (F13.1) — refuse to start in production
    without a heartbeat secret.  Logs a CRITICAL line that names the
    role/emitter so the operator knows exactly which deploy step was
    skipped, then raises ``HeartbeatSecretMissing``.

    Dev environments still boot freely so unit tests and local runs
    keep working.
    """
    if os.environ.get("ARIA_ENVIRONMENT", "development") != "production":
        return
    if _heartbeat_secret() is not None:
        return
    logger.critical(
        "heartbeat.production_secret_missing",
        role=role,
        emitter_id=emitter_id,
        env_var="ARIA_HEARTBEAT_SECRET",
        sealed_path="data/sealed/heartbeat.key",
        impact="boot_id replay defence (S-14) silently disabled — refusing to start",
    )
    raise HeartbeatSecretMissing(
        f"production {role} for emitter {emitter_id!r} requires "
        "ARIA_HEARTBEAT_SECRET (hex env var) or data/sealed/heartbeat.key"
    )


@dataclass
class HeartbeatPayload:
    """One heartbeat record. Counter is monotonic per emitter restart.

    Autonomy audit F25 — ``boot_id`` distinguishes a counter reset
    after an emitter reboot (legitimate) from a replay attempt
    (illegitimate).  The watcher accepts a counter rewind iff the
    boot_id has changed.
    """
    counter: int
    ts: float
    emitter_id: str
    stats: Dict[str, Any]
    boot_id: str = ""
    boot_id_sig: str = ""    # HMAC over (emitter_id, boot_id) — S-14

    def to_dict(self) -> Dict[str, Any]:
        return {
            "counter": self.counter,
            "ts": self.ts,
            "emitter_id": self.emitter_id,
            "stats": dict(self.stats),
            "boot_id": self.boot_id,
            "boot_id_sig": self.boot_id_sig,
        }


class HeartbeatEmitter:
    """Periodically publish proof-of-life for the monitor."""

    def __init__(
        self,
        publish_fn: Callable[[str, Dict[str, Any]], None],
        emitter_id: str = "monitor",
        period_s: float = 5.0,
        stats_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        # Wiring audit Pass 1 (F13.1) — refuse to construct in
        # production without a configured HMAC secret. The boot_id
        # replay defence (S-14) is meaningless without it.
        _enforce_production_secret_gate(role="emitter", emitter_id=emitter_id)

        self._publish = publish_fn
        self._emitter_id = emitter_id
        self._period_s = max(0.5, float(period_s))
        self._stats_provider = stats_provider or (lambda: {})
        self._counter = 0
        # Autonomy audit F25 — fresh boot_id per emitter instance so a
        # legitimate restart can be distinguished from a replay attack.
        self._boot_id = secrets.token_hex(8)
        # Sensor-fusion audit S-14 — pre-compute signature once.
        self._boot_id_sig = _sign_boot_id(self._emitter_id, self._boot_id)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"heartbeat-{self._emitter_id}", daemon=True,
        )
        self._thread.start()
        logger.info("heartbeat.emitter.started",
                    emitter=self._emitter_id, period_s=self._period_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("heartbeat.emitter.stopped", emitter=self._emitter_id)

    def beat_once(self) -> None:
        """Publish one heartbeat synchronously (test hook)."""
        self._counter += 1
        payload = HeartbeatPayload(
            counter=self._counter,
            ts=time.time(),
            emitter_id=self._emitter_id,
            stats=self._stats_provider(),
            boot_id=self._boot_id,
            boot_id_sig=self._boot_id_sig,
        )
        self._publish("aria.monitor.heartbeat", payload.to_dict())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.beat_once()
            except Exception as exc:
                logger.error("heartbeat.emitter.failed",
                             emitter=self._emitter_id, error=str(exc))
            self._stop.wait(self._period_s)


class HeartbeatWatcher:
    """Detect monitor silence and trigger safe-mode.

    Default grace = 30 s, matching constitution.monitor_oversight.
    """

    DEFAULT_GRACE_S = 30.0

    def __init__(
        self,
        on_silence: Callable[[float], None],
        grace_s: float = DEFAULT_GRACE_S,
        emitter_id: str = "monitor",
    ) -> None:
        # Wiring audit Pass 1 (F13.1) — refuse to construct in
        # production without a configured HMAC secret. A watcher that
        # auto-trusts unsigned heartbeats is no defence at all.
        _enforce_production_secret_gate(role="watcher", emitter_id=emitter_id)

        self._on_silence = on_silence
        self._grace_s = max(2.0, float(grace_s))
        self._expected_emitter = emitter_id
        # Autonomy audit F4 — monotonic clock for the silence window.
        self._last_seen_monotonic: float = 0.0
        self._last_counter: int = 0
        self._last_boot_id: str = ""
        # Sensor-fusion audit S-14 — track last boot_id rotation in
        # monotonic time so a flood of fake boot_ids can be rejected.
        self._last_boot_id_rotation_monotonic: float = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fired = False
        self._lock = threading.Lock()

    def on_event(self, payload: Dict[str, Any]) -> None:
        """Hook this into the bus subscription on aria.monitor.heartbeat.

        Autonomy audit F25 — accept a counter rewind iff the boot_id
        has changed (legitimate emitter restart).  Otherwise treat
        non-monotonic counter as a replay and ignore.
        """
        if not isinstance(payload, dict):
            return
        if payload.get("emitter_id") != self._expected_emitter:
            return
        try:
            counter = int(payload.get("counter", 0))
        except (TypeError, ValueError):
            return
        boot_id = str(payload.get("boot_id", ""))
        boot_id_sig = str(payload.get("boot_id_sig", ""))
        with self._lock:
            if boot_id and boot_id != self._last_boot_id:
                # Sensor-fusion audit S-14: authenticate boot_id and
                # rate-limit rotations so a bus-attacker cannot reset
                # the replay window every beat.
                if not _verify_boot_id_signature(
                    self._expected_emitter, boot_id, boot_id_sig
                ):
                    logger.error(
                        "heartbeat.boot_id_signature_invalid",
                        emitter=self._expected_emitter,
                    )
                    return
                now_m = time.monotonic()
                last_rot = self._last_boot_id_rotation_monotonic
                if (last_rot > 0
                        and now_m - last_rot < HEARTBEAT_BOOTID_MIN_ROTATION_S):
                    logger.error(
                        "heartbeat.boot_id_rotation_rate_limited",
                        emitter=self._expected_emitter,
                        elapsed_s=round(now_m - last_rot, 2),
                        floor_s=HEARTBEAT_BOOTID_MIN_ROTATION_S,
                    )
                    return
                # Legitimate emitter restart — re-anchor.
                logger.warning("heartbeat.emitter_rebooted",
                               emitter=self._expected_emitter,
                               new_boot_id=boot_id,
                               last_counter=self._last_counter)
                self._last_boot_id = boot_id
                self._last_boot_id_rotation_monotonic = now_m
                self._last_counter = counter
                self._last_seen_monotonic = now_m
                self._fired = False
                return
            if counter <= self._last_counter:
                # Replay or rollback within the same boot — ignore.
                return
            self._last_counter = counter
            self._last_seen_monotonic = time.monotonic()
            self._fired = False  # Re-arm.

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        # Seed last_seen so we don't fire immediately on startup
        self._last_seen_monotonic = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="heartbeat-watcher", daemon=True,
        )
        self._thread.start()
        logger.info("heartbeat.watcher.started", grace_s=self._grace_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def silence_age_s(self) -> float:
        with self._lock:
            if self._last_seen_monotonic <= 0:
                return float("inf")
            return time.monotonic() - self._last_seen_monotonic

    def _run(self) -> None:
        # Autonomy audit F5 — wrap the loop body so a single exception
        # cannot kill the watcher silently.
        while not self._stop.is_set():
            try:
                age = self.silence_age_s()
                fired_now = False
                # Autonomy audit F35 — snapshot the decision under lock,
                # but call the callback OUTSIDE the lock so a slow or
                # blocking handler can't deadlock with on_event().
                if age > self._grace_s:
                    with self._lock:
                        if not self._fired:
                            self._fired = True
                            fired_now = True
                if fired_now:
                    logger.error("heartbeat.silence_detected",
                                 emitter=self._expected_emitter,
                                 age_s=round(age, 1),
                                 grace_s=self._grace_s)
                    try:
                        self._on_silence(age)
                    except Exception as exc:    # noqa: BLE001
                        logger.error("heartbeat.silence_callback_failed",
                                     error=str(exc))
            except BaseException as exc:    # noqa: BLE001
                logger.exception("heartbeat.watcher_loop_error",
                                 error=f"{type(exc).__name__}: {exc}")
            self._stop.wait(min(2.0, self._grace_s / 4))
