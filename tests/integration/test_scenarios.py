from __future__ import annotations

import pytest

from aria.replay import (
    ClosedLoop, ReplayScenario, SCENARIOS, StubAdvisor, StubCrossMonitor,
    WindowedZScoreDetector, get_scenario, list_scenarios,
)


class TestRegistry:
    def test_six_scenarios_registered(self):
        ids = list_scenarios()
        assert len(ids) >= 6
        assert "apollo_13_cryo_stir" in ids
        assert "apollo_12_lightning" in ids
        assert "sts_114_gap_filler" in ids
        assert "soho_1998_attitude_loss" in ids
        assert "mir_spektr_collision" in ids
        assert "hubble_sm4_stuck_bolt" in ids

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_scenario("not_a_real_one")

    def test_each_scenario_has_required_fields(self):
        for scenario_id, scenario in SCENARIOS.items():
            assert scenario.title
            assert scenario.date_iso
            assert scenario.description
            assert scenario.parameters
            assert scenario.expected_keywords
            assert scenario.citations
            assert callable(scenario.samples_factory)


class TestSamplesFactories:
    @pytest.mark.parametrize("scenario_id", [
        "apollo_12_lightning",
        "sts_114_gap_filler",
        "soho_1998_attitude_loss",
        "mir_spektr_collision",
        "hubble_sm4_stuck_bolt",
    ])
    def test_factory_produces_samples(self, scenario_id: str):
        scenario = get_scenario(scenario_id)
        samples = scenario.samples_factory()
        assert samples
        assert all(sample.parameter in scenario.parameters for sample in samples)


class TestClosedLoopAcrossScenarios:
    @pytest.mark.parametrize("scenario_id", [
        "apollo_12_lightning",
        "sts_114_gap_filler",
        "mir_spektr_collision",
    ])
    def test_loop_flags_anomaly_in_scenario(self, scenario_id: str):
        scenario = get_scenario(scenario_id)
        applied: list[str] = []
        loop = ClosedLoop(
            detector=WindowedZScoreDetector(
                parameters=scenario.parameters,
                window_size=15, warmup_samples=5, z_threshold=3.0,
            ),
            advisor=StubAdvisor(),
            monitor=StubCrossMonitor(),
            hal_apply_fn=lambda primitive, verdict: applied.append(primitive),
        )
        for sample in scenario.samples_factory():
            loop.step(sample)
        assert loop.outcomes, (
            f"scenario {scenario_id} produced zero anomaly outcomes"
        )
