"""Unit tests for the hull fatigue bridge module.

Benchmarks:
  - Timoshenko 1970 *Theory of Plates and Shells* §113 — thin-wall
    hoop stress σ_h = pR/t.
  - Suresh 1998 *Fatigue of Materials* 2nd ed §7.4 — Goodman
    correction; §7.5 Miner's rule.
  - MMPDS-17 §5.3 — Ti-6Al-4V ultimate, yield, and Basquin
    coefficients (σ_f' = 2030 MPa, b = -0.104).
"""

from __future__ import annotations

import math

import pytest

from aria.physics.hull_fatigue import (
    CycleBlock,
    HullFatigueReport,
    HullGeometry,
    ThermalCycleBlock,
    build_hull_fatigue_report,
)


# A 3 m radius, 10 mm wall Ti-6Al-4V cabin hull (R/t = 300 → deep in
# the thin-wall regime).
_HABITAT_HULL = HullGeometry(
    radius_m=3.0, wall_thickness_m=1.0e-2, material_name="Ti-6Al-4V"
)


def test_hull_geometry_rejects_thick_wall_configuration():
    with pytest.raises(ValueError):
        HullGeometry(radius_m=0.1, wall_thickness_m=0.05)


def test_pressure_only_report_hoop_stress_matches_pR_over_t():
    """1 atm cabin pressure on the 3 m × 10 mm hull gives
    σ_h = 101325 · 3 / 0.01 = 3.04e7 Pa = 30.4 MPa at peak.
    Amplitude is half of that = 15.2 MPa."""
    report = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=10.0),),
    )
    amp = report.goodman_amplitude_by_block["pressure"]
    # Goodman-corrected amplitude is slightly higher than the raw
    # 15.2 MPa half-range because σ_mean > 0; σ_UTS(Ti-6Al-4V) ≈
    # 895 MPa, so the correction factor is 1/(1 - 15.2/895) ≈ 1.017.
    assert 1.5e7 < amp < 1.6e7


def test_pressure_only_titanium_hcf_life_is_very_long():
    """At 15 MPa amplitude on Ti-6Al-4V the Basquin life is well
    above 10¹² cycles — the hull is effectively infinite-life under
    a single-atmosphere cabin cycle."""
    report = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=10.0),),
    )
    n_f = report.basquin_life_by_block["pressure"]
    assert n_f > 1.0e10
    assert report.years_to_failure > 1.0e9


def test_thermal_only_block_returns_finite_damage():
    """A ±75 K day-night thermal cycle gives ~73 MPa amplitude on
    Ti-6Al-4V (E=113.8 GPa, α=8.6e-6). Basquin life at 73 MPa is
    finite but still very long (> 10⁹ cycles)."""
    report = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        thermal_blocks=(
            ThermalCycleBlock(delta_t_k=150.0, cycles_per_year=365.25),
        ),
    )
    amp = report.goodman_amplitude_by_block["thermal"]
    # σ_peak-to-peak = E α ΔT = 113.8e9 × 8.6e-6 × 150 = 1.47e8 Pa
    # amplitude = half = 7.34e7 Pa
    assert 7.0e7 < amp < 8.0e7
    assert report.basquin_life_by_block["thermal"] > 1.0e5


def test_combined_blocks_sum_damage():
    """Miner damage of a combined (pressure + thermal) load must be
    strictly larger than either individual block."""
    p_only = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=10.0),),
    )
    t_only = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        thermal_blocks=(
            ThermalCycleBlock(delta_t_k=150.0, cycles_per_year=365.25),
        ),
    )
    combined = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=10.0),),
        thermal_blocks=(
            ThermalCycleBlock(delta_t_k=150.0, cycles_per_year=365.25),
        ),
    )
    assert combined.cumulative_damage_per_year >= p_only.cumulative_damage_per_year
    assert combined.cumulative_damage_per_year >= t_only.cumulative_damage_per_year
    # Linearity: combined damage should equal the sum of per-block
    # damages (Miner's rule is additive).
    assert combined.cumulative_damage_per_year == pytest.approx(
        p_only.cumulative_damage_per_year + t_only.cumulative_damage_per_year,
        rel=1.0e-12,
    )


def test_build_report_rejects_empty_blocks():
    with pytest.raises(ValueError):
        build_hull_fatigue_report(geometry=_HABITAT_HULL)


def test_years_to_failure_inverse_of_cumulative_damage():
    report = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=100.0),),
    )
    assert report.years_to_failure == pytest.approx(
        1.0 / report.cumulative_damage_per_year, rel=1.0e-12
    )


def test_larger_pressure_swing_increases_damage():
    """Damage must be monotone increasing in the pressure range."""
    low = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=50000.0, cycles_per_year=10.0),),
    )
    hi = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=200000.0, cycles_per_year=10.0),),
    )
    assert hi.cumulative_damage_per_year > low.cumulative_damage_per_year


def test_cycle_block_validation():
    with pytest.raises(ValueError):
        CycleBlock(delta_pressure_pa=0.0, cycles_per_year=1.0)
    with pytest.raises(ValueError):
        CycleBlock(delta_pressure_pa=1.0, cycles_per_year=0.0)
    with pytest.raises(ValueError):
        ThermalCycleBlock(delta_t_k=0.0, cycles_per_year=1.0)


def test_report_is_frozen_dataclass():
    """HullFatigueReport should be immutable so callers can trust
    logged values."""
    report = build_hull_fatigue_report(
        geometry=_HABITAT_HULL,
        pressure_blocks=(CycleBlock(delta_pressure_pa=101325.0, cycles_per_year=1.0),),
    )
    assert isinstance(report, HullFatigueReport)
    with pytest.raises((AttributeError, TypeError)):
        report.cumulative_damage_per_year = 0.0  # type: ignore[misc]
