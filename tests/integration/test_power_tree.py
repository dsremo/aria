from __future__ import annotations

import math

import pytest

from aria.physics.eps.li_ion_cells import LiIonCell, VES180
from aria.physics.eps.solar_cells import SolarCell, XTJ_PRIME
from aria.physics.eps.power_tree import (
    BatteryPack,
    LoadGroup,
    LoadSheddingPolicy,
    MpptStage,
    PowerTree,
    SolarArray,
    simulate_leo_orbit,
)
from aria.physics.eps.iss_validation import (
    ISS_PUBLISHED_NOMINAL_GENERATION_KW,
    ISS_PUBLISHED_PEAK_GENERATION_KW,
    validate_against_iss_published_numbers,
)


def _build_iss_like_array() -> SolarArray:
    return SolarArray(
        cells_in_series=82,
        cells_in_parallel=400,
        cell=XTJ_PRIME,
        pointing_efficiency=0.95,
        harness_efficiency=0.96,
        degradation_factor=0.90,
    )


def _build_battery() -> BatteryPack:
    return BatteryPack(
        cell=VES180, cells_in_series=82, parallel_strings=24,
        soc_fraction=1.0, temperature_c=20.0,
    )


class TestPowerTreeStep:
    def test_sun_charges_battery(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(efficiency=0.96),
            battery=_build_battery(),
        )
        tree.battery.soc_fraction = 0.5
        snap = tree.step(
            irradiance_w_m2=1361.0, cell_temp_k=320.0,
            load_demand_w=20000.0, dt_s=60.0,
        )
        assert snap.battery_charge_w > 0
        assert snap.battery_discharge_w == 0
        assert tree.battery.soc_fraction > 0.5

    def test_eclipse_discharges_battery(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(),
            battery=_build_battery(),
        )
        tree.battery.soc_fraction = 0.8
        snap = tree.step(
            irradiance_w_m2=1361.0, cell_temp_k=263.0,
            load_demand_w=80000.0, dt_s=60.0, eclipse=True,
        )
        assert snap.array_dc_w == 0
        assert snap.battery_discharge_w > 0
        assert tree.battery.soc_fraction < 0.8

    def test_negative_load_rejected(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(), battery=_build_battery(),
        )
        with pytest.raises(ValueError, match="non-negative"):
            tree.step(
                irradiance_w_m2=1361.0, cell_temp_k=320.0,
                load_demand_w=-1.0, dt_s=60.0,
            )


class TestLoadShedding:
    def test_priority_order_respected(self):
        policy = LoadSheddingPolicy(groups=(
            LoadGroup("life_support", nominal_w=10000.0, priority=1),
            LoadGroup("attitude", nominal_w=5000.0, priority=2),
            LoadGroup("comms", nominal_w=2000.0, priority=3),
            LoadGroup("experiments", nominal_w=20000.0, priority=4),
        ))
        result = policy.shed_to_budget(available_w=15000.0)
        result_dict = dict(result)
        assert result_dict["life_support"] == 10000.0
        assert result_dict["attitude"] == 5000.0
        assert result_dict["comms"] == 0.0
        assert result_dict["experiments"] == 0.0

    def test_full_budget_satisfies_all(self):
        policy = LoadSheddingPolicy(groups=(
            LoadGroup("a", nominal_w=100.0, priority=1),
            LoadGroup("b", nominal_w=50.0, priority=2),
        ))
        result = dict(policy.shed_to_budget(available_w=200.0))
        assert result["a"] == 100.0
        assert result["b"] == 50.0


class TestLeoOrbitSim:
    def test_one_orbit_runs(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(),
            battery=_build_battery(),
        )
        snapshots = simulate_leo_orbit(
            tree, n_orbits=1, base_load_w=84_000.0, sample_period_s=60.0,
        )
        assert len(snapshots) > 50
        eclipse_snaps = [snap for snap in snapshots if snap.eclipse]
        sunlit_snaps = [snap for snap in snapshots if not snap.eclipse]
        assert sunlit_snaps and eclipse_snaps

    def test_one_wing_generation_in_envelope(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(),
            battery=_build_battery(),
        )
        snapshots = simulate_leo_orbit(
            tree, n_orbits=2, base_load_w=84_000.0, sample_period_s=60.0,
        )
        sunlit = [snap.array_dc_w for snap in snapshots if not snap.eclipse]
        assert sunlit
        peak_w = max(sunlit)
        peak_kw = peak_w / 1000.0
        assert 15.0 <= peak_kw <= 45.0, (
            f"peak per-wing generation {peak_kw:.1f} kW outside expected band "
            "(15..45 kW for one wing-equivalent of XTJ-Prime cells; ISS uses 8 wings)"
        )


class TestIssValidation:
    def test_within_tolerance_when_reasonable(self):
        report = validate_against_iss_published_numbers(
            measured_avg_generation_kw=ISS_PUBLISHED_NOMINAL_GENERATION_KW * 1.10,
            measured_peak_generation_kw=ISS_PUBLISHED_PEAK_GENERATION_KW * 0.90,
            measured_battery_total_kwh=224.0 * 1.05,
            measured_eclipse_fraction=0.36,
        )
        assert report.overall_within_tolerance

    def test_out_of_tolerance_when_off(self):
        report = validate_against_iss_published_numbers(
            measured_avg_generation_kw=10.0,
            measured_peak_generation_kw=20.0,
            measured_battery_total_kwh=5.0,
            measured_eclipse_fraction=0.10,
        )
        assert not report.overall_within_tolerance

    def test_report_dict_structure(self):
        report = validate_against_iss_published_numbers(
            measured_avg_generation_kw=95.0,
            measured_peak_generation_kw=240.0,
            measured_battery_total_kwh=224.0,
            measured_eclipse_fraction=0.36,
        )
        payload = report.as_dict()
        assert "deltas" in payload
        assert any(d["parameter"] == "avg_generation" for d in payload["deltas"])

    def test_eight_wings_validates_against_iss(self):
        tree = PowerTree(
            array=_build_iss_like_array(),
            mppt=MpptStage(),
            battery=_build_battery(),
        )
        snapshots = simulate_leo_orbit(
            tree, n_orbits=2, base_load_w=84_000.0, sample_period_s=60.0,
        )
        sunlit = [snap.array_dc_w for snap in snapshots if not snap.eclipse]
        per_wing_avg_kw = sum(sunlit) / max(1, len(sunlit)) / 1000.0
        per_wing_peak_kw = max(sunlit) / 1000.0
        full_iss_avg_kw = per_wing_avg_kw * 8.0
        full_iss_peak_kw = per_wing_peak_kw * 8.0
        report = validate_against_iss_published_numbers(
            measured_avg_generation_kw=full_iss_avg_kw,
            measured_peak_generation_kw=full_iss_peak_kw,
            measured_battery_total_kwh=224.0,
            measured_eclipse_fraction=0.36,
            tolerance_pct=50.0,
        )
        assert report.deltas
        within = sum(1 for d in report.deltas if d.within_tolerance)
        assert within >= 3, (
            f"only {within}/{len(report.deltas)} deltas in tolerance: "
            + "; ".join(
                f"{d.parameter}: {d.measured_value:.1f}{d.units} vs "
                f"{d.published_value}{d.units} ({d.relative_error_pct:.0f}%)"
                for d in report.deltas
            )
        )
