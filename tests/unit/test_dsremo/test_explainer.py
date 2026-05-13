"""Tests for the explainability engine."""

from datetime import datetime, timezone

import pytest

from aria.dsremo.core.models import Anomaly, Severity
from aria.dsremo.explain.explainer import AnomalyExplainer


class TestAnomalyExplainer:
    @pytest.fixture
    def explainer(self):
        return AnomalyExplainer(grouping_window_sec=120.0)

    def _make_anomaly(self, param: str, subsystem: str = "eps", severity: Severity = Severity.WARNING) -> Anomaly:
        return Anomaly(
            satellite_id="SAT-01",
            timestamp=datetime.now(timezone.utc),
            subsystem=subsystem,
            parameter=param,
            value=5.8,
            severity=severity,
            confidence=0.72,
            detectors_triggered=("statistical",),
            explanation="test",
            contributing_params={"solar_array_current": -0.3},
        )

    def test_basic_explanation(self, explainer):
        anomaly = self._make_anomaly("battery_voltage")
        exp = explainer.explain(anomaly)
        assert exp.anomaly_id == anomaly.id
        assert len(exp.summary) > 0
        assert len(exp.detail) > 0

    def test_causal_chain_found(self, explainer):
        # Create an upstream anomaly first
        upstream = self._make_anomaly("solar_array_current")
        explainer.explain(upstream)

        # Now battery_voltage — should find the causal chain
        downstream = self._make_anomaly("battery_voltage")
        exp = explainer.explain(downstream, [upstream])
        assert any("solar_array_current" in c for c in exp.causal_chain)

    def test_root_cause_grouping(self, explainer):
        a1 = self._make_anomaly("battery_voltage", "eps")
        a2 = self._make_anomaly("battery_current", "eps")

        exp1 = explainer.explain(a1)
        exp2 = explainer.explain(a2)

        # Both should be in the same incident group
        assert exp1.root_cause_group is not None
        assert exp1.root_cause_group == exp2.root_cause_group

    def test_different_subsystems_separate_groups(self, explainer):
        a1 = self._make_anomaly("battery_voltage", "eps")
        a2 = self._make_anomaly("signal_strength", "comms")

        exp1 = explainer.explain(a1)
        exp2 = explainer.explain(a2)

        # Different subsystems, no causal link — different groups
        assert exp1.root_cause_group != exp2.root_cause_group

    def test_counterfactual_generated(self, explainer):
        anomaly = self._make_anomaly("battery_voltage", severity=Severity.CRITICAL)
        exp = explainer.explain(anomaly)
        assert len(exp.counterfactual) > 0
        assert "nominal" in exp.counterfactual.lower() or "rolling" in exp.counterfactual.lower()

    def test_contributing_params_preserved(self, explainer):
        anomaly = self._make_anomaly("battery_voltage")
        exp = explainer.explain(anomaly)
        assert "solar_array_current" in exp.contributing_params
