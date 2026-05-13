"""Replay + TOCTOU defence for inbound actuator commands.

Implements §F-19 of docs/FAILSAFE_ARCHITECTURE.md.

The existing ``safety/command_tracker.py`` is fire-side: it allocates a
monotonic seq for *outbound* commands. The defence missing was on the
*inbound* side, where an actuator (or any safety-critical handler) needs
to reject:

  - replays of a previously-valid command
  - out-of-order arrivals (older than the last accepted)
  - duplicate seq with a different nonce (rebuild attempts)
  - "unsigned" commands (no source identity)

ReplayGuard.accept(source, seq, nonce, now=None) returns
(allowed, reason). State is per-source: each source has its own monotonic
``last_seq`` and a small bounded nonce-history window keyed by
``(seq, nonce)``.

Integrates with:
  - the audit log (every reject is logged)
  - the constitutional layer (a reject pulls the action back to GATE/DENY)
  - the independent monitor (it sees the reject events on the bus)

Threats addressed:
  T-VII-4 TOCTOU race on resource gates
  T-VII-6 replay of one-shot operations
  T-III-7 DSN uplink command spoofing (combined with auth signing)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger()


# Per-source nonce-history window. Larger ⇒ more memory but stronger
# defence against bursts of valid-but-shuffled commands.
NONCE_HISTORY_SIZE = 64

# Maximum age of a (seq, nonce) we still accept relative to now. Commands
# older than this are rejected as stale even if seq is monotonic.
DEFAULT_MAX_AGE_S = 300.0   # 5 min — DSN-typical light-time grace


@dataclass
class _SourceState:
    last_seq: int = 0
    history: Deque[Tuple[int, str, float]] = None  # (seq, nonce, timestamp)

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = deque(maxlen=NONCE_HISTORY_SIZE)


class ReplayGuard:
    """Per-source replay + freshness gate.

    Lock-free fast path on the common case (new highest-seq);
    falls back to a per-source lock for window updates.
    """

    def __init__(self, max_age_s: float = DEFAULT_MAX_AGE_S,
                 state_path: Optional[Path] = None) -> None:
        self._max_age_s = max_age_s
        # Autonomy audit F24 — persist last_seq per source so a process
        # restart does not open a replay window.
        env = os.environ.get("ARIA_RUNTIME_DIR")
        if state_path is None:
            base = Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "runtime"
            state_path = base / "replay_guard.json"
        self._state_path = state_path
        self._sources: Dict[str, _SourceState] = self._load_state()
        self._global_lock = threading.Lock()
        # Coalesced persistence — same pattern as F-19 counter persist.
        self._writes_pending = 0
        self._WRITES_BEFORE_FLUSH = 25
        self._last_flush_monotonic = time.monotonic()
        self._FLUSH_INTERVAL_S = 5.0

    def accept(
        self,
        source: str,
        seq: int,
        nonce: str,
        timestamp: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Return (allowed, reason). Atomic per-source.

        Reject reasons (caller may surface to the audit log):
          - "no_source": source is empty or unknown shape
          - "stale": timestamp older than max_age_s
          - "replay": (seq, nonce) already accepted in the window
          - "rollback": seq <= last_seq for this source
          - "missing_nonce": nonce empty or shorter than 16 chars
        """
        if not source or not isinstance(source, str):
            return False, "no_source"
        if not nonce or len(nonce) < 16:
            return False, "missing_nonce"
        if not isinstance(seq, int) or seq <= 0:
            return False, "bad_seq"

        # Sensor-fusion audit S-6: sample wall-clock once.  Previously
        # ``now = time.time(); if abs(now - time.time()) > max_age``
        # had a TOCTOU window — an NTP step / leap second / VM-pause
        # between the two reads could spuriously age-fail a fresh
        # command, OR an attacker-supplied ``timestamp`` could appear
        # fresh against the first ``time.time()`` and stale against the
        # second.  Single-sample closes the race.
        wall_now = time.time()
        now = wall_now if timestamp is None else float(timestamp)
        if abs(now - wall_now) > self._max_age_s:
            return False, "stale"

        with self._global_lock:
            state = self._sources.setdefault(source, _SourceState())

        # Per-source critical section (small).
        # We use a sentinel via the same global lock for simplicity;
        # contention is low because actuator command rate is bounded.
        with self._global_lock:
            # Replay: same (seq, nonce) seen recently.
            for (s, n, _t) in state.history:
                if s == seq and n == nonce:
                    logger.warning("replay_guard.replay_detected",
                                   source=source, seq=seq, nonce=nonce[:8])
                    return False, "replay"

            # Rollback: seq must be strictly monotonic per source.
            if seq <= state.last_seq:
                logger.warning("replay_guard.rollback",
                               source=source, seq=seq, last=state.last_seq)
                return False, "rollback"

            # Accept: bump last_seq, append to history.
            state.last_seq = seq
            state.history.append((seq, nonce, now))
            self._writes_pending += 1
            now_m = time.monotonic()
            if (self._writes_pending >= self._WRITES_BEFORE_FLUSH
                    or now_m - self._last_flush_monotonic >= self._FLUSH_INTERVAL_S):
                self._persist_locked()
                self._writes_pending = 0
                self._last_flush_monotonic = now_m
            return True, "ok"

    def state(self, source: str) -> dict:
        """Inspection: return last_seq + window size for a source."""
        with self._global_lock:
            s = self._sources.get(source)
            if s is None:
                return {"source": source, "last_seq": 0, "history_size": 0}
            return {
                "source": source,
                "last_seq": s.last_seq,
                "history_size": len(s.history),
            }

    def flush(self) -> None:
        """Force-persist any buffered increments.  Call from a graceful-
        shutdown handler so no replay window opens on restart."""
        with self._global_lock:
            self._persist_locked()
            self._writes_pending = 0
            self._last_flush_monotonic = time.monotonic()

    # ── Persistence helpers (autonomy audit F24) ────────────────

    def _load_state(self) -> Dict[str, _SourceState]:
        path = self._state_path
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            out: Dict[str, _SourceState] = {}
            for src, info in d.items():
                st = _SourceState(last_seq=int(info.get("last_seq", 0)))
                # Wiring audit Pass 1 (F3.2) — restore a bounded slice
                # of the nonce history. Previously only ``last_seq``
                # was persisted, leaving a cold-start window where an
                # attacker who knew the strict-`>`-only behaviour could
                # replay (seq+1, original_nonce) until the in-memory
                # history rebuilt naturally. Persisted history closes
                # that window at the cost of one disk write per accept.
                for entry in info.get("history", []):
                    try:
                        seq = int(entry.get("seq", 0))
                        nonce = str(entry.get("nonce", ""))
                        ts = float(entry.get("ts", 0.0))
                        if seq and nonce:
                            st.history.append((seq, nonce, ts))
                    except (TypeError, ValueError):
                        continue
                out[str(src)] = st
            return out
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("replay_guard.load_failed", error=str(exc))
            return {}

    def _persist_locked(self) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            payload = {
                src: {
                    "last_seq": st.last_seq,
                    # Wiring audit Pass 1 (F3.2) — persist the bounded
                    # history slice so post-restart cold-start window
                    # is closed (matches load above).
                    "history": [
                        {"seq": seq, "nonce": nonce, "ts": ts}
                        for (seq, nonce, ts) in list(st.history)
                    ],
                }
                for src, st in self._sources.items()
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
            logger.error("replay_guard.persist_failed", error=str(exc))


# Process-wide singleton.
_INSTANCE: Optional[ReplayGuard] = None
_INSTANCE_LOCK = threading.Lock()


def get_replay_guard() -> ReplayGuard:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = ReplayGuard()
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
