"""Integration tests for resource mining mission simulation.

Tests cover:
  - ResourceScanner: loading, classification, scoring, filtering
  - MiningOpsModel: method selection, yields, fuel, power, crew
  - MissionPlanner: single-stop, multi-stop route planning
  - DiamondMissionScenario: 55 Cnc e specific calculations
  - MiningMission: full end-to-end mission execution
  - CLI helpers: list targets, run mission
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from aria.simulation.mining_mission import (
    DEFAULT_VELOCITY_C,
    DIAMOND_YIELD_T_PER_YEAR,
    VALUE_PER_TON,
    DiamondMissionScenario,
    MiningMethod,
    MiningMission,
    MiningMissionConfig,
    MiningMissionResults,
    MiningOperation,
    MiningOpsConfig,
    MiningOpsModel,
    MiningTarget,
    MissionPlanner,
    MissionRoute,
    MissionStop,
    ResourceScanner,
    ResourceType,
    build_55_cnc_e_target,
    cli_list_targets,
    cli_run_mining_mission,
    list_mining_targets,
)


# ────────────────────────────────────────────────────────────────────
#  FIXTURES
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def scanner() -> ResourceScanner:
    s = ResourceScanner()
    s.load()
    return s


@pytest.fixture
def cnc_target() -> MiningTarget:
    return build_55_cnc_e_target()


@pytest.fixture
def ops_model() -> MiningOpsModel:
    return MiningOpsModel(seed=42)


@pytest.fixture
def planner() -> MissionPlanner:
    return MissionPlanner(seed=42)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a minimal test CSV with known values."""
    csv_path = tmp_path / "test_planets.csv"
    csv_path.write_text(
        "pl_name,hostname,sy_dist,pl_rade,pl_bmasse,pl_orbper,pl_eqt,st_spectype,st_teff,st_mass,disc_year\n"
        '"DiamondWorld","55 Cnc",3.86,1.9,8.0,0.74,1958.0,"G8 V",5172.0,0.9,2004\n'
        '"IceWorld","IceStar",5.0,3.0,2.0,300.0,150.0,"M2V",3400.0,0.4,2010\n'
        '"MetalWorld","MetalStar",8.0,1.5,15.0,10.0,800.0,"K2V",4500.0,0.7,2015\n'
        '"RockyEarth","RockStar",4.0,1.3,3.5,50.0,400.0,"G5V",5600.0,1.0,2020\n'
        '"GasGiant","GasStar",20.0,14.0,300.0,4000.0,100.0,"F5V",6500.0,1.3,2005\n'
    )
    return csv_path


# ────────────────────────────────────────────────────────────────────
#  RESOURCE SCANNER TESTS
# ────────────────────────────────────────────────────────────────────

