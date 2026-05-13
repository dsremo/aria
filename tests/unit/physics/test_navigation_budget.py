"""Unit tests for the navigation-budget bridge module."""

from __future__ import annotations

import math

import pytest

from aria.physics.navigation_budget import (
    MissionProfile,
    NavigationBudget,
    build_navigation_budget,
    mars_transit_profile,
    proxima_cruise_profile,
)


def test_mission_profile_rejects_nonpositive_mass():
    with pytest.raises(ValueError):
        MissionProfile(
            name="bad",
            ship_mass_kg=0.0,
            cross_section_m2=1.0,
            cruise_velocity_m_s=1.0,
            leg_distance_m=1.0,
        )


def test_mission_profile_transit_time_finite():
    p = MissionProfile(
        name="t",
        ship_mass_kg=1.0e6,
        cross_section_m2=100.0,
        cruise_velocity_m_s=1.0e4,
        leg_distance_m=1.0e10,
    )
    assert p.transit_time_s == pytest.approx(1.0e6)


def test_mission_profile_transit_time_infinite_at_rest():
    p = MissionProfile(
        name="rest",
        ship_mass_kg=1.0e6,
        cross_section_m2=100.0,
        cruise_velocity_m_s=0.0,
        leg_distance_m=1.0e10,
    )
    assert math.isinf(p.transit_time_s)


def test_mars_factory_matches_1_5_au():
    p = mars_transit_profile()
    au = 1.495978707e11
    assert p.leg_distance_m == pytest.approx(1.5 * au)
    assert p.is_intergalactic is False


def test_proxima_factory_matches_4_244_ly_at_0_1c():
    p = proxima_cruise_profile()
    ly = 9.4607304725808e15
    assert p.leg_distance_m == pytest.approx(4.244 * ly)
    assert p.cruise_velocity_m_s == pytest.approx(0.1 * 299792458.0)


def test_build_budget_mars_transit_structure():
    profile = mars_transit_profile()
    budget = build_navigation_budget(profile)
    assert isinstance(budget, NavigationBudget)
    assert len(budget.rows) == 3  # no Λ row for interplanetary
    assert budget.total_position_error_m >= 0.0
    assert budget.stopping_length_m > 0.0
    # Units consistency
    for row in budget.rows:
        assert row.units == "m"


def test_build_budget_intergalactic_includes_lambda_row():
    profile = MissionProfile(
        name="intergalactic test",
        ship_mass_kg=1.0e6,
        cross_section_m2=300.0,
        cruise_velocity_m_s=1.0e5,
        leg_distance_m=3.086e22 * 10.0,  # 10 Mpc
        is_intergalactic=True,
    )
    budget = build_navigation_budget(profile)
    assert len(budget.rows) == 4
    names = {row.name for row in budget.rows}
    assert "Lambda_cosmological" in names


def test_quadrature_total_matches_euclidean_norm():
    profile = proxima_cruise_profile()
    budget = build_navigation_budget(profile)
    expected = math.sqrt(
        sum(row.perturbation_value ** 2 for row in budget.rows)
    )
    assert budget.total_position_error_m == pytest.approx(expected, rel=1.0e-12)


def test_proxima_budget_dominated_by_ism_ram_drag():
    """At 0.1 c in the LIC, ISM ram drag should dominate the M1 DM
    upper bound by many orders of magnitude — confirming the
    bookkeeping role of the dark-sector row."""
    profile = proxima_cruise_profile()
    budget = build_navigation_budget(profile)
    by_name = {r.name: r.perturbation_value for r in budget.rows}
    assert by_name["ISM_ram_LIC"] > by_name["DM_drag_XENONnT_30GeV"] * 1.0e6


def test_mars_cruise_not_drag_limited():
    """Stopping length for a 1e6 kg ship with 100 m² cross section
    in LIC gas is ~10²³ m, vastly larger than the 1.5 AU Mars leg,
    so `is_drag_limited` must be False."""
    profile = mars_transit_profile()
    budget = build_navigation_budget(profile)
    assert budget.is_drag_limited is False
    assert budget.stopping_length_m > profile.leg_distance_m * 1.0e9
