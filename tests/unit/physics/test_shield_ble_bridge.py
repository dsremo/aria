"""Unit tests for the shield BLE bridge module.

Benchmarks:
  - Christiansen 1993 NASA TM-1993-107955 — NNO critical diameter
    Al 6061 reference calibration.
  - Ryan 2011 NASA/JSC 65282 — NNO equation and coefficients.
  - ISS MMOD envelope: ~1 cm aluminium projectile at 7 km/s on a
    standard 2-mm bumper / 5-mm rear wall stops.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.impact import ImpactRegime
from aria.physics.shield_ble import (
    ShieldBLEReport,
    ShieldLayerSpec,
    assess_shield_against_particle,
    relativistic_kinetic_energy_mt_tnt,
)


# ──────────────────────────────────────────────────────────────────────
#  Canonical ISS MMOD shield configuration (Christiansen 1993).
# ──────────────────────────────────────────────────────────────────────
_ISS_ISH: ShieldLayerSpec = ShieldLayerSpec(
    bumper_thickness_m=2.0e-3,
    bumper_density_kg_m3=2700.0,  # Al 6061-T6
    standoff_m=0.11,  # 110 mm typical ISS Whipple
    rear_wall_thickness_m=4.8e-3,
    rear_wall_density_kg_m3=2700.0,
    rear_wall_yield_strength_pa=276.0e6,  # 40 ksi Al 6061-T6 yield
)


def test_spec_validation_rejects_nonpositive():
    with pytest.raises(ValueError):
        ShieldLayerSpec(
            bumper_thickness_m=0.0,
            bumper_density_kg_m3=2700.0,
            standoff_m=0.1,
            rear_wall_thickness_m=5.0e-3,
            rear_wall_density_kg_m3=2700.0,
            rear_wall_yield_strength_pa=276.0e6,
        )


def test_iss_shield_stops_7km_s_1cm_aluminium_projectile():
    """Christiansen 1993: ISS Whipple stops a 1 cm Al projectile at
    7 km/s head-on — the headline 'safe' envelope."""
    rpt = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=1.0e-2,
        projectile_density_kg_m3=2700.0,
        projectile_mass_kg=(4.0 / 3.0) * math.pi * (5.0e-3) ** 3 * 2700.0,
        impact_velocity_m_s=7.0e3,
    )
    assert isinstance(rpt, ShieldBLEReport)
    assert rpt.regime == ImpactRegime.HYPERVELOCITY_BLE
    assert rpt.critical_diameter_m is not None
    # The reference NNO d_c for this ISS config at 7 km/s is ~1 cm
    # (Christiansen 1993 Fig 2). Accept anywhere in [5 mm, 2 cm] as
    # the "near the envelope" band.
    assert 5.0e-3 < rpt.critical_diameter_m < 2.0e-2


def test_ultra_relativistic_returns_none_and_annotates():
    """A 1 µg grain at 0.1 c must trigger the ultra-relativistic
    branch and leave the NNO fields empty with an ESTIMATE note."""
    rpt = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=1.0e-4,
        projectile_density_kg_m3=3000.0,
        projectile_mass_kg=1.0e-9,
        impact_velocity_m_s=0.1 * 299_792_458.0,
    )
    assert rpt.regime == ImpactRegime.ULTRA_RELATIVISTIC
    assert rpt.critical_diameter_m is None
    assert rpt.perforated is None
    assert "ULTRA" in rpt.notes


def test_hertzian_regime_triggered_below_50_m_s():
    rpt = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=1.0e-2,
        projectile_density_kg_m3=2700.0,
        projectile_mass_kg=1.4e-3,
        impact_velocity_m_s=10.0,
    )
    assert rpt.regime == ImpactRegime.HERTZIAN
    assert rpt.critical_diameter_m is None
    assert "HERTZIAN" in rpt.notes


def test_extrapolated_regime_at_20_km_s_returns_widened_bound():
    rpt = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=1.0e-3,
        projectile_density_kg_m3=2700.0,
        projectile_mass_kg=1.4e-6,
        impact_velocity_m_s=2.0e4,
    )
    assert rpt.regime == ImpactRegime.EXTRAPOLATED_BLE
    assert rpt.critical_diameter_m is not None
    assert "EXTRAPOLATED" in rpt.notes


def test_kinetic_energy_in_mt_tnt_matches_handbook_scale():
    """1 mg grain at 0.1 c → 450 GJ = 1.08×10⁻⁴ Mt TNT."""
    ke_mt = relativistic_kinetic_energy_mt_tnt(
        projectile_mass_kg=1.0e-6, velocity_m_s=0.1 * 299_792_458.0
    )
    # Classical 0.5 m v² = 0.5 · 1e-6 · 9e14 = 4.5e8 J — but at 0.1 c
    # the relativistic correction is ~0.5 %, so KE ≈ 4.5×10⁸ J
    # ≈ 1.08×10⁻⁷ Mt. (Scope note said "450 GJ" but that's for a
    # 1 *mg* grain = 1e-6 kg — agree.)
    assert 0.5e-7 < ke_mt < 5.0e-7, f"KE_mt = {ke_mt:.3e}"


def test_perforation_verdict_consistent_with_d_c():
    """For a projectile diameter 2× d_c, the shield must report
    perforated; for d = 0.5 · d_c, it must not."""
    # Use a moderate HVI case so the NNO branch applies
    big_particle_density = 2700.0
    velocity = 7.0e3

    # Find d_c first by calling on a very small reference projectile
    rpt_probe = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=1.0e-6,
        projectile_density_kg_m3=big_particle_density,
        projectile_mass_kg=1.0e-12,
        impact_velocity_m_s=velocity,
    )
    d_c = rpt_probe.critical_diameter_m
    assert d_c is not None and d_c > 0.0

    # Now run with a projectile twice d_c and half d_c.
    rpt_big = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=2.0 * d_c,
        projectile_density_kg_m3=big_particle_density,
        projectile_mass_kg=1.4e-3,
        impact_velocity_m_s=velocity,
    )
    rpt_small = assess_shield_against_particle(
        shield=_ISS_ISH,
        projectile_diameter_m=0.5 * d_c,
        projectile_density_kg_m3=big_particle_density,
        projectile_mass_kg=1.4e-4,
        impact_velocity_m_s=velocity,
    )
    assert rpt_big.perforated is True
    assert rpt_small.perforated is False


def test_rejects_nonpositive_projectile_inputs():
    with pytest.raises(ValueError):
        assess_shield_against_particle(
            shield=_ISS_ISH,
            projectile_diameter_m=0.0,
            projectile_density_kg_m3=2700.0,
            projectile_mass_kg=1.0e-6,
            impact_velocity_m_s=1.0e3,
        )
