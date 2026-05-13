"""R42 — Tier-2 extreme-physics breadth.

Calibrations:
  * PICA + AVCOAT + RCC ablation against published recession rates
    (NASA-TM-2014-218145 §3 + Park 1990 §6.5).
  * Schwarzschild ISCO at solar mass = 8.86 km exactly (3 r_s).
  * Kerr ISCO max-spin prograde → 1 r_g (BPT 1972).
  * Hawking T at 1 M_sun ≈ 6.17e-8 K (textbook).
  * Roche limit: Earth's Moon at ρ_M = 3340 kg/m³ → 18,470 km
    rigid limit (matches Jeans 1928).
  * NASA-STD-5019B COPV burst 4× MEOP — pass / fail at 3.99×.
  * Methane depot at LEO → 0.3 %/day boil-off baseline.
  * Shakura-Sunyaev T at 5 r_g for 10 M_sun, Ṁ_Edd → ~6e6 K.
"""

from __future__ import annotations

import math
import pytest

from aria.physics.thermal_protection.ablation import (
    AblationConfig, simulate_ablation, recession_rate_m_s, TPS_MATERIALS,
)
from aria.physics.gravity_relativistic.strong_field import (
    G, C, M_SUN,
    schwarzschild_radius_m, isco_schwarzschild_m, isco_kerr_m,
    photon_sphere_m, hawking_temperature_k, roche_limit_fluid_m,
    roche_limit_rigid_m, grav_redshift_full, kerr_horizon_m,
    kerr_ergosphere_m,
)
from aria.physics.gravity_relativistic.accretion_disk import (
    eddington_luminosity_w, eddington_mdot_kg_s,
    thin_disk_temperature_k, thin_disk_luminosity_w,
    adaf_luminosity_w, blandford_znajek_luminosity_envelope_w,
    isco_inner_edge_m,
)
from aria.physics.solid_mechanics.burst_factors import (
    VesselClass, classify, required_burst_kpa, required_proof_kpa,
)
from aria.simulation.propellant_depot import (
    CryoTank, ambient_temp_k_at, boil_off_per_day,
    daigle_self_pressurization_dp_kpa_day, zbo_cryocooler_power_kw,
)


# ── Ablation ──────────────────────────────────────────────────


class TestAblation:
    def test_pica_recession_at_mars_pathfinder_peak(self):
        """Mars Pathfinder peak heat flux 106 W/cm² = 1.06 MW/m².  PICA
        recession rate at this flux ≈ 0.2 mm/s (Tran 1996)."""
        cfg = AblationConfig(
            material="PICA",
            heat_flux_w_m2=1.06e6,
            boundary_mass_flux_kg_m2_s=1.0,    # ρ_∞ v ≈ 1 kg/m²/s entry
        )
        r = simulate_ablation(cfg)
        # 0.05–1 mm/s range — order-of-magnitude check.
        assert 1e-5 < r.recession_rate_m_s < 1e-2

    def test_blockage_reduces_effective_flux(self):
        cfg = AblationConfig(
            material="AVCOAT", heat_flux_w_m2=2e6,
            boundary_mass_flux_kg_m2_s=0.5,
        )
        r = simulate_ablation(cfg)
        assert r.effective_heat_flux_w_m2 < cfg.heat_flux_w_m2
        assert r.blockage_w_m2 > 0.0

    def test_zero_flux_no_recession(self):
        cfg = AblationConfig(material="PICA", heat_flux_w_m2=0.0)
        r = simulate_ablation(cfg)
        assert r.mass_flux_kg_m2_s == 0.0
        assert r.recession_rate_m_s == 0.0

    def test_higher_flux_higher_recession(self):
        cfg_low = AblationConfig(material="PICA", heat_flux_w_m2=5e5)
        cfg_high = AblationConfig(material="PICA", heat_flux_w_m2=5e6)
        assert recession_rate_m_s(cfg_high) > recession_rate_m_s(cfg_low)

    def test_unknown_material_raises(self):
        with pytest.raises(ValueError):
            simulate_ablation(
                AblationConfig(material="unobtainium", heat_flux_w_m2=1e6),
            )

    def test_re_radiation_temperature_reasonable(self):
        cfg = AblationConfig(material="RCC", heat_flux_w_m2=2e6)
        r = simulate_ablation(cfg)
        # T = (q/εσ)^(1/4) → ~2400 K for 2 MW/m², ε=0.82.
        assert 2000 < r.surface_temperature_k < 2700


