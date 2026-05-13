from __future__ import annotations

import json
from pathlib import Path

import pytest

from aria.replay.report import (
    ReportInputs,
    collect_report_inputs_from_audit,
    render_one_page_markdown,
)


class TestRenderMarkdown:
    def _inputs(self) -> ReportInputs:
        return ReportInputs(
            scenario_id="apollo_13_cryo_stir",
            scenario_title="Apollo 13 cryo-stir",
            historical_alarm_get_s=201293.0,
            historical_response_get_s=201353.0,
            n_outcomes=16, n_hal_applied=13, n_residual=3,
            first_anomaly_get_s=201199.0, first_critical_get_s=201199.0,
            advisor_label="claude-cli", monitor_label="stub-cross-monitor",
            doctrine_active=True, lessons_active=True, noise_active=True,
            audit_log_path="/tmp/audit.jsonl",
        )

    def test_renders_summary_block(self):
        out = render_one_page_markdown(self._inputs(), outcomes=[])
        assert "ARIA Replay Report" in out
        assert "16" in out
        assert "Lead vs historical alarm" in out

    def test_includes_outcome_table(self):
        outcomes = [
            {
                "anomaly": {
                    "parameter": "O2_TANK_2_PRESSURE",
                    "severity": "HIGH", "get_seconds": 201199.0,
                },
                "advisor": {"proposed_action": "isolate_o2_tank_2"},
                "translation": {"status": "deferred"},
                "hal_applied": None,
            },
        ]
        out = render_one_page_markdown(self._inputs(), outcomes=outcomes)
        assert "O2_TANK_2_PRESSURE" in out
        assert "isolate_o2_tank_2" in out
        assert "deferred" in out

    def test_includes_doctrine_section_when_provided(self):
        out = render_one_page_markdown(
            self._inputs(),
            outcomes=[],
            doctrine_hits=[{
                "rule_id": "APOLLO-FR-5-9",
                "title": "Cryo divergence",
                "citation": "AOH §5.9",
            }],
        )
        assert "APOLLO-FR-5-9" in out
        assert "AOH §5.9" in out

    def test_what_this_does_not_show_present(self):
        out = render_one_page_markdown(self._inputs(), outcomes=[])
        assert "does NOT show" in out
        assert "flight-grade" in out


class TestCollectFromAudit:
    def test_collects_outcomes_from_jsonl(self, tmp_path: Path):
        path = tmp_path / "audit.jsonl"
        path.write_text(
            json.dumps({
                "anomaly": {"parameter": "X", "severity": "HIGH", "get_seconds": 100.0},
                "advisor": {"proposed_action": "ping"},
                "translation": {"status": "applied", "residual": ""},
                "hal_applied": "ping",
            }) + "\n"
            + json.dumps({
                "anomaly": {"parameter": "Y", "severity": "CRITICAL", "get_seconds": 150.0},
                "advisor": {"proposed_action": "isolate"},
                "translation": {"status": "deferred", "residual": "no primitive"},
                "hal_applied": None,
            }) + "\n"
        )
        inputs, outcomes = collect_report_inputs_from_audit(
            audit_log_path=path,
            scenario_id="test", scenario_title="Test",
            historical_alarm_get_s=200.0, historical_response_get_s=300.0,
            advisor_label="stub", monitor_label="stub",
            doctrine_active=False, lessons_active=False, noise_active=False,
        )
        assert inputs.n_outcomes == 2
        assert inputs.n_hal_applied == 1
        assert inputs.n_residual == 1
        assert inputs.first_anomaly_get_s == 100.0
        assert inputs.first_critical_get_s == 150.0
        assert len(outcomes) == 2

    def test_handles_missing_audit_log(self, tmp_path: Path):
        inputs, outcomes = collect_report_inputs_from_audit(
            audit_log_path=tmp_path / "no_such.jsonl",
            scenario_id="x", scenario_title="X",
            historical_alarm_get_s=0.0, historical_response_get_s=0.0,
            advisor_label="stub", monitor_label="stub",
            doctrine_active=False, lessons_active=False, noise_active=False,
        )
        assert inputs.n_outcomes == 0
        assert outcomes == []
