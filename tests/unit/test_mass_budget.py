"""Tests for ship mass budget computation."""

from aria.digital_twin.mass_budget import compute_mass_budget, MassBudget


class TestMassBudget:
    def test_budget_has_items(self):
        budget = compute_mass_budget()
        assert len(budget.items) > 10

    def test_total_mass_positive(self):
        budget = compute_mass_budget()
        assert budget.total_mass_kg > 0

    def test_all_items_have_source(self):
        budget = compute_mass_budget()
        for item in budget.items:
            assert len(item.source) > 5, f"{item.name} missing source"

    def test_structure_is_significant(self):
        budget = compute_mass_budget()
        struct = sum(i.mass_kg for i in budget.items if i.subsystem == "structure")
        assert struct > 1e6  # > 1000 tonnes

    def test_habitat_ring_is_significant(self):
        """Habitat ring (torus + spokes + interior) should be a major mass
        contributor. After 7dafeea fixed solid→hollow spokes, the ring
        dropped from 54 Mt to ~20 Mt — the hull structure (23 Mt at 80 mm
        Ti-6Al-4V wall) is now heavier. The old assertion 'ring > struct'
        was only true because of the 50× solid-spoke bug."""
        budget = compute_mass_budget()
        habitat = sum(i.mass_kg for i in budget.items if i.subsystem == "habitat_ring")
        total = budget.total_mass_kg
        # Ring should be at least 15% of total (it's ~31% at defaults)
        assert habitat / total > 0.15, (
            f"Habitat ring mass {habitat:,.0f} kg is only "
            f"{habitat/total*100:.1f}% of total — unexpectedly small"
        )

    def test_propellant_included(self):
        budget = compute_mass_budget()
        fuel = sum(i.mass_kg for i in budget.items if i.subsystem == "propellant")
        assert fuel > 0

    def test_summary_string(self):
        budget = compute_mass_budget()
        s = budget.summary()
        assert "TOTAL" in s
        assert "Config target" in s

    def test_discrepancy_computed(self):
        budget = compute_mass_budget()
        assert budget.discrepancy_pct != 0  # Should differ from config
