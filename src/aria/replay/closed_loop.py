from __future__ import annotations

import json
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Optional, Protocol

import structlog

from aria.cognitive.doctrine import (
    DoctrineBundle,
    format_doctrine_for_prompt,
    select_relevant_entries,
)
from aria.replay.action_translator import (
    ActionRegistry,
    ActionTranslation,
    make_default_registry,
)
from aria.replay.apollo13_cryo_stir import TelemetrySample

logger = structlog.get_logger()


@dataclass(frozen=True)
class AnomalyEvent:
    detected_at_get_s: float
    parameter: str
    value: float
    units: str
    score: float
    severity: str
    detector_name: str
    reason: str
    raw_window: tuple[float, ...] = ()

    def get_string(self) -> str:
        total = int(self.detected_at_get_s)
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True)
class AdvisorVerdict:
    proposed_action: str
    rationale: str
    immediate_steps: tuple[str, ...]
    confidence: float
    raw_response: str = ""


@dataclass(frozen=True)
class MonitorVerdict:
    decision: str
    reason: str
    provider_label: str = ""


@dataclass(frozen=True)
class LoopOutcome:
    anomaly: AnomalyEvent
    advisor: Optional[AdvisorVerdict]
    monitor: Optional[MonitorVerdict]
    hal_command: Optional[str]
    elapsed_advisor_s: float
    elapsed_monitor_s: float
    translation: Optional[ActionTranslation] = None
    residual_log_entry: Optional[str] = None


class WindowedZScoreDetector:
    def __init__(
        self,
        *,
        parameters: tuple[str, ...],
        window_size: int = 30,
        warmup_samples: int = 10,
        z_threshold: float = 3.5,
        cooldown_s: float = 5.0,
    ) -> None:
        if window_size < 4:
            raise ValueError("window_size >= 4 required for sane variance")
        if warmup_samples < 4 or warmup_samples > window_size:
            raise ValueError("warmup_samples must be in [4, window_size]")
        self._parameters = set(parameters)
        self._window_size = window_size
        self._warmup_samples = warmup_samples
        self._z_threshold = z_threshold
        self._cooldown_s = cooldown_s
        self._buffers: dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size),
        )
        self._last_alert_get: dict[str, float] = {}

    def name(self) -> str:
        return f"WindowedZScore(window={self._window_size},z={self._z_threshold})"

    def step(self, sample: TelemetrySample) -> Optional[AnomalyEvent]:
        if sample.parameter not in self._parameters:
            return None
        if math.isnan(sample.value):
            return None
        buffer = self._buffers[sample.parameter]
        if len(buffer) < self._warmup_samples:
            buffer.append(sample.value)
            return None
        mean = sum(buffer) / len(buffer)
        variance = sum((x - mean) ** 2 for x in buffer) / max(1, len(buffer) - 1)
        std = math.sqrt(max(variance, 1e-9))
        if std < 1e-6:
            buffer.append(sample.value)
            return None
        z = abs(sample.value - mean) / std
        last = self._last_alert_get.get(sample.parameter, -math.inf)
        if z >= self._z_threshold and (sample.get_seconds - last) >= self._cooldown_s:
            self._last_alert_get[sample.parameter] = sample.get_seconds
            severity = "CRITICAL" if z > 8.0 else "HIGH" if z > 5.0 else "MEDIUM"
            event = AnomalyEvent(
                detected_at_get_s=sample.get_seconds,
                parameter=sample.parameter,
                value=sample.value,
                units=sample.units,
                score=min(z / 10.0, 1.0),
                severity=severity,
                detector_name=self.name(),
                reason=f"z={z:.2f} (mean={mean:.2f}, std={std:.2f}, threshold={self._z_threshold})",
                raw_window=tuple(buffer),
            )
            buffer.append(sample.value)
            return event
        buffer.append(sample.value)
        return None


class LlmAdvisor(Protocol):
    label: str
    def advise(
        self,
        anomaly: AnomalyEvent,
        recent_state: dict[str, float],
        doctrine: str,
    ) -> AdvisorVerdict: ...


class StubAdvisor:
    label = "stub"

    def advise(
        self,
        anomaly: AnomalyEvent,
        recent_state: dict[str, float],
        doctrine: str,
    ) -> AdvisorVerdict:
        steps: list[str] = []
        if "O2_TANK" in anomaly.parameter and "PRESSURE" in anomaly.parameter:
            steps = [
                "Acknowledge master alarm and confirm with crew.",
                "Switch fuel cell to redundant reactant feed.",
                "Begin LM lifeboat checklist if loss confirmed.",
                "Power down non-essential CSM loads.",
            ]
            action = "isolate_o2_tank_2_and_prepare_lm_lifeboat"
            rationale = "O2 tank 2 pressure anomaly with possible rupture; conserve remaining cryogens."
        elif "FUEL_CELL" in anomaly.parameter and "VOLTAGE" in anomaly.parameter:
            steps = [
                "Confirm fuel cell reactant pressure on remaining cells.",
                "Reduce CSM bus load to within remaining-cell capacity.",
            ]
            action = "load_shed_csm_bus_a"
            rationale = "Fuel-cell voltage drop with reactant supply suspect."
        else:
            steps = ["Investigate; no immediate action."]
            action = "investigate"
            rationale = "Unfamiliar anomaly shape; defer to ground."
        return AdvisorVerdict(
            proposed_action=action, rationale=rationale,
            immediate_steps=tuple(steps), confidence=0.6,
            raw_response="(stub)",
        )


