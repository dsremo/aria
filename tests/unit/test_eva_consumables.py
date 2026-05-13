"""EVA consumables model tests."""

from __future__ import annotations

import pytest

from aria.simulation.eva_consumables import (
    SuitConfig, simulate_eva, apollo_11_eva_1, artemis_3_eva_sv,
)


def test_apollo_11_duration_matches_historical():
    """Apollo 11 EVA was 2h 31m (2.52 h). Our simulator within ±30 min."""
    r = apollo_11_eva_1()
    assert 1.8 < r.total_duration_h < 3.0


def test_xemu_full_6h_with_margin():
    """xEMU is designed for a nominal 6-hour EVA with 2 h reserve."""
    r = artemis_3_eva_sv()
    assert r.total_duration_h > 5.5
    # Should still have some margin (nominal 6h EVA leaves ≥1h of consumables)
    assert r.time_remaining_h > 1.0


def test_abort_recommended_when_binding_low():
    """Forcing low initial O₂ should trip the abort recommendation."""
    cfg = SuitConfig(o2_kg=0.10, battery_wh=500, co2_scrubber_capacity_kg=0.5,
                     cooling_water_kg=2.0, abort_margin_h=0.5)
    r = simulate_eva(cfg, [(2.0, "moderate")])
    assert r.abort_recommended
    assert r.binding_consumable in ("o2", "battery", "co2", "cooling")


def test_rest_activity_uses_less_than_heavy():
    """Resting for 1h should burn fewer consumables than heavy work for 1h."""
    cfg1 = SuitConfig()
    cfg2 = SuitConfig()
    rest = simulate_eva(cfg1, [(1.0, "rest")])
    heavy = simulate_eva(cfg2, [(1.0, "heavy")])
    assert rest.states[-1].o2_kg > heavy.states[-1].o2_kg
    assert rest.states[-1].cooling_water_kg > heavy.states[-1].cooling_water_kg


def test_all_consumables_monotonically_decreasing():
    """O₂, battery, cooling water must only decrease. CO₂ must only increase."""
    r = artemis_3_eva_sv()
    for prev, cur in zip(r.states, r.states[1:]):
        assert cur.o2_kg <= prev.o2_kg + 1e-9
        assert cur.battery_wh <= prev.battery_wh + 1e-9
        assert cur.cooling_water_kg <= prev.cooling_water_kg + 1e-9
        assert cur.co2_scrubbed_kg >= prev.co2_scrubbed_kg - 1e-9


def test_no_consumable_goes_negative():
    r = artemis_3_eva_sv()
    for s in r.states:
        assert s.o2_kg >= 0
        assert s.battery_wh >= 0
        assert s.cooling_water_kg >= 0
        assert s.co2_scrubbed_kg >= 0


def test_time_remaining_finite_and_nonneg():
    r = apollo_11_eva_1()
    assert r.time_remaining_h is not None and r.time_remaining_h >= 0
