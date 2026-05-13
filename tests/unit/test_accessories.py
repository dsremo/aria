"""Tests for ship geometry accessories, CoM computation, and habitat decks.

Covers antenna arrays, escape pods, viewports, centre-of-mass estimation,
and habitat ring deck layout.
"""

from __future__ import annotations

import math

import pytest

from aria.digital_twin.parameters import ShipParameters


@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


@pytest.fixture
def small_params() -> ShipParameters:
    """Small ship for fast CAD operations in tests."""
    return ShipParameters(
        hull_wall_thickness_m=0.5,
        hull_length_m=20.0,
        ship_mass_kg=1e6,
        ship_cross_section_m2=50.0,
    )


# ── Antenna array ───────────────────────────────────────────────────────


class TestAntennaArray:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_antenna_array_creates_4_dishes(self, small_params):
        from aria.digital_twin.geometry.accessories import create_antenna_array
        assy = create_antenna_array(small_params)
        assert len(assy.children) == 4

    def test_antenna_dishes_named(self, small_params):
        from aria.digital_twin.geometry.accessories import create_antenna_array
        assy = create_antenna_array(small_params)
        names = [child.name for child in assy.children]
        for i in range(4):
            assert f"antenna_{i:02d}" in names


# ── Escape pods ─────────────────────────────────────────────────────────


class TestEscapePods:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_escape_pods_created(self, small_params):
        from aria.digital_twin.geometry.accessories import create_escape_pods
        assy = create_escape_pods(small_params, n_pods=4)
        assert assy is not None
        assert len(assy.children) == 4

    def test_escape_pods_named(self, small_params):
        from aria.digital_twin.geometry.accessories import create_escape_pods
        assy = create_escape_pods(small_params, n_pods=4)
        names = [child.name for child in assy.children]
        assert "escape_pod_00" in names
        assert "escape_pod_03" in names


# ── Viewports ───────────────────────────────────────────────────────────


class TestViewports:
    @pytest.fixture(autouse=True)
    def _import_cq(self):
        pytest.importorskip("cadquery")

    def test_viewports_are_holes(self, small_params):
        """Viewports should be thin cylinders (cutout volumes), not glass."""
        from aria.digital_twin.geometry.accessories import create_viewports
        assy = create_viewports(small_params, n_ports=8)
        assert len(assy.children) == 8

    def test_viewport_count_configurable(self, small_params):
        from aria.digital_twin.geometry.accessories import create_viewports
        assy = create_viewports(small_params, n_ports=4)
        assert len(assy.children) == 4


# ── Centre of mass ──────────────────────────────────────────────────────


class TestCenterOfMass:
    def test_com_within_hull_bounds(self, params):
        from aria.digital_twin.geometry.assembly import compute_center_of_mass
        result = compute_center_of_mass(params)
        assert 0.0 <= result["z_com_m"] <= params.hull_length_m

    def test_com_on_thrust_axis(self, params):
        from aria.digital_twin.geometry.assembly import compute_center_of_mass
        result = compute_center_of_mass(params)
        assert result["on_thrust_axis"] is True

    def test_com_returns_offset(self, params):
        from aria.digital_twin.geometry.assembly import compute_center_of_mass
        result = compute_center_of_mass(params)
        assert "offset_m" in result
        # Offset should be finite
        assert math.isfinite(result["offset_m"])


# ── Habitat decks ──────────────────────────────────────────────────────


class TestHabitatDecks:
    def test_13_decks(self, params):
        from aria.digital_twin.geometry.habitat_ring import get_habitat_decks
        decks = get_habitat_decks(params)
        assert len(decks) == 13

    def test_deck_floor_areas_positive(self, params):
        from aria.digital_twin.geometry.habitat_ring import get_habitat_decks
        decks = get_habitat_decks(params)
        for deck in decks:
            assert deck["floor_area_m2"] > 0.0, (
                f"Deck {deck['deck_number']} has non-positive floor area"
            )

    def test_deck_purposes_assigned(self, params):
        from aria.digital_twin.geometry.habitat_ring import get_habitat_decks
        decks = get_habitat_decks(params)
        for deck in decks:
            assert deck["purpose"] != "unassigned", (
                f"Deck {deck['deck_number']} has no purpose"
            )

    def test_deck_numbers_sequential(self, params):
        from aria.digital_twin.geometry.habitat_ring import get_habitat_decks
        decks = get_habitat_decks(params)
        numbers = [d["deck_number"] for d in decks]
        assert numbers == list(range(1, 14))