class LlmCliAdvisor:
    label = "claude-cli"

    def __init__(
        self,
        *,
        binary: str = "claude",
        effort: str = "low",
        timeout_s: float = 90.0,
    ) -> None:
        self._binary = binary
        self._effort = effort
        self._timeout_s = timeout_s

    def advise(
        self,
        anomaly: AnomalyEvent,
        recent_state: dict[str, float],
        doctrine: str,
    ) -> AdvisorVerdict:
        import shutil
        import subprocess
        if shutil.which(self._binary) is None:
            return _stub_fallback("claude-cli-not-on-path", anomaly)
        prompt = _build_prompt(anomaly, recent_state, doctrine)
        cmd = [
            self._binary, "--print", "--no-session-persistence",
            "--effort", self._effort,
            "--append-system-prompt", _SYSTEM_PROMPT,
        ]
        try:
            result = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                timeout=self._timeout_s, check=False,
            )
        except subprocess.TimeoutExpired:
            return _stub_fallback("claude-cli-timeout", anomaly)
        if result.returncode != 0:
            return _stub_fallback(
                f"claude-cli-exit-{result.returncode}", anomaly,
                raw=result.stderr.strip()[:200],
            )
        return _parse_advisor_response(result.stdout)


_SYSTEM_PROMPT = (
    "You are an Apollo-era flight controller advising on a real-time "
    "spacecraft anomaly. Respond with exactly this JSON shape:\n"
    '{"proposed_action": "<short_snake_case>", "rationale": "<one sentence>",'
    ' "immediate_steps": ["<step1>", "<step2>", ...], "confidence": <0..1>}\n'
    "No prose outside the JSON. No markdown fences. Keep steps short and "
    "actionable. If you don't know, say so in rationale and propose 'investigate'."
)


def _build_prompt(
    anomaly: AnomalyEvent,
    recent_state: dict[str, float],
    doctrine: str,
) -> str:
    state_lines = "\n".join(
        f"  {param}: {value}" for param, value in sorted(recent_state.items())
    )
    return (
        f"GET={anomaly.get_string()}\n"
        f"Anomaly: {anomaly.parameter} = {anomaly.value:.2f} {anomaly.units}\n"
        f"Severity: {anomaly.severity}\n"
        f"Detector: {anomaly.detector_name}\n"
        f"Reason: {anomaly.reason}\n\n"
        f"Recent state:\n{state_lines}\n\n"
        f"Doctrine excerpt:\n{doctrine}\n\n"
        "Return the JSON object only."
    )


def _parse_advisor_response(raw: str) -> AdvisorVerdict:
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return AdvisorVerdict(
            proposed_action="investigate",
            rationale="advisor returned no JSON",
            immediate_steps=(),
            confidence=0.0,
            raw_response=raw[:400],
        )
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return AdvisorVerdict(
            proposed_action="investigate",
            rationale="advisor JSON malformed",
            immediate_steps=(),
            confidence=0.0,
            raw_response=raw[:400],
        )
    return AdvisorVerdict(
        proposed_action=str(parsed.get("proposed_action") or "investigate"),
        rationale=str(parsed.get("rationale") or ""),
        immediate_steps=tuple(
            str(step) for step in (parsed.get("immediate_steps") or ())
        ),
        confidence=float(parsed.get("confidence") or 0.0),
        raw_response=raw[:400],
    )


def _stub_fallback(reason: str, anomaly: AnomalyEvent, *, raw: str = "") -> AdvisorVerdict:
    fallback = StubAdvisor().advise(anomaly, {}, "")
    return AdvisorVerdict(
        proposed_action=fallback.proposed_action,
        rationale=f"{fallback.rationale} (advisor degraded: {reason})",
        immediate_steps=fallback.immediate_steps,
        confidence=fallback.confidence * 0.5,
        raw_response=raw,
    )


class CrossMonitor(Protocol):
    label: str
    def review(
        self, advisor: AdvisorVerdict, anomaly: AnomalyEvent,
    ) -> MonitorVerdict: ...


class StubCrossMonitor:
    label = "stub-cross-monitor"

    def review(
        self, advisor: AdvisorVerdict, anomaly: AnomalyEvent,
    ) -> MonitorVerdict:
        if advisor.confidence < 0.3:
            return MonitorVerdict(
                decision="DEFER",
                reason="advisor confidence below 0.3",
                provider_label=self.label,
            )
        return MonitorVerdict(
            decision="APPROVE",
            reason="default approval for stub monitor",
            provider_label=self.label,
        )


