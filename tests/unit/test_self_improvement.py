"""Tests for AI self-improvement system."""

from aria.cognitive.self_improvement import SelfImprovementEngine, ModelPerformance


class TestModelPerformance:
    def test_accuracy(self):
        p = ModelPerformance(name="test", true_positives=90, false_positives=5, true_negatives=900, false_negatives=5)
        assert 0.98 < p.accuracy < 1.0

    def test_precision(self):
        p = ModelPerformance(name="test", true_positives=90, false_positives=10)
        assert abs(p.precision - 0.9) < 0.01

    def test_recall(self):
        p = ModelPerformance(name="test", true_positives=90, false_negatives=10)
        assert abs(p.recall - 0.9) < 0.01

    def test_f1_score(self):
        p = ModelPerformance(name="test", true_positives=80, false_positives=10, false_negatives=10)
        assert 0.8 < p.f1_score < 0.9

    def test_false_alarm_rate(self):
        p = ModelPerformance(name="test", false_positives=50, true_negatives=950)
        assert abs(p.false_alarm_rate - 0.05) < 0.01


class TestSelfImprovementEngine:
    def test_record_prediction(self):
        engine = SelfImprovementEngine()
        engine.record_prediction("dsremo", True, True)
        engine.record_prediction("dsremo", True, False)
        engine.record_prediction("dsremo", False, False)

        report = engine.get_model_report()
        assert "dsremo" in report
        assert report["dsremo"]["total_predictions"] == 3

    def test_decision_accuracy(self):
        engine = SelfImprovementEngine()
        engine.record_decision_outcome("d1", "test", "action", "correct")
        engine.record_decision_outcome("d2", "test", "action", "correct")
        engine.record_decision_outcome("d3", "test", "action", "incorrect")
        assert abs(engine.get_decision_accuracy() - 2/3) < 0.01

    def test_identify_high_false_alarm(self):
        engine = SelfImprovementEngine()
        for _ in range(50):
            engine.record_prediction("noisy_model", True, False)
        for _ in range(50):
            engine.record_prediction("noisy_model", False, False)

        suggestions = engine.identify_improvements()
        assert any(s["issue"] == "high_false_alarm_rate" for s in suggestions)

    def test_identify_low_recall(self):
        engine = SelfImprovementEngine()
        for _ in range(20):
            engine.record_prediction("blind_model", True, True)
        for _ in range(80):
            engine.record_prediction("blind_model", False, True)  # Missed!

        suggestions = engine.identify_improvements()
        assert any(s["issue"] == "low_recall" for s in suggestions)

    def test_evolve_increments_version(self):
        engine = SelfImprovementEngine()
        assert engine.version == 1
        result = engine.evolve(mission_year=50)
        assert result["evolved"]
        assert engine.version == 2

    def test_evolve_cooldown(self):
        engine = SelfImprovementEngine()
        engine.evolve(mission_year=50)
        result = engine.evolve(mission_year=60)  # Too soon
        assert not result["evolved"]

    def test_evolve_after_cooldown(self):
        engine = SelfImprovementEngine()
        engine.evolve(mission_year=50)
        result = engine.evolve(mission_year=100)
        assert result["evolved"]
        assert engine.version == 3

    def test_improvement_history(self):
        engine = SelfImprovementEngine()
        engine.evolve(mission_year=50)
        engine.evolve(mission_year=100)
        assert len(engine.improvement_history) == 2
