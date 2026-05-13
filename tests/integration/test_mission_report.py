"""Integration tests for ARIA Mission Report Generator.

Covers text/JSON/HTML generation, scoring, physics validation,
recommendations engine, and edge cases across LEO/GEO/interstellar missions.
"""

from __future__ import annotations

import json
import math

import pytest

from aria.dashboard.health_dashboard import DashboardSnapshot, SubsystemHealth
from aria.reporting.mission_report import (
    MissionReportGenerator,
    MissionScore,
    ReportFormat,
    _generate_recommendations,
    _validate_physics,
)
from aria.simulation.mission_runner import MissionResults


# ────────────────────────────────────────────────────────────────────
#  Fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def leo_results() -> MissionResults:
    """Healthy LEO mission results."""
    return MissionResults(
        mission_name="LEO-ISS-Test",
        mission_type="LEO",
        duration_sim_s=5520.0,
        duration_wall_s=3.14,
        total_frames=552,
        total_events=1200,
        total_alerts=5,
        altitude_range_km=(398.5, 401.2),
        velocity_range_m_s=(7668.0, 7673.0),
        latitude_range_deg=(-51.6, 51.6),
        eclipse_count=1,
        agent_messages_processed=4800,
        anomalies_detected=3,
        severity_distribution={"WARNING": 3, "CRITICAL": 1, "WATCH": 1},
    )


@pytest.fixture
def interstellar_results() -> MissionResults:
    """Interstellar mission with some terminal challenges."""
    return MissionResults(
        mission_name="Interstellar-100yr",
        mission_type="INTERSTELLAR",
        duration_sim_s=100.0,
        duration_wall_s=12.5,
        total_frames=100,
        total_events=5000,
        total_alerts=150,
        altitude_range_km=(0.0, 0.0),
        velocity_range_m_s=(0.0, 0.0),
        latitude_range_deg=(0.0, 0.0),
        eclipse_count=0,
        agent_messages_processed=2000,
        anomalies_detected=80,
        severity_distribution={"WARNING": 50, "CRITICAL": 60, "EMERGENCY": 30, "WATCH": 10},
        challenge_states={
            "material_entropy": "critical",
            "food_century": "terminal",
            "knowledge_preservation": "active",
            "genetic_diversity": "terminal",
            "psychological_decay": "emerging",
            "fuel_cliff": "nominal",
        },
        terminal_challenges=2,
    )


@pytest.fixture
def dashboard_nominal() -> DashboardSnapshot:
    """Nominal dashboard snapshot."""
    snap = DashboardSnapshot(
        mission_name="LEO-ISS-Test",
        mission_phase="CRUISE",
        altitude_km=400.0,
        velocity_m_s=7670.0,
        battery_soc_pct=85.0,
        solar_power_w=2700.0,
        total_load_w=1800.0,
        bus_voltage_v=28.0,
        agent_count=9,
        agents_healthy=9,
        bus_messages_total=4800,
        overall_status="NOMINAL",
    )
    snap.subsystems["power"] = SubsystemHealth(name="power", status="NOMINAL", dsremo_score=0.05)
    snap.subsystems["thermal"] = SubsystemHealth(name="thermal", status="NOMINAL", dsremo_score=0.02)
    return snap


@pytest.fixture
def dashboard_degraded() -> DashboardSnapshot:
    """Degraded dashboard with low battery and warnings."""
    snap = DashboardSnapshot(
        mission_name="LEO-Test",
        battery_soc_pct=12.0,
        solar_power_w=50.0,
        total_load_w=1800.0,
        bus_voltage_v=24.0,
        overall_status="CRITICAL",
        in_eclipse=True,
    )
    snap.subsystems["power"] = SubsystemHealth(name="power", status="CRITICAL", active_alerts=3, dsremo_score=0.85)
    return snap


@pytest.fixture
def challenge_summary() -> dict:
    """Challenge summary from orchestrator."""
    return {
        "material_entropy": {"status": "critical", "severity": 0.75, "metrics": {"aluminum_kg": 30000}},
        "food_century": {"status": "terminal", "severity": 1.0, "metrics": {"seed_viability_pct": 0.0}},
        "knowledge_preservation": {"status": "active", "severity": 0.45, "metrics": {}},
        "genetic_diversity": {"status": "terminal", "severity": 0.95, "metrics": {}},
        "psychological_decay": {"status": "emerging", "severity": 0.2, "metrics": {}},
        "fuel_cliff": {"status": "nominal", "severity": 0.05, "metrics": {}},
    }