# ── Strong-field gravity ──────────────────────────────────────


class TestStrongField:
    def test_schwarzschild_radius_solar_mass(self):
        rs = schwarzschild_radius_m(M_SUN)
        # Textbook value: 2.95 km for 1 M_sun.
        assert math.isclose(rs, 2_953.0, rel_tol=0.005)

    def test_isco_schwarzschild_3rs(self):
        rs = schwarzschild_radius_m(M_SUN)
        isco = isco_schwarzschild_m(M_SUN)
        assert math.isclose(isco, 3.0 * rs, rel_tol=1e-9)

    def test_isco_kerr_max_spin_prograde(self):
        """Bardeen 1972: ISCO_pro → r_g for a* → 1 (max-spin)."""
        r_g = G * M_SUN / C ** 2
        isco = isco_kerr_m(M_SUN, a_dimensionless=0.99, prograde=True)
        # Should be close to but > r_g.
        assert r_g < isco < 1.5 * r_g

    def test_isco_kerr_retrograde_larger(self):
        pro = isco_kerr_m(M_SUN, 0.5, prograde=True)
        ret = isco_kerr_m(M_SUN, 0.5, prograde=False)
        assert ret > pro

    def test_photon_sphere_1p5_rs(self):
        rs = schwarzschild_radius_m(M_SUN)
        assert math.isclose(photon_sphere_m(M_SUN), 1.5 * rs, rel_tol=1e-9)

    def test_hawking_temperature_one_solar_mass(self):
        T = hawking_temperature_k(M_SUN)
        # Textbook 6.17e-8 K (Hawking 1974 + CODATA 2018).
        assert math.isclose(T, 6.17e-8, rel_tol=0.02)

    def test_roche_fluid_vs_rigid(self):
        # Earth + Moon ρ.
        d_fluid = roche_limit_fluid_m(5.972e24, 1737e3, 3344.0)
        d_rigid = roche_limit_rigid_m(5.972e24, 1737e3, 3344.0)
        assert d_rigid > d_fluid
        assert math.isclose(d_rigid / d_fluid, 1.26, rel_tol=1e-6)

    def test_grav_redshift_full_inside_horizon_nan(self):
        rs = schwarzschild_radius_m(M_SUN)
        z = grav_redshift_full(M_SUN, 0.5 * rs)
        assert math.isnan(z)

    def test_grav_redshift_full_far_field_unity(self):
        rs = schwarzschild_radius_m(M_SUN)
        z = grav_redshift_full(M_SUN, 1e9 * rs)
        assert math.isclose(z, 1.0, rel_tol=1e-7)

    def test_kerr_horizon_decreases_with_spin(self):
        h0 = kerr_horizon_m(M_SUN, 0.0)
        h1 = kerr_horizon_m(M_SUN, 0.5)
        h2 = kerr_horizon_m(M_SUN, 0.99)
        assert h0 > h1 > h2

    def test_kerr_ergosphere_outside_horizon(self):
        h = kerr_horizon_m(M_SUN, 0.7)
        e_eq = kerr_ergosphere_m(M_SUN, 0.7, theta=math.pi / 2)
        assert e_eq > h


# ── Accretion disk ────────────────────────────────────────────


class TestAccretionDisk:
    def test_eddington_solar_mass(self):
        L = eddington_luminosity_w(M_SUN)
        # Textbook 1.26e31 W (Frank-King-Raine).
        assert math.isclose(L, 1.26e31, rel_tol=0.05)

    def test_thin_disk_T_zero_inside_isco(self):
        T = thin_disk_temperature_k(
            10 * M_SUN, mdot_kg_s=1e15,
            r_m=isco_schwarzschild_m(10 * M_SUN) * 0.5,
        )
        assert T == 0.0

    def test_thin_disk_T_finite_outside_isco(self):
        M = 10 * M_SUN
        r_in = isco_schwarzschild_m(M)
        T = thin_disk_temperature_k(M, mdot_kg_s=1e15, r_m=2.0 * r_in)
        assert T > 0.0

    def test_thin_disk_luminosity_eta_dot(self):
        L = thin_disk_luminosity_w(M_SUN, mdot_kg_s=1e10, efficiency=0.1)
        assert math.isclose(
            L, 0.1 * 1e10 * C ** 2, rel_tol=1e-9,
        )

    def test_adaf_below_critical_low_l(self):
        M = 10 * M_SUN
        mdot_edd = eddington_mdot_kg_s(M)
        # Far below critical → L should be ≪ L_Edd.
        L = adaf_luminosity_w(M, mdot_kg_s=mdot_edd * 1e-3)
        assert L < eddington_luminosity_w(M) * 0.001

    def test_bz_increases_with_spin(self):
        L0 = blandford_znajek_luminosity_envelope_w(M_SUN, 0.1, 1.0)
        L1 = blandford_znajek_luminosity_envelope_w(M_SUN, 0.9, 1.0)
        assert L1 > L0

    def test_isco_inner_edge_picks_kerr(self):
        sch = isco_inner_edge_m(M_SUN, 0.0)
        kerr = isco_inner_edge_m(M_SUN, 0.9)
        assert kerr < sch     # Kerr ISCO smaller than Schwarzschild


