"""Scenario 1: 1000-year interstellar cruise through the Local
Interstellar Cloud.

Pulls primitives from four independent pods and confirms that the
combined navigation-budget error at arrival is dominated by the
expected source (ISM ram drag for a big blunt ship, Λ position
drift at intergalactic scale, DM upper bound for exotic channels):

  - cruise_drag.ram_pressure (ISM ram drag)
  - cruise_drag.dynamical_friction (Chandrasekhar)
  - dark_sector.dark_matter (XENONnT upper bound + Λ)
  - dark_sector.uncertainty_budget (shared quadrature)

Cross-pod invariants verified:
  1. The ISM ram deceleration is *larger* than the DM drag upper
     bound by many orders of magnitude — i.e. dark matter is not
     the dominant drag, matching the dark-sector bookkeeping role.
  2. The ISM stopping length is much longer than the transit length,
     so the cruise is not drag-limited.
  3. Λ position drift over a 100 Mpc leg is larger than the
     dynamical friction drift over an equal time — the bookkeeping
     budget is intergalactic-dominated at that scale.
  4. Rows fed into quadrature_sum_rows match the expected
     Euclidean-norm total within float tolerance.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.cruise_drag import (
    LOCAL_INTERSTELLAR_CLOUD,
    chandrasekhar_dynamical_friction_acceleration,
    ram_pressure_drag_acceleration,
    stopping_length_m,
)
from aria.physics.dark_sector import (
    MEGAPARSEC_M,
    UncertaintyBudgetRow,
    cosmological_lambda_acceleration,
    dark_matter_drag_upper_bound,
    propagate_position_uncertainty_m,
    quadrature_sum_rows,
)


# ──────────────────────────────────────────────────────────────────────
#  Mission scenario (frozen inputs for the regression)
# ──────────────────────────────────────────────────────────────────────

_SHIP_MASS_KG: float = 1.0e6
_SHIP_CROSS_SECTION_M2: float = 300.0
_CRUISE_VELOCITY_M_S: float = 1.0e5  # ≈ 100 km/s, slow interstellar
_MISSION_DURATION_S: float = 1000.0 * 365.25 * 86400.0  # 1000 yr
_INTERGALACTIC_LEG_M: float = 10.0 * MEGAPARSEC_M


# ──────────────────────────────────────────────────────────────────────
#  Cross-pod invariants
# ──────────────────────────────────────────────────────────────────────


def test_ism_ram_drag_dominates_dark_matter_upper_bound():
    """The actual ISM ram drag at cruise speed must exceed the
    XENONnT-consistent DM drag upper bound by at least 8 orders of
    magnitude — confirming that dark matter is a bookkeeping row,
    not a dynamical effect."""
    a_ram = ram_pressure_drag_acceleration(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        relative_velocity_m_s=_CRUISE_VELOCITY_M_S,
        cross_section_m2=_SHIP_CROSS_SECTION_M2,
        ship_mass_kg=_SHIP_MASS_KG,
    )
    a_dm = dark_matter_drag_upper_bound(
        ship_mass_kg=_SHIP_MASS_KG,
        ship_velocity_through_halo_m_s=_CRUISE_VELOCITY_M_S,
    )
    assert a_ram > 0.0
    assert a_dm >= 0.0
    assert a_ram / max(a_dm, 1.0e-300) > 1.0e8, (
        f"a_ram = {a_ram:.3e}, a_dm = {a_dm:.3e}"
    )


def test_cruise_not_drag_limited_over_mission():
    """Stopping length must be much longer than the distance
    travelled over the mission, so the cruise is not drag-limited."""
    l_stop = stopping_length_m(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        cross_section_m2=_SHIP_CROSS_SECTION_M2,
        ship_mass_kg=_SHIP_MASS_KG,
    )
    distance = _CRUISE_VELOCITY_M_S * _MISSION_DURATION_S
    assert l_stop > 1.0e3 * distance, (
        f"L_stop = {l_stop:.3e}, distance = {distance:.3e}"
    )


def test_dynamical_friction_sub_ram_drag_in_lic():
    """Inside the LIC, Chandrasekhar drag against baryonic gas is
    negligible compared to hydrodynamic ram drag (the gas is
    collisional, not collisionless, so Chandrasekhar drag is an
    upper bound that's always loose inside a neutral cloud)."""
    a_df = chandrasekhar_dynamical_friction_acceleration(
        ship_mass_kg=_SHIP_MASS_KG,
        velocity_m_s=_CRUISE_VELOCITY_M_S,
        background_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        velocity_dispersion_m_s=1.0e4,  # LIC thermal sound speed
    )
    a_ram = ram_pressure_drag_acceleration(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        relative_velocity_m_s=_CRUISE_VELOCITY_M_S,
        cross_section_m2=_SHIP_CROSS_SECTION_M2,
        ship_mass_kg=_SHIP_MASS_KG,
    )
    assert a_df < a_ram


def test_lambda_drift_dominates_nav_budget_at_intergalactic_scales():
    """At a 10 Mpc leg with a 1000-year transit, the Λ-induced
    position drift must dwarf the ISM ram-drag position drift.
    (ISM density at intergalactic scales is much smaller than LIC
    but we conservatively use LIC here as an upper bound.)"""
    a_lambda = cosmological_lambda_acceleration(_INTERGALACTIC_LEG_M)
    dx_lambda = propagate_position_uncertainty_m(a_lambda, _MISSION_DURATION_S)

    a_ram = ram_pressure_drag_acceleration(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        relative_velocity_m_s=_CRUISE_VELOCITY_M_S,
        cross_section_m2=_SHIP_CROSS_SECTION_M2,
        ship_mass_kg=_SHIP_MASS_KG,
    )
    dx_ram = propagate_position_uncertainty_m(a_ram, _MISSION_DURATION_S)

    assert dx_lambda > dx_ram, (
        f"dx_Λ = {dx_lambda:.3e}, dx_ram = {dx_ram:.3e}"
    )


def test_combined_nav_budget_quadrature_is_euclidean_norm():
    """UncertaintyBudgetRow consumers combine in quadrature: the
    shared sum must equal the Euclidean norm of the individual rows."""
    a_ram = ram_pressure_drag_acceleration(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        relative_velocity_m_s=_CRUISE_VELOCITY_M_S,
        cross_section_m2=_SHIP_CROSS_SECTION_M2,
        ship_mass_kg=_SHIP_MASS_KG,
    )
    a_dm = dark_matter_drag_upper_bound(ship_mass_kg=_SHIP_MASS_KG)
    a_df = chandrasekhar_dynamical_friction_acceleration(
        ship_mass_kg=_SHIP_MASS_KG,
        velocity_m_s=_CRUISE_VELOCITY_M_S,
        background_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        velocity_dispersion_m_s=1.0e4,
    )

    dx_ram = propagate_position_uncertainty_m(a_ram, _MISSION_DURATION_S)
    dx_dm = propagate_position_uncertainty_m(a_dm, _MISSION_DURATION_S)
    dx_df = propagate_position_uncertainty_m(a_df, _MISSION_DURATION_S)

    rows = [
        UncertaintyBudgetRow("ISM_ram_LIC", "H2", dx_ram, "m", "Ferriere 2001"),
        UncertaintyBudgetRow("DM_drag_XENONnT", "M1", dx_dm, "m", "Aprile 2023"),
        UncertaintyBudgetRow("Chandra_DF", "A2", dx_df, "m", "Chandrasekhar 1943"),
    ]
    total = quadrature_sum_rows(rows, unit_filter="m")
    expected = math.sqrt(dx_ram * dx_ram + dx_dm * dx_dm + dx_df * dx_df)
    assert total == pytest.approx(expected, rel=1.0e-12)
    # And the ISM ram row must be the single largest contributor.
    assert dx_ram > dx_dm
    assert dx_ram > dx_df
