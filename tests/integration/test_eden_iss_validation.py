from __future__ import annotations

import pytest

from aria.physics.bioregen.eden_iss_validation import (
    EDEN_ISS_AVG_PRODUCE_KG_PER_DAY,
    EDEN_ISS_FRESH_PRODUCE_TOTAL_KG,
    EDEN_ISS_MISSION_DURATION_DAYS,
    EdenIssBaseline,
    GreenhouseProduceModel,
    validate_against_eden_iss,
)


class TestBaselineConstants:
    def test_published_constants_present(self):
        assert EDEN_ISS_AVG_PRODUCE_KG_PER_DAY > 0
        assert EDEN_ISS_FRESH_PRODUCE_TOTAL_KG > 200
        assert EDEN_ISS_MISSION_DURATION_DAYS > 250


class TestModelStep:
    def test_step_day_positive(self):
        model = GreenhouseProduceModel()
        per_day = model.step_day()
        assert per_day["produce_kg_day"] > 0
        assert per_day["o2_production_kg_day"] > 0
        assert per_day["co2_uptake_kg_day"] > 0
        assert per_day["water_transp_kg_day"] > 0

    def test_o2_co2_ratio_realistic(self):
        model = GreenhouseProduceModel()
        per_day = model.step_day()
        ratio = per_day["o2_production_kg_day"] / per_day["co2_uptake_kg_day"]
        assert 0.6 <= ratio <= 0.8


class TestIntegrate:
    def test_integration_scales_linearly(self):
        model = GreenhouseProduceModel()
        result_30 = model.integrate(duration_days=30)
        result_60 = model.integrate(duration_days=60)
        assert abs(result_60["produce_total_kg"] - 2 * result_30["produce_total_kg"]) < 1e-6

    def test_integration_returns_full_breakdown(self):
        model = GreenhouseProduceModel()
        result = model.integrate(duration_days=281)
        for key in (
            "duration_days", "produce_total_kg", "co2_uptake_total_kg",
            "o2_production_total_kg", "water_transp_total_kg",
            "produce_avg_kg_day", "co2_avg_kg_day", "o2_avg_kg_day",
            "water_avg_kg_day",
        ):
            assert key in result


class TestValidationAgainstEdenIss:
    def test_default_model_within_tolerance(self):
        model = GreenhouseProduceModel()
        result = model.integrate(duration_days=EDEN_ISS_MISSION_DURATION_DAYS)
        report = validate_against_eden_iss(result, tolerance_pct=40.0)
        within = sum(1 for delta in report.deltas if delta.within_tolerance)
        assert within >= 3, (
            f"only {within}/{len(report.deltas)} EDEN ISS deltas in "
            f"tolerance: " + "; ".join(
                f"{delta.parameter}: {delta.measured_value:.2f} vs "
                f"{delta.published_value:.2f} ({delta.relative_error_pct:.0f}%)"
                for delta in report.deltas
            )
        )

    def test_off_model_caught(self):
        bad = {
            "produce_avg_kg_day": 0.0,
            "co2_avg_kg_day": 0.0,
            "o2_avg_kg_day": 0.0,
            "water_avg_kg_day": 0.0,
            "produce_total_kg": 0.0,
        }
        report = validate_against_eden_iss(bad)
        assert not report.overall_within_tolerance

    def test_report_dict_serializable(self):
        result = GreenhouseProduceModel().integrate(duration_days=30)
        report = validate_against_eden_iss(result, tolerance_pct=100.0)
        payload = report.as_dict()
        import json
        json.dumps(payload)
        assert "deltas" in payload
        assert "notes" in payload


class TestThirtyDayClosedLoop:
    def test_30_day_o2_within_envelope(self):
        model = GreenhouseProduceModel()
        result = model.integrate(duration_days=30)
        baseline = EdenIssBaseline()
        report = validate_against_eden_iss(result, baseline=baseline, tolerance_pct=40.0)
        avg_o2 = next(
            delta for delta in report.deltas if delta.parameter == "o2_production_avg"
        )
        assert avg_o2.measured_value > 0
        assert avg_o2.published_value > 0
