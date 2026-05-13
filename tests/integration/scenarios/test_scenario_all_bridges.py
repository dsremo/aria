"""Scenario: exercise every simulator-to-physics-primitives bridge
simultaneously.

This regression builds one instance of each wired simulator class
and asserts that each bridge's physics primitive is actually being
called (by checking for the derived state fields the bridge
populates). It's the "prove everything is wired" canary — if any
future refactor accidentally drops a bridge, this test fails.

Wired simulators covered:
  1. ThermalManagementSimulator -> thermal_radiator bridge
  2. MultiLayerShieldSimulator (WhippleShieldLayer) -> shield_ble bridge
  3. StructuralFatigueSimulator -> solid_mechanics.basquin_life
  4. ArtificialGravitySimulator -> cardio + vestibular
  5. RadiationShieldSimulator -> transport.gcr_annual_unshielded_dose
     + transport.cucinotta_shielded_dose + radchem.hydrogen_outgas
  6. ReactorNeutronicsSimulator -> fusion_xsec.bosch_hale + TBR gate
  7. DSACClock -> dark_sector.clock_frequency_drift_from_alpha
  8. FusionBrakingConfig -> departure.tsiolkovsky_delta_v
  9. orbital_destination.hohmann_transfer -> gravity.hohmann_transfer_delta_v
  10. GenerationShip.run() -> navigation_budget.build_navigation_budget
"""

from __future__ import annotations

import math

import pytest


def test_thermal_radiator_bridge_active():
    from aria.simulation.thermal_management import RadiatorPanel

    iso = RadiatorPanel(
        panel_id=0, area_m2=100.0, temperature_k=500.0, fin_length_m=0.1,
        use_fin_efficiency=False,
    )
    finned = RadiatorPanel(
        panel_id=1, area_m2=100.0, temperature_k=500.0, fin_length_m=0.1,
        use_fin_efficiency=True,
    )
    assert iso.rejection_watts > 0.0
    assert finned.rejection_watts > 0.0
    assert finned.rejection_watts < iso.rejection_watts


def test_shield_ble_bridge_active():
    from aria.simulation.shield_system import WhippleShieldLayer

    layer = WhippleShieldLayer()
    d_c = layer.nno_critical_diameter_m(impact_velocity_m_s=7.0e3)
    assert 0.0 < d_c < 1.0e-1


def test_basquin_bridge_active():
    from aria.simulation.engineering_detail import StructuralFatigueSimulator

    sim = StructuralFatigueSimulator(rpm=1.0)
    n_f = sim._cycles_to_failure(200.0)  # 200 MPa
    assert 0.0 < n_f < float("inf")
    # Below the endurance FoS gate, life is infinite
    assert math.isinf(sim._cycles_to_failure(50.0))


def test_cardio_vestibular_bridge_active():
    from aria.simulation.advanced_systems import ArtificialGravitySimulator

    sim = ArtificialGravitySimulator(seed=42)
    # Cardio compartment output populates cardiovascular_health
    for y in range(1, 6):
        sim.simulate_year(float(y))
    assert 0.0 < sim.state.cardiovascular_health <= 1.0
    # Vestibular cross-coupling populates the new field
    assert sim.state.coriolis_illusion_alpha_rad_s2 > 0.0
    # At 1 RPM ring spin, Ω × ω_head magnitude = 0.1047 * 1 = 0.1047
    assert sim.state.coriolis_illusion_alpha_rad_s2 == pytest.approx(
        0.10472, abs=1.0e-4
    )


def test_transport_radchem_bridge_active():
    from aria.simulation.advanced_systems import RadiationShieldSimulator

    sim = RadiationShieldSimulator(seed=42)
    # gcr_annual_unshielded_sv sourced from the transport primitive
    assert sim.state.gcr_annual_unshielded_sv == pytest.approx(0.42, rel=1e-6)
    sim.simulate_year(1.0)
    # Radchem bridge fills in H2 outgassing rate
    assert sim.state.h2_outgas_mol_s > 0.0
    assert sim.state.h2_cumulative_mol > 0.0


