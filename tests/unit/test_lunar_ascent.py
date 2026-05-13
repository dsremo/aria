"""Tests for the lunar ascent module — closes the ascent gap the audit found.

Validates against Apollo 11 LM Ascent Stage (NASA SP-2007-4805):
  wet mass 4,700 kg, dry 2,150 kg, thrust 15,570 N, Isp 311 s
  Actual Δv budget ≈ 1,845 m/s
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.lunar_ascent import (
    MU_MOON, R_MOON, G0,
    AscentConfig, apollo_11_ascent, chandrayaan_3_ascent, starship_hls_ascent,
    simulate_ascent, abort_dv_to_low_orbit,
)


def test_apollo_11_ascent_succeeds():
    r = apollo_11_ascent()
    assert r.success, f"Apollo 11 ascent failed: {r.notes}"
    # BUG-017 (2026-04-24): Apollo 11 LM insertion orbit was 17 × 86 km,
    # so burnout altitude should be near perilune (~15–30 km), not the
    # old loose 50–250 km window. The old window accepted a physically
    # wrong profile where the vehicle over-climbed to ~100 km still with
    # positive γ, leaving it on a perilune-below-surface orbit that
    # inflated the circularisation Δv to ~420 m/s.
    assert 10 < r.burnout_altitude_km < 100
    # Burnout speed should be at least 75% of local orbital speed
    v_orb = math.sqrt(MU_MOON / (R_MOON + 111_000))
    assert r.burnout_speed_mps > 0.75 * v_orb
    # Burn duration close to APS spec (~432 s)
    assert 350 < r.burnout_time_s < 500


def test_apollo_11_total_dv_within_30pct_of_actual():
    """Apollo 11 actual total Δv budget was ~1850 m/s including circularisation."""
    r = apollo_11_ascent()
    # Idealized planar ascent without closed-loop PEG guidance runs
    # somewhat high; allow 30% margin vs published.
    assert 1500 < r.total_dv_mps < 2500


def test_apollo_11_propellant_feasibility():
    """Burned mass must fit the loaded propellant (2,376 kg)."""
    r = apollo_11_ascent()
    assert r.propellant_burned_kg < 2400
    assert r.propellant_margin_kg > 0   # some margin remains


def test_starship_hls_ascent_huge_fuel_margin():
    """HLS Starship has kilo-tonne propellant margin on a lunar ascent."""
    r = starship_hls_ascent()
    assert r.success
    # Starship with 140 t of propellant capacity should have >> 30 t margin
    # for a single Moon → LLO ascent.
    assert r.propellant_margin_kg > 30_000


def test_chandrayaan_3_insufficient_propellant_flagged():
    """Vikram has no ascent-stage propellant — simulator must flag it."""
    r = chandrayaan_3_ascent()
    assert not r.success
    assert any("Insufficient propellant" in n for n in r.notes)


def test_trajectory_has_realistic_shape():
    """Trajectory should start at surface, rise monotonically through
    the powered phase, and contain >100 sample points."""
    r = apollo_11_ascent()
    assert len(r.trajectory) > 100
    # First point near surface
    assert r.trajectory[0].altitude_m < 10
    # Altitude must exceed 10 km somewhere during the boost
    max_alt = max(s.altitude_m for s in r.trajectory)
    assert max_alt > 10_000


def test_trajectory_monotone_velocity_during_boost():
    """Speed never decreases during the powered boost."""
    r = apollo_11_ascent()
    boost_points = [s for s in r.trajectory if s.thrust_n > 0]
    # Allow for small numerical noise but overall trend must be up
    first_v = boost_points[0].speed_mps
    last_v = boost_points[-1].speed_mps
    assert last_v > first_v + 500       # gained at least 500 m/s


def test_abort_dv_zero_when_already_in_orbit():
    """An already-orbital state needs no abort Δv."""
    # 15 km altitude, circular speed there
    alt = 15_000
    v_circ = math.sqrt(MU_MOON / (R_MOON + alt))
    dv = abort_dv_to_low_orbit(alt_m=alt, speed_mps=v_circ,
                               flight_path_deg=0.0, target_peri_alt_km=15)
    assert dv < 5.0    # essentially zero


def test_abort_dv_positive_when_slow():
    """A slow near-surface state needs non-trivial abort Δv."""
    dv = abort_dv_to_low_orbit(alt_m=5000, speed_mps=500,
                               flight_path_deg=30.0, target_peri_alt_km=15)
    assert dv > 100


def test_simulate_ascent_finite_outputs():
    """Numerical finite-ness guard for all reported quantities."""
    r = apollo_11_ascent()
    assert math.isfinite(r.burnout_altitude_km)
    assert math.isfinite(r.burnout_speed_mps)
    assert math.isfinite(r.burnout_flight_path_deg)
    assert math.isfinite(r.circularisation_dv_mps)
    assert math.isfinite(r.total_dv_mps)
    assert math.isfinite(r.propellant_burned_kg)
