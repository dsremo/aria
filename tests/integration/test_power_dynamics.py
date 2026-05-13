from __future__ import annotations

import pytest

from aria.physics.eps.power_dynamics import (
    BatteryAgingModel,
    BmsImbalance,
    CellThermalNode,
    MpptController,
    PlasmaLatchupSimulator,
)


class TestCellThermal:
    def test_warms_under_load(self):
        node = CellThermalNode(cell_temp_k=293.15, sink_temp_k=293.15)
        for _ in range(60):
            node.step(joule_heat_w=20.0, irradiance_w_m2=0.0, dt_s=1.0)
        assert node.cell_temp_k > 293.15

    def test_cools_in_eclipse(self):
        node = CellThermalNode(cell_temp_k=320.0, sink_temp_k=200.0)
        for _ in range(60):
            node.step(joule_heat_w=0.0, irradiance_w_m2=0.0, dt_s=1.0)
        assert node.cell_temp_k < 320.0


class TestMpptController:
    def test_perturb_and_observe_climbs(self):
        controller = MpptController(duty_cycle=0.30)
        powers = [10.0, 12.0, 14.0, 13.0, 11.0]
        for power in powers:
            controller.update(current_power_w=power)
        assert 0.10 <= controller.duty_cycle <= 0.90

    def test_transfer_efficiency_drops_at_extreme_duty(self):
        c1 = MpptController(duty_cycle=0.50)
        c2 = MpptController(duty_cycle=0.10)
        e1 = c1.transfer(source_w=100.0)
        e2 = c2.transfer(source_w=100.0)
        assert e1 > e2


class TestBmsImbalance:
    def test_cells_have_spread(self):
        bms = BmsImbalance(n_cells=82, base_capacity_ah=50.0)
        assert bms.weakest_cell_capacity_ah() < bms.strongest_cell_capacity_ah()
        ratio = bms.imbalance_ratio()
        assert 0 < ratio < 0.20

    def test_aging_reduces_capacity(self):
        bms = BmsImbalance(n_cells=10, base_capacity_ah=50.0)
        before = sum(bms.cell_capacities_ah)
        bms.step_age(equivalent_full_cycles=100.0, dt_days=30.0)
        after = sum(bms.cell_capacities_ah)
        assert after < before


class TestAging:
    def test_capacity_fades_over_cycles(self):
        model = BatteryAgingModel()
        before = model.capacity_fade_factor
        model.step(equivalent_full_cycles=1000.0, dt_days=365.0, temperature_c=25.0)
        after = model.capacity_fade_factor
        assert after < before
        assert after > 0.6

    def test_high_temp_accelerates_aging(self):
        cool = BatteryAgingModel()
        warm = BatteryAgingModel()
        cool.step(equivalent_full_cycles=0.0, dt_days=365.0, temperature_c=10.0)
        warm.step(equivalent_full_cycles=0.0, dt_days=365.0, temperature_c=45.0)
        assert warm.capacity_fade_factor < cool.capacity_fade_factor


class TestPlasmaLatchup:
    def test_baseline_rare(self):
        sim = PlasmaLatchupSimulator(rng_seed=42)
        events = []
        for _ in range(1000):
            event = sim.step(dt_s=60.0, in_saa=False, spe_active=False)
            if event is not None:
                events.append(event)
        assert len(events) <= 5

    def test_spe_increases_rate(self):
        sim_quiet = PlasmaLatchupSimulator(rng_seed=7)
        sim_spe = PlasmaLatchupSimulator(rng_seed=7)
        events_quiet = sum(
            1 for _ in range(2000)
            if sim_quiet.step(dt_s=3600.0, spe_active=False) is not None
        )
        events_spe = sum(
            1 for _ in range(2000)
            if sim_spe.step(dt_s=3600.0, spe_active=True) is not None
        )
        assert events_spe > events_quiet
