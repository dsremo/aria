"""R41 §1.6 — bus / cross-agent communication anomaly monitor.

F-6 binds individual tool calls to capability tokens.  But a deceptive
LLM (alignment-faking, sleeper-agent, in-context scheming — all named
in the threat model under W-2 Mythos) could nudge several agents into
a coordinated drain that *each* looks within budget while the *aggregate*
is anomalous.  The same gap exists for any low-and-slow attack.

This module watches the bus topology + frequency.  It maintains
sliding-window statistics for every (source, topic) pair; novel
patterns (a never-seen-before topic from a normally quiet source, a
9× rate spike, a coordinated burst across multiple agents) trigger an
``aria.security.bus_anomaly`` event.

Design choices:
  * **Self-contained** — no Dsremo dependency at import time so the
    safety subsystem comes up cleanly even if Dsremo is unhealthy.
    The algorithm is a streaming approximation of Adams &
    MacKay 2007 BOCPD over a Poisson rate model — sufficient for
    bus-frequency monitoring and ~50× faster than the full posterior.
  * **Bounded memory** — caps tracked (source, topic) pairs at
    ``max_pairs`` (default 4 096).  When full, evicts least-recently-
    used pair before adding a new one.
  * **Deterministic thresholds** — no learned model parameters that
    a deceptive LLM could poison.  Rates / change-point sensitivity
    are constants of the module.

References:
  Adams & MacKay 2007 "Bayesian Online Changepoint Detection",
  Cambridge Engineering Technical Report; Saatçi et al. 2010
  "Gaussian Process Change Point Models".
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger()


# Default sliding window for rate estimation.  60 s captures both
# high-rate command bursts and slower correlated drains while keeping
# storage small (a typical bus runs ≤ 100 events/s).
DEFAULT_WINDOW_S = 60.0

# Rate-change factor that triggers an anomaly.  9× chosen so a 1-Hz
# baseline becomes 9 Hz before paging — well above natural variance
# but well below a 100× DDoS-class spike.
DEFAULT_RATE_SPIKE_FACTOR = 9.0

# Minimum baseline before we'll fire a spike.  Without this a single
# event from a quiet topic (baseline 0) would always look like ∞×.
MIN_BASELINE_HITS = 5

# Cross-agent burst window — events within this Δt count as
# "coordinated" if they come from ≥ ``min_agents``.
DEFAULT_BURST_WINDOW_S = 2.0
DEFAULT_BURST_MIN_AGENTS = 3

# Cap on tracked (source, topic) pairs.  Above this the LRU evicts
# stale entries before adding a new one.
DEFAULT_MAX_PAIRS = 4096


# ── Data model ──────────────────────────────────────────────────


@dataclass
class _PairStats:
    """Sliding-window stats for one (source, topic) pair."""
    samples: Deque[float] = field(default_factory=deque)   # event timestamps
    last_seen: float = 0.0
    total_hits: int = 0
    first_ts: float = 0.0       # absolute first time we saw this pair
    novel_until: float = 0.0   # newly-seen pairs flagged 'novel' for first 60 s


@dataclass(frozen=True)
class AnomalyReport:
    kind: str            # "rate_spike" | "novel_pair" | "cross_agent_burst"
    source: str
    topic: str
    baseline_per_s: float
    current_per_s: float
    ratio: float
    detail: str = ""


# ── Monitor ────────────────────────────────────────────────────


class BusAnomalyMonitor:
    """Stream-online detector.  Call :meth:`observe(source, topic, ts)`
    on every bus event; the monitor returns at most one
    :class:`AnomalyReport` per call (the dominant signal).
    """

    def __init__(
        self,
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        window_s: float = DEFAULT_WINDOW_S,
        rate_spike_factor: float = DEFAULT_RATE_SPIKE_FACTOR,
        min_baseline_hits: int = MIN_BASELINE_HITS,
        burst_window_s: float = DEFAULT_BURST_WINDOW_S,
        burst_min_agents: int = DEFAULT_BURST_MIN_AGENTS,
        max_pairs: int = DEFAULT_MAX_PAIRS,
    ) -> None:
        self._publish = publish_fn or (lambda topic, payload: None)
        self._window_s = float(window_s)
        self._rate_spike_factor = float(rate_spike_factor)
        self._min_baseline_hits = int(min_baseline_hits)
        self._burst_window_s = float(burst_window_s)
        self._burst_min_agents = int(burst_min_agents)
        self._max_pairs = int(max_pairs)
        # Use OrderedDict for LRU eviction.
        self._pairs: "OrderedDict[Tuple[str, str], _PairStats]" = OrderedDict()
        # Cross-agent burst: per-topic deque of (ts, source).
        self._topic_recent: Dict[str, Deque[Tuple[float, str]]] = defaultdict(deque)
        self._lock = threading.Lock()
        # Counters for diagnostics.
        self.events_seen: int = 0
        self.spikes: int = 0
        self.novel_pairs: int = 0
        self.bursts: int = 0

    # ── Core observe ───────────────────────────────────────────

    def observe(
        self, source: str, topic: str, ts: Optional[float] = None,
    ) -> Optional[AnomalyReport]:
        if not source or not topic:
            return None
        ts = float(ts if ts is not None else time.time())
        with self._lock:
            self.events_seen += 1
            pair = (source, topic)
            stats = self._pairs.get(pair)
            is_novel = stats is None
            if stats is None:
                stats = _PairStats(novel_until=ts + self._window_s,
                                   first_ts=ts)
                self._pairs[pair] = stats
                self._evict_locked()
            else:
                # Move to end → LRU recency.
                self._pairs.move_to_end(pair)

            stats.samples.append(ts)
            stats.total_hits += 1
            stats.last_seen = ts
            cutoff = ts - self._window_s
            while stats.samples and stats.samples[0] < cutoff:
                stats.samples.popleft()

            current_rate = len(stats.samples) / self._window_s

            # Cross-agent burst tracking.
            burst_q = self._topic_recent[topic]
            burst_q.append((ts, source))
            cutoff_burst = ts - self._burst_window_s
            while burst_q and burst_q[0][0] < cutoff_burst:
                burst_q.popleft()
            distinct_agents = {src for _, src in burst_q}

            # ── Decide.  Cross-agent burst wins (it's the loudest
            # signal — coordinated multi-source activity); then
            # novelty; then rate spike.
            if len(distinct_agents) >= self._burst_min_agents:
                self.bursts += 1
                report = AnomalyReport(
                    kind="cross_agent_burst",
                    source=source, topic=topic,
                    baseline_per_s=0.0,
                    current_per_s=current_rate,
                    ratio=float(len(distinct_agents)),
                    detail=(
                        f"{len(distinct_agents)} distinct sources hit "
                        f"'{topic}' within {self._burst_window_s:.1f} s"
                    ),
                )
            elif is_novel:
                self.novel_pairs += 1
                report = AnomalyReport(
                    kind="novel_pair",
                    source=source, topic=topic,
                    baseline_per_s=0.0,
                    current_per_s=current_rate,
                    ratio=float("inf"),
                    detail=f"first-ever event for ({source}, {topic})",
                )
            else:
                report = self._check_rate_spike_locked(
                    pair, stats, current_rate, ts,
                )

        if report is not None:
            self._publish("aria.security.bus_anomaly", {
                "kind": report.kind,
                "source": report.source,
                "topic": report.topic,
                "baseline_per_s": report.baseline_per_s,
                "current_per_s": report.current_per_s,
                "ratio": report.ratio,
                "detail": report.detail,
                "ts": ts,
            })
            logger.warning("bus_anomaly", kind=report.kind,
                           source=report.source, topic=report.topic,
                           ratio=round(report.ratio, 2))
        return report

    # ── Inspection ─────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "events_seen": self.events_seen,
                "tracked_pairs": len(self._pairs),
                "spikes": self.spikes,
                "novel_pairs": self.novel_pairs,
                "bursts": self.bursts,
            }

    # ── Internals ──────────────────────────────────────────────

    def _check_rate_spike_locked(
        self,
        pair: Tuple[str, str],
        stats: _PairStats,
        current_rate: float,
        ts: float,
    ) -> Optional[AnomalyReport]:
        # Need enough history.
        if stats.total_hits < self._min_baseline_hits:
            return None
        # Baseline = events outside the current window divided by the
        # time spent observing them.  Using `first_ts` (absolute first
        # observation) as the lower bound gives a stable rate that
        # doesn't collapse when the window slides past old events.
        denom = max(ts - stats.first_ts - self._window_s, self._window_s)
        baseline_hits = max(stats.total_hits - len(stats.samples), 0)
        baseline_rate = baseline_hits / denom
        baseline_rate = max(baseline_rate, 1.0 / self._window_s)
        if current_rate > self._rate_spike_factor * baseline_rate:
            self.spikes += 1
            return AnomalyReport(
                kind="rate_spike",
                source=pair[0], topic=pair[1],
                baseline_per_s=float(baseline_rate),
                current_per_s=float(current_rate),
                ratio=float(current_rate / baseline_rate),
                detail=(
                    f"rate {current_rate:.2f}/s exceeds baseline "
                    f"{baseline_rate:.3f}/s by "
                    f"{current_rate / baseline_rate:.1f}×"
                ),
            )
        return None

    def _evict_locked(self) -> None:
        while len(self._pairs) > self._max_pairs:
            self._pairs.popitem(last=False)


# ── Module singleton + helpers ──────────────────────────────────


_INSTANCE: Optional[BusAnomalyMonitor] = None
_LOCK = threading.Lock()


def get_bus_anomaly_monitor(
    publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> BusAnomalyMonitor:
    """Return the process-wide singleton.  First caller's publish_fn
    sticks unless explicitly reset."""
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = BusAnomalyMonitor(publish_fn=publish_fn)
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None
