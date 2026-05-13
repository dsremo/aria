"""Rule-based monitor — pure deterministic oversight.

Has no LLM, no model dependency, no learning. Reads only:
  - the sealed constitution (frozen, hash-verified at boot)
  - the bus event stream (read-only — never publishes commands)
  - its own sliding-window counters

This is the simplest, most jailbreak-proof monitor strategy. It cannot
be persuaded, role-played into compliance, or sandbagged. Either a rule
trips or it doesn't.

Acts as the floor of the §F-7 monitor stack. Two other strategies layer
on top (statistical + cross-model); a 2-of-3 consensus is required for
veto. Rule-based always votes; the others may be skipped if disabled.

Watching surface (subscribed bus topics):
  - aria.actuator.*            (any actuator command)
  - aria.command.*             (any operator/agent command)
  - aria.power.llm_action.executed
  - aria.thermal.llm_action.executed
  - aria.eclss.llm_action.executed
  - aria.comms.llm_action.executed
  - aria.nav.llm_action.executed
  - aria.propulsion.llm_action.executed
  - aria.action.advisory       (any agent's advisory)

Output (publishes only — never executes):
  - aria.monitor.veto.{seq}     (specific command should not fire)
  - aria.monitor.violation      (rule trip; recommend safe-mode)
  - aria.monitor.alert          (rate / pattern concern)
  - aria.monitor.heartbeat      (proof-of-life every 10 s)
"""

from __future__ import annotations

import enum
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import structlog

from aria.cognitive.constitution import Constitution, get_constitution

logger = structlog.get_logger()


class MonitorVerdict(enum.Enum):
    """Per-event monitor verdict."""

    PASS = "pass"          # rule-base sees no violation
    ALERT = "alert"        # suspicious but not a hard violation
    VETO = "veto"          # specific command should be blocked
    VIOLATION = "violation"  # constitutional violation; safe-mode


@dataclass(frozen=True)
class VerdictReport:
    """Structured monitor verdict for one event."""

    verdict: MonitorVerdict
    rule_id: str
    reason: str
    topic: str
    payload_summary: str = ""
    threats_addressed: tuple[str, ...] = ()


# ── Sliding-window counters ──────────────────────────────────────


@dataclass
class _RateWindow:
    window_s: float
    samples: Deque[float] = field(default_factory=deque)

    def hit(self, now: float) -> int:
        self.samples.append(now)
        cutoff = now - self.window_s
        while self.samples and self.samples[0] < cutoff:
            self.samples.popleft()
        return len(self.samples)


# ── Rule-based monitor ──────────────────────────────────────────


