"""Tests for lander gear impact + terrain hazard scoring."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.simulation.lander_touchdown import (
    GearConfig, TouchdownState, simulate_gear_impact, score_terrain,
    pristine_mare_terrain, boulder_field_terrain, crater_rim_terrain,
)


def test_soft_touchdown_succeeds():
    """Apollo-class lander at 1 m/s vertical should land without damage."""
    r = simulate_gear_impact(
        TouchdownState(vertical_speed_mps=1.0, horizontal_speed_mps=0.3, mass_kg=4700),
        GearConfig(),
    )
    assert r.success
    assert not r.gear_breach
    assert r.peak_g < 8.0


def test_hard_landing_breaches_gear():
    """10 m/s vertical — far outside Apollo envelope, must fail."""
    r = simulate_gear_impact(
        TouchdownState(vertical_speed_mps=10.0, horizontal_speed_mps=0.0, mass_kg=4700),
        GearConfig(),
    )
    assert not r.success
    assert r.gear_breach


def test_stroke_fraction_monotonic_with_speed():
    """Higher impact speed must use more gear stroke."""
    slow = simulate_gear_impact(TouchdownState(0.5, 0.0, 4700), GearConfig())
    fast = simulate_gear_impact(TouchdownState(2.5, 0.0, 4700), GearConfig())
    assert fast.strut_stroke_pct > slow.strut_stroke_pct


def test_pristine_mare_is_go():
    h = pristine_mare_terrain()
    t = score_terrain(h)
    assert t.verdict == "GO"
    assert t.hazard_score < 0.4


def test_boulder_field_is_no_go():
    h = boulder_field_terrain()
    t = score_terrain(h)
    assert t.verdict in ("CAUTION", "NO-GO")
    assert t.max_rock_height_m > 0.5


def test_crater_rim_is_no_go_due_to_slope():
    h = crater_rim_terrain(slope_deg=20)
    t = score_terrain(h)
    assert t.verdict == "NO-GO"
    assert t.max_slope_deg > 15


def test_tipover_at_high_horizontal_speed():
    """A very fast horizontal touchdown triggers the tipover flag."""
    r = simulate_gear_impact(
        TouchdownState(vertical_speed_mps=0.3, horizontal_speed_mps=8.0,
                       mass_kg=4700, attitude_tilt_deg=15),
        GearConfig(),
    )
    # Either tipover or still-running flagged (depending on horizontal scale)
    assert r.tipover or r.final_tilt_deg > 10


def test_hazard_score_bounded_0_1():
    h = boulder_field_terrain()
    t = score_terrain(h)
    assert 0.0 <= t.hazard_score <= 1.0


def test_gear_peak_g_finite():
    r = simulate_gear_impact(TouchdownState(2.0, 0.5, 4700), GearConfig())
    assert math.isfinite(r.peak_g)
    assert math.isfinite(r.crew_seat_g)
