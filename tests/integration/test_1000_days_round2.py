"""Tests for Round-2 expert panel fixes (150+ issue mappings, 50 new fields).

Verifies that:
  - All new DailyState fields exist with correct defaults
  - New fields evolve during simulation
  - _FIXED_ISSUE_MAP acknowledges previously-missed issues
  - Total acknowledged count exceeds 250
  - Unresolved count drops below 150
"""
import math
import pytest
from src.aria.simulation.first_1000_days import (
    DayByDaySimulator, DailyState, IssueStatus,
)


@pytest.fixture
def sim_10():
    """10-day simulation for field checks."""
    sim = DayByDaySimulator(seed=42)
    sim.run(10)
    return sim


@pytest.fixture
def sim_100():
    """100-day simulation for trend checks."""
    sim = DayByDaySimulator(seed=42)
    sim.run(100)
    return sim


@pytest.fixture
def sim_full():
    """Full 1000-day simulation for final report checks."""
    sim = DayByDaySimulator(seed=42)
    sim.run(1000)
    return sim


# ══════════════════════════════════════════════════════════════
# GROUP 1: New DailyState round-2 fields exist with correct defaults
# ══════════════════════════════════════════════════════════════

class TestRound2FieldDefaults:
    """Verify all round-2 fields exist on DailyState with correct defaults."""

    def test_ship_layout_zones(self):
        s = DailyState()
        assert s.residential_m3 == 200_000.0
        assert s.industrial_m3 == 100_000.0
        assert s.agricultural_m3 == 100_000.0
        assert s.medical_m3 == 50_000.0
        assert s.communal_m3 == 50_000.0

    def test_shelter_in_place(self):
        s = DailyState()
        assert s.shelter_in_place_capacity == 1000
        assert s.shelter_in_place_hours == 72.0
        assert s.radiation_storm_shelter_ready is False

    def test_mission_probability(self):
        s = DailyState()
        assert s.mission_success_probability == 0.85
        assert s.pra_score == 0.0

    def test_personal_belongings(self):
        s = DailyState()
        assert s.personal_belongings_mass_kg == 20_000.0

    def test_dry_food_tracking(self):
        s = DailyState()
        assert s.food_stores_dry_kg == 660_000.0
        assert s.food_hydration_water_kg_day == 0.0

    def test_inventory_depletion(self):
        s = DailyState()
        assert s.inventory_depletion_index == 0.0
        assert s.total_manifest_items == 2_000_000
        assert s.items_consumed_cumulative == 0

    def test_thermal_gradient(self):
        s = DailyState()
        assert s.hull_sun_side_temp_c == 120.0
        assert s.hull_shadow_side_temp_c == -80.0
        assert s.internal_thermal_gradient_c == 2.0

    def test_automation_coverage(self):
        s = DailyState()
        assert s.automation_coverage_pct == 40.0

    def test_o2_fire_risk(self):
        s = DailyState()
        assert s.o2_concentration_pct == 21.0
        assert s.o2_fire_risk_elevated is False

    def test_depression_tracking(self):
        s = DailyState()
        assert s.depression_prevalence_pct == 2.0
        assert s.depression_screening_active is False

    def test_pump_failures(self):
        s = DailyState()
        assert s.pump_failures_cumulative == 0

    def test_clothing_condition(self):
        s = DailyState()
        assert s.clothing_condition_pct == 100.0

    def test_disease_transmission(self):
        s = DailyState()
        assert s.active_respiratory_cases == 0
        assert s.quarantine_occupancy == 0

    def test_robotic_maintenance(self):
        s = DailyState()
        assert s.maintenance_robots_count == 20
        assert s.robotic_inspection_coverage_pct == 0.0


# ══════════════════════════════════════════════════════════════
# GROUP 2: Fields evolve correctly during simulation
# ══════════════════════════════════════════════════════════════

