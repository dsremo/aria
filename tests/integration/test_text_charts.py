"""Tests for text-based visualization."""

from aria.visualization.text_charts import (
    bar_chart,
    comparison_table,
    mission_summary_card,
    severity_summary,
    timeline_chart,
)


class TestBarChart:
    def test_basic(self) -> None:
        result = bar_chart({"A": 10, "B": 5, "C": 8})
        assert "A" in result
        assert "█" in result

    def test_empty(self) -> None:
        result = bar_chart({})
        assert "no data" in result

    def test_with_title(self) -> None:
        result = bar_chart({"X": 1}, title="Test Chart")
        assert "Test Chart" in result

    def test_with_unit(self) -> None:
        result = bar_chart({"fuel": 50000}, unit=" kg")
        assert "kg" in result


class TestTimelineChart:
    def test_basic(self) -> None:
        data = [(y, 100 - y * 0.1) for y in range(100)]
        result = timeline_chart(data, title="Fuel")
        assert "Fuel" in result
        assert "▁" in result or "█" in result or "▃" in result

    def test_empty(self) -> None:
        result = timeline_chart([])
        assert "no data" in result


class TestComparisonTable:
    def test_basic(self) -> None:
        result = comparison_table(
            {"food": 0.0, "hull": 0.0},
            {"food": 6.5, "hull": 58.3},
        )
        assert "Legacy" in result
        assert "Breakthrough" in result
        assert "food" in result

    def test_missing_keys(self) -> None:
        result = comparison_table({"a": 1}, {"b": 2})
        assert "a" in result
        assert "b" in result


class TestSeveritySummary:
    def test_basic(self) -> None:
        result = severity_summary({
            "CRITICAL": 100, "WARNING": 200, "NOMINAL": 50,
        })
        assert "CRITICAL" in result
        assert "100" in result

    def test_empty(self) -> None:
        result = severity_summary({})
        assert "total: 0" in result


class TestMissionSummaryCard:
    def test_basic(self) -> None:
        result = mission_summary_card({
            "name": "LEO-ISS",
            "type": "LEO",
            "duration_s": 5520,
            "frames": 553,
            "events": 1200,
            "status": "SUCCESS",
        })
        assert "LEO-ISS" in result
        assert "SUCCESS" in result
        assert "┌" in result