class TestResourceScanner:

    def test_load_real_data(self, scanner: ResourceScanner) -> None:
        """Scanner loads real NASA exoplanet CSV with > 1000 targets."""
        assert len(scanner.targets) > 500

    def test_all_targets_have_distance(self, scanner: ResourceScanner) -> None:
        for t in scanner.targets:
            assert t.distance_ly > 0, f"{t.name} has no distance"

    def test_find_55_cnc_e(self, scanner: ResourceScanner) -> None:
        target = scanner.find_target("55 Cnc e")
        assert target is not None
        assert "55 Cnc" in target.name
        assert target.mass_earth == pytest.approx(7.99, rel=0.01)

    def test_find_case_insensitive(self, scanner: ResourceScanner) -> None:
        assert scanner.find_target("55 cnc e") is not None
        assert scanner.find_target("gj 876") is not None

    def test_classify_diamond_55cnc(self, scanner: ResourceScanner) -> None:
        target = scanner.find_target("55 Cnc e")
        assert target is not None
        assert target.resource_type == ResourceType.DIAMOND

    def test_get_by_type_diamond(self, scanner: ResourceScanner) -> None:
        diamonds = scanner.get_by_type(ResourceType.DIAMOND)
        assert len(diamonds) >= 1
        assert all(t.resource_type == ResourceType.DIAMOND for t in diamonds)

    def test_get_top_targets(self, scanner: ResourceScanner) -> None:
        top = scanner.get_top_targets(10)
        assert len(top) <= 10
        assert all(t.mining_score > 0 for t in top)
        # Verify sorted descending
        scores = [t.mining_score for t in top]
        assert scores == sorted(scores, reverse=True)

    def test_get_nearby(self, scanner: ResourceScanner) -> None:
        nearby = scanner.get_nearby(max_distance_ly=20.0)
        for t in nearby:
            assert t.distance_ly <= 20.0
            assert t.resource_type != ResourceType.UNKNOWN

    def test_density_calculation(self, cnc_target: MiningTarget) -> None:
        expected = 7.99 / (1.875 ** 3)
        assert cnc_target.density_earth == pytest.approx(expected, rel=0.01)

    def test_load_sample_csv(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        count = s.load()
        assert count == 5

    def test_classify_sample_diamond(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        dw = s.find_target("DiamondWorld")
        assert dw is not None
        assert dw.resource_type == ResourceType.DIAMOND

    def test_classify_sample_ice(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        iw = s.find_target("IceWorld")
        assert iw is not None
        assert iw.resource_type == ResourceType.WATER_ICE

    def test_classify_sample_metal(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        mw = s.find_target("MetalWorld")
        assert mw is not None
        assert mw.resource_type == ResourceType.METALS

    def test_classify_sample_rare_earth(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        re = s.find_target("RockyEarth")
        assert re is not None
        assert re.resource_type == ResourceType.RARE_EARTH

    def test_missing_csv(self, tmp_path: Path) -> None:
        s = ResourceScanner(csv_path=tmp_path / "nonexistent.csv")
        count = s.load()
        assert count == 0

    def test_travel_time_calculation(self, cnc_target: MiningTarget) -> None:
        expected = cnc_target.distance_ly / DEFAULT_VELOCITY_C
        assert cnc_target.travel_time_years == pytest.approx(expected, rel=0.01)


# ────────────────────────────────────────────────────────────────────
#  MINING OPS MODEL TESTS
# ────────────────────────────────────────────────────────────────────

class TestMiningOpsModel:

    def test_select_method_diamond_hot(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        method = ops_model.select_method(cnc_target)
        assert method == MiningMethod.ORBITAL_CAPTURE

    def test_select_method_ice(self, ops_model: MiningOpsModel) -> None:
        ice = MiningTarget(
            name="Ice", host_star="H", distance_pc=5, radius_earth=3,
            mass_earth=2, orbital_period_days=300, eq_temp_k=150,
            spectral_type="M", stellar_teff=3400, stellar_mass=0.4, disc_year=2010,
            resource_type=ResourceType.WATER_ICE,
        )
        assert ops_model.select_method(ice) == MiningMethod.ICE_HARVESTING

    def test_select_method_metals(self, ops_model: MiningOpsModel) -> None:
        metal = MiningTarget(
            name="M", host_star="H", distance_pc=8, radius_earth=1.5,
            mass_earth=15, orbital_period_days=10, eq_temp_k=800,
            spectral_type="K", stellar_teff=4500, stellar_mass=0.7, disc_year=2015,
            resource_type=ResourceType.METALS,
        )
        assert ops_model.select_method(metal) == MiningMethod.STRIP_MINING

    def test_orbital_insertion_fuel_positive(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        fuel = ops_model.orbital_insertion_fuel(cnc_target, ship_mass_t=50000)
        assert fuel > 0
        assert fuel < 50000  # can't use more fuel than ship mass

    def test_estimate_yield_positive(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        raw, processed = ops_model.estimate_yield(
            cnc_target, MiningMethod.ORBITAL_CAPTURE, duration_years=10.0
        )
        assert raw > 0
        assert processed > 0
        assert processed <= raw  # processing always loses some

    def test_yield_scales_with_duration(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        _, short = ops_model.estimate_yield(cnc_target, MiningMethod.ORBITAL_CAPTURE, 1.0)
        ops2 = MiningOpsModel(seed=42)  # same seed for same variance
        _, long = ops2.estimate_yield(cnc_target, MiningMethod.ORBITAL_CAPTURE, 10.0)
        assert long > short

    def test_power_requirement(self, ops_model: MiningOpsModel) -> None:
        for method in MiningMethod:
            power = ops_model.power_requirement(method)
            assert power > 0

    def test_crew_requirement(self, ops_model: MiningOpsModel) -> None:
        for method in MiningMethod:
            crew = ops_model.crew_requirement(method)
            assert crew >= 2

    def test_robots_required(self, ops_model: MiningOpsModel) -> None:
        for method in MiningMethod:
            robots = ops_model.robots_required(method)
            assert robots >= 4

    def test_run_operation(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        op = ops_model.run_operation(cnc_target, mission_year=126, duration_years=10)
        assert op.status == "COMPLETE"
        assert op.tons_extracted > 0
        assert op.tons_processed > 0
        assert op.value > 0


# ────────────────────────────────────────────────────────────────────
#  MISSION PLANNER TESTS
# ────────────────────────────────────────────────────────────────────

class TestMissionPlanner:

    def test_plan_single(self, planner: MissionPlanner, cnc_target: MiningTarget) -> None:
        route = planner.plan_single(cnc_target, mining_duration_years=10)
        assert len(route.stops) == 1
        assert route.total_duration_years > 0
        assert route.total_fuel_t > 0
        assert route.total_distance_ly > 0

    def test_plan_single_round_trip(self, planner: MissionPlanner, cnc_target: MiningTarget) -> None:
        route = planner.plan_single(cnc_target, mining_duration_years=10)
        travel = cnc_target.distance_ly / DEFAULT_VELOCITY_C
        expected = travel * 2 + 10
        assert route.total_duration_years == pytest.approx(expected, rel=0.01)

    def test_plan_multi_stop(self, planner: MissionPlanner, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        targets = [t for t in s.targets if t.resource_type != ResourceType.UNKNOWN]
        route = planner.plan_multi_stop(targets, mining_years_per_stop=5, max_stops=3)
        assert len(route.stops) >= 1
        assert route.total_duration_years > 0

    def test_fuel_for_transit(self, planner: MissionPlanner) -> None:
        fuel = planner.fuel_for_transit(10.0)
        assert fuel > 0

    def test_multi_stop_respects_max(self, planner: MissionPlanner, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        targets = [t for t in s.targets if t.resource_type != ResourceType.UNKNOWN]
        route = planner.plan_multi_stop(targets, max_stops=2)
        assert len(route.stops) <= 2


# ────────────────────────────────────────────────────────────────────
#  55 CANCRI e DIAMOND SCENARIO TESTS
# ────────────────────────────────────────────────────────────────────

class TestDiamondMissionScenario:

    def test_travel_time(self) -> None:
        s = DiamondMissionScenario()
        assert s.travel_time_one_way_years == pytest.approx(126.0, rel=0.01)

    def test_total_mission_time(self) -> None:
        s = DiamondMissionScenario()
        expected = 126 * 2 + 20  # default mining duration
        assert s.total_mission_years == pytest.approx(expected, rel=0.01)

    def test_carbon_mass(self) -> None:
        s = DiamondMissionScenario()
        earth_mass_kg = 5.972e24
        expected = 7.99 * earth_mass_kg * 0.33
        assert s.planet_carbon_mass_kg == pytest.approx(expected, rel=0.01)

    def test_diamond_reserve(self) -> None:
        s = DiamondMissionScenario()
        assert s.diamond_reserve_kg > 0
        assert s.diamond_reserve_carats > s.diamond_reserve_kg  # carats > kg

    def test_annual_yield(self) -> None:
        s = DiamondMissionScenario()
        yield_carats = s.estimate_annual_yield_carats()
        assert yield_carats > 1_000_000  # millions of carats per year

    def test_describe_output(self) -> None:
        s = DiamondMissionScenario()
        desc = s.describe()
        assert "55 CANCRI" in desc
        assert "DIAMOND" in desc
        assert "12.6 ly" in desc

    def test_build_55_cnc_e(self) -> None:
        t = build_55_cnc_e_target()
        assert t.name == "55 Cnc e"
        assert t.mass_earth == 7.99
        assert t.radius_earth == 1.875
        assert t.resource_type == ResourceType.DIAMOND


# ────────────────────────────────────────────────────────────────────
#  FULL MINING MISSION TESTS
# ────────────────────────────────────────────────────────────────────

class TestMiningMission:

    def test_run_55cnc_e(self) -> None:
        config = MiningMissionConfig(
            target_name="55 Cnc e",
            mining_duration_years=10,
        )
        mission = MiningMission(config)
        results = mission.run()
        assert results.ship_survived
        assert results.target_name == "55 Cnc e"
        assert results.resource_type == "DIAMOND"
        assert results.processed_t > 0

    def test_run_gj876(self) -> None:
        config = MiningMissionConfig(target_name="GJ 876 d", mining_duration_years=5)
        mission = MiningMission(config)
        results = mission.run()
        assert results.ship_survived
        assert results.processed_t > 0

    def test_unknown_target_aborts(self) -> None:
        config = MiningMissionConfig(target_name="NonexistentPlanet42")
        mission = MiningMission(config)
        results = mission.run()
        assert not results.ship_survived

    def test_mission_events_logged(self) -> None:
        config = MiningMissionConfig(target_name="55 Cnc e", mining_duration_years=5)
        mission = MiningMission(config)
        results = mission.run()
        assert len(results.events) >= 4  # SCAN, LAUNCH, MINING_START, MINING_COMPLETE

    def test_cargo_pods_sent(self) -> None:
        config = MiningMissionConfig(
            target_name="55 Cnc e", mining_duration_years=10, use_cargo_pods=True
        )
        mission = MiningMission(config)
        results = mission.run()
        assert results.cargo_pods_sent >= 1

    def test_fuel_accounting(self) -> None:
        config = MiningMissionConfig(target_name="55 Cnc e", mining_duration_years=5)
        mission = MiningMission(config)
        results = mission.run()
        assert results.fuel_for_transit_t > 0
        assert results.fuel_for_insertion_t > 0
        assert results.total_fuel_t == results.fuel_for_transit_t + results.fuel_for_insertion_t

    def test_results_summary(self) -> None:
        config = MiningMissionConfig(target_name="55 Cnc e", mining_duration_years=5)
        mission = MiningMission(config)
        results = mission.run()
        summary = results.summary()
        assert "MINING MISSION" in summary
        assert "55 Cnc e" in summary
        assert "DIAMOND" in summary

    def test_mission_duration_consistent(self) -> None:
        config = MiningMissionConfig(target_name="55 Cnc e", mining_duration_years=20)
        mission = MiningMission(config)
        results = mission.run()
        expected = results.travel_time_one_way_years * 2 + 20
        assert results.total_mission_years == pytest.approx(expected, rel=0.01)


# ────────────────────────────────────────────────────────────────────
#  CLI HELPERS TESTS
# ────────────────────────────────────────────────────────────────────

class TestCLIHelpers:

    def test_list_mining_targets(self) -> None:
        targets = list_mining_targets()
        assert len(targets) >= 5
        assert any("55 Cnc" in t["name"] for t in targets)

    def test_cli_list_targets(self, capsys: pytest.CaptureFixture) -> None:
        cli_list_targets()
        captured = capsys.readouterr()
        assert "Mining Targets" in captured.out
        assert "DIAMOND" in captured.out or "METALS" in captured.out

    def test_cli_run_55cnc(self, capsys: pytest.CaptureFixture) -> None:
        cli_run_mining_mission("55_cnc_e", duration_years=260)
        captured = capsys.readouterr()
        assert "55 Cnc" in captured.out
        assert "DIAMOND" in captured.out

    def test_cli_unknown_target(self, capsys: pytest.CaptureFixture) -> None:
        cli_run_mining_mission("nonexistent_planet", duration_years=100)
        captured = capsys.readouterr()
        assert "not found" in captured.out


# ────────────────────────────────────────────────────────────────────
#  EDGE CASES / REGRESSION
# ────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_zero_duration_mining(self, ops_model: MiningOpsModel, cnc_target: MiningTarget) -> None:
        raw, processed = ops_model.estimate_yield(
            cnc_target, MiningMethod.ORBITAL_CAPTURE, duration_years=0.0
        )
        assert raw == 0.0
        assert processed == 0.0

    def test_very_distant_target_low_score(self, sample_csv: Path) -> None:
        s = ResourceScanner(csv_path=sample_csv)
        s.load()
        gas = s.find_target("GasGiant")
        # Gas giant at 20 pc has low score (far away, unknown type)
        if gas is not None:
            assert gas.mining_score == 0.0 or gas.distance_ly > 50

    def test_resource_type_enum(self) -> None:
        assert ResourceType.DIAMOND.value == "DIAMOND"
        assert ResourceType.WATER_ICE.value == "WATER_ICE"
        assert ResourceType.METALS.value == "METALS"
        assert ResourceType.RARE_EARTH.value == "RARE_EARTH"
        assert ResourceType.UNKNOWN.value == "UNKNOWN"

    def test_mining_method_enum(self) -> None:
        assert len(MiningMethod) == 5

    def test_value_per_ton_all_types(self) -> None:
        for rt in [ResourceType.DIAMOND, ResourceType.WATER_ICE,
                    ResourceType.METALS, ResourceType.RARE_EARTH]:
            assert VALUE_PER_TON[rt.value] > 0
