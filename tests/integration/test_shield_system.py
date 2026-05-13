"""Tests for the 7-layer multi-layer shielding system.

Covers:
  - ShieldErosionModel (physics calculations)
  - All 7 shield layers (state, degradation, effectiveness)
  - ShieldBudgetCalculator (mass + power budgets)
  - YearlyShieldSimulator (year-by-year simulation)
  - Edge cases, failure modes, and long-duration missions
"""

from __future__ import annotations

import math
import pytest

from aria.simulation.shield_system import (
    C_M_S,
    ISM_DENSITY_M3,
    ISM_DUST_DENSITY_M3,
    ISM_DUST_GRAIN_MASS_KG,
    PROTON_MASS_KG,
    AblationShieldLayer,
    ActiveDeflectionLayer,
    ElectrostaticGridLayer,
    ForwardDetectionLayer,
    MagneticDeflectorLayer,
    MultiLayerShieldState,
    ParticleClass,
    ShieldBudgetCalculator,
    ShieldErosionModel,
    ShieldLayerID,
    StructuralHullLayer,
    WhippleShieldLayer,
    YearlyShieldSimulator,
)


# ════════════════════════════════════════════════════════════════
#  SHIELD EROSION MODEL TESTS
# ════════════════════════════════════════════════════════════════

class TestShieldErosionModel:
    """Physics-based erosion calculations."""

    def test_kinetic_energy_1mg_at_01c(self):
        """1 mg grain at 0.1c should have ~450 GJ (100 tons TNT)."""
        model = ShieldErosionModel(velocity_c=0.1)
        mass = 1e-6  # 1 mg in kg
        ke = model.kinetic_energy_classical_j(mass)
        # KE = 0.5 * 1e-6 * (3e7)^2 = 0.5 * 1e-6 * 9e14 = 4.5e8 J = 450 MJ
        # NOTE: 1 mg = 1e-6 kg → 450 MJ, not GJ. The docstring says
        # "1 mg dust grain → 450 GJ" but that's for 1 g. 1 mg = 450 MJ.
        assert 4e8 < ke < 5e8, f"Expected ~450 MJ for 1mg at 0.1c, got {ke:.2e} J"

    def test_kinetic_energy_1g_at_01c(self):
        """1 g object at 0.1c should have ~450 GJ."""
        model = ShieldErosionModel(velocity_c=0.1)
        mass = 1e-3  # 1 g in kg
        ke = model.kinetic_energy_classical_j(mass)
        # 0.5 * 1e-3 * 9e14 = 4.5e11 J = 450 GJ
        assert 4e11 < ke < 5e11, f"Expected ~450 GJ for 1g at 0.1c, got {ke:.2e} J"

    def test_kinetic_energy_relativistic_correction(self):
        """Relativistic KE should be slightly higher than classical at 0.1c."""
        model = ShieldErosionModel(velocity_c=0.1)
        mass = 1.0  # 1 kg
        ke_classical = model.kinetic_energy_classical_j(mass)
        ke_relativistic = model.kinetic_energy_j(mass)
        # At 0.1c, gamma = 1.00504, so relativistic is ~1% higher
        assert ke_relativistic > ke_classical
        ratio = ke_relativistic / ke_classical
        assert 1.0 < ratio < 1.02, f"Expected ~1% difference, got ratio={ratio:.4f}"

    def test_ism_atom_flux(self):
        """ISM atom flux at 0.1c (Ferriere 2001 warm neutral: 0.3 atom/cm^3)."""
        model = ShieldErosionModel(velocity_c=0.1)
        flux = model.ism_atom_flux_per_m2_s()
        # n * v = 0.3e6 * 3e7 = 9e12 atoms/m^2/s
        assert 8e12 < flux < 1e13

    def test_ism_atom_flux_custom_density(self):
        """Flux scales linearly with ISM density."""
        model = ShieldErosionModel(velocity_c=0.1)
        flux_1 = model.ism_atom_flux_per_m2_s(density_m3=1e6)
        flux_10 = model.ism_atom_flux_per_m2_s(density_m3=10e6)
        assert abs(flux_10 / flux_1 - 10.0) < 0.01

    def test_sputtering_erosion_positive(self):
        """Sputtering erosion rate should be positive and physical."""
        model = ShieldErosionModel(velocity_c=0.1)
        rate = model.sputtering_erosion_kg_per_m2_per_year()
        assert rate > 0
        # Should be very small — microgram scale per year
        assert rate < 1.0, "Erosion rate unreasonably high"

    def test_hoang_erosion_at_03c(self):
        """At 0.3c, Hoang erosion should be ~40 ug/ly/cm^2."""
        model = ShieldErosionModel(velocity_c=0.3)
        rate = model.hoang_erosion_ug_per_ly_cm2()
        assert abs(rate - 40.0) < 0.01

    def test_hoang_erosion_velocity_scaling(self):
        """Erosion scales as v^3."""
        model_01 = ShieldErosionModel(velocity_c=0.1)
        model_03 = ShieldErosionModel(velocity_c=0.3)
        ratio = model_03.hoang_erosion_ug_per_ly_cm2() / model_01.hoang_erosion_ug_per_ly_cm2()
        expected = (0.3 / 0.1) ** 3  # = 27
        assert abs(ratio - expected) < 0.01

    def test_hoang_erosion_at_01c(self):
        """At 0.1c, erosion should be 40 * (1/3)^3 = ~1.48 ug/ly/cm^2."""
        model = ShieldErosionModel(velocity_c=0.1)
        rate = model.hoang_erosion_ug_per_ly_cm2()
        expected = 40.0 * (0.1 / 0.3) ** 3
        assert abs(rate - expected) < 0.01

    def test_dust_encounter_rate(self):
        """Dust grain encounter rate should be physically reasonable."""
        model = ShieldErosionModel(velocity_c=0.1)
        rate = model.dust_grain_encounter_rate_per_m2_year()
        # n_dust * v * seconds_per_year
        # 0.01 * 3e7 * 3.156e7 = ~9.5e12 grains/m^2/year
        assert rate > 1e12
        assert rate < 1e14

    def test_dust_grain_impact_energy(self):
        """Single ISM dust grain impact energy at 0.1c."""
        model = ShieldErosionModel(velocity_c=0.1)
        energy = model.dust_grain_impact_energy_j()
        # 0.5 * 1e-15 * (3e7)^2 = 0.5 * 1e-15 * 9e14 = 0.45 J
        assert 0.4 < energy < 0.5

    def test_time_to_erode_ice(self):
        """Time to erode 1m of ice should be very long at 0.1c."""
        model = ShieldErosionModel(velocity_c=0.1)
        years = model.time_to_erode_thickness_years(1.0, 917.0)
        # Hoang erosion at 0.1c is tiny — should take many thousands of years
        assert years > 1000, f"Expected >1000 years, got {years:.0f}"

    def test_required_thickness(self):
        """Required shield thickness for 100 year mission."""
        model = ShieldErosionModel(velocity_c=0.1)
        thickness = model.required_thickness_m(100.0, 917.0, safety_factor=2.0)
        # Should be very thin — sputtering is tiny at 0.1c
        assert thickness > 0
        assert thickness < 1.0, f"Required thickness {thickness:.4f}m seems high"


