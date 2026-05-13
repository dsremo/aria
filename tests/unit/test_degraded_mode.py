"""Tests for degraded-mode survival analysis (Al-Rashidi R6 PDR)."""

import math

import pytest

from aria.digital_twin.degraded_mode import (
    DEGRADED_SCENARIOS,
    get_fatal_scenarios,
    get_recoverable_scenarios,
    get_scenario,
    survival_probability,
    total_fatal_risk_per_year,
)


class TestScenarios:
    def test_scenarios_exist(self):
        assert len(DEGRADED_SCENARIOS) >= 6

    def test_all_have_mitigation(self):
        for s in DEGRADED_SCENARIOS:
            assert len(s.mitigation) > 20

    def test_severity_values(self):
        valid = {"recoverable", "critical", "fatal"}
        for s in DEGRADED_SCENARIOS:
            assert s.severity in valid


class TestLookup:
    def test_get_scenario(self):
        s = get_scenario("reactor_scram")
        assert s.severity == "fatal"
        assert s.crew_survival_hours == 48.0

    def test_unknown_scenario_raises(self):
        with pytest.raises(KeyError):
            get_scenario("nonexistent")


class TestRiskAnalysis:
    def test_fatal_scenarios_exist(self):
        fatals = get_fatal_scenarios()
        assert len(fatals) > 0

    def test_recoverable_exist(self):
        recov = get_recoverable_scenarios()
        assert len(recov) > 0

    def test_total_fatal_risk_positive(self):
        risk = total_fatal_risk_per_year()
        assert risk > 0
        assert risk < 1  # Not certain death per year

    def test_survival_decreases_over_time(self):
        p1 = survival_probability(1)
        p10 = survival_probability(10)
        p100 = survival_probability(100)
        assert p1 > p10 > p100

    def test_survival_is_probability(self):
        p = survival_probability(50)
        assert 0 <= p <= 1
