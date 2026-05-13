from __future__ import annotations

from pathlib import Path

import pytest

from aria.replay.audit_log import (
    AuditLogger,
    loop_outcome_to_event,
    replay_audit_events_from,
)


class TestAuditLogger:
    def test_write_and_replay(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        logger = AuditLogger(path=path)
        logger.write_event({"a": 1})
        logger.write_event({"b": 2, "ts": 12345})
        logger.close()
        events = replay_audit_events_from(path)
        assert len(events) == 2
        assert events[0]["a"] == 1
        assert events[1]["b"] == 2
        assert events[1]["ts"] == 12345
        assert "ts" in events[0]

    def test_replay_missing_file_returns_empty(self, tmp_path: Path):
        events = replay_audit_events_from(tmp_path / "no_such.jsonl")
        assert events == []

    def test_replay_skips_malformed_lines(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        path.write_text("{\"good\": 1}\nbroken-line\n{\"good\": 2}\n")
        events = replay_audit_events_from(path)
        assert events == [{"good": 1}, {"good": 2}]


class TestLoopOutcomeEvent:
    def test_event_shape(self):
        from aria.replay import (
            AnomalyEvent, AdvisorVerdict, MonitorVerdict, LoopOutcome,
        )
        from aria.replay.action_translator import (
            ActionTranslation, HalCommand,
        )
        anomaly = AnomalyEvent(
            detected_at_get_s=42.0, parameter="X", value=1.0, units="x",
            score=0.9, severity="HIGH", detector_name="d", reason="r",
        )
        advisor = AdvisorVerdict(
            proposed_action="ping", rationale="r",
            immediate_steps=("a", "b"), confidence=0.7, raw_response="",
        )
        monitor = MonitorVerdict(decision="APPROVE", reason="ok", provider_label="m")
        translation = ActionTranslation(
            proposed_action="ping", status="applied",
            hal_command=HalCommand(primitive="ping", params={}),
            subsystem="ops",
        )
        outcome = LoopOutcome(
            anomaly=anomaly, advisor=advisor, monitor=monitor,
            hal_command="ping", elapsed_advisor_s=0.5, elapsed_monitor_s=0.1,
            translation=translation,
        )
        event = loop_outcome_to_event(outcome, "test_scenario")
        assert event["scenario"] == "test_scenario"
        assert event["anomaly"]["parameter"] == "X"
        assert event["advisor"]["proposed_action"] == "ping"
        assert event["monitor"]["decision"] == "APPROVE"
        assert event["translation"]["status"] == "applied"
        assert event["hal_applied"] == "ping"