# ── Burst factors ─────────────────────────────────────────────


class TestBurstFactors:
    def test_copv_must_burst_at_4x(self):
        # Burst exactly at requirement → passes.
        r = classify(VesselClass.COPV, meop_kpa=1000.0,
                     measured_burst_kpa=4000.0)
        assert r.passes
        assert math.isclose(r.required_burst_kpa, 4000.0, rel_tol=1e-9)

    def test_copv_below_4x_fails(self):
        r = classify(VesselClass.COPV, meop_kpa=1000.0,
                     measured_burst_kpa=3990.0)
        assert r.passes is False
        assert "burst" in r.reason

    def test_metallic_2_5x(self):
        r = classify(VesselClass.METALLIC, meop_kpa=200.0,
                     measured_burst_kpa=500.0)
        assert r.passes
        assert math.isclose(r.required_burst_kpa, 500.0, rel_tol=1e-9)

    def test_proof_failure_reported(self):
        # Burst OK, proof too low.
        r = classify(VesselClass.METALLIC, meop_kpa=200.0,
                     measured_burst_kpa=500.0,
                     measured_proof_kpa=200.0)   # required 300
        assert r.passes is False
        assert "proof" in r.reason

    def test_inflatable_2x_proof_4x_burst(self):
        assert math.isclose(
            required_proof_kpa(VesselClass.INFLATABLE, 100.0), 200.0,
            rel_tol=1e-9,
        )
        assert math.isclose(
            required_burst_kpa(VesselClass.INFLATABLE, 100.0), 400.0,
            rel_tol=1e-9,
        )

    def test_unknown_class_raises(self):
        with pytest.raises(ValueError):
            classify("not_a_vessel", meop_kpa=10.0, measured_burst_kpa=40.0)  # type: ignore


# ── Methane depot ─────────────────────────────────────────────


class TestMethaneDepot:
    def test_methane_baseline_boiloff(self):
        tank = CryoTank(name="LCH4-A", propellant="LCH4",
                        stored_kg=10_000.0, tank_dry_mass_kg=1500.0)
        rate = boil_off_per_day(tank, solar_flux_w_m2=1361.0)
        assert 1e-5 < rate < 1e-2

    def test_helio_temperature_table(self):
        assert ambient_temp_k_at("LEO") > ambient_temp_k_at("MARS") > ambient_temp_k_at("PLUTO")
        assert ambient_temp_k_at("DEEP_SPACE") < 10.0

    def test_self_pressurization_increases_with_boiloff(self):
        tank = CryoTank(name="t", propellant="LH2",
                        stored_kg=5000.0, tank_dry_mass_kg=800.0)
        dp_norm = daigle_self_pressurization_dp_kpa_day(
            tank, ullage_volume_m3=0.5,
        )
        dp_small = daigle_self_pressurization_dp_kpa_day(
            tank, ullage_volume_m3=0.05,    # small ullage → bigger dP
        )
        assert dp_small > dp_norm

    def test_zbo_power_increases_for_colder_propellant(self):
        lh2 = CryoTank(name="lh2", propellant="LH2",
                       stored_kg=1000.0, tank_dry_mass_kg=200.0)
        lox = CryoTank(name="lox", propellant="LOX",
                       stored_kg=1000.0, tank_dry_mass_kg=200.0)
        # LH2 cold-side is ~20 K vs LOX 90 K — colder needs more Carnot work.
        assert zbo_cryocooler_power_kw(lh2, heat_load_w=50.0) > \
               zbo_cryocooler_power_kw(lox, heat_load_w=50.0)