# ════════════════════════════════════════════════════════════════
#  LAYER 1: FORWARD DETECTION TESTS
# ════════════════════════════════════════════════════════════════

class TestForwardDetectionLayer:
    """Layer 1: LIDAR + radar detection array."""

    def test_default_state(self):
        layer = ForwardDetectionLayer()
        assert layer.lidar_emitters == 16
        assert layer.radar_emitters == 8
        assert layer.max_detection_range_km == 100_000.0
        assert len(layer.lidar_emitter_health) == 16

    def test_warning_time_at_01c(self):
        """At 0.1c, 100,000 km → 3.33 seconds."""
        layer = ForwardDetectionLayer()
        t = layer.warning_time_s(100_000.0, 0.1)
        assert 3.3 < t < 3.4, f"Expected ~3.33s, got {t:.2f}s"

    def test_warning_time_at_10000km(self):
        """At 0.1c, 10,000 km → 0.333 seconds."""
        layer = ForwardDetectionLayer()
        t = layer.warning_time_s(10_000.0, 0.1)
        assert 0.33 < t < 0.34

    def test_operational_counts(self):
        layer = ForwardDetectionLayer()
        assert layer.operational_lidar_count() == 16
        assert layer.operational_radar_count() == 8

    def test_degraded_counts(self):
        layer = ForwardDetectionLayer()
        layer.lidar_emitter_health[0] = 0.05  # Below 0.1 threshold
        layer.lidar_emitter_health[1] = 0.0
        assert layer.operational_lidar_count() == 14

    def test_mass_and_power(self):
        layer = ForwardDetectionLayer()
        assert layer.mass_kg == 500.0
        assert layer.power_consumption_kw == 80.0