@pytest.fixture
def sample_alerts() -> list[dict]:
    """Sample alert list."""
    return [
        {"topic": "aria.anomaly.power.undervoltage", "severity": "CRITICAL", "message": "Bus voltage dropped to 23.5V"},
        {"topic": "aria.anomaly.thermal.overheat", "severity": "WARNING", "message": "Thermal panel T=95C"},
        {"topic": "aria.anomaly.eclss.co2", "severity": "WARNING", "message": "CO2 rising above 3000ppm"},
        {"topic": "aria.anomaly.nav.drift", "severity": "WATCH", "message": "Slight orbital drift detected"},
    ]


# ────────────────────────────────────────────────────────────────────
#  Score Tests
# ────────────────────────────────────────────────────────────────────

class TestMissionScore:
    def test_score_weights_sum_to_one(self):
        s = MissionScore()
        assert abs(sum(s.weights.values()) - 1.0) < 1e-9

    def test_perfect_score(self):
        s = MissionScore(
            completion=100, alert_health=100, system_health=100,
            challenge_survival=100, physics_compliance=100,
        )
        total = s.compute_total()
        assert total == 100.0
        assert s.grade() == "A"

    def test_zero_score(self):
        s = MissionScore(
            completion=0, alert_health=0, system_health=0,
            challenge_survival=0, physics_compliance=0,
        )
        total = s.compute_total()
        assert total == 0.0
        assert s.grade() == "F"

    def test_grade_boundaries(self):
        for total, expected in [(95, "A"), (90, "A"), (85, "B"), (80, "B"),
                                (75, "C"), (70, "C"), (65, "D"), (60, "D"),
                                (55, "F"), (0, "F")]:
            s = MissionScore()
            s.total = total
            assert s.grade() == expected, f"total={total} expected grade={expected}"

    def test_score_clamped_to_0_100(self):
        s = MissionScore(
            completion=150, alert_health=200, system_health=100,
            challenge_survival=100, physics_compliance=100,
        )
        total = s.compute_total()
        assert total == 100.0

    def test_negative_subscores_clamped(self):
        s = MissionScore(
            completion=-50, alert_health=-20, system_health=100,
            challenge_survival=100, physics_compliance=100,
        )
        total = s.compute_total()
        assert total >= 0.0


# ────────────────────────────────────────────────────────────────────
#  Text Report Tests
# ────────────────────────────────────────────────────────────────────

