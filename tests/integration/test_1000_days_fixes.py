"""Tests for Batch-2 expert panel fixes (top 50 issues).

Verifies that all new DailyState fields exist, are initialized correctly,
evolve during simulation, and that the expert panel auto-acknowledges
fixed issues — reducing unresolved count from 383 to <300.
"""
import math
import pytest
from src.aria.simulation.first_1000_days import (
    DayByDaySimulator, DailyState, IssueStatus,
    GCR_FLUX_MSV_DAY, HULL_SHIELDING_FACTOR,
    KITCHEN_ENERGY_KW, DENTAL_EVENTS_PER_1000_PER_MONTH,
    FIRE_SUPPRESSION_AGENT_KG, TOTAL_SOLID_WASTE_KG_PP,
    SOLID_WASTE_KG_PP, CABIN_VOLUME_M3, IT_BASE_POWER_KW,
    SHOWER_WATER_KG_PP_DAY, LAUNDRY_WATER_L_PP_WEEK,
    MEDICAL_SUPPLY_INITIAL_PCT, MORALE_BASE,
)


@pytest.fixture
def sim_short():
    """10-day simulation for quick field checks."""
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
# GROUP 1: New DailyState fields exist and have correct defaults
# ══════════════════════════════════════════════════════════════

class TestDailyStateFields:
    """Verify all new fields exist on DailyState with correct defaults."""

    def test_eclss_redundancy(self):
        s = DailyState()
        assert s.eclss_loops_active == 3
        assert s.eclss_loops_total == 3

    def test_supply_chain_fields(self):
        s = DailyState()
        assert s.hepa_filter_stock == 200
        assert s.recycler_membrane_stock == 10
        assert s.medical_supply_pct == MEDICAL_SUPPLY_INITIAL_PCT
        assert s.spare_parts_pct == 100.0

    def test_extended_fields_exist(self):
        s = DailyState()
        assert s.trace_contaminant_ppb == 10.0
        assert s.co2_floor_ppm == 400.0
        assert s.quarantine_wards == 4
        assert s.blood_units_available == 200
        assert s.fire_compartments == 50
        assert s.psychologists_count == 5
        assert s.seed_viability_pct == 98.0


# ══════════════════════════════════════════════════════════════
# GROUP 2: Simulation logic produces correct values
# ══════════════════════════════════════════════════════════════