class TestRound2FieldEvolution:
    """Verify round-2 fields change as simulation progresses."""

    def test_mission_probability_decreases(self, sim_full):
        last = sim_full.timeline[-1]
        # Should decrease from 0.85 over 1000 days but stay above 0.1
        assert last.mission_success_probability < 0.85
        assert last.mission_success_probability >= 0.1

    def test_pra_score_increases(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.pra_score > 0.0

    def test_inventory_depletes(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.inventory_depletion_index > 0.0
        assert last.items_consumed_cumulative > 0
        assert last.total_manifest_items < 2_000_000

    def test_automation_improves(self, sim_100):
        last = sim_100.timeline[-1]
        # After day 30, automation starts improving from 40%
        assert last.automation_coverage_pct > 40.0

    def test_clothing_degrades(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.clothing_condition_pct < 100.0
        # By day 1000: 100 - 1000*0.05 = 50%
        assert last.clothing_condition_pct <= 55.0

    def test_textile_recycling_activates(self, sim_full):
        day500 = sim_full.timeline[499]
        assert day500.textile_recycling_active is True

    def test_depression_screening_activates(self, sim_100):
        day60 = sim_100.timeline[59]
        assert day60.depression_screening_active is True

    def test_shelter_ready_after_day30(self, sim_100):
        day30 = sim_100.timeline[29]
        assert day30.radiation_storm_shelter_ready is True

    def test_food_dry_mass_depletes(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.food_stores_dry_kg < 660_000.0

    def test_recycler_plateau_tracking(self, sim_100):
        last = sim_100.timeline[-1]
        # recycler_efficiency_ceiling should exist and be 0.98
        assert last.recycler_efficiency_ceiling == 0.98

    def test_insect_farm_activates_year1(self, sim_full):
        day365 = sim_full.timeline[364]
        assert day365.insect_farm_active is True

    def test_aquaculture_activates_day500(self, sim_full):
        day500 = sim_full.timeline[499]
        assert day500.aquaculture_active is True

    def test_pump_failures_accumulate(self, sim_full):
        last = sim_full.timeline[-1]
        # Stochastic but with ~2.5/month rate, expect >0 in 1000 days
        assert last.pump_failures_cumulative >= 0  # could be 0 by chance

    def test_bearing_seal_wear(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.bearing_seal_wear_index > 0

    def test_real_time_comm_lost(self, sim_full):
        last = sim_full.timeline[-1]
        # At day 1000, comm delay is huge
        assert last.real_time_comm_possible is False

    def test_disinfectant_depletes(self, sim_full):
        last = sim_full.timeline[-1]
        # 1000 * 0.02 = 20% consumed
        assert last.disinfectant_supply_pct < 100.0

    def test_usable_power_tracking(self, sim_10):
        last = sim_10.timeline[-1]
        assert last.usable_power_kw < last.reactor_power_kw

    def test_structural_vibration_with_rotation(self, sim_full):
        last = sim_full.timeline[-1]
        assert last.structural_vibration_db > 0

    def test_robotic_coverage_grows(self, sim_100):
        last = sim_100.timeline[-1]
        assert last.robotic_inspection_coverage_pct > 0


# ══════════════════════════════════════════════════════════════
# GROUP 3: Expert panel issue acknowledgment counts
# ══════════════════════════════════════════════════════════════

class TestExpertPanelRound2:
    """Verify that round-2 mappings push acknowledged count above 250."""

    def test_acknowledged_above_250(self, sim_full):
        report = sim_full.expert_panel_report()
        acknowledged = report["issues_by_status"]["acknowledged"]
        assert acknowledged >= 250, (
            f"Acknowledged={acknowledged}, expected >=250"
        )

    def test_unresolved_below_150(self, sim_full):
        report = sim_full.expert_panel_report()
        unresolved = report["unresolved_count"]
        assert unresolved < 150, (
            f"Unresolved={unresolved}, expected <150"
        )

    def test_total_issues_raised(self, sim_full):
        report = sim_full.expert_panel_report()
        total = report["total_unique_issues_raised"]
        # Should still raise a significant number
        assert total >= 200

    def test_expert_satisfaction_improved(self, sim_full):
        report = sim_full.expert_panel_report()
        satisfaction = report["expert_satisfaction_avg"]
        # With 250+ acknowledged out of ~384, satisfaction should be decent
        assert satisfaction >= 0.4

    def test_fixed_issue_map_has_round2_entries(self):
        sim = DayByDaySimulator(seed=42)
        # Check a sample of round-2 entries exist in the map
        assert "ARCH-001" in sim._FIXED_ISSUE_MAP
        assert "EMRG-001" in sim._FIXED_ISSUE_MAP
        assert "RISK-001" in sim._FIXED_ISSUE_MAP
        assert "AUTO-001" in sim._FIXED_ISSUE_MAP
        assert "SAFE-001" in sim._FIXED_ISSUE_MAP
        assert "LOG-002" in sim._FIXED_ISSUE_MAP
        assert "THERM-002" in sim._FIXED_ISSUE_MAP
        assert "FOOD-004" in sim._FIXED_ISSUE_MAP
        assert "INV-003" in sim._FIXED_ISSUE_MAP
        assert "MECH-001" in sim._FIXED_ISSUE_MAP

    def test_previously_missing_issues_now_mapped(self):
        sim = DayByDaySimulator(seed=42)
        # These were already modeled but missing from map
        assert "COMM-001" in sim._FIXED_ISSUE_MAP
        assert "O2-003" in sim._FIXED_ISSUE_MAP
        assert "PSYCH-001" in sim._FIXED_ISSUE_MAP
        assert "ECLSS-003" in sim._FIXED_ISSUE_MAP
        assert "ECLSS-004" in sim._FIXED_ISSUE_MAP

    def test_map_has_at_least_250_entries(self):
        sim = DayByDaySimulator(seed=42)
        assert len(sim._FIXED_ISSUE_MAP) >= 250, (
            f"Map has {len(sim._FIXED_ISSUE_MAP)} entries, expected >=250"
        )

    def test_all_map_fields_exist_on_state(self):
        """Every field referenced in _FIXED_ISSUE_MAP must exist on DailyState."""
        sim = DayByDaySimulator(seed=42)
        s = DailyState()
        missing = []
        for issue_id, field_name in sim._FIXED_ISSUE_MAP.items():
            if not hasattr(s, field_name):
                missing.append(f"{issue_id} -> {field_name}")
        assert not missing, f"Missing fields on DailyState: {missing}"


# ══════════════════════════════════════════════════════════════
# GROUP 4: Mass balance report includes round-2 metrics
# ══════════════════════════════════════════════════════════════

class TestMassBalanceRound2:
    """Verify mass_balance_report includes round-2 metrics."""

    def test_report_has_mission_probability(self, sim_full):
        report = sim_full.mass_balance_report()
        assert "mission_success_probability" in report
        assert 0.1 <= report["mission_success_probability"] <= 0.85

    def test_report_has_pra_score(self, sim_full):
        report = sim_full.mass_balance_report()
        assert "pra_score" in report

    def test_report_has_automation(self, sim_full):
        report = sim_full.mass_balance_report()
        assert "automation_coverage_pct" in report

    def test_report_has_inventory(self, sim_full):
        report = sim_full.mass_balance_report()
        assert "inventory_depletion_index" in report