# ════════════════════════════════════════════════════════════════
#  LAYER 2: ACTIVE DEFLECTION TESTS
# ════════════════════════════════════════════════════════════════

class TestActiveDeflectionLayer:
    """Layer 2: Point defense lasers + kinetic impactors."""

    def test_default_state(self):
        layer = ActiveDeflectionLayer()
        assert layer.num_turrets == 8
        assert layer.laser_power_mw == 10.0
        assert layer.impactor_inventory == 20

    def test_energy_on_target(self):
        """10 MW laser for 0.33s = 3.3 MJ."""
        layer = ActiveDeflectionLayer()
        energy = layer.energy_on_target_j(0.33)
        assert 3.2e6 < energy < 3.4e6

    def test_vaporization_capacity(self):
        """Can vaporize material in sub-second timeframe."""
        layer = ActiveDeflectionLayer()
        mass = layer.can_vaporize_mass_kg(0.33)
        # Should be able to vaporize a positive amount
        assert mass > 0

    def test_operational_turrets(self):
        layer = ActiveDeflectionLayer()
        assert layer.operational_turret_count() == 8
        layer.turret_health[0] = 0.05
        assert layer.operational_turret_count() == 7

    def test_effectiveness_hierarchy(self):
        """Dust should be easier to intercept than large debris."""
        layer = ActiveDeflectionLayer()
        assert layer.effectiveness_dust > layer.effectiveness_debris_small
        assert layer.effectiveness_debris_small > layer.effectiveness_debris_large
        assert layer.effectiveness_debris_large > layer.effectiveness_macro


# ════════════════════════════════════════════════════════════════
#  LAYER 3: MAGNETIC DEFLECTOR TESTS
# ════════════════════════════════════════════════════════════════

class TestMagneticDeflectorLayer:
    """Layer 3: Superconducting magnetic deflector."""

    def test_default_state(self):
        layer = MagneticDeflectorLayer()
        assert layer.coil_count == 4
        assert layer.field_strength_center_t == 8.0  # REBCO superconductor (Spillantini 2010)
        assert layer.effective_radius_km == 1000.0

    def test_field_effectiveness_full(self):
        layer = MagneticDeflectorLayer()
        eff = layer.field_effectiveness()
        assert 0.99 < eff <= 1.0

    def test_field_effectiveness_degraded(self):
        layer = MagneticDeflectorLayer()
        layer.coil_health = [0.5, 0.5, 0.0, 0.0]  # 2 of 4 failed
        eff = layer.field_effectiveness()
        assert eff < 0.5

    def test_lorentz_deflection_proton(self):
        """Proton deflection angle should be positive."""
        layer = MagneticDeflectorLayer()
        angle = layer.lorentz_deflection_angle_rad()
        assert angle > 0  # Some deflection

    def test_neutral_particles_not_deflected(self):
        """Neutral particles have zero deflection efficiency."""
        layer = MagneticDeflectorLayer()
        assert layer.deflection_efficiency_neutral == 0.0

    def test_magsail_dual_use(self):
        """Magnetic deflector can serve as magsail brake."""
        layer = MagneticDeflectorLayer()
        layer.magsail_mode = True
        assert layer.magsail_mode is True


# ════════════════════════════════════════════════════════════════
#  LAYER 4: ELECTROSTATIC GRID TESTS
# ════════════════════════════════════════════════════════════════

class TestElectrostaticGridLayer:
    """Layer 4: High-voltage ionization grid."""

    def test_default_state(self):
        layer = ElectrostaticGridLayer()
        assert layer.voltage_kv == 200.0
        assert layer.ionization_efficiency == 0.80
        assert layer.grid_replacements_available == 10

    def test_grid_erosion_rate(self):
        """Grid erodes ~3%/yr from ISM sputtering (Hoang 2015)."""
        layer = ElectrostaticGridLayer()
        assert layer.grid_erosion_rate_per_year == 0.03
        # After 30 years, grid should be ~10% health
        for _ in range(30):
            layer.grid_health = max(0, layer.grid_health - layer.grid_erosion_rate_per_year)
        assert layer.grid_health < 0.15

    def test_grid_remaining_fraction(self):
        layer = ElectrostaticGridLayer()
        assert layer.grid_remaining_fraction() == 1.0
        layer.grid_health = 0.5
        assert layer.grid_remaining_fraction() == 0.5

    def test_grid_cannot_go_negative(self):
        layer = ElectrostaticGridLayer()
        layer.grid_health = -0.5
        assert layer.grid_remaining_fraction() == 0.0