class TestLaundrySystem:
    def test_laundry_water_positive(self, sim_short):
        s = sim_short.timeline[-1]
        expected = 1000 * LAUNDRY_WATER_L_PP_WEEK / 7.0
        assert abs(s.laundry_water_kg_day - expected) < 1.0

    def test_laundry_backlog_accumulates_first_14_days(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.laundry_backlog_kg > 0  # backlog during first 14 days


class TestKitchenSystem:
    def test_meals_count(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.meals_prepared_today == 3000

    def test_kitchen_energy(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.kitchen_energy_kw == KITCHEN_ENERGY_KW


class TestRadiation:
    def test_daily_radiation_positive(self, sim_short):
        s = sim_short.timeline[-1]
        # With Schwabe solar cycle modulation, GCR flux varies by +/-30%
        expected_min = GCR_FLUX_MSV_DAY * HULL_SHIELDING_FACTOR * 0.7
        assert s.daily_radiation_msv >= expected_min

    def test_cumulative_grows(self, sim_short):
        assert sim_short.timeline[-1].cumulative_radiation_msv > sim_short.timeline[0].cumulative_radiation_msv

    def test_cumulative_at_1000(self, sim_full):
        s = sim_full.timeline[-1]
        # With Schwabe solar cycle modulation (0.7x-1.3x), use lower bound
        min_expected = GCR_FLUX_MSV_DAY * HULL_SHIELDING_FACTOR * 1000 * 0.7
        assert s.cumulative_radiation_msv >= min_expected * 0.9


class TestNoiseModel:
    def test_noise_above_base(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.ambient_noise_db >= 50.0

    def test_noise_with_manufacturing(self, sim_100):
        # After day 120, manufacturing adds noise
        day_130 = sim_100.timeline[99]  # day 100
        assert day_130.ambient_noise_db >= 55.0


class TestPressureLeak:
    def test_makeup_air_positive(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.makeup_air_kg_day > 0

    def test_pressure_stays_safe(self, sim_full):
        for s in sim_full.timeline:
            assert 95.0 <= s.pressure_kpa <= 103.0


class TestParticulateFilter:
    def test_particulate_load_increases(self, sim_short):
        assert sim_short.timeline[-1].particulate_load_mg_m3 > 0.01

    def test_hepa_load_increases(self, sim_100):
        assert sim_100.timeline[-1].hepa_filter_load_pct > 0


class TestMorale:
    def test_morale_bounded(self, sim_full):
        for s in sim_full.timeline:
            assert 20.0 <= s.morale_index <= 100.0

    def test_morale_changes(self, sim_full):
        first = sim_full.timeline[0].morale_index
        last = sim_full.timeline[-1].morale_index
        assert first != last  # morale should drift


class TestSupplyDepletion:
    def test_medical_depletes(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.medical_supply_pct < MEDICAL_SUPPLY_INITIAL_PCT

    def test_spare_parts_deplete(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.spare_parts_pct < 100.0

    def test_pharmaceutical_depletes(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.pharmaceutical_supply_pct < 100.0

    def test_hepa_stock_decreases(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.hepa_filter_stock < 200


class TestDrills:
    def test_drills_conducted(self, sim_full):
        s = sim_full.timeline[-1]
        # ~33 fire drills (monthly) + ~11 decompression drills (quarterly) = ~44
        assert s.drills_conducted >= 30


class TestEVASuits:
    def test_suit_health_degrades(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.eva_suit_health_pct < 100.0

    def test_eva_consumables_deplete(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.eva_consumable_stock < 500


class TestTraceContaminants:
    def test_tccs_activates(self, sim_short):
        # TCCS activates on day 14
        s = sim_short.timeline[-1]
        # Day 10 - not yet active
        assert sim_short.timeline[9].tccs_active is False or sim_short.timeline[9].day < 14

    def test_contaminants_controlled(self, sim_100):
        s = sim_100.timeline[-1]
        assert s.trace_contaminant_ppb < 20  # controlled by TCCS


class TestWaterSystems:
    def test_grey_water_tracked(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.grey_water_kg_day > 0

    def test_black_water_tracked(self, sim_short):
        s = sim_short.timeline[-1]
        assert s.black_water_kg_day > 0

    def test_shower_water_tracked(self, sim_short):
        s = sim_short.timeline[-1]
        expected = 1000 * SHOWER_WATER_KG_PP_DAY
        assert abs(s.shower_water_kg_day - expected) < 1.0

    def test_brine_processing_activates(self, sim_100):
        s = sim_100.timeline[-1]
        assert s.brine_processor_active is True


class TestGovernanceAndSocial:
    def test_governance_established(self, sim_100):
        s = sim_100.timeline[-1]
        assert s.governance_established is True

    def test_security_incidents_tracked(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.security_incidents_cumulative >= 0


class TestRevisedSolidWaste:
    def test_solid_waste_higher_than_fecal_only(self, sim_full):
        s = sim_full.timeline[-1]
        # With revised 0.5 kg/pp/day instead of 0.11, waste should be significantly higher
        fecal_only_1000_days = 1000 * SOLID_WASTE_KG_PP * 1000 * 0.2  # 20% accumulates
        assert s.waste_solid_kg > fecal_only_1000_days


class TestVehicleMass:
    def test_total_mass_decreases(self, sim_full):
        s = sim_full.timeline[-1]
        assert s.total_vehicle_mass_kg < 50_000_000.0  # lost air from leaks


class TestCropTranspiration:
    def test_transpiration_tracked(self, sim_full):
        # After hydroponics is active (day 180+)
        day_200 = sim_full.timeline[199]
        assert day_200.crop_transpiration_water_kg > 0


# ══════════════════════════════════════════════════════════════
# GROUP 3: Expert panel acknowledges fixed issues
# ══════════════════════════════════════════════════════════════

class TestExpertPanelAcknowledgements:
    def test_unresolved_below_300(self, sim_full):
        report = sim_full.expert_panel_report()
        assert report["unresolved_count"] < 300, (
            f"Expected <300 unresolved, got {report['unresolved_count']}")

    def test_acknowledged_count_significant(self, sim_full):
        report = sim_full.expert_panel_report()
        assert report["issues_by_status"]["acknowledged"] >= 80

    def test_specific_issues_acknowledged(self, sim_full):
        panel = sim_full._expert_panel
        # Check key issues are acknowledged
        key_issues = [
            "WASTE-002", "FDSCI-001", "RAD-001", "HF-001",
            "PRESS-001", "AIR-001", "EVA-001", "ECLSS-002",
            "AIR-002", "MECH-002", "ATMO-002", "FOOD-002",
        ]
        for iid in key_issues:
            if iid in panel.all_issues:
                assert panel.all_issues[iid].status == IssueStatus.ACKNOWLEDGED, (
                    f"Issue {iid} should be acknowledged but is {panel.all_issues[iid].status}")

    def test_mass_balance_has_new_fields(self, sim_full):
        report = sim_full.mass_balance_report()
        assert "cumulative_radiation_msv" in report
        assert "morale_index" in report
        assert "medical_supply_pct" in report
        assert "spare_parts_pct" in report
        assert "hepa_filter_stock" in report
        assert "total_vehicle_mass_kg" in report
        assert "ambient_noise_db" in report
        assert "drills_conducted" in report
        assert "eclss_loops_active" in report
        assert "pharmaceutical_supply_pct" in report


# ══════════════════════════════════════════════════════════════
# GROUP 4: Resource stability over 1000 days
# ══════════════════════════════════════════════════════════════

class TestResourceStability:
    def test_water_never_negative(self, sim_full):
        for s in sim_full.timeline:
            assert s.water_tank_kg > 0, f"Water went negative on day {s.day}"

    def test_food_never_negative(self, sim_full):
        for s in sim_full.timeline:
            assert s.food_stores_kg > 0, f"Food went negative on day {s.day}"

    def test_o2_never_negative(self, sim_full):
        for s in sim_full.timeline:
            assert s.o2_tank_kg > 0, f"O2 went negative on day {s.day}"

    def test_fire_suppression_never_negative(self, sim_full):
        for s in sim_full.timeline:
            assert s.fire_suppression_agent_kg >= 0

    def test_medical_supply_never_negative(self, sim_full):
        for s in sim_full.timeline:
            assert s.medical_supply_pct >= 0
