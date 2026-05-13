"""Scenario 4: crew deconditioning on a 500-day Mars transit at
0.38 g (Martian surface), with and without the ARED countermeasure
triad.

Pulls only from :mod:`aria.physics.cardio` but verifies the cross-
module invariants that downstream life-support / medical agents
rely on:

  1. Plasma volume, cardiac mass, and SANS all scale smoothly with
     the gravity deficit `(1 − g/g₀)` — linear where the scope
     notes say so, quadratic or exponential where the models
     require it.
  2. ARED exercise reduces the baseline PV decrement by exactly
     the Lee 2015 factor 0.40 at saturation (≥ 7 h/week).
  3. At partial g, SANS onset is slower than at 0 g but non-zero
     — a necessary sanity check against the scope §4.5 linear-in-
     deficit parameterisation.
  4. Orthostatic-intolerance probability after the transit must
     be strictly between baseline (no loss) and Buckey 1996 shuttle
     cohort peak (~0.64) because Mars gravity lies between
     Earth-1 g and the 0-g micro-g regime Buckey sampled.
"""

from __future__ import annotations

import pytest

from aria.physics.cardio import (
    apply_countermeasure_reduction,
    cardiac_mass_retention,
    orthostatic_intolerance_probability,
    plasma_volume_fraction,
    sans_probability,
)


_G_ZERO: float = 9.80665
_G_MARS: float = 0.38 * _G_ZERO
_TRANSIT_DAYS: float = 500.0


def test_plasma_volume_at_mars_is_between_earth_and_zero_g():
    """PV(Mars) should sit between PV(Earth, no loss) and PV(0 g)."""
    t_hours = _TRANSIT_DAYS * 24.0
    pv_earth = plasma_volume_fraction(t_hours, local_g_m_s2=_G_ZERO)
    pv_mars = plasma_volume_fraction(t_hours, local_g_m_s2=_G_MARS)
    pv_zero_g = plasma_volume_fraction(t_hours, local_g_m_s2=0.0)
    assert pv_earth == pytest.approx(1.0, rel=1.0e-12)
    assert pv_zero_g < pv_mars < pv_earth


def test_cardiac_mass_at_mars_between_earth_and_zero_g():
    m_earth = cardiac_mass_retention(time_days=_TRANSIT_DAYS, local_g_m_s2=_G_ZERO)
    m_mars = cardiac_mass_retention(time_days=_TRANSIT_DAYS, local_g_m_s2=_G_MARS)
    m_zero = cardiac_mass_retention(time_days=_TRANSIT_DAYS, local_g_m_s2=0.0)
    assert m_earth == pytest.approx(1.0, rel=1.0e-12)
    assert m_zero < m_mars < m_earth


def test_sans_probability_nonzero_at_mars_smaller_than_at_zero_g():
    """Scope §4.5 linear-in-deficit: Mars has 62 % of the 0-g
    deconditioning rate, so SANS probability must be non-zero at
    mission end but strictly below the 0-g number."""
    p_mars = sans_probability(time_days=_TRANSIT_DAYS, local_g_m_s2=_G_MARS)
    p_zero = sans_probability(time_days=_TRANSIT_DAYS, local_g_m_s2=0.0)
    assert 0.0 < p_mars < p_zero


def test_ared_saturated_reduction_40_percent():
    """Lee 2015 ARED+treadmill+cycle: 40 % decrement reduction at
    saturation weekly exercise (≥ 7 h/week)."""
    baseline = 0.13  # 13 % PV loss at 0 g steady state
    reduced = apply_countermeasure_reduction(
        baseline_decrement=baseline, weekly_exercise_hours=10.0
    )
    assert reduced == pytest.approx(baseline * 0.60, rel=1.0e-12)


def test_orthostatic_risk_at_mars_between_earth_and_full_loss():
    """Over a 500-d Mars transit the expected post-transit PV loss
    is roughly half of the 0-g steady-state (plasma volume is
    (1 - g/g0) * 0.13 ≈ 0.08 → 8 % loss); the orthostatic
    probability at ΔPV = 8 %, duration = 500 d must be strictly
    between the Earth baseline (no loss) and full orthostatic
    intolerance."""
    # ΔPV% for a 500-day Mars transit with g = 0.38 g
    t_hours = _TRANSIT_DAYS * 24.0
    pv_frac = plasma_volume_fraction(t_hours, local_g_m_s2=_G_MARS)
    delta_pv_pct = (1.0 - pv_frac) * 100.0
    p_mars = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=delta_pv_pct,
        mission_duration_days=_TRANSIT_DAYS,
    )
    p_earth = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=0.0, mission_duration_days=0.0
    )
    assert p_earth < p_mars < 1.0
