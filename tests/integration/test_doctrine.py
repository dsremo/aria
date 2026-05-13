from __future__ import annotations

import json
from pathlib import Path

import pytest

from aria.cognitive.doctrine import (
    DoctrineBundle,
    DoctrineEntry,
    DoctrineKind,
    DoctrineLoader,
    format_doctrine_for_prompt,
    select_relevant_entries,
)


SAMPLE_PAYLOAD = [
    {
        "rule_id": "TEST-CRYO-1",
        "kind": "flight_rule",
        "title": "Cryo divergence",
        "body": "Pressure > 3 sigma → isolate tank.",
        "keywords": ["cryo", "tank", "pressure"],
        "citation": "TEST-CITE",
        "parameters": ["O2_TANK_2_PRESSURE"],
    },
    {
        "rule_id": "TEST-PWR-1",
        "kind": "flight_rule",
        "title": "Bus voltage low",
        "body": "Below 113 VDC → load shed.",
        "keywords": ["voltage", "load shed"],
        "citation": "TEST-CITE",
        "parameters": ["MAIN_BUS_VOLTAGE_VDC"],
    },
    {
        "rule_id": "TEST-MAL-1",
        "kind": "malfunction_procedure",
        "title": "O2 cryo stir malfunction",
        "body": "Close isolation valve, de-energize heater.",
        "keywords": ["cryo", "stir", "valve"],
        "citation": "TEST-CITE",
        "parameters": ["O2_TANK_2_PRESSURE"],
    },
]


@pytest.fixture
def doctrine_dir(tmp_path: Path) -> Path:
    target = tmp_path / "doctrine"
    target.mkdir()
    (target / "test_rules.json").write_text(json.dumps(SAMPLE_PAYLOAD))
    return target


class TestLoader:
    def test_loads_entries(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        assert len(bundle.entries) == 3

    def test_loads_zero_when_dir_missing(self, tmp_path: Path):
        bundle = DoctrineLoader(tmp_path / "nope").load()
        assert bundle.entries == ()

    def test_skips_malformed_json(self, tmp_path: Path):
        target = tmp_path / "doctrine"
        target.mkdir()
        (target / "broken.json").write_text("{not valid json")
        (target / "ok.json").write_text(json.dumps(SAMPLE_PAYLOAD[:1]))
        bundle = DoctrineLoader(target).load()
        assert len(bundle.entries) == 1

    def test_kind_parsed(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        kinds = {entry.kind for entry in bundle.entries}
        assert DoctrineKind.FLIGHT_RULE in kinds
        assert DoctrineKind.MALFUNCTION_PROCEDURE in kinds

    def test_real_apollo_doctrine_loadable(self):
        bundle = DoctrineLoader(Path("data/doctrine")).load()
        ids = {entry.rule_id for entry in bundle.entries}
        assert "APOLLO-FR-5-9" in ids
        assert "ISS-FR-ECLSS-101" in ids


class TestSelectRelevant:
    def test_parameter_match_scores_highest(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        entries = select_relevant_entries(
            bundle, parameter="O2_TANK_2_PRESSURE",
        )
        assert entries[0].parameters == ("O2_TANK_2_PRESSURE",)

    def test_no_match_returns_empty(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        entries = select_relevant_entries(bundle, parameter="UNRELATED_PARAM")
        assert entries == ()

    def test_top_k_limit(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        entries = select_relevant_entries(
            bundle, parameter="O2_TANK_2_PRESSURE", top_k=1,
        )
        assert len(entries) <= 1

    def test_keyword_match_via_free_text(self, doctrine_dir: Path):
        bundle = DoctrineLoader(doctrine_dir).load()
        entries = select_relevant_entries(
            bundle, free_text="voltage low load shed",
        )
        rule_ids = {entry.rule_id for entry in entries}
        assert "TEST-PWR-1" in rule_ids


class TestFormatForPrompt:
    def test_renders_entries_separated(self):
        entry_a = DoctrineEntry(
            rule_id="A", kind=DoctrineKind.FLIGHT_RULE,
            title="Title A", body="Body A.", citation="CITE",
        )
        entry_b = DoctrineEntry(
            rule_id="B", kind=DoctrineKind.MALFUNCTION_PROCEDURE,
            title="Title B", body="Body B.", citation="CITE",
        )
        prompt = format_doctrine_for_prompt([entry_a, entry_b])
        assert "FLIGHT_RULE A" in prompt
        assert "MALFUNCTION_PROCEDURE B" in prompt
        assert "CITE" in prompt

    def test_budget_truncates(self):
        entry_a = DoctrineEntry(
            rule_id="A", kind=DoctrineKind.FLIGHT_RULE,
            title="Title A", body="x" * 500, citation="CITE",
        )
        entry_b = DoctrineEntry(
            rule_id="B", kind=DoctrineKind.FLIGHT_RULE,
            title="Title B", body="y" * 500, citation="CITE",
        )
        prompt = format_doctrine_for_prompt(
            [entry_a, entry_b], budget_chars=600,
        )
        assert "Title A" in prompt
        assert "Title B" not in prompt


class TestClosedLoopWithDoctrine:
    def test_doctrine_bundle_injected_into_advisor_prompt(self):
        from aria.replay import (
            ClosedLoop, GET_MASTER_ALARM_S, GET_T0_S, StubCrossMonitor,
            WindowedZScoreDetector, generate_apollo13_cryo_stir_telemetry,
        )
        from aria.replay.closed_loop import AdvisorVerdict, AnomalyEvent

        captured: list[str] = []

        class _CapturingAdvisor:
            label = "capture"

            def advise(self, anomaly: AnomalyEvent, recent_state, doctrine):
                captured.append(doctrine)
                return AdvisorVerdict(
                    proposed_action="ping",
                    rationale="captured",
                    immediate_steps=(),
                    confidence=0.5,
                )

        bundle = DoctrineLoader(Path("data/doctrine")).load()
        loop = ClosedLoop(
            detector=WindowedZScoreDetector(
                parameters=("O2_TANK_2_PRESSURE", "O2_TANK_2_HEATER_CURRENT"),
                window_size=30, warmup_samples=10, z_threshold=3.5,
            ),
            advisor=_CapturingAdvisor(),
            monitor=StubCrossMonitor(),
            doctrine_bundle=bundle,
        )
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 5.0,
        ):
            loop.step(sample)
        assert captured, "advisor never received a doctrine prompt"
        assert "APOLLO" in captured[0]
        assert "Cortright" in captured[0] or "APOLLO-MP" in captured[0] or "APOLLO-FR" in captured[0]
