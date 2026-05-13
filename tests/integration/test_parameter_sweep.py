"""Tests for parameter sweep analysis."""

import pytest

from aria.analysis.parameter_sweep import ParameterSweep, SweepResult


class TestParameterSweep:
    def test_sweep_crew_size(self) -> None:
        sweep = ParameterSweep()
        results = sweep.sweep_crew_size(crew_range=[4, 10], years=10)
        assert len(results) == 2
        assert results[0].param_name == "crew_size"
        assert results[0].param_value == 4
        assert results[1].param_value == 10

    def test_sweep_years(self) -> None:
        sweep = ParameterSweep()
        results = sweep.sweep_mission_years(year_range=[10, 50])
        assert len(results) == 2
        assert results[1].events >= results[0].events  # More years = more events

    def test_format_results(self) -> None:
        results = [
            SweepResult(param_name="crew", param_value=4, terminal_challenges=3, food_ratio=0.1, events=500),
            SweepResult(param_name="crew", param_value=10, terminal_challenges=2, food_ratio=0.5, events=800),
        ]
        output = ParameterSweep.format_results(results)
        assert "crew" in output
        assert "Terminal" in output

    def test_empty_results(self) -> None:
        assert "No results" in ParameterSweep.format_results([])
