"""Ship-wide event bus for subsystem pub/sub.

Every subsystem publishes semantic events (reactor_ignited, shield_impact,
eclss_breach, phase_transition, …) to a single in-process bus. Subscribers
pick the events they care about by topic prefix.

Events are also kept in a rolling ring-buffer so the UI can query recent
history via `/api/events/recent` without needing a WebSocket.

Design constraints:
  * **No external broker.** The whole sim is in-process — a dict of callbacks
    is all we need.
  * **Thread-safe** — reactor_neutronics and thermal_management may tick
    from different executors; use a lock around publish/subscribe.
  * **Frozen Event records** — no mutable mistakes leaking into the ring.
  * **Per-subscriber bounded queues** — a slow subscriber never blocks
    other subscribers or the publisher. Queue overflow drops with metrics.
  * **Monotonic sequence counter** — receivers detect gaps (missed events).
  * **Zero external deps.** stdlib only.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


# ── Event record ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Event:
    """One published event. `topic` uses dotted segments so subscribers
    can match prefixes, e.g. subscribing to ``"reactor.*"`` catches
    ``"reactor.ignition"`` and ``"reactor.scram"``.

    The `seq` field is a monotonic per-bus sequence counter, auto-assigned
    on publish. Subscribers can detect gaps (dropped events) by checking
    for missing sequence numbers.
    """

    topic:     str
    timestamp: float                     # wall-clock UNIX time
    sim_time_yr: float                   # mission-elapsed years, if known
    severity:  str                       # 'info' / 'warning' / 'critical' / 'debug'
    payload:   Dict[str, Any] = field(default_factory=dict)
    source:    str = ""                  # module/subsystem that published
    seq:       int = 0                   # monotonic sequence counter
    trace_id:  str = ""                  # R35: propagation id from origin

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ── Bus ─────────────────────────────────────────────────────────────

SubscriberFn = Callable[[Event], None]


# Severity ordering for spam-detector tiers. Higher = more severe.
_SEV_ORDER: Dict[str, int] = {"debug": 0, "info": 1, "warning": 2, "critical": 3}


class EventBus:
    """Thread-safe topic-prefix subscription bus with a ring-buffered history.

    Subscription topic syntax:
      * ``"reactor.ignition"`` — exact topic match
      * ``"reactor.*"``        — prefix match, any sub-topic under reactor
      * ``"*"``                — catch-all
    """

    def __init__(self, history_size: int = 20_000) -> None:
        self._subs: Dict[str, List[SubscriberFn]] = {}
        self._history: Deque[Event] = deque(maxlen=history_size)
        self._lock = threading.RLock()
        self._start_ts = time.time()
        self._seq_counter: int = 0       # monotonic sequence counter
        self._drops: int = 0              # count of subscriber delivery failures

    # ── publish ──────────────────────────────────────────────

    def publish(
        self,
        topic: str,
        *,
        severity: str = "info",
        payload: Optional[Dict[str, Any]] = None,
        source: str = "",
        sim_time_yr: float = 0.0,
        trace_id: str = "",
    ) -> Event:
        """Broadcast an event. Returns the published Event record.

        Each event is assigned a monotonic sequence number for gap detection.

        R35: ``trace_id`` is the top-of-flow correlation id. Defaults
        to the active TraceContext (auto-minted on first read), so a
        publisher inside an HTTP request handler / scheduler tick / bus
        subscriber inherits the originator's id without explicit plumbing.
        Pass an explicit value when crossing a process boundary
        (ground uplink, restored task) where the ContextVar is empty.
        """
        if not trace_id:
            try:
                from aria.security.trace_context import current_trace_id
                trace_id = current_trace_id()
            except Exception:
                trace_id = ""
        with self._lock:
            self._seq_counter += 1
            seq = self._seq_counter
        event = Event(
            topic=topic,
            timestamp=time.time(),
            sim_time_yr=sim_time_yr,
            severity=severity,
            payload=dict(payload or {}),
            source=source,
            seq=seq,
            trace_id=trace_id,
        )
        with self._lock:
            self._history.append(event)
            # Iterate a copy so subscribers can subscribe/unsubscribe inside callbacks
            matches: List[SubscriberFn] = []
            for pattern, fns in self._subs.items():
                if _topic_matches(topic, pattern):
                    matches.extend(fns)
        # Fire outside the lock so slow subscribers don't block publishers.
        # R35: install the event's trace_id into the ContextVar for the
        # duration of each subscriber so any audit / publish that fans
        # out from the handler shares the originator's trace id.
        try:
            from aria.security.trace_context import set_trace_id, reset_trace_id
            _trace_helpers = (set_trace_id, reset_trace_id)
        except Exception:
            _trace_helpers = None
        for fn in matches:
            token = None
            if _trace_helpers and trace_id:
                token = _trace_helpers[0](trace_id)
            try:
                fn(event)
            except Exception as e:
                # Subscriber failure must not take down the publisher.
                # Re-emit as a 'bus.subscriber_error' so operators can see it.
                with self._lock:
                    err_event = Event(
                        topic="bus.subscriber_error",
                        timestamp=time.time(),
                        sim_time_yr=sim_time_yr,
                        severity="warning",
                        payload={"original_topic": topic, "error": str(e)},
                        source="event_bus",
                        trace_id=trace_id,
                    )
                    self._history.append(err_event)
            finally:
                if token is not None and _trace_helpers:
                    _trace_helpers[1](token)
        return event

    # ── subscribe / unsubscribe ──────────────────────────────

    def subscribe(self, pattern: str, fn: SubscriberFn) -> SubscriberFn:
        """Register `fn` to be called for every event whose topic matches
        `pattern`. Returns the function so it can be used as a decorator::

            @bus.subscribe("reactor.*")
            def on_reactor_event(e): ...

        Returns the function unchanged to support decorator syntax.
        """
        with self._lock:
            self._subs.setdefault(pattern, []).append(fn)
        return fn

    def subscribe_queued(
        self, pattern: str, maxsize: int = 1000
    ) -> "queue.Queue[Event]":
        """Subscribe with a bounded queue instead of a callback.

        Returns a Queue that receives matching events. If the queue is
        full, the event is dropped (never blocks the publisher). The
        caller drains the queue at their own pace.

        This is the preferred subscription model for slow consumers
        (e.g., log writers, telemetry recorders, UI websocket bridges).

        Args:
            pattern: Topic pattern (same glob syntax as subscribe).
            maxsize: Max queue depth. Default 1000.

        Returns:
            A Queue[Event] the caller reads from.
        """
        q: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        # R7 (2026-04-24, sync refactor): queue overflow used to drop
        # events SILENTLY — only visible via /api/events/health.
        # Now we publish a `bus.queue_overflow` event the FIRST time
        # the queue fills (per pattern) so the narrator + alarm panel
        # surface the loss to operators.  The flag is per-subscriber
        # so a re-firing during sustained backpressure stays a single
        # warning, not a flood.
        _overflow_announced = {"value": False}

        def _enqueue(event: Event) -> None:
            try:
                q.put_nowait(event)
            except queue.Full:
                with self._lock:
                    self._drops += 1
                # Announce only once per subscriber to avoid feedback
                # loops if the announce-event itself is slow to drain.
                if not _overflow_announced["value"]:
                    _overflow_announced["value"] = True
                    try:
                        # Defer the publish to a side thread so we
                        # don't recurse from inside an `_enqueue` that
                        # is itself running under `publish`.
                        threading.Thread(
                            target=self.publish,
                            kwargs={
                                "topic":   "bus.queue_overflow",
                                "severity": "warning",
                                "source":   "event_bus",
                                "payload":  {"pattern": pattern, "maxsize": maxsize},
                            },
                            daemon=True, name="bus-overflow-warn",
                        ).start()
                    except Exception:
                        pass

        self.subscribe(pattern, _enqueue)
        return q

    def unsubscribe(self, pattern: str, fn: SubscriberFn) -> bool:
        with self._lock:
            subs = self._subs.get(pattern)
            if not subs:
                return False
            try:
                subs.remove(fn)
                if not subs:
                    del self._subs[pattern]
                return True
            except ValueError:
                return False

    # ── history ──────────────────────────────────────────────

    def recent(
        self,
        n: int = 100,
        *,
        topic_prefix: Optional[str] = None,
        min_severity: Optional[str] = None,
    ) -> List[Event]:
        """Last `n` events, most recent first. Optional filters."""
        order = {"debug": 0, "info": 1, "warning": 2, "critical": 3}
        min_level = order.get((min_severity or "debug").lower(), 0)
        with self._lock:
            events = list(self._history)
        events.reverse()
        out: List[Event] = []
        for e in events:
            if topic_prefix and not _topic_matches(e.topic, topic_prefix.rstrip("*") + "*"):
                continue
            if order.get(e.severity.lower(), 0) < min_level:
                continue
            out.append(e)
            if len(out) >= n:
                break
        return out

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    # ── introspection ────────────────────────────────────────

    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._subs.values())

    def topics(self) -> List[str]:
        with self._lock:
            return sorted({e.topic for e in self._history})

    def health(self, window_sim_yr: float | None = None) -> Dict[str, Any]:
        """Observability snapshot: per-topic count + severity histogram
        over the most recent history window (or a bounded sim-yr range).
        Used by the integration tests + `/api/events/health` endpoint
        to detect event spam, silent stalls, or suddenly-firing topics.

        Returns:
            {
              "total_events": int,
              "severity": {info: n, warning: n, critical: n, debug: n},
              "topics": {<topic>: count},
              "top_topics": [[<topic>, count], ...],   # sorted desc
              "spammed_topics": [<topic>, ...],        # >10× within window
              "window_sim_yr": float | None,
              "history_size": int,                     # ring buffer capacity
            }
        """
        with self._lock:
            events = list(self._history)
        if window_sim_yr is not None and events:
            max_t = max(e.sim_time_yr for e in events)
            events = [e for e in events if e.sim_time_yr >= max_t - window_sim_yr]
        from collections import Counter
        topic_counts = Counter(e.topic for e in events)
        sev_counts   = Counter(e.severity for e in events)
        # Spam detector is severity-tiered. The old flat "> 10 anywhere
        # in ring" triggered on every periodic info topic (harvests,
        # SEU rollups, MMOD impacts) once the ring grew to 20 k slots —
        # the list became noise, not signal. Only flag topics that
        # exceed their severity's operational rate:
        #   critical > 5    — rare, one-shot alarms should never fire more
        #   warning  > 50   — stochastic events can fire more, but not this much
        #   info/debug      — never flagged (designed to be high-volume)
        # Scale thresholds proportionally to the effective window. If
        # the caller passed window_sim_yr, use that; otherwise infer the
        # window from the timespan covered by the retained events. Long
        # missions with legitimate periodic warnings (env.solar_flare,
        # hull.impact.*) would otherwise always flag on the flat "> 50"
        # cap once the ring held more than 50 of them.
        if window_sim_yr is not None:
            window_scale = max(1.0, window_sim_yr)
        elif events:
            min_t = min(e.sim_time_yr for e in events)
            max_t = max(e.sim_time_yr for e in events)
            window_scale = max(1.0, max_t - min_t)
        else:
            window_scale = 1.0
        topic_sev: Dict[str, str] = {}
        for e in events:
            # Track worst severity per topic (critical > warning > info).
            prev = topic_sev.get(e.topic)
            if prev is None or _SEV_ORDER.get(e.severity, 0) > _SEV_ORDER.get(prev, 0):
                topic_sev[e.topic] = e.severity
        spammed: List[str] = []
        for topic, count in topic_counts.items():
            sev = topic_sev.get(topic, "info")
            if sev == "critical" and count > 5 * window_scale:
                spammed.append(topic)
            elif sev == "warning" and count > 50 * window_scale:
                spammed.append(topic)
        return {
            "total_events": len(events),
            "severity": dict(sev_counts),
            "topics": dict(topic_counts),
            "top_topics": topic_counts.most_common(10),
            "spammed_topics": spammed,
            "window_sim_yr": window_sim_yr,
            "history_size": self._history.maxlen or 0,
            "sequence_counter": self._seq_counter,
            "subscriber_drops": self._drops,
        }


# ── topic-matching helper ───────────────────────────────────────────

def _topic_matches(topic: str, pattern: str) -> bool:
    """Simple glob-ish matching:
      * "*"           — matches any topic
      * "prefix.*"    — matches topics starting with "prefix."
      * exact string  — matches exact topic
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return topic.startswith(pattern[:-1])
    if pattern.endswith("*"):
        return topic.startswith(pattern[:-1])
    return topic == pattern


# ── Module-level singleton ──────────────────────────────────────────

_DEFAULT_BUS: Optional[EventBus] = None
_DEFAULT_BUS_LOCK = threading.Lock()


def get_event_bus() -> EventBus:
    """Process-wide singleton event bus.

    R65 (2026-04-24): added a module-level lock around the double-checked
    singleton init.  Before the lock, two threads (the aiohttp request
    handler + the auto-tick daemon) could both see `_DEFAULT_BUS is
    None` on first call and each construct a fresh EventBus — whichever
    lost the assignment race would silently drop its subscribers.
    """
    global _DEFAULT_BUS
    if _DEFAULT_BUS is not None:
        return _DEFAULT_BUS
    with _DEFAULT_BUS_LOCK:
        if _DEFAULT_BUS is None:
            _DEFAULT_BUS = EventBus()
        return _DEFAULT_BUS
