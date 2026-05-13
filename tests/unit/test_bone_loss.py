"""Tests for biphasic partial-gravity bone loss model.

Validates:
1.  Phase 1 (0–12 mo): acute rate = k₁ × (1 − g) (Lang 2004).
2.  Phase 2 (12+ mo): chronic rate = k₂ × (1 − g) (Keyak 2009; Sibonga 2015).
3.  Phase 2 rate is ~3× lower than Phase 1.
4.  ARED exercise reduces both phases by 80% (Smith 2012).
5.  At 1g, loss rate is always 0 regardless of phase or exercise.
6.  update_bone_state steps through phase boundary correctly.
7.  30-year career at 0.56g + ARED gives ~16–18% BMD loss (NOT 47.5%).
8.  T-score = cumulative_bmd_loss_pct / (−10).
9.  has_osteopenia flag at T ≤ −1.0; has_osteoporosis at T ≤ −2.5.
10. fracture_risk_pct = 2.0 × 2^(−t_score) [FRAX proxy].
11. Recovery Phase 1 (0–12 mo post-return): 0.60 %/mo.
12. Recovery Phase 2 (12+ mo post-return): 0.12 %/mo.
13. Recovery caps at 0% (no super-normal bone density).
14. update_bone_state with months=0 is a no-op.
15. BoneLossState months_since_return increments during recovery.
16. Osteoporosis not reached at 30 years with ARED at 0.56g.
"""

from __future__ import annotations

import math

import pytest

from aria.digital_twin.bone_loss_model import (
    CHRONIC_LOSS_PCT_MO_0G,
    LANG_2004_ACUTE_LOSS_PCT_MO_0G,
    OSTEOPENIA_T_SCORE_THRESHOLD,
    OSTEOPOROSIS_T_SCORE_THRESHOLD,
    PHASE_TRANSITION_MONTHS,
    RECOVERY_FAST_PCT_MO,
    RECOVERY_PHASE_TRANSITION_MONTHS,
    RECOVERY_SLOW_PCT_MO,
    SMITH_2012_ARED_REDUCTION,
    BoneLossState,
    bmd_loss_rate_per_month,
    bmd_recovery_rate_per_month,
    career_bmd_loss_at_gravity,
    update_bone_recovery,
    update_bone_state,
)


def _fresh(gravity_g: float = 0.56) -> BoneLossState:
    return BoneLossState(crew_id="test", age_years=35.0, gravity_g=gravity_g)


# ── Loss rate ─────────────────────────────────────────────────────────────────

class TestBmdLossRatePhase1:
    """Phase 1: months_elapsed < 12."""

    def test_0g_no_exercise_matches_lang2004(self):
        rate = bmd_loss_rate_per_month(0.0, 0.0, exercise_compliant=False)
        assert abs(rate - LANG_2004_ACUTE_LOSS_PCT_MO_0G) < 1e-9

    def test_1g_always_zero_phase1(self):
        assert bmd_loss_rate_per_month(1.0, 0.0) == 0.0

    def test_partial_gravity_linear_phase1(self):
        g = 0.56
        rate = bmd_loss_rate_per_month(g, 0.0, exercise_compliant=False)
        expected = LANG_2004_ACUTE_LOSS_PCT_MO_0G * (1.0 - g)
        assert abs(rate - expected) < 1e-9

    def test_ared_reduces_phase1_by_80pct(self):
        no_ex = bmd_loss_rate_per_month(0.0, 0.0, exercise_compliant=False)
        with_ex = bmd_loss_rate_per_month(0.0, 0.0, exercise_compliant=True)
        assert abs(with_ex / no_ex - (1.0 - SMITH_2012_ARED_REDUCTION)) < 1e-9

    def test_rate_nonnegative_at_0g_phase1(self):
        assert bmd_loss_rate_per_month(0.0, 0.0) >= 0.0

    def test_clamp_gravity_above_1g(self):
        assert bmd_loss_rate_per_month(1.5, 0.0) == 0.0

    def test_clamp_gravity_below_0g(self):
        # gravity < 0 treated as 0; still valid result (not negative)
        assert bmd_loss_rate_per_month(-0.1, 0.0) >= 0.0


