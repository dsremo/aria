"""Tests for the spacecraft component database and assembly interfaces.

Covers data integrity, query functions, fastener mass budgets,
and interface consistency.
"""

from __future__ import annotations

import pytest

from aria.digital_twin.components_db import (
    COMPONENT_DATABASE,
    Component,
    get_category_summary,
    get_component,
    get_components_by_category,
    get_components_by_subcategory,
    total_unique_components,
)
from aria.digital_twin.assembly_interfaces import (
    SHIP_INTERFACES,
    InterfaceSpec,
    get_fastener_count,
    get_interface_by_name,
    get_interfaces_for_part,
    get_seal_count,
    get_total_fastener_mass_kg,
    get_total_seal_mass_kg,
)


# ── Component Database Tests ─────────────────────────────────────────────

class TestComponentDatabase:
    """Validate component data integrity and query helpers."""

    def test_database_not_empty(self):
        assert len(COMPONENT_DATABASE) > 0

    def test_minimum_component_count(self):
        """At least 100 unique component types should exist."""
        assert total_unique_components() >= 100

    def test_all_categories_present(self):
        """Every expected top-level category must have entries."""
        expected = {
            "fasteners", "seals", "bearings", "actuators",
            "valves", "electrical", "sensors", "pipes",
        }
        actual = set(get_category_summary().keys())
        assert expected.issubset(actual), f"Missing categories: {expected - actual}"

    def test_no_zero_mass(self):
        """Every component must have a positive mass."""
        for pn, comp in COMPONENT_DATABASE.items():
            assert comp.mass_g > 0, f"{pn} has non-positive mass"

    def test_no_zero_max_temp(self):
        """Every component must have a positive max operating temperature."""
        for pn, comp in COMPONENT_DATABASE.items():
            assert comp.max_operating_temp_k > 0, f"{pn} has non-positive max temp"

    def test_get_component_found(self):
        comp = get_component("ISO-4014-M10x60-8.8")
        assert comp.name == "Hex bolt M10x60 Grade 8.8"
        assert comp.category == "fasteners"

    def test_get_component_not_found(self):
        with pytest.raises(KeyError):
            get_component("NONEXISTENT-PART-999")

    def test_get_components_by_category_fasteners(self):
        fasteners = get_components_by_category("fasteners")
        assert len(fasteners) >= 20  # bolts + nuts + washers + rivets + studs + inserts

    def test_get_components_by_subcategory_bolt(self):
        bolts = get_components_by_subcategory("bolt")
        assert len(bolts) >= 10  # 5 sizes × 2 grades

    def test_bolt_proof_load_increases_with_diameter(self):
        """Proof load must increase monotonically with bolt diameter (same grade)."""
        grade_88_bolts = [
            c for c in get_components_by_subcategory("bolt")
            if c.extra.get("grade") == 8.8
        ]
        grade_88_bolts.sort(key=lambda c: c.key_dimensions["diameter_mm"])
        for i in range(1, len(grade_88_bolts)):
            assert (
                grade_88_bolts[i].extra["proof_load_kn"]
                > grade_88_bolts[i - 1].extra["proof_load_kn"]
            ), "Proof load must increase with diameter for same grade"

    def test_unique_part_numbers(self):
        """Part numbers must be unique (enforced at import, but verify)."""
        pns = [comp.part_number for comp in COMPONENT_DATABASE.values()]
        assert len(pns) == len(set(pns))

    def test_every_component_has_source(self):
        """Every component should have a non-empty source citation."""
        for pn, comp in COMPONENT_DATABASE.items():
            assert comp.source, f"{pn} is missing a source citation"

    def test_category_summary_counts(self):
        summary = get_category_summary()
        total = sum(summary.values())
        assert total == total_unique_components()


# ── Assembly Interface Tests ─────────────────────────────────────────────

class TestAssemblyInterfaces:
    """Validate interface definitions and analysis functions."""

    def test_minimum_interface_count(self):
        """At least 30 interfaces should be defined."""
        assert len(SHIP_INTERFACES) >= 30

    def test_all_interface_names_unique(self):
        names = [iface.joint_name for iface in SHIP_INTERFACES]
        assert len(names) == len(set(names)), "Duplicate interface joint names"

    def test_fastener_references_valid(self):
        """Every fastener_type must exist in COMPONENT_DATABASE."""
        for iface in SHIP_INTERFACES:
            if iface.fastener_type is not None:
                assert iface.fastener_type in COMPONENT_DATABASE, (
                    f"Interface {iface.joint_name} references unknown fastener "
                    f"{iface.fastener_type}"
                )

    def test_seal_references_valid(self):
        """Every seal_type must exist in COMPONENT_DATABASE."""
        for iface in SHIP_INTERFACES:
            if iface.seal_type is not None:
                assert iface.seal_type in COMPONENT_DATABASE, (
                    f"Interface {iface.joint_name} references unknown seal "
                    f"{iface.seal_type}"
                )

    def test_get_fastener_count_non_empty(self):
        counts = get_fastener_count()
        assert len(counts) > 0
        assert all(v > 0 for v in counts.values())

    def test_total_fastener_mass_positive(self):
        mass_kg = get_total_fastener_mass_kg()
        assert mass_kg > 0

    def test_total_fastener_mass_reasonable(self):
        """Total fastener mass should be between 50 kg and 50 000 kg for a ship."""
        mass_kg = get_total_fastener_mass_kg()
        assert 50.0 < mass_kg < 50000.0, f"Fastener mass {mass_kg:.1f} kg seems unreasonable"

    def test_get_interface_by_name(self):
        iface = get_interface_by_name("hull_fwd_to_main_bulkhead")
        assert iface.fastener_count == 120
        assert iface.connection_type == "bolted"

    def test_get_interface_by_name_not_found(self):
        with pytest.raises(KeyError):
            get_interface_by_name("nonexistent_joint")

    def test_get_interfaces_for_part(self):
        hull_interfaces = get_interfaces_for_part("Hull")
        assert len(hull_interfaces) >= 3  # hull appears in many joints

    def test_seal_count_non_empty(self):
        counts = get_seal_count()
        assert len(counts) > 0

    def test_total_seal_mass_positive(self):
        mass_kg = get_total_seal_mass_kg()
        assert mass_kg > 0

    def test_bolted_joints_have_torque(self):
        """Every bolted joint must specify a torque value."""
        for iface in SHIP_INTERFACES:
            if iface.connection_type == "bolted":
                assert iface.torque_spec_nm is not None and iface.torque_spec_nm > 0, (
                    f"Bolted joint {iface.joint_name} missing torque spec"
                )
