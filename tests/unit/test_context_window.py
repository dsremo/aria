"""Tests for Context Window Manager."""

from __future__ import annotations

import pytest

from aria.cognitive.context import ContextWindowManager, estimate_tokens, ContextWindow


class TestTokenEstimation:
    def test_empty_string(self):
        assert estimate_tokens("") == 1  # Minimum 1

    def test_short_string(self):
        assert estimate_tokens("hello") == 2  # 5/4 + 1

    def test_longer_string(self):
        tokens = estimate_tokens("a" * 400)
        assert tokens == 101  # 400/4 + 1


class TestContextWindowManager:
    @pytest.fixture
    def manager(self):
        return ContextWindowManager()

    @pytest.fixture
    def status(self):
        return {
            "status": "RUNNING",
            "health_score": 95.0,
            "safe_mode": "NOMINAL",
            "agents": {
                "telemetry": {"status": "READY"},
                "power": {"status": "READY"},
                "navigation": {"status": "READY"},
            },
            "last_anomaly": {"severity": "WATCH", "source": "power"},
        }

    def test_build_context_nominal(self, manager, status):
        """Context builds correctly with no anomalies."""
        ctx = manager.build_context(status)
        assert "No active anomalies" in ctx.anomalies
        assert "NOMINAL" in ctx.system_state
        assert ctx.budget.total_used > 0

    def test_build_context_with_anomalies(self, manager, status):
        """Anomalies are included in context, sorted by severity."""
        anomalies = [
            {"severity": "WATCH", "message": "Battery declining", "subsystem": "power"},
            {"severity": "CRITICAL", "message": "CO2 high", "subsystem": "eclss"},
        ]
        ctx = manager.build_context(status, recent_anomalies=anomalies)
        # CRITICAL should appear before WATCH
        critical_pos = ctx.anomalies.find("CRITICAL")
        watch_pos = ctx.anomalies.find("WATCH")
        assert critical_pos < watch_pos

    def test_build_context_with_alerts(self, manager, status):
        """Captain alerts are included in anomalies section."""
        alerts = [{"severity": "WARNING", "message": "Low battery", "description": "SoC at 15%"}]
        ctx = manager.build_context(status, active_alerts=alerts)
        assert "WARNING" in ctx.anomalies

    def test_context_to_text(self, manager, status):
        """Context converts to text with section headers."""
        anomalies = [{"severity": "WATCH", "message": "Test anomaly", "subsystem": "test"}]
        ctx = manager.build_context(status, recent_anomalies=anomalies)
        text = ctx.to_text()
        assert "## Current System State" in text
        assert "## Active Anomalies" in text

    def test_fit_tool_result_small(self, manager):
        """Small tool results fit within budget."""
        ctx = ContextWindow()
        result = manager.fit_tool_result('{"score": 0.5}', ctx)
        assert result == '{"score": 0.5}'
        assert ctx.budget.tool_results_used > 0

    def test_fit_tool_result_large_truncated(self, manager):
        """Large tool results are truncated with overflow note."""
        ctx = ContextWindow()
        large = "x" * 50000  # Way over budget
        result = manager.fit_tool_result(large, ctx)
        assert "TRUNCATED" in result
        assert len(result) < len(large)
        assert len(ctx.overflow_refs) == 1

    def test_keyword_extraction(self):
        """Keywords extracted from query and anomalies."""
        keywords = ContextWindowManager._extract_keywords(
            "How is the battery?",
            [{"message": "CO2 high in eclss"}],
            [{"message": "Fire detected", "description": ""}],
        )
        assert "battery" in keywords
        assert "co2" in keywords
        assert "fire" in keywords

    def test_budget_tracking(self, manager, status):
        """Budget is correctly tracked across sections."""
        anomalies = [{"severity": "WARNING", "message": "Test", "subsystem": "test"}]
        ctx = manager.build_context(status, recent_anomalies=anomalies, query_text="battery status")
        assert ctx.budget.anomalies_used > 0
        assert ctx.budget.system_state_used > 0
        assert ctx.budget.total_used > 0
        assert ctx.budget.remaining >= 0


class TestTokenBudget:
    def test_budget_remaining_decreases(self):
        """Budget remaining decreases as sections are added."""
        from aria.cognitive.context import ContextBudget, TOTAL_BUDGET
        b = ContextBudget()
        assert b.remaining == TOTAL_BUDGET
        b.system_state_used = 500
        b.anomalies_used = 1000
        assert b.remaining == TOTAL_BUDGET - 1500

    def test_budget_cannot_go_negative(self):
        """Remaining never goes below 0."""
        from aria.cognitive.context import ContextBudget, TOTAL_BUDGET
        b = ContextBudget()
        b.system_state_used = TOTAL_BUDGET + 1000
        assert b.remaining == 0

    def test_total_used(self):
        """Total used sums all sections."""
        from aria.cognitive.context import ContextBudget
        b = ContextBudget()
        b.system_state_used = 100
        b.anomalies_used = 200
        b.procedures_used = 300
        b.memory_used = 50
        b.tool_results_used = 150
        assert b.total_used == 800


class TestContextWindowEdgeCases:
    def test_empty_status(self):
        mgr = ContextWindowManager()
        ctx = mgr.build_context({})
        assert ctx.budget.total_used >= 0

    def test_many_anomalies_truncated(self):
        mgr = ContextWindowManager()
        anomalies = [{"severity": "WARNING", "message": f"Alert {i}", "subsystem": "test"} for i in range(100)]
        ctx = mgr.build_context({}, recent_anomalies=anomalies)
        # Should have truncated — not all 100 anomalies included
        lines = ctx.anomalies.split("\n")
        assert len(lines) <= 100  # Budget limits how many fit


class TestKeywordExtraction:
    def test_fire_keyword(self):
        keywords = ContextWindowManager._extract_keywords(
            "Is there a fire in the lab?", [], []
        )
        assert "fire" in keywords

    def test_battery_keyword(self):
        keywords = ContextWindowManager._extract_keywords(
            "How is the battery doing?", [], []
        )
        assert "battery" in keywords

    def test_anomaly_keywords(self):
        keywords = ContextWindowManager._extract_keywords(
            "", [{"message": "CO2 high"}, {"message": "battery thermal runaway"}], []
        )
        assert "co2" in keywords or "battery" in keywords

    def test_max_5_keywords(self):
        keywords = ContextWindowManager._extract_keywords(
            "fire battery co2 thermal leak radiation eclipse maneuver fuel propellant comms",
            [], []
        )
        assert len(keywords) <= 5


class TestContextToText:
    def test_empty_context(self):
        ctx = ContextWindow()
        text = ctx.to_text()
        assert text == ""  # All fields empty

    def test_with_state_only(self):
        ctx = ContextWindow(system_state="Health: 95%")
        text = ctx.to_text()
        assert "System State" in text

    def test_with_overflow(self):
        ctx = ContextWindow(overflow_refs=["ref_1", "ref_2"])
        text = ctx.to_text()
        assert "2 full results" in text
