"""Tests for aria.digital_twin.tools_inventory — crew tool and equipment catalog.

Covers:
  - Clean import and ToolItem construction
  - Inventory is non-empty with expected categories
  - Total mass computation
  - Category grouping completeness
  - Non-replaceable and power-consumer filters
  - Summary statistics
"""

from __future__ import annotations

import pytest

from aria.digital_twin.tools_inventory import (
    TOOL_INVENTORY,
    ToolItem,
    get_by_category,
    get_inventory,
    get_non_replaceable,
    get_power_consumers,
    get_summary,
    get_total_mass_kg,
)


class TestToolItem:
    """ToolItem dataclass basics."""

    def test_construction(self):
        item = ToolItem(
            name="Test wrench",
            category="hand_tools",
            subcategory="wrenches",
            quantity=5,
            mass_kg=1.5,
        )
        assert item.name == "Test wrench"
        assert item.quantity == 5
        assert item.mass_kg == 1.5
        assert item.power_watts == 0
        assert item.replaceable is True

    def test_frozen_immutability(self):
        item = ToolItem("x", "y", "z", 1, 1.0)
        with pytest.raises(AttributeError):
            item.name = "changed"


class TestInventoryCatalog:
    """The global TOOL_INVENTORY list."""

    def test_inventory_is_nonempty(self):
        assert len(TOOL_INVENTORY) > 50

    def test_get_inventory_returns_copy(self):
        inv = get_inventory()
        assert len(inv) == len(TOOL_INVENTORY)
        # Modifying the copy should not affect the original
        inv.pop()
        assert len(inv) == len(TOOL_INVENTORY) - 1
        assert len(get_inventory()) == len(TOOL_INVENTORY)

    def test_all_items_have_positive_mass(self):
        for item in TOOL_INVENTORY:
            assert item.mass_kg > 0, f"{item.name} has non-positive mass"

    def test_all_items_have_positive_quantity(self):
        for item in TOOL_INVENTORY:
            assert item.quantity > 0, f"{item.name} has non-positive quantity"


class TestTotalMass:
    """Total mass computation."""

    def test_total_mass_is_positive(self):
        mass = get_total_mass_kg()
        assert mass > 0

    def test_total_mass_is_sum_of_qty_times_unit_mass(self):
        expected = sum(t.mass_kg * t.quantity for t in TOOL_INVENTORY)
        assert abs(get_total_mass_kg() - expected) < 1e-6


class TestCategoryGrouping:
    """Grouping tools by category."""

    def test_by_category_covers_all_items(self):
        by_cat = get_by_category()
        total_in_cats = sum(len(items) for items in by_cat.values())
        assert total_in_cats == len(TOOL_INVENTORY)

    def test_expected_categories_present(self):
        by_cat = get_by_category()
        expected = {"hand_tools", "power_tools", "measurement", "welding", "safety", "medical"}
        for cat in expected:
            assert cat in by_cat, f"Missing expected category: {cat}"


class TestFilters:
    """Non-replaceable items and power consumers."""

    def test_non_replaceable_items_exist(self):
        non_rep = get_non_replaceable()
        assert len(non_rep) > 0
        assert all(not item.replaceable for item in non_rep)

    def test_power_consumers_have_positive_watts(self):
        powered = get_power_consumers()
        assert len(powered) > 0
        assert all(item.power_watts > 0 for item in powered)

    def test_non_replaceable_is_subset_of_inventory(self):
        non_rep_names = {item.name for item in get_non_replaceable()}
        all_names = {item.name for item in TOOL_INVENTORY}
        assert non_rep_names.issubset(all_names)


class TestSummary:
    """Summary statistics."""

    def test_summary_keys(self):
        s = get_summary()
        assert isinstance(s, dict)
        expected_keys = {
            "total_items", "unique_types", "total_mass_kg",
            "categories", "non_replaceable_count", "max_power_consumer_w",
        }
        assert expected_keys.issubset(s.keys())

    def test_summary_values_are_consistent(self):
        s = get_summary()
        assert s["unique_types"] == len(TOOL_INVENTORY)
        assert s["total_items"] == sum(t.quantity for t in TOOL_INVENTORY)
        assert s["total_mass_kg"] == get_total_mass_kg()
        assert s["non_replaceable_count"] == len(get_non_replaceable())
        assert s["max_power_consumer_w"] == max(t.power_watts for t in TOOL_INVENTORY)
