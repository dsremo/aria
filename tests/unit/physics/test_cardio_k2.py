"""Unit tests for Pod K2 — cardiovascular deconditioning (P1-10).

Benchmarks:
  - Convertino 1996 *J Appl Physiol* 81 7 — biphasic PV fit.
  - Pavy-Le Traon et al. 2007 *EJAP* 101 143 Fig 4 — 60-d HDT PV ≈ 87 %.
  - Perhonen 2001 *J Appl Physiol* 91 645 — 8 % cardiac mass loss at 6 wk.
  - Buckey et al. 1996 *J Appl Physiol* 81 7 Table 3 — 64 % presyncope.
  - Hargens & Vico 2016 *EJAP* 116 29 — 2 L cephalic fluid shift.
  - Mader et al. 2011 *Ophthalmology* 118 2058 — SANS cohort.
  - Lee et al. 2015 *Aviat Space Environ Med* 86 A1 — ARED 40 %.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.cardio import (
    ARED_EFFECTIVENESS_FRACTION,
    CARDIAC_MASS_ALPHA,
    CONVERTINO_A_FAST,
    CONVERTINO_A_SLOW,
    FLUID_SHIFT_DELTA_V_MAX_L,
    SANS_K_PER_DAY,
    SANS_ONSET_DAYS,
    apply_countermeasure_reduction,
    cardiac_mass_retention,
    cephalic_fluid_volume,
    orthostatic_intolerance_probability,
    plasma_volume_fraction,
    sans_probability,
)


# ──────────────────────────────────────────────────────────────────────
#  Cephalic fluid shift (Hargens 2016)
# ──────────────────────────────────────────────────────────────────────


def test_cephalic_fluid_zero_time_returns_initial():
    v = cephalic_fluid_volume(time_s=0.0, local_g_m_s2=0.0, initial_volume_l=0.5)
    assert v == 0.5


def test_cephalic_fluid_saturation_hargens_2016():
    """After many time constants at g = 0 the shift should approach
    ΔV_max = 2 L (Hargens & Vico 2016)."""
    v = cephalic_fluid_volume(
        time_s=20.0 * 3600.0,  # 20 hours >> 6 h tau
        local_g_m_s2=0.0,
    )
    assert v == pytest.approx(FLUID_SHIFT_DELTA_V_MAX_L, rel=0.05)


def test_cephalic_fluid_at_1g_is_zero():
    v = cephalic_fluid_volume(time_s=24.0 * 3600.0, local_g_m_s2=9.80665)
    assert v == 0.0


# ──────────────────────────────────────────────────────────────────────
#  Plasma volume (Convertino 1996 + Pavy-Le Traon 2007)
# ──────────────────────────────────────────────────────────────────────


def test_pv_baseline_at_time_zero():
    frac = plasma_volume_fraction(time_hours=0.0, local_g_m_s2=0.0)
    assert frac == pytest.approx(1.0, rel=1.0e-12)


def test_pv_fraction_pavy_le_traon_60d_hdt():
    """Pavy-Le Traon 2007 Fig 4: 60-d HDT → PV ≈ 87 % at g = 0.

    Convertino 1996 steady-state fit: 1 − (A_fast + A_slow) = 0.87.
    """
    frac = plasma_volume_fraction(time_hours=60.0 * 24.0, local_g_m_s2=0.0)
    expected = 1.0 - (CONVERTINO_A_FAST + CONVERTINO_A_SLOW)
    assert frac == pytest.approx(expected, abs=1.0e-3)
    assert 0.86 < frac < 0.88


def test_pv_fraction_at_1g_is_unchanged():
    """No hypogravity deficit → no PV loss."""
    frac = plasma_volume_fraction(time_hours=100.0 * 24.0, local_g_m_s2=9.80665)
    assert frac == pytest.approx(1.0, rel=1.0e-12)


def test_pv_fraction_partial_g_linear_scaling():
    """At 0.5 g the decrement is half of the full 0-g decrement."""
    t = 30.0 * 24.0  # 30 days
    d_0g = 1.0 - plasma_volume_fraction(t, local_g_m_s2=0.0)
    d_half = 1.0 - plasma_volume_fraction(t, local_g_m_s2=0.5 * 9.80665)
    assert d_half == pytest.approx(0.5 * d_0g, rel=1.0e-12)


# ──────────────────────────────────────────────────────────────────────
#  Cardiac mass (Perhonen 2001)
# ──────────────────────────────────────────────────────────────────────


def test_cardiac_mass_perhonen_6wk_8pct_loss():
    """Perhonen 2001: ~8 % mass loss at 6 weeks HDT (42 days).

    Model: 1 − α·(1 − exp(−42/21)) = 1 − 0.10·(1 − e⁻²) ≈ 0.914.
    """
    m = cardiac_mass_retention(time_days=42.0, local_g_m_s2=0.0)
    expected = 1.0 - CARDIAC_MASS_ALPHA * (1.0 - math.exp(-42.0 / 21.0))
    assert m == pytest.approx(expected, rel=1.0e-12)
    assert 0.90 < m < 0.93


def test_cardiac_mass_at_1g_is_unchanged():
    m = cardiac_mass_retention(time_days=200.0, local_g_m_s2=9.80665)
    assert m == pytest.approx(1.0, rel=1.0e-12)


# ──────────────────────────────────────────────────────────────────────
#  Orthostatic intolerance (Buckey 1996)
# ──────────────────────────────────────────────────────────────────────


def test_orthostatic_probability_bounds_in_unit_interval():
    p = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=0.0, mission_duration_days=0.0
    )
    assert 0.0 <= p <= 1.0


def test_orthostatic_probability_monotone_in_pv_loss():
    p_low = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=0.0, mission_duration_days=12.0
    )
    p_hi = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=20.0, mission_duration_days=12.0
    )
    assert p_hi > p_low


def test_orthostatic_probability_buckey_1996_headline():
    """Buckey 1996 Table 3: 64 % presyncope at ΔPV ≈ 13 % after 12-d
    shuttle flights. The default coefficients are tuned to reproduce
    this within 2 percentage points."""
    p = orthostatic_intolerance_probability(
        plasma_volume_loss_percent=13.0, mission_duration_days=12.0
    )
    assert 0.60 < p < 0.68, f"P_OI = {p:.3f}"


# ──────────────────────────────────────────────────────────────────────
#  SANS (Mader 2011 / Lee 2018)
# ──────────────────────────────────────────────────────────────────────


def test_sans_probability_zero_before_onset():
    p = sans_probability(time_days=10.0, local_g_m_s2=0.0)
    assert p == 0.0
    assert SANS_ONSET_DAYS == 30.0


def test_sans_probability_monotone_after_onset():
    p1 = sans_probability(time_days=60.0, local_g_m_s2=0.0)
    p2 = sans_probability(time_days=180.0, local_g_m_s2=0.0)
    assert 0.0 < p1 < p2


def test_sans_probability_zero_at_1g():
    p = sans_probability(time_days=365.0, local_g_m_s2=9.80665)
    assert p == 0.0


def test_sans_k_parameter_mader():
    assert SANS_K_PER_DAY == 0.003


# ──────────────────────────────────────────────────────────────────────
#  Countermeasures (Lee 2015)
# ──────────────────────────────────────────────────────────────────────


def test_ared_effectiveness_lee_2015():
    assert ARED_EFFECTIVENESS_FRACTION == 0.40


def test_no_exercise_no_reduction():
    reduced = apply_countermeasure_reduction(
        baseline_decrement=0.13, weekly_exercise_hours=0.0
    )
    assert reduced == pytest.approx(0.13, rel=1.0e-12)


def test_full_exercise_full_reduction():
    reduced = apply_countermeasure_reduction(
        baseline_decrement=0.13, weekly_exercise_hours=10.0
    )
    assert reduced == pytest.approx(0.13 * (1.0 - 0.40), rel=1.0e-12)


def test_partial_exercise_linear_reduction():
    """At midway between min (2 h) and saturation (7 h) the
    reduction should be half of the maximum."""
    reduced = apply_countermeasure_reduction(
        baseline_decrement=1.0, weekly_exercise_hours=4.5
    )
    assert reduced == pytest.approx(1.0 - 0.20, rel=1.0e-12)
