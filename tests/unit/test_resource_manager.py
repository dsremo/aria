"""Tests for aria.resource.manager — inventory tracking and forecasting."""

import math
import pytest

from aria.resource.manager import (
    INTERSTELLAR_RESOURCES,
    Resource,
    ResourceForecaster,
    ResourceInventory,
)


# -- helpers ---------------------------------------------------------------

def _make_inventory() -> ResourceInventory:
    """Small deterministic inventory for unit tests."""
    return ResourceInventory([
        Resource("fuel", 1000.0, consumption_rate_per_day=10.0, critical_threshold_kg=100.0),
        Resource("water", 500.0, consumption_rate_per_day=5.0, critical_threshold_kg=50.0,
                 can_be_recycled=True, recycling_efficiency=0.90),
        Resource("food", 300.0, consumption_rate_per_day=3.0, critical_threshold_kg=30.0),
    ])


# -- Resource dataclass ----------------------------------------------------

class TestResource:
    def test_negative_quantity_raises(self):
        with pytest.raises(ValueError, match="quantity_kg cannot be negative"):
            Resource("x", -1.0)

    def test_bad_recycling_efficiency_raises(self):
        with pytest.raises(ValueError, match="recycling_efficiency"):
            Resource("x", 10.0, recycling_efficiency=1.5)


# -- ResourceInventory -----------------------------------------------------

class TestResourceInventory:
    def test_consume_reduces_quantity(self):
        inv = _make_inventory()
        consumed = inv.consume("fuel", 200.0)
        assert consumed == 200.0
        r = [r for r in inv.get_all_resources() if r.name == "fuel"][0]
        assert r.quantity_kg == pytest.approx(800.0)

    def test_consume_clamps_to_available(self):
        inv = _make_inventory()
        consumed = inv.consume("food", 9999.0)
        assert consumed == pytest.approx(300.0)
        r = [r for r in inv.get_all_resources() if r.name == "food"][0]
        assert r.quantity_kg == pytest.approx(0.0)

    def test_consume_unknown_raises(self):
        inv = _make_inventory()
        with pytest.raises(KeyError, match="Unknown resource"):
            inv.consume("unobtanium", 1.0)

    def test_produce_increases_quantity(self):
        inv = _make_inventory()
        inv.produce("water", 100.0)
        r = [r for r in inv.get_all_resources() if r.name == "water"][0]
        assert r.quantity_kg == pytest.approx(600.0)

    def test_days_remaining_no_recycling(self):
        inv = _make_inventory()
        # fuel: 1000 / 10 = 100 days
        assert inv.get_days_remaining("fuel") == pytest.approx(100.0)

    def test_days_remaining_with_recycling(self):
        inv = _make_inventory()
        # water: 500 / (5 * 0.10) = 1000 days
        assert inv.get_days_remaining("water") == pytest.approx(1000.0)

    def test_days_remaining_zero_rate(self):
        inv = ResourceInventory([Resource("ore", 100.0, consumption_rate_per_day=0.0)])
        assert inv.get_days_remaining("ore") == float("inf")

    def test_get_critical_resources(self):
        inv = _make_inventory()
        inv.consume("fuel", 950.0)  # 50 left, threshold 100 -> critical
        critical = inv.get_critical_resources()
        names = [r.name for r in critical]
        assert "fuel" in names
        assert "water" not in names

    def test_get_all_resources_length(self):
        inv = _make_inventory()
        assert len(inv.get_all_resources()) == 3


# -- ResourceForecaster ----------------------------------------------------

class TestResourceForecaster:
    def test_predict_depletion(self):
        inv = _make_inventory()
        depletion = ResourceForecaster.predict_depletion(inv)
        assert depletion["fuel"] == pytest.approx(100.0)
        assert depletion["water"] == pytest.approx(1000.0)
        assert depletion["food"] == pytest.approx(100.0)

    def test_get_critical_in_days(self):
        inv = _make_inventory()
        # After 95 days: fuel = 1000 - 10*95 = 50 (< 100 threshold) -> critical
        #                food = 300 - 3*95 = 15 (< 30 threshold) -> critical
        #                water = 500 - 0.5*95 = 452.5 (> 50) -> safe
        critical = ResourceForecaster.get_critical_in_days(inv, 95)
        names = [r.name for r in critical]
        assert "fuel" in names
        assert "food" in names
        assert "water" not in names


# -- INTERSTELLAR_RESOURCES preset -----------------------------------------

class TestInterstellarResources:
    def test_has_all_six(self):
        names = {r.name for r in INTERSTELLAR_RESOURCES}
        assert names == {"fuel", "water", "food", "metals", "chemicals", "spare_parts"}

    def test_inventory_loads(self):
        inv = ResourceInventory(INTERSTELLAR_RESOURCES)
        assert len(inv.get_all_resources()) == 6