class TestBmdLossRatePhase2:
    """Phase 2: months_elapsed >= 12."""

    def test_0g_no_exercise_matches_chronic_rate(self):
        rate = bmd_loss_rate_per_month(0.0, PHASE_TRANSITION_MONTHS,
                                       exercise_compliant=False)
        assert abs(rate - CHRONIC_LOSS_PCT_MO_0G) < 1e-9

    def test_phase2_three_times_lower_than_phase1(self):
        p1 = bmd_loss_rate_per_month(0.0, 0.0, exercise_compliant=False)
        p2 = bmd_loss_rate_per_month(0.0, PHASE_TRANSITION_MONTHS,
                                     exercise_compliant=False)
        assert p1 / p2 == pytest.approx(3.0, rel=0.01)

    def test_1g_always_zero_phase2(self):
        assert bmd_loss_rate_per_month(1.0, 24.0) == 0.0

    def test_ared_reduces_phase2_by_80pct(self):
        no_ex = bmd_loss_rate_per_month(0.0, 24.0, exercise_compliant=False)
        with_ex = bmd_loss_rate_per_month(0.0, 24.0, exercise_compliant=True)
        assert abs(with_ex / no_ex - (1.0 - SMITH_2012_ARED_REDUCTION)) < 1e-9

    def test_partial_gravity_phase2(self):
        g = 0.38  # Mars gravity
        rate = bmd_loss_rate_per_month(g, 24.0, exercise_compliant=False)
        expected = CHRONIC_LOSS_PCT_MO_0G * (1.0 - g)
        assert abs(rate - expected) < 1e-9

    def test_phase_transition_at_exact_12_months(self):
        # At exactly 12 months, Phase 2 rate applies
        rate_11 = bmd_loss_rate_per_month(0.0, 11.9, exercise_compliant=False)
        rate_12 = bmd_loss_rate_per_month(0.0, 12.0, exercise_compliant=False)
        assert rate_11 == pytest.approx(LANG_2004_ACUTE_LOSS_PCT_MO_0G, rel=0.01)
        assert rate_12 == pytest.approx(CHRONIC_LOSS_PCT_MO_0G, rel=0.01)


# ── Recovery rate ──────────────────────────────────────────────────────────────

class TestBmdRecoveryRate:

    def test_early_recovery_fast(self):
        assert bmd_recovery_rate_per_month(0.0) == RECOVERY_FAST_PCT_MO

    def test_late_recovery_slow(self):
        assert bmd_recovery_rate_per_month(RECOVERY_PHASE_TRANSITION_MONTHS) == RECOVERY_SLOW_PCT_MO

    def test_fast_greater_than_slow(self):
        assert RECOVERY_FAST_PCT_MO > RECOVERY_SLOW_PCT_MO

    def test_at_11_months_still_fast(self):
        assert bmd_recovery_rate_per_month(11.9) == RECOVERY_FAST_PCT_MO

    def test_at_12_months_switches_slow(self):
        assert bmd_recovery_rate_per_month(12.0) == RECOVERY_SLOW_PCT_MO


# ── update_bone_state ─────────────────────────────────────────────────────────

class TestUpdateBoneState:

    def test_zero_months_noop(self):
        state = _fresh()
        update_bone_state(state, 0.0)
        assert state.cumulative_bmd_loss_pct == 0.0
        assert state.months_elapsed == 0.0

    def test_negative_months_noop(self):
        state = _fresh()
        update_bone_state(state, -5.0)
        assert state.cumulative_bmd_loss_pct == 0.0

    def test_accumulates_loss(self):
        state = _fresh(gravity_g=0.56)
        update_bone_state(state, 6.0)
        assert state.cumulative_bmd_loss_pct > 0.0
        assert state.months_elapsed == pytest.approx(6.0)

    def test_phase_boundary_crossed_correctly(self):
        """Stepwise across T₁ should yield less total loss than pure Phase 1."""
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 24.0, exercise_compliant=False)
        # Phase1: 1.50 × 12 = 18, Phase2: 0.50 × 12 = 6 → total 24
        expected = 1.50 * 12.0 + 0.50 * 12.0
        assert abs(state.cumulative_bmd_loss_pct - expected) < 0.05

    def test_returns_same_state_object(self):
        state = _fresh()
        returned = update_bone_state(state, 3.0)
        assert returned is state

    def test_1g_no_loss_ever(self):
        state = _fresh(gravity_g=1.0)
        update_bone_state(state, 360.0)
        assert state.cumulative_bmd_loss_pct == 0.0
        assert not state.has_osteoporosis

    def test_t_score_computed_correctly(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 20.0, exercise_compliant=False)
        expected_t = -state.cumulative_bmd_loss_pct / 10.0
        assert abs(state.t_score - expected_t) < 1e-9

    def test_osteopenia_flag_set(self):
        # At 0g, 12 months no exercise → 18% loss → T = −1.8 → osteopenia
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0, exercise_compliant=False)
        assert state.t_score <= OSTEOPENIA_T_SCORE_THRESHOLD
        assert state.has_osteopenia

    def test_osteoporosis_flag_set(self):
        # At 0g, 25 months no exercise:
        # Phase 1: 18%, Phase 2: 0.50×13=6.5% → 24.5% → T=−2.45 ... need more
        # 0g, 30 months no exercise: 18 + 0.50×18=9 = 27% → T=−2.7
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 30.0, exercise_compliant=False)
        assert state.has_osteoporosis
        assert state.t_score <= OSTEOPOROSIS_T_SCORE_THRESHOLD

    def test_frax_proxy_at_t_zero(self):
        state = _fresh(gravity_g=1.0)
        update_bone_state(state, 1.0)  # 1g, no loss
        # FRAX proxy: 2.0 × 2^(−0) = 2.0
        assert abs(state.fracture_risk_pct - 2.0) < 0.01

    def test_frax_increases_with_loss(self):
        s1 = _fresh(gravity_g=0.0)
        s2 = _fresh(gravity_g=0.0)
        update_bone_state(s1, 6.0, exercise_compliant=False)
        update_bone_state(s2, 24.0, exercise_compliant=False)
        assert s2.fracture_risk_pct > s1.fracture_risk_pct

    def test_frax_capped_at_100(self):
        # extreme case: no exercise, 0g, 200 months
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 200.0, exercise_compliant=False)
        assert state.fracture_risk_pct <= 100.0