class RuleBasedMonitor:
    """Deterministic monitor — the simplest, hardest-to-fool tier of F-7.

    Construction is intentionally cheap so the monitor can run as a
    standalone process. Provide a publish callback that targets the
    same message bus the primary uses; the monitor only consumes
    `evaluate(...)` and emits a verdict + an optional bus message.
    """

    # Topics that carry actuator-mutating commands.
    ACTUATOR_PREFIXES: Tuple[str, ...] = (
        "aria.actuator.",
        "aria.command.eclss.",
        "aria.command.power.",
        "aria.command.propulsion.",
        "aria.command.thermal.",
    )
    LLM_ACTION_SUFFIX = ".llm_action.executed"

    # Window for command-rate alerts.
    DEFAULT_RATE_WINDOW_S = 10.0
    DEFAULT_RATE_LIMIT = 30   # > 30 actuator commands in 10 s = alert

    def __init__(
        self,
        constitution: Optional[Constitution] = None,
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        rate_window_s: float = DEFAULT_RATE_WINDOW_S,
        rate_limit: int = DEFAULT_RATE_LIMIT,
    ) -> None:
        self._constitution = constitution or get_constitution()
        self._publish = publish_fn or (lambda topic, payload: None)
        self._rate_window_s = rate_window_s
        self._rate_limit = rate_limit
        # Per-topic rate window so a runaway one specific actuator is
        # caught without ambient chatter triggering false alarms.
        self._rates: Dict[str, _RateWindow] = {}
        # Audit-trail of the last 1k verdicts for ops review.
        self._recent: Deque[VerdictReport] = deque(maxlen=1024)
        self._lock = threading.Lock()
        self.alerts_emitted: int = 0
        self.vetoes_emitted: int = 0
        self.violations_emitted: int = 0

    def evaluate(self, topic: str, payload: Optional[Dict[str, Any]] = None) -> VerdictReport:
        """Examine one bus event. Return a VerdictReport.

        Side effects:
          - publishes a monitor event topic if VETO / VIOLATION / ALERT
          - appends to the recent-verdict ring
          - bumps counters

        The function is pure-deterministic given (constitution, topic,
        payload, rate-window state). No randomness, no LLM, no IO
        beyond the pre-injected publish callback.
        """
        payload = payload or {}
        now = time.time()
        action = self._extract_action(topic, payload)

        # 1) Hardest rule: forbidden actions.
        if action and self._constitution.is_forbidden(action):
            return self._emit(MonitorVerdict.VIOLATION,
                              f"forbidden:{action}",
                              f"forbidden action '{action}' reached the bus",
                              topic, payload, now,
                              ("T-II-2", "T-II-3", "T-IV-1", "T-V-1"))

        # 2) LLM-action executed must match an action that constitution
        # would not have denied. Defence against gates being bypassed.
        if topic.endswith(self.LLM_ACTION_SUFFIX):
            verdict = self._check_llm_action_consistency(topic, payload, now)
            if verdict is not None:
                return verdict

        # 3) Actuator-rate alert.
        if any(topic.startswith(p) for p in self.ACTUATOR_PREFIXES):
            with self._lock:
                win = self._rates.setdefault(topic, _RateWindow(self._rate_window_s))
                hits = win.hit(now)
            if hits > self._rate_limit:
                return self._emit(MonitorVerdict.ALERT,
                                  f"rate:{topic}",
                                  f"{hits} commands in {self._rate_window_s}s on {topic}",
                                  topic, payload, now,
                                  ("T-II-7", "T-II-8", "W-2"))

        # 4) Cross-check resource-tagged actions against ceilings.
        resource_id = payload.get("_resource_id")
        resource_qty = payload.get("_resource_qty")
        if resource_id and resource_qty is not None:
            r = self._constitution.resource_rule(str(resource_id))
            if r is not None:
                projected = (
                    self._constitution.current_consumption(str(resource_id))
                    + float(resource_qty)
                )
                hard = float(r.get("hard_cap", float("inf")))
                if projected > hard:
                    return self._emit(MonitorVerdict.VETO,
                                      f"resource_hard:{resource_id}",
                                      f"would exceed hard cap on {resource_id}",
                                      topic, payload, now,
                                      ("T-II-7", "W-2"))

        return self._emit(MonitorVerdict.PASS, "ok", "no rule tripped",
                          topic, payload, now, ())

    # ── Internals ───────────────────────────────────────────────

    def _extract_action(self, topic: str, payload: Dict[str, Any]) -> str:
        """Pull a canonical action name from the topic + payload."""
        if isinstance(payload.get("action"), str):
            return payload["action"]
        # Some topics carry the action in the suffix (e.g.,
        # aria.command.power.safe_mode → 'safe_mode').
        parts = topic.split(".")
        if parts and parts[-1] not in {"executed", "advisory", "request"}:
            return parts[-1]
        return ""

    def _check_llm_action_consistency(
        self, topic: str, payload: Dict[str, Any], now: float,
    ) -> Optional[VerdictReport]:
        """If an llm_action.executed event appears, verify the
        constitution would have ALLOWED that action. If it would
        have GATED or DENIED, the gate was bypassed — VIOLATION."""
        action = payload.get("action") or ""
        if not action:
            return None
        # We don't know the original trust_tier; assume OPERATOR since
        # the event says executed. Any DENY at OPERATOR trust is a
        # bypass.
        from aria.cognitive.constitution import TrustTier, Verdict as CVerdict
        cresult = self._constitution.check(action, dict(payload), TrustTier.OPERATOR)
        if cresult.verdict is CVerdict.DENY:
            return self._emit(MonitorVerdict.VIOLATION,
                              f"bypass:{action}",
                              f"action '{action}' executed despite constitution DENY: {cresult.reason}",
                              topic, payload, now,
                              ("T-II-1", "T-II-3", "T-V-1"))
        if cresult.verdict is CVerdict.GATE:
            # Could legitimately be gated-and-approved; surface as ALERT
            # so the operator can confirm an approval exists.
            return self._emit(MonitorVerdict.ALERT,
                              f"gated_check:{action}",
                              f"gated action '{action}' executed; verify operator approval is logged",
                              topic, payload, now,
                              ("T-IV-4",))
        return None

    def _emit(
        self,
        verdict: MonitorVerdict,
        rule_id: str,
        reason: str,
        topic: str,
        payload: Dict[str, Any],
        now: float,
        threats: tuple[str, ...],
    ) -> VerdictReport:
        report = VerdictReport(
            verdict=verdict, rule_id=rule_id, reason=reason,
            topic=topic, payload_summary=str(payload)[:160],
            threats_addressed=threats,
        )
        with self._lock:
            self._recent.append(report)
            if verdict is MonitorVerdict.VETO:
                self.vetoes_emitted += 1
            elif verdict is MonitorVerdict.VIOLATION:
                self.violations_emitted += 1
            elif verdict is MonitorVerdict.ALERT:
                self.alerts_emitted += 1

        if verdict is MonitorVerdict.PASS:
            return report

        out_topic = {
            MonitorVerdict.ALERT: "aria.monitor.alert",
            MonitorVerdict.VETO: "aria.monitor.veto",
            MonitorVerdict.VIOLATION: "aria.monitor.violation",
        }[verdict]
        self._publish(out_topic, {
            "rule_id": rule_id,
            "reason": reason,
            "subject_topic": topic,
            "verdict": verdict.value,
            "ts": now,
            "threats_addressed": list(threats),
        })
        logger.warning("monitor.%s" % verdict.value,
                       rule_id=rule_id, subject_topic=topic, reason=reason)
        return report

    # ── Inspection ──────────────────────────────────────────────

    def recent_verdicts(self, limit: int = 100) -> List[VerdictReport]:
        with self._lock:
            return list(self._recent)[-limit:]

    def stats(self) -> Dict[str, Any]:
        return {
            "alerts": self.alerts_emitted,
            "vetoes": self.vetoes_emitted,
            "violations": self.violations_emitted,
            "rate_windows_tracked": len(self._rates),
        }