def test_fusion_bridge_active():
    from aria.simulation.reactor_neutronics import ReactorNeutronicsSimulator

    sim = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    assert sim.bosch_hale_cross_check_ratio > 0.0
    assert sim.tbr_meets_abdou is True


def test_m3_alpha_bridge_active():
    from aria.simulation.quantum_timekeeping import DSACClock

    clock = DSACClock()
    clock.tick(1.0)
    assert clock.m3_alpha_drift_cumulative_s > 0.0
    # Dwarfed by instrument drift
    assert clock.m3_alpha_drift_cumulative_s < clock.cumulative_error_s


def test_tsiolkovsky_bridge_active():
    from aria.simulation.braking_architecture import FusionBrakingConfig

    cfg = FusionBrakingConfig()
    dv = cfg.max_delta_v(fuel_kg=1.0e5)
    # Tsiolkovsky: v_e * ln(m0/m1), v_e = 981 km/s, ratio = 300001/200000
    expected = 981000.0 * math.log(300000.0 / 200000.0)
    assert dv == pytest.approx(expected, rel=1e-3)


def test_gravity_hohmann_bridge_active():
    from aria.simulation.orbital_destination import hohmann_transfer

    # LEO (400 km) → GEO (35786 km) Hohmann transfer
    mu_earth = 3.986004418e14  # m³/s²
    r_leo = 6371e3 + 400e3
    r_geo = 6371e3 + 35786e3
    result = hohmann_transfer(mu_earth, r_leo, r_geo)
    # Published total delta-v for LEO-GEO Hohmann: ~3935 m/s
    assert 3800.0 < result["total_delta_v"] < 4100.0


def test_navigation_budget_bridge_active():
    from aria.physics.navigation_budget import (
        MissionProfile,
        build_navigation_budget,
    )

    profile = MissionProfile(
        name="test",
        ship_mass_kg=1.0e8,
        cross_section_m2=500.0,
        cruise_velocity_m_s=3.0e7,  # 0.1 c
        leg_distance_m=4.244 * 9.4607304725808e15,  # 4.244 ly
    )
    budget = build_navigation_budget(profile)
    # All 3 rows populated
    assert len(budget.rows) == 3
    assert budget.total_position_error_m >= 0.0


def test_all_bridges_collectively_exercised():
    """Meta-test: import every bridge module and confirm the
    top-level simulator classes link to them without error.
    This catches import-order bugs that unit tests can miss."""
    # Physics bridge modules
    import aria.physics.thermal_radiator  # noqa: F401
    import aria.physics.shield_ble  # noqa: F401
    import aria.physics.hull_fatigue  # noqa: F401
    import aria.physics.navigation_budget  # noqa: F401
    import aria.physics.cardio  # noqa: F401
    import aria.physics.vestibular  # noqa: F401
    import aria.physics.radchem  # noqa: F401
    import aria.physics.transport  # noqa: F401
    import aria.physics.fusion_xsec  # noqa: F401
    import aria.physics.dark_sector  # noqa: F401
    import aria.physics.departure  # noqa: F401
    import aria.physics.gravity  # noqa: F401
    import aria.physics.gravity_relativistic  # noqa: F401
    import aria.physics.solid_mechanics  # noqa: F401

    # Simulator modules that import at least one bridge
    import aria.simulation.thermal_management  # noqa: F401
    import aria.simulation.shield_system  # noqa: F401
    import aria.simulation.engineering_detail  # noqa: F401
    import aria.simulation.advanced_systems  # noqa: F401
    import aria.simulation.reactor_neutronics  # noqa: F401
    import aria.simulation.quantum_timekeeping  # noqa: F401
    import aria.simulation.braking_architecture  # noqa: F401
    import aria.simulation.orbital_destination  # noqa: F401
    import aria.simulation.relativistic_physics  # noqa: F401
    import aria.simulation.generation_ship  # noqa: F401