# ── update_bone_recovery ──────────────────────────────────────────────────────

class TestUpdateBoneRecovery:

    def test_recovery_reduces_bmd_loss(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0, exercise_compliant=False)  # 18% loss
        loss_before = state.cumulative_bmd_loss_pct
        update_bone_recovery(state, 6.0)
        assert state.cumulative_bmd_loss_pct < loss_before

    def test_recovery_increments_months_since_return(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0, exercise_compliant=False)
        update_bone_recovery(state, 6.0)
        assert state.months_since_return == pytest.approx(6.0)

    def test_full_recovery_caps_at_zero(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 6.0, exercise_compliant=False)  # ~9% loss
        update_bone_recovery(state, 48.0)  # far more recovery time than needed
        assert state.cumulative_bmd_loss_pct == 0.0

    def test_recovery_fast_phase_rate(self):
        """6 months recovery at fast rate: ~3.6% recovery."""
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0, exercise_compliant=False)  # 18% loss
        update_bone_recovery(state, 6.0)
        # fast phase: 0.60 %/mo × 6 = 3.6
        expected_loss = 18.0 - RECOVERY_FAST_PCT_MO * 6.0
        assert abs(state.cumulative_bmd_loss_pct - expected_loss) < 0.1

    def test_zero_months_recovery_noop(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0, exercise_compliant=False)
        loss_before = state.cumulative_bmd_loss_pct
        update_bone_recovery(state, 0.0)
        assert state.cumulative_bmd_loss_pct == loss_before

    def test_recovery_returns_same_state(self):
        state = _fresh(gravity_g=0.0)
        update_bone_state(state, 12.0)
        returned = update_bone_recovery(state, 3.0)
        assert returned is state

    def test_no_recovery_above_zero_baseline(self):
        state = _fresh(gravity_g=1.0)
        state.cumulative_bmd_loss_pct = 0.0  # already at baseline
        update_bone_recovery(state, 12.0)
        assert state.cumulative_bmd_loss_pct == 0.0


# ── career_bmd_loss_at_gravity ────────────────────────────────────────────────

class TestCareerBmdLoss:

    def test_30yr_at_0_56g_ared_is_realistic(self):
        """Revised prediction: ~16–18% BMD loss (NOT the impossible 47.5%)."""
        loss = career_bmd_loss_at_gravity(0.56, career_years=30,
                                          exercise_compliant=True)
        assert 14.0 < loss < 22.0, f"Expected ~17%, got {loss:.1f}%"

    def test_30yr_no_exercise_higher_than_exercise(self):
        with_ex = career_bmd_loss_at_gravity(0.56, 30, exercise_compliant=True)
        no_ex = career_bmd_loss_at_gravity(0.56, 30, exercise_compliant=False)
        assert no_ex > with_ex

    def test_1g_career_zero_loss(self):
        assert career_bmd_loss_at_gravity(1.0, 30) == 0.0

    def test_higher_gravity_less_loss(self):
        loss_mars = career_bmd_loss_at_gravity(0.38, 30, exercise_compliant=True)
        loss_luna = career_bmd_loss_at_gravity(0.165, 30, exercise_compliant=True)
        assert loss_mars < loss_luna

    def test_longer_career_more_loss(self):
        loss_10 = career_bmd_loss_at_gravity(0.56, 10)
        loss_30 = career_bmd_loss_at_gravity(0.56, 30)
        assert loss_30 > loss_10

    def test_no_osteoporosis_30yr_ared_0_56g(self):
        """At 0.56g + ARED, 30 years: T-score should stay above −2.5 threshold."""
        loss = career_bmd_loss_at_gravity(0.56, 30, exercise_compliant=True)
        t_score = -loss / 10.0
        assert t_score > OSTEOPOROSIS_T_SCORE_THRESHOLD, (
            f"T={t_score:.2f} reached osteoporosis at 0.56g + ARED — model error"
        )

    def test_phase1_contribution_capped(self):
        """Phase 1 runs only 12 months; phase 2 dominates in long missions."""
        loss = career_bmd_loss_at_gravity(0.0, 30, exercise_compliant=False)
        # Phase 1: 1.50 × 12 = 18%, Phase 2: 0.50 × 348 = 174% → 192% (very high)
        # vs pure-Phase-1 extrapolation: 1.50 × 360 = 540%
        # Ensures biphasic is far less than naive extrapolation
        naive = LANG_2004_ACUTE_LOSS_PCT_MO_0G * 30 * 12
        assert loss < naive * 0.5