@dataclass
class ClosedLoop:
    detector: WindowedZScoreDetector
    advisor: LlmAdvisor
    monitor: CrossMonitor
    hal_apply_fn: Optional[Callable[[str, AdvisorVerdict], None]] = None
    doctrine_text: str = ""
    state_window_size: int = 60
    action_registry: ActionRegistry = field(default_factory=make_default_registry)
    residual_log: list[str] = field(default_factory=list)
    doctrine_bundle: Optional[DoctrineBundle] = None
    doctrine_budget_chars: int = 4000
    lesson_index: Optional[Any] = None
    lesson_top_k: int = 3
    lesson_budget_chars: int = 2000
    _state: dict[str, float] = field(default_factory=dict)
    _outcomes: list[LoopOutcome] = field(default_factory=list)

    def _build_lessons(self, event: AnomalyEvent) -> str:
        if self.lesson_index is None:
            return ""
        query = f"{event.parameter} {event.severity} {event.reason}"
        try:
            hits = self.lesson_index.search(query, top_k=self.lesson_top_k)
        except Exception as exc:
            logger.warning("closed_loop.lesson_search_failed", error=str(exc))
            return ""
        if not hits:
            return ""
        rendered: list[str] = []
        used = 0
        for hit in hits:
            block = (
                f"[LESSON {hit.record.record_id}] {hit.record.title}\n"
                f"  ({hit.record.citation})\n"
                f"  {hit.record.summary}"
            )
            if used + len(block) + 2 > self.lesson_budget_chars and rendered:
                break
            rendered.append(block)
            used += len(block) + 2
        if not rendered:
            return ""
        return "Relevant prior incidents:\n" + "\n\n".join(rendered)

    def _build_doctrine(self, event: AnomalyEvent) -> str:
        if self.doctrine_bundle is None or not self.doctrine_bundle.entries:
            return self.doctrine_text
        relevant = select_relevant_entries(
            self.doctrine_bundle,
            parameter=event.parameter,
            severity=event.severity,
            recent_state=dict(self._state),
            free_text=event.reason,
        )
        if not relevant:
            return self.doctrine_text
        body = format_doctrine_for_prompt(
            relevant, budget_chars=self.doctrine_budget_chars,
        )
        if self.doctrine_text:
            return f"{self.doctrine_text}\n\nRelevant doctrine entries:\n{body}"
        return f"Relevant doctrine entries:\n{body}"

    def step(self, sample: TelemetrySample) -> Optional[LoopOutcome]:
        self._state[sample.parameter] = sample.value
        event = self.detector.step(sample)
        if event is None:
            return None
        t0 = time.time()
        doctrine = self._build_doctrine(event)
        lessons = self._build_lessons(event)
        if lessons:
            doctrine = f"{doctrine}\n\n{lessons}" if doctrine else lessons
        verdict = self.advisor.advise(
            anomaly=event,
            recent_state=dict(self._state),
            doctrine=doctrine,
        )
        elapsed_advisor = time.time() - t0
        t1 = time.time()
        monitor = self.monitor.review(verdict, event)
        elapsed_monitor = time.time() - t1
        translation = self.action_registry.translate(
            verdict.proposed_action,
            context={"anomaly": event, "state": dict(self._state)},
        )
        applied: Optional[str] = None
        residual_entry: Optional[str] = None
        if monitor.decision == "APPROVE":
            if translation.applied and translation.hal_command is not None:
                if self.hal_apply_fn is not None:
                    try:
                        self.hal_apply_fn(translation.hal_command.primitive, verdict)
                        applied = translation.hal_command.primitive
                    except Exception as exc:
                        logger.warning("closed_loop.hal_apply_failed", error=str(exc))
                        residual_entry = (
                            f"GET={event.get_string()} action="
                            f"{verdict.proposed_action} HAL_apply_failed: {exc}"
                        )
            else:
                residual_entry = (
                    f"GET={event.get_string()} action="
                    f"{verdict.proposed_action} status={translation.status} "
                    f"residual={translation.residual_reason}"
                )
        else:
            residual_entry = (
                f"GET={event.get_string()} action="
                f"{verdict.proposed_action} monitor_decision="
                f"{monitor.decision} reason={monitor.reason}"
            )
        if residual_entry is not None:
            self.residual_log.append(residual_entry)
            logger.warning("closed_loop.residual", entry=residual_entry)
        outcome = LoopOutcome(
            anomaly=event,
            advisor=verdict,
            monitor=monitor,
            hal_command=applied,
            elapsed_advisor_s=elapsed_advisor,
            elapsed_monitor_s=elapsed_monitor,
            translation=translation,
            residual_log_entry=residual_entry,
        )
        self._outcomes.append(outcome)
        return outcome

    @property
    def outcomes(self) -> tuple[LoopOutcome, ...]:
        return tuple(self._outcomes)

    def first_anomaly_get_s(self) -> Optional[float]:
        if not self._outcomes:
            return None
        return self._outcomes[0].anomaly.detected_at_get_s

    def first_o2_tank_anomaly_get_s(self) -> Optional[float]:
        for outcome in self._outcomes:
            if "O2_TANK" in outcome.anomaly.parameter:
                return outcome.anomaly.detected_at_get_s
        return None