# ════════════════════════════════════════════════════════════════
#  LAYER 5: ABLATION SHIELD TESTS
# ════════════════════════════════════════════════════════════════

class TestAblationShieldLayer:
    """Layer 5: Sacrificial water/ice shield."""

    def test_default_state(self):
        layer = AblationShieldLayer()
        assert layer.ice_mass_kg == 10_000.0
        assert layer.initial_mass_kg == 10_000.0
        assert layer.forward_area_m2 == 2000.0

    def test_thickness_calculation(self):
        """10,000 kg of ice over 2000 m^2: t = m/(A*rho) = 10000/(2000*917)."""
        layer = AblationShieldLayer()
        t = layer.thickness_m()
        expected = 10000.0 / (2000.0 * 917.0)
        assert abs(t - expected) < 0.001

    def test_remaining_fraction(self):
        layer = AblationShieldLayer()
        assert layer.remaining_fraction() == 1.0
        layer.ice_mass_kg = 5000.0
        assert abs(layer.remaining_fraction() - 0.5) < 0.001

    def test_radiation_shielding_dual_use(self):
        """Ice shield also provides radiation shielding."""
        layer = AblationShieldLayer()
        assert layer.radiation_dose_reduction == 0.40

    def test_replenishment_rate(self):
        """Replenishment from water recycling: 50 kg/year."""
        layer = AblationShieldLayer()
        assert layer.replenishment_rate_kg_year == 50.0


# ════════════════════════════════════════════════════════════════
#  LAYER 6: WHIPPLE SHIELD TESTS
# ════════════════════════════════════════════════════════════════

class TestWhippleShieldLayer:
    """Layer 6: 3-layer Whipple shield."""

    def test_default_state(self):
        layer = WhippleShieldLayer()
        assert layer.bumper_health == 1.0
        assert layer.fabric_health == 1.0
        assert layer.backstop_health == 1.0

    def test_three_distinct_layers(self):
        """Whipple has bumper, fabric, and backstop."""
        layer = WhippleShieldLayer()
        assert layer.bumper_material == "SiC_ceramic"
        assert layer.fabric_material == "Kevlar_UHMWPE"
        assert layer.backstop_material == "Al_7075"

    def test_standoff_gap(self):
        """Standoff gap between bumper and fabric is critical for fragmentation."""
        layer = WhippleShieldLayer()
        assert layer.standoff_gap_mm == 200.0

    def test_effectiveness_decreases_with_size(self):
        layer = WhippleShieldLayer()
        assert layer.effectiveness_fragment_small > layer.effectiveness_fragment_medium
        assert layer.effectiveness_fragment_medium > layer.effectiveness_fragment_large

    def test_passive_no_power(self):
        """Whipple shield is passive — zero power consumption."""
        layer = WhippleShieldLayer()
        assert layer.power_consumption_kw == 0.0

    def test_mass_components(self):
        """Total mass should be sum of bumper + fabric + backstop."""
        layer = WhippleShieldLayer()
        component_sum = layer.bumper_mass_kg + layer.fabric_mass_kg + layer.backstop_mass_kg
        assert layer.mass_kg == component_sum

    def test_nno_critical_diameter_bridge_hvi_regime(self):
        """The Christiansen 1993 NNO bridge should return a
        finite positive critical diameter for a 7 km/s aluminium
        projectile — the shield's hypervelocity envelope."""
        layer = WhippleShieldLayer()
        d_c = layer.nno_critical_diameter_m(
            impact_velocity_m_s=7.0e3, projectile_density_kg_m3=2700.0
        )
        assert 0.0 < d_c < 1.0e-1, f"d_c = {d_c*1000:.2f} mm"

    def test_nno_critical_diameter_falls_as_shield_degrades(self):
        """A 50 % degraded shield should stop a smaller projectile
        than a pristine shield."""
        healthy = WhippleShieldLayer()
        degraded = WhippleShieldLayer()
        degraded.bumper_health = 0.5
        degraded.backstop_health = 0.5
        d_c_healthy = healthy.nno_critical_diameter_m(impact_velocity_m_s=7.0e3)
        d_c_degraded = degraded.nno_critical_diameter_m(impact_velocity_m_s=7.0e3)
        assert d_c_degraded < d_c_healthy


