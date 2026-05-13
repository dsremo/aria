"""Ground-handshake dead-man watchdog (TT&C audit D-3).

If the spacecraft has not received a signed envelope from ground in
``silence_threshold_s`` seconds, the watchdog forces the SafeMode
manager to ``MONITORING_ONLY`` and emits ``aria.ground.silence`` so the
autonomy stack stops accepting non-survival commands until a fresh
ground re-handshake arrives.  The threshold is mission-phase-tunable:

    LEO          24 h    (typical 8-pass-per-day budget)
    Lunar        48 h
    Mars         168 h   (1 week — JPL DSN deep-space practice)

Reference: NASA-STD-8729.1A §5 (dormant-mode autonomy);
JPL DSN deep-space comms playbook (DSN810-005-200) §4.7.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger()


# Per-phase silence thresholds.  Values capture the operational reality
# that long-cruise missions have natural multi-day silences but a LEO
# spacecraft losing ground for 24 h is a real anomaly.
PHASE_SILENCE_THRESHOLDS_S: dict[str, float] = {
    "NOMINAL_LEO":     86_400.0,    # 24 h — Wertz/Larson §15 LEO contact cadence
    "LUNAR_TRANSIT":   172_800.0,   # 48 h
    "MARS_TRANSIT":    604_800.0,   # 7 d  — JPL DSN810-005-200 §4.7
    "OUTER_PLANETARY": 1_209_600.0, # 14 d
}

DEFAULT_SILENCE_THRESHOLD_S = 86_400.0   # s — LEO default per Wertz/Larson §15


@dataclass
class GroundDeadmanState:
    last_handshake_monotonic: float = 0.0
    fired: bool = False


class GroundDeadmanWatchdog:
    """Background watcher that demotes to MONITORING_ONLY on prolonged
    ground silence.  Single-instance per process.
    """

    def __init__(
        self,
        on_silence: Callable[[float], None],
        publish_fn: Optional[Callable[[str, dict[str, Any]], None]] = None,
        silence_threshold_s: float = DEFAULT_SILENCE_THRESHOLD_S,
        poll_interval_s: float = 60.0,
    ) -> None:
        self._on_silence = on_silence
        self._publish = publish_fn or (lambda topic, payload: None)
        self._threshold_s = float(silence_threshold_s)
        # Production poll defaults to 60 s; tests pass small intervals
        # so we accept anything > 0 here and clamp the production
        # default elsewhere.  The watchdog cost is negligible.
        self._poll_interval_s = max(0.001, float(poll_interval_s))
        self._state = GroundDeadmanState()
        # Seed last_handshake to "now" so a fresh boot does not
        # immediately fire — we wait one full silence window before the
        # first alarm.
        self._state.last_handshake_monotonic = time.monotonic()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def record_handshake(self) -> None:
        """Call this every time a verified envelope arrives from ground."""
        with self._lock:
            self._state.last_handshake_monotonic = time.monotonic()
            if self._state.fired:
                logger.warning("ground_deadman.recovered")
                self._state.fired = False
                self._publish("aria.ground.recovered", {})

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ground-deadman-watchdog",
            daemon=True,
        )
        self._thread.start()
        logger.info("ground_deadman.started",
                    threshold_s=self._threshold_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def silence_age_s(self) -> float:
        with self._lock:
            return time.monotonic() - self._state.last_handshake_monotonic

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                age = self.silence_age_s()
                if age > self._threshold_s:
                    fired_now = False
                    with self._lock:
                        if not self._state.fired:
                            self._state.fired = True
                            fired_now = True
                    if fired_now:
                        logger.error(
                            "ground_deadman.silence_detected",
                            age_s=round(age, 0),
                            threshold_s=self._threshold_s,
                        )
                        self._publish("aria.ground.silence", {
                            "age_s": age,
                            "threshold_s": self._threshold_s,
                        })
                        try:
                            self._on_silence(age)
                        except Exception as exc:    # noqa: BLE001
                            logger.error("ground_deadman.callback_failed",
                                         error=str(exc))
            except BaseException as exc:    # noqa: BLE001
                logger.exception("ground_deadman.loop_error",
                                 error=f"{type(exc).__name__}: {exc}")
            self._stop.wait(self._poll_interval_s)