class TestTextReport:
    def test_text_contains_all_sections(self, leo_results, dashboard_nominal):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal, generated_at="2026-04-07T00:00:00Z")
        text = gen.generate_text()

        required_sections = [
            "MISSION SUMMARY", "ORBITAL PARAMETERS", "POWER SYSTEM",
            "ALERT SUMMARY", "AGENT PERFORMANCE", "CHALLENGE STATUS",
            "PHYSICS VALIDATION", "RECOMMENDATIONS", "SCORE BREAKDOWN",
        ]
        for section in required_sections:
            assert section in text, f"Missing section: {section}"

    def test_text_contains_mission_name(self, leo_results):
        gen = MissionReportGenerator(leo_results, generated_at="2026-04-07T00:00:00Z")
        text = gen.generate_text()
        assert "LEO-ISS-Test" in text

    def test_text_shows_success_status(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        text = gen.generate_text()
        assert "SUCCESS" in text

    def test_text_shows_failure_status(self, leo_results):
        leo_results.errors = ["Basilisk crash", "Agent timeout"]
        gen = MissionReportGenerator(leo_results)
        text = gen.generate_text()
        assert "FAILED" in text
        assert "Basilisk crash" in text

    def test_text_format_via_generate(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        text = gen.generate(ReportFormat.TEXT)
        assert "ARIA MISSION REPORT" in text

    def test_text_with_alerts(self, leo_results, sample_alerts):
        gen = MissionReportGenerator(leo_results, alerts=sample_alerts)
        text = gen.generate_text()
        assert "Bus voltage dropped" in text
        assert "[CRITICAL]" in text

    def test_text_interstellar_challenges(self, interstellar_results, challenge_summary):
        gen = MissionReportGenerator(interstellar_results, challenge_summary=challenge_summary)
        text = gen.generate_text()
        assert "material_entropy" in text
        assert "terminal" in text.lower()
        assert "2/6" in text


# ────────────────────────────────────────────────────────────────────
#  JSON Report Tests
# ────────────────────────────────────────────────────────────────────

class TestJsonReport:
    def test_json_structure(self, leo_results, dashboard_nominal):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal)
        data = gen.generate_json()

        required_keys = [
            "meta", "score", "mission_summary", "orbital_parameters",
            "power_system", "alert_summary", "agent_performance",
            "challenge_status", "physics_validation", "recommendations",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_json_serializable(self, leo_results, dashboard_nominal, sample_alerts):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal, alerts=sample_alerts)
        json_str = gen.generate_json_string()
        parsed = json.loads(json_str)
        assert parsed["meta"]["format_version"] == "1.0"

    def test_json_score_matches_compute(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        data = gen.generate_json()
        score = gen.compute_score()
        assert data["score"]["total"] == score.total
        assert data["score"]["grade"] == score.grade()

    def test_json_power_none_without_dashboard(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        data = gen.generate_json()
        assert data["power_system"] is None

    def test_json_power_present_with_dashboard(self, leo_results, dashboard_nominal):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal)
        data = gen.generate_json()
        assert data["power_system"]["battery_soc_pct"] == 85.0

    def test_json_format_via_generate(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        result = gen.generate(ReportFormat.JSON)
        parsed = json.loads(result)
        assert "score" in parsed


# ────────────────────────────────────────────────────────────────────
#  HTML Report Tests
# ────────────────────────────────────────────────────────────────────

class TestHtmlReport:
    def test_html_is_valid_document(self, leo_results, dashboard_nominal):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal)
        html = gen.generate_html()
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<title>" in html

    def test_html_contains_mission_name(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        html = gen.generate_html()
        assert "LEO-ISS-Test" in html

    def test_html_contains_score(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        html = gen.generate_html()
        score = gen.compute_score()
        assert f"{score.total:.0f}/100" in html

    def test_html_escapes_special_chars(self):
        results = MissionResults(
            mission_name='<script>alert("xss")</script>',
            mission_type="LEO",
        )
        gen = MissionReportGenerator(results)
        html = gen.generate_html()
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_format_via_generate(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        html = gen.generate(ReportFormat.HTML)
        assert "<!DOCTYPE html>" in html


# ────────────────────────────────────────────────────────────────────
#  Physics Validation Tests
# ────────────────────────────────────────────────────────────────────

class TestPhysicsValidation:
    def test_iss_velocity_passes(self):
        """ISS at 400km should have velocity ~7672 m/s."""
        results = MissionResults(
            mission_name="ISS",
            mission_type="LEO",
            altitude_range_km=(399.0, 401.0),
            velocity_range_m_s=(7668.0, 7676.0),
        )
        checks = _validate_physics(results)
        velocity_checks = [c for c in checks if "kepler_velocity" in c["check"]]
        assert len(velocity_checks) == 2
        for c in velocity_checks:
            assert c["passed"], f"{c['check']} failed: deviation={c['deviation_pct']}%"

    def test_no_data_returns_fail(self):
        results = MissionResults(
            mission_name="empty",
            mission_type="LEO",
            altitude_range_km=(0, 0),
            velocity_range_m_s=(0, 0),
        )
        checks = _validate_physics(results)
        assert len(checks) == 1
        assert not checks[0]["passed"]
        assert "No orbital data" in checks[0]["detail"]

    def test_geo_velocity_passes(self):
        """GEO at 35786km should have velocity ~3075 m/s."""
        r_m = (35786 + 6371) * 1000.0
        v_expected = math.sqrt(3.986004418e14 / r_m)
        results = MissionResults(
            mission_name="GEO",
            mission_type="GEO",
            altitude_range_km=(35780.0, 35790.0),
            velocity_range_m_s=(v_expected - 5, v_expected + 5),
        )
        checks = _validate_physics(results)
        velocity_checks = [c for c in checks if "kepler_velocity" in c["check"]]
        for c in velocity_checks:
            assert c["passed"]

    def test_eccentricity_check(self):
        results = MissionResults(
            mission_name="eccentric",
            mission_type="LEO",
            altitude_range_km=(200.0, 2000.0),
            velocity_range_m_s=(6000.0, 8000.0),
        )
        checks = _validate_physics(results)
        ecc_check = [c for c in checks if c["check"] == "eccentricity_estimate"][0]
        # Large altitude spread = high eccentricity, should fail the <0.1 check
        assert not ecc_check["passed"]


# ────────────────────────────────────────────────────────────────────
#  Recommendations Tests
# ────────────────────────────────────────────────────────────────────

class TestRecommendations:
    def test_nominal_mission_no_critical_recs(self, leo_results, dashboard_nominal):
        score = MissionScore(completion=100, alert_health=95, system_health=100,
                             challenge_survival=100, physics_compliance=100)
        score.compute_total()
        recs = _generate_recommendations(leo_results, dashboard_nominal, score)
        assert len(recs) >= 1
        assert "nominal" in recs[0].lower() or "no critical" in recs[0].lower()

    def test_emergency_events_flagged(self, interstellar_results):
        score = MissionScore()
        score.total = 40
        score.compute_total()
        recs = _generate_recommendations(interstellar_results, None, score)
        assert any("EMERGENCY" in r for r in recs)

    def test_low_battery_recommendation(self, leo_results, dashboard_degraded):
        score = MissionScore()
        score.total = 50
        score.compute_total()
        recs = _generate_recommendations(leo_results, dashboard_degraded, score)
        assert any("BATTERY" in r or "SoC" in r for r in recs)

    def test_terminal_challenges_recommendation(self, interstellar_results):
        score = MissionScore()
        score.total = 30
        score.compute_total()
        recs = _generate_recommendations(interstellar_results, None, score)
        assert any("TERMINAL" in r for r in recs)

    def test_errors_recommendation(self):
        results = MissionResults(
            mission_name="broken",
            mission_type="LEO",
            errors=["Basilisk crash"],
        )
        score = MissionScore()
        score.total = 60
        score.compute_total()
        recs = _generate_recommendations(results, None, score)
        assert any("RUNTIME ERRORS" in r for r in recs)


# ────────────────────────────────────────────────────────────────────
#  Scoring Integration Tests
# ────────────────────────────────────────────────────────────────────

class TestScoringIntegration:
    def test_healthy_leo_scores_high(self, leo_results, dashboard_nominal):
        gen = MissionReportGenerator(leo_results, dashboard=dashboard_nominal)
        score = gen.compute_score()
        assert score.total >= 80.0
        assert score.grade() in ("A", "B")

    def test_failed_mission_scores_low(self):
        results = MissionResults(
            mission_name="failed",
            mission_type="LEO",
            errors=["crash1", "crash2", "crash3", "crash4", "crash5", "crash6"],
            total_frames=10,
            total_alerts=10,
        )
        gen = MissionReportGenerator(results)
        score = gen.compute_score()
        assert score.total < 50.0
        assert score.completion == 0.0

    def test_interstellar_terminal_reduces_score(self, interstellar_results):
        gen = MissionReportGenerator(interstellar_results)
        score = gen.compute_score()
        # 2/6 terminal = 4/6 survived = ~66.7
        assert 60 < score.challenge_survival < 70

    def test_high_alert_ratio_penalizes(self):
        results = MissionResults(
            mission_name="noisy",
            mission_type="LEO",
            total_frames=100,
            total_alerts=100,  # 1:1 ratio
        )
        gen = MissionReportGenerator(results)
        score = gen.compute_score()
        assert score.alert_health == 0.0

    def test_no_alerts_full_health(self):
        results = MissionResults(
            mission_name="quiet",
            mission_type="LEO",
            total_frames=500,
            total_alerts=0,
        )
        gen = MissionReportGenerator(results)
        score = gen.compute_score()
        assert score.alert_health == 100.0

    def test_dashboard_status_maps_to_score(self, leo_results):
        for status, expected_min in [("NOMINAL", 100), ("WARNING", 60), ("CRITICAL", 30), ("EMERGENCY", 0)]:
            snap = DashboardSnapshot(overall_status=status)
            gen = MissionReportGenerator(leo_results, dashboard=snap)
            score = gen.compute_score()
            assert score.system_health >= expected_min, f"status={status}"


# ────────────────────────────────────────────────────────────────────
#  Edge Cases
# ────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_minimal_results(self):
        """Bare-minimum MissionResults should not crash."""
        results = MissionResults(mission_name="bare", mission_type="LEO")
        gen = MissionReportGenerator(results)
        text = gen.generate_text()
        data = gen.generate_json()
        html = gen.generate_html()
        assert "bare" in text
        assert data["mission_summary"]["name"] == "bare"
        assert "bare" in html

    def test_empty_challenge_states(self, leo_results):
        gen = MissionReportGenerator(leo_results, challenge_summary={})
        text = gen.generate_text()
        assert "N/A" in text

    def test_unsupported_format_raises(self, leo_results):
        gen = MissionReportGenerator(leo_results)
        with pytest.raises(ValueError, match="Unsupported format"):
            gen.generate("INVALID")  # type: ignore[arg-type]

    def test_generated_at_override(self, leo_results):
        gen = MissionReportGenerator(leo_results, generated_at="2026-01-01T00:00:00Z")
        text = gen.generate_text()
        assert "2026-01-01T00:00:00Z" in text

    def test_all_six_challenges_terminal(self):
        results = MissionResults(
            mission_name="doom",
            mission_type="INTERSTELLAR",
            challenge_states={
                "material_entropy": "terminal",
                "food_century": "terminal",
                "knowledge_preservation": "terminal",
                "genetic_diversity": "terminal",
                "psychological_decay": "terminal",
                "fuel_cliff": "terminal",
            },
            terminal_challenges=6,
            total_frames=100,
            total_alerts=500,
        )
        gen = MissionReportGenerator(results)
        score = gen.compute_score()
        assert score.challenge_survival == 0.0
        recs = gen._recommendations
        assert any("MISSION VIABILITY" in r for r in recs)

    def test_large_alert_list_top_10(self, leo_results):
        alerts = [{"severity": "WARNING", "message": f"Alert {i}"} for i in range(50)]
        gen = MissionReportGenerator(leo_results, alerts=alerts)
        data = gen.generate_json()
        assert len(data["alert_summary"]["top_alerts"]) == 10