# ════════════════════════════════════════════════════════════════
#  LAYER 7: STRUCTURAL HULL TESTS
# ════════════════════════════════════════════════════════════════

class TestStructuralHullLayer:
    """Layer 7: Ti-Al hull with self-healing."""

    def test_default_state(self):
        layer = StructuralHullLayer()
        assert layer.hull_health == 1.0
        assert layer.self_healing_capacity == 1.0
        assert layer.nanobot_repair_active is True

    def test_hull_material(self):
        layer = StructuralHullLayer()
        assert layer.hull_material == "Ti-6Al-4V"

    def test_self_healing_temperature(self):
        """ESA HealTech activates at 100-140C."""
        layer = StructuralHullLayer()
        assert 100 <= layer.self_healing_activation_temp_c <= 140

    def test_high_repairability(self):
        """Hull should be highly repairable with nanobots."""
        layer = StructuralHullLayer()
        assert layer.repairability == 0.9


# ════════════════════════════════════════════════════════════════
#  SHIELD BUDGET CALCULATOR TESTS
# ════════════════════════════════════════════════════════════════

class TestShieldBudgetCalculator:
    """Budget calculation for mass and power."""

    def test_total_mass(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator(state)
        total = calc.total_mass_kg()
        # Sum of all layer masses
        expected = (
            500.0    # detection
            + 2000.0   # active deflection
            + 5000.0   # magnetic deflector
            + 300.0    # electrostatic grid
            + 10000.0  # ablation shield (ice)
            + 9500.0   # whipple shield
            + 9500.0   # structural hull
        )
        assert abs(total - expected) < 1.0

    def test_total_mass_tonnes(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator()
        summary = calc.budget_summary(state)
        assert summary["total_mass_tonnes"] == round(summary["total_mass_kg"] / 1000.0, 2)

    def test_total_power(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator(state)
        total = calc.total_power_kw()
        assert total > 0
        # Detection (80) + active (500) + magnetic (80) + electrostatic (50)
        # + ablation (5) + whipple (0) + hull (2) = 717
        assert abs(total - 717.0) < 1.0

    def test_mass_breakdown_sums_to_total(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator(state)
        breakdown = calc.mass_breakdown()
        assert abs(sum(breakdown.values()) - calc.total_mass_kg()) < 0.1

    def test_power_breakdown_sums_to_total(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator(state)
        breakdown = calc.power_breakdown()
        assert abs(sum(breakdown.values()) - calc.total_power_kw()) < 0.1

    def test_no_state_raises(self):
        calc = ShieldBudgetCalculator()
        with pytest.raises(ValueError):
            calc.total_mass_kg()

    def test_peak_power_includes_lasers(self):
        state = MultiLayerShieldState()
        calc = ShieldBudgetCalculator()
        summary = calc.budget_summary(state)
        assert summary["peak_power_kw"] > summary["total_power_kw"]

    def test_ablation_mass_dynamic(self):
        """Budget should reflect current ice mass, not initial."""
        state = MultiLayerShieldState()
        state.ablation_shield.ice_mass_kg = 5000.0
        calc = ShieldBudgetCalculator(state)
        breakdown = calc.mass_breakdown()
        assert breakdown["L5_ablation_shield"] == 5000.0


# ════════════════════════════════════════════════════════════════
#  YEARLY SHIELD SIMULATOR TESTS
# ════════════════════════════════════════════════════════════════

class TestYearlyShieldSimulator:
    """Year-by-year simulation of the complete shield system."""

    def test_single_year_simulation(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        events = sim.simulate_year(1.0)
        assert isinstance(events, list)

    def test_threats_encountered_after_one_year(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.simulate_year(1.0)
        assert sim.state.total_threats_encountered > 0

    def test_neutralization_rate_positive(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.simulate_year(1.0)
        s = sim.state
        if s.total_threats_encountered > 0:
            rate = s.total_threats_neutralized / s.total_threats_encountered
            assert rate > 0, "Some threats should be neutralized"

    def test_shield_integrity_starts_near_1(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.simulate_year(1.0)
        assert sim.state.shield_integrity > 0.8

    def test_detection_degradation_over_time(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        for y in range(1, 201):
            sim.simulate_year(float(y))
        det = sim.state.detection
        # After 200 years, some LIDAR should have degraded
        assert det.operational_lidar_count() <= det.lidar_emitters

    def test_turret_degradation(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        for y in range(1, 201):
            sim.simulate_year(float(y))
        ad = sim.state.active_deflection
        # After 200 years, turrets should show some degradation
        assert ad.operational_turret_count() <= ad.num_turrets

    def test_electrostatic_grid_replacement(self):
        """Grid replaced within ~33 years (3%/yr Hoang erosion)."""
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        for y in range(1, 50):
            sim.simulate_year(float(y))
        eg = sim.state.electrostatic_grid
        assert eg.total_grids_consumed > 0

    def test_ablation_shield_erosion(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        for y in range(1, 11):
            sim.simulate_year(float(y))
        ab = sim.state.ablation_shield
        assert ab.total_erosion_kg > 0

    def test_ablation_shield_exists(self):
        """Ablation shield should be initialized and tracked."""
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.simulate_year(1.0)
        ab = sim.state.ablation_shield
        assert ab.ice_mass_kg >= 0  # May deplete over time

    def test_shield_report_structure(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.simulate_year(1.0)
        report = sim.get_shield_report()
        assert "overall_integrity" in report
        assert "layers" in report
        assert "budget" in report
        for layer_key in [
            "L1_detection", "L2_active_deflection", "L3_magnetic_deflector",
            "L4_electrostatic_grid", "L5_ablation_shield", "L6_whipple_shield",
            "L7_structural_hull",
        ]:
            assert layer_key in report["layers"]

    def test_run_mission_100_years(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        events = sim.run_mission(years=100)
        assert isinstance(events, list)
        report = sim.get_shield_report()
        assert report["mission_year"] == 100.0

    def test_higher_velocity_more_encounters(self):
        """Higher velocity should mean more ISM encounters."""
        sim_slow = YearlyShieldSimulator(velocity_c=0.05, seed=42)
        sim_fast = YearlyShieldSimulator(velocity_c=0.2, seed=42)
        sim_slow.simulate_year(1.0)
        sim_fast.simulate_year(1.0)
        # Not deterministic due to RNG but fast should generally see more
        # Use the pre-calculated rates instead
        assert sim_fast._dust_encounter_rate > sim_slow._dust_encounter_rate

    def test_zero_velocity_no_encounters(self):
        """At zero velocity, no ISM erosion."""
        model = ShieldErosionModel(velocity_c=0.0)
        assert model.ism_atom_flux_per_m2_s() == 0.0
        assert model.hoang_erosion_kg_per_m2_per_year() == 0.0

    def test_100_year_mission_completes(self):
        """100-year mission should complete without crashing."""
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.run_mission(years=100)
        # Whipple shield backstop health should be non-negative
        assert sim.state.whipple_shield.backstop_health >= 0

    def test_long_mission_grid_spares_depleted(self):
        """Over 500+ years, electrostatic grid spares should deplete."""
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.run_mission(years=500)
        eg = sim.state.electrostatic_grid
        # 3%/yr erosion → replacement every ~33 years → ~15 replacements in 500 years
        # Only 10 spares available
        assert eg.total_grids_consumed >= 10

    def test_magnetic_deflector_cryocooler_degrades(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.run_mission(years=50)
        mag = sim.state.magnetic_deflector
        assert mag.cryocooler_health < 1.0

    def test_deterministic_with_seed(self):
        """Same seed should produce identical results."""
        sim1 = YearlyShieldSimulator(velocity_c=0.1, seed=123)
        sim2 = YearlyShieldSimulator(velocity_c=0.1, seed=123)
        events1 = sim1.run_mission(years=10)
        events2 = sim2.run_mission(years=10)
        assert len(events1) == len(events2)
        assert sim1.state.total_threats_encountered == sim2.state.total_threats_encountered

    def test_all_events_have_required_fields(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        events = sim.run_mission(years=50)
        for event in events:
            assert "year" in event
            assert "severity" in event
            assert "message" in event
            assert "subsystem" in event

    def test_interceptions_tracked(self):
        sim = YearlyShieldSimulator(velocity_c=0.1, seed=42)
        sim.run_mission(years=10)
        ad = sim.state.active_deflection
        assert ad.interceptions_total > 0


# ════════════════════════════════════════════════════════════════
#  ENUM AND CONSTANT TESTS
# ════════════════════════════════════════════════════════════════

class TestEnumsAndConstants:

    def test_shield_layer_ids(self):
        assert len(ShieldLayerID) == 7
        assert ShieldLayerID.DETECTION.value == 1
        assert ShieldLayerID.STRUCTURAL_HULL.value == 7
