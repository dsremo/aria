"""Per-source-IP sliding-window rate limiter for the HTTP/WS command path.

TT&C audit H-1: the previous per-endpoint list (`self._command_timestamps`)
was a global counter — a flood from one IP starved every other client of
the budget; a distributed flood bypassed the limit entirely.  This
limiter buckets per source-IP and exponentially backs off after
repeated violations.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Optional

import structlog

logger = structlog.get_logger()


# Sliding-window defaults — match the previous module-wide budget so
# legitimate ground-station clients do not see a behavioural regression.
DEFAULT_RATE_PER_MIN = 30        # commands/minute per IP — ground-cmd typical
DEFAULT_WINDOW_S = 60.0          # s — sliding window length
DEFAULT_BACKOFF_BASE_S = 5.0     # s — first violation block; doubles per repeat
DEFAULT_BACKOFF_MAX_S = 3600.0   # s — 1 h ceiling
DEFAULT_MAX_TRACKED_IPS = 10_000 # bound the dict so a /16 scan can't blow RAM


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    remaining: int = 0
    retry_after_s: float = 0.0
    violations: int = 0
    reason: str = ""


class _IPState:
    __slots__ = ("hits", "violations", "blocked_until")

    def __init__(self) -> None:
        self.hits: Deque[float] = deque()
        self.violations: int = 0
        self.blocked_until: float = 0.0


class PerIPRateLimiter:
    """Thread-safe sliding-window + exponential-backoff per-IP limiter."""

    def __init__(
        self,
        rate_per_min: int = DEFAULT_RATE_PER_MIN,
        window_s: float = DEFAULT_WINDOW_S,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        backoff_max_s: float = DEFAULT_BACKOFF_MAX_S,
        max_tracked_ips: int = DEFAULT_MAX_TRACKED_IPS,
        persist_path: Optional[str | os.PathLike] = None,
    ) -> None:
        self._rate_per_min = int(rate_per_min)
        self._window_s = float(window_s)
        self._backoff_base_s = float(backoff_base_s)
        self._backoff_max_s = float(backoff_max_s)
        self._max_tracked_ips = int(max_tracked_ips)
        self._states: "OrderedDict[str, _IPState]" = OrderedDict()
        self._lock = threading.Lock()
        # Wiring audit Pass 7 (F5.3) — persist the violations counter
        # and blocked_until window so a process bounce cannot silently
        # reset an attacker's exponential-backoff cooldown. The hits
        # deque (sliding window) is intentionally NOT persisted — it
        # rebuilds naturally and persisting wall-clock-relative
        # monotonic timestamps would mis-translate across restart.
        env = os.environ.get("ARIA_RUNTIME_DIR")
        if persist_path is not None:
            self._persist_path: Optional[Path] = Path(persist_path)
        elif env:
            self._persist_path = Path(env) / "api_rate_limiter.json"
        else:
            self._persist_path = (
                Path(__file__).resolve().parents[3]
                / "data" / "runtime" / "api_rate_limiter.json"
            )
        self._load_persisted_state()
        # Wiring audit Pass 7 (F5.3) — coalesce writes; persist when a
        # violation lands or when a block is set, not on every check().
        self._dirty: bool = False

    def check(self, source_ip: str) -> RateLimitVerdict:
        if not source_ip:
            source_ip = "unknown"
        now = time.monotonic()
        cutoff = now - self._window_s

        with self._lock:
            state = self._states.get(source_ip)
            if state is None:
                # Wiring audit Pass 7 (F5.5) — when the LRU is full,
                # do NOT evict an entry whose ``blocked_until`` window
                # is still active. Eviction silently clears the
                # exponential-backoff hard-block of attacker IPs that
                # an adversary could trigger via a /16 scan flooding
                # 10000 distinct source-IPs to reset their own block.
                # If every slot is currently blocked, refuse the new
                # IP outright — the limiter is full of real abusers,
                # so legitimate clients can wait the cooldown.
                if len(self._states) >= self._max_tracked_ips:
                    evicted = False
                    for candidate_ip, candidate_state in list(
                        self._states.items()
                    ):
                        if candidate_state.blocked_until <= now:
                            del self._states[candidate_ip]
                            evicted = True
                            break
                    if not evicted:
                        return RateLimitVerdict(
                            allowed=False,
                            remaining=0,
                            retry_after_s=self._backoff_base_s,
                            violations=0,
                            reason="overflow",
                        )
                state = _IPState()
                self._states[source_ip] = state
            else:
                self._states.move_to_end(source_ip)

            # Hard block window from prior violations.
            if state.blocked_until > now:
                return RateLimitVerdict(
                    allowed=False,
                    remaining=0,
                    retry_after_s=state.blocked_until - now,
                    violations=state.violations,
                    reason="blocked",
                )

            # Drop hits older than window_s.
            while state.hits and state.hits[0] < cutoff:
                state.hits.popleft()

            if len(state.hits) >= self._rate_per_min:
                state.violations += 1
                shift = min(state.violations - 1, 10)
                backoff = min(
                    self._backoff_base_s * (2 ** shift),
                    self._backoff_max_s,
                )
                state.blocked_until = now + backoff
                self._dirty = True
                self._persist_locked()
                return RateLimitVerdict(
                    allowed=False,
                    remaining=0,
                    retry_after_s=backoff,
                    violations=state.violations,
                    reason="rate_exceeded",
                )

            state.hits.append(now)
            return RateLimitVerdict(
                allowed=True,
                remaining=self._rate_per_min - len(state.hits),
                retry_after_s=0.0,
                violations=state.violations,
                reason="ok",
            )

    # ── Persistence (F5.3) ──────────────────────────────────────────

    def _persist_locked(self) -> None:
        """Atomically write violations + blocked_until per IP. Caller
        must hold ``self._lock``. The transient ``hits`` deque is NOT
        persisted (sliding-window rebuilds naturally; monotonic
        timestamps don't survive restart anyway).

        ``blocked_until`` is converted to a wall-clock deadline so the
        new monotonic clock on restart can re-anchor.
        """
        if self._persist_path is None:
            return
        if not self._dirty:
            return
        now_mono = time.monotonic()
        now_wall = time.time()
        payload = {
            "schema_version": 1,
            "saved_at_wall": now_wall,
            "states": {
                source_ip: {
                    "violations": st.violations,
                    "blocked_until_age_s": (
                        st.blocked_until - now_mono
                        if st.blocked_until > now_mono
                        else 0.0
                    ),
                }
                for source_ip, st in self._states.items()
                # Only persist IPs with non-zero state (sparse).
                if st.violations > 0 or st.blocked_until > now_mono
            },
        }
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(
                self._persist_path.suffix + ".tmp"
            )
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp, self._persist_path)
            self._dirty = False
        except OSError as exc:
            logger.warning("rate_limiter.persist_failed", error=str(exc))

    def _load_persisted_state(self) -> None:
        if self._persist_path is None or not self._persist_path.is_file():
            return
        try:
            payload = json.loads(
                self._persist_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("rate_limiter.load_failed", error=str(exc))
            return
        if payload.get("schema_version") != 1:
            return

        now_mono = time.monotonic()
        now_wall = time.time()
        saved_at_wall = float(payload.get("saved_at_wall", now_wall))
        elapsed_since_save = max(0.0, now_wall - saved_at_wall)

        for source_ip, info in payload.get("states", {}).items():
            try:
                st = _IPState()
                st.violations = int(info.get("violations", 0))
                blocked_age_remaining = (
                    float(info.get("blocked_until_age_s", 0.0))
                    - elapsed_since_save
                )
                if blocked_age_remaining > 0:
                    st.blocked_until = now_mono + blocked_age_remaining
                self._states[str(source_ip)] = st
            except (TypeError, ValueError):
                continue

    def reset_for_test(self) -> None:
        with self._lock:
            self._states.clear()
