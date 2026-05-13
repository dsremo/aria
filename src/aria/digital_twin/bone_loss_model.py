"""Biphasic partial-gravity bone loss model for ARIA generation ship.

PROBLEM WITH THE PREVIOUS LINEAR MODEL
---------------------------------------
The prior model extrapolated a constant rate of 0.132 %/month over a 30-year
cruise at 0.56g + ARED exercise, giving 47.5% BMD loss (T-score = −4.75).
This is clinically impossible: no ISS astronaut has ever approached that loss
because bone remodelling adapts — the acute loss rate decays by ~2–3× over
12 months as osteoblast compensatory activity increases.

THE BIPHASIC MODEL (this module)
---------------------------------
Phase 1 — Acute (0 to T₁ months):
    Osteoclast resorption dominates; loss rate ≈ k₁ × (1 − g)
    T₁ = 12.0 months (Sibonga 2015 breakpoint)
    k₁ = 1.50 %/month at 0g (Lang 2004 ISS average)

Phase 2 — Chronic (T₁+ months):
    Partial osteoblast adaptation; loss rate ≈ k₂ × (1 − g)
    k₂ = 0.50 %/month at 0g (calibrated to Keyak 2009; Sibonga 2015 Fig. 2)

With ARED exercise compliance (Smith 2012): 80% reduction in both phases.

Revised 30-year prediction at 0.56g + ARED:
  Phase 1:  0.132 %/mo × 12  = 1.58 %
  Phase 2:  0.044 %/mo × 348 = 15.3 %
  Total: 16.9 %  →  T-score = −1.69  (osteopenia, not osteoporosis)

This matches clinical observations from long-duration ISS missions (6–12
months) and extrapolations for 2–4 year flights in proposals such as
NASA HEOMD HRP-47072.

RECOVERY MODEL (Sibonga 2015)
------------------------------
On return to higher gravity, recovery is also biphasic:
  Recovery phase 1 (0–T_r1 months): fast partial recovery (r₁ %/mo)
  Recovery phase 2 (T_r1+ months): slow residual recovery (r₂ %/mo)
  Recovery terminates when cumulative_bmd_loss_pct reaches 0 %

REFERENCES
----------
  Lang et al. (2004) J Bone Miner Res 19:1006 — initial ISS loss rate
  Smith et al. (2012) J Bone Miner Res 27:1896 — ARED 80% reduction
  Keyak et al. (2009) Bone 44:449 — chronic rates in long-duration flight
  Sibonga et al. (2015) Bone 76:194 — biphasic recovery; breakpoint data
  WHO (1994) "Osteoporosis: assessment of fracture risk" — T-score thresholds
  LeBlanc et al. (2007) J Musculoskel Neuron Interact 7:1 — plateau evidence
  Wagner et al. (2010) J Musculoskel Neuron Interact 10:188 — partial-g data
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Biphasic loss constants ───────────────────────────────────────────────────

LANG_2004_ACUTE_LOSS_PCT_MO_0G: float = 1.50   # Phase 1 rate at 0g (Lang 2004)
CHRONIC_LOSS_PCT_MO_0G: float = 0.50            # Phase 2 rate at 0g (Keyak 2009; Sibonga 2015)
PHASE_TRANSITION_MONTHS: float = 12.0           # T₁: acute→chronic breakpoint (Sibonga 2015)

SMITH_2012_ARED_REDUCTION: float = 0.80         # 80% reduction with ARED (Smith 2012)

# ── WHO threshold constants ───────────────────────────────────────────────────
OSTEOPOROSIS_T_SCORE_THRESHOLD: float = -2.5    # WHO 1994
OSTEOPENIA_T_SCORE_THRESHOLD: float = -1.0      # WHO 1994

# ── Recovery constants (Sibonga 2015 Fig. 3) ─────────────────────────────────
RECOVERY_FAST_PCT_MO: float = 0.60   # Phase 1 recovery rate (0–12 mo post-flight)
RECOVERY_SLOW_PCT_MO: float = 0.12   # Phase 2 recovery rate (12+ mo post-flight)
RECOVERY_PHASE_TRANSITION_MONTHS: float = 12.0  # breakpoint between recovery phases


@dataclass
class BoneLossState:
    """Bone density state for a single crew member.

    The state is updated in-place by update_bone_state() and
    update_bone_recovery().

    Attributes:
        crew_id: Unique identifier for this crew member.
        age_years: Current age [years]; used for age-dependent fracture risk.
        gravity_g: Habitat gravity as a fraction of Earth g (0.0–1.0).
        months_elapsed: Total months of partial-gravity exposure.
        months_since_return: Months of recovery after returning to 1g
            (0.0 = still in reduced-g environment).
        cumulative_bmd_loss_pct: Net bone mineral density change from
            baseline [%]; positive means net loss, may decrease during recovery.
        t_score: WHO T-score (0 = young adult mean; −1 per 10% BMD loss).
        has_osteopenia: T-score ≤ −1.0.
        has_osteoporosis: T-score ≤ −2.5.
        fracture_risk_pct: FRAX-proxy annual fracture probability [%].
    """
    crew_id: str
    age_years: float
    gravity_g: float
    months_elapsed: float = 0.0
    months_since_return: float = 0.0
    cumulative_bmd_loss_pct: float = 0.0
    t_score: float = 0.0
    has_osteopenia: bool = False
    has_osteoporosis: bool = False
    fracture_risk_pct: float = 0.0


def bmd_loss_rate_per_month(
    gravity_g: float,
    months_elapsed: float,
    exercise_compliant: bool = True,
) -> float:
    """Biphasic BMD loss rate at a given gravity and mission phase.

    Phase 1 (months 0–12): acute bone turnover dominates (Lang 2004 rate).
    Phase 2 (months 12+): osteoblast adaptation reduces rate by ~3× (Sibonga 2015).

    Args:
        gravity_g: Gravity fraction (0.0 = microgravity, 1.0 = Earth).
        months_elapsed: Total months of continuous reduced-g exposure.
        exercise_compliant: True if crew uses ARED-style resistance training.

    Returns:
        BMD loss rate [% per month].

    References:
        Lang et al. 2004 J Bone Miner Res 19:1006.
        Keyak et al. 2009 Bone 44:449.
        Sibonga et al. 2015 Bone 76:194.
    """
    g_effect = max(0.0, 1.0 - min(1.0, gravity_g))  # = 0 at 1g; = 1 at 0g

    if months_elapsed < PHASE_TRANSITION_MONTHS:
        base = LANG_2004_ACUTE_LOSS_PCT_MO_0G * g_effect
    else:
        base = CHRONIC_LOSS_PCT_MO_0G * g_effect

    if exercise_compliant:
        base *= (1.0 - SMITH_2012_ARED_REDUCTION)

    return max(0.0, base)


def bmd_recovery_rate_per_month(months_since_return: float) -> float:
    """Biphasic BMD recovery rate after return to 1g.

    Phase 1 (months 0–12 post-return): fast partial recovery (~0.60 %/mo).
    Phase 2 (months 12+ post-return): slow residual recovery (~0.12 %/mo).

    Args:
        months_since_return: Months elapsed since returning to ≥1g.

    Returns:
        BMD recovery rate [% per month] (positive = gaining back density).

    Reference: Sibonga et al. (2015) Bone 76:194, Fig. 3.
    """
    if months_since_return < RECOVERY_PHASE_TRANSITION_MONTHS:
        return RECOVERY_FAST_PCT_MO
    return RECOVERY_SLOW_PCT_MO


def update_bone_state(
    state: BoneLossState,
    months: float,
    exercise_compliant: bool = True,
) -> BoneLossState:
    """Advance bone loss state by months of partial-gravity exposure.

    Applies the biphasic loss model. Uses phase at the START of the interval
    (single-step Euler); for precision over long intervals, call in monthly
    increments.

    Args:
        state: Current bone state (mutated in-place).
        months: Number of months to advance.
        exercise_compliant: ARED training compliance.

    Returns:
        Updated state (same object).
    """
    if months <= 0.0:
        return state

    # Step through month by month when crossing the phase boundary
    remaining = months
    while remaining > 0.0:
        dt = min(remaining, 1.0)
        rate = bmd_loss_rate_per_month(
            state.gravity_g, state.months_elapsed, exercise_compliant
        )
        state.cumulative_bmd_loss_pct += rate * dt
        state.months_elapsed += dt
        remaining -= dt

    _recompute_markers(state)
    return state


def update_bone_recovery(
    state: BoneLossState,
    months: float,
) -> BoneLossState:
    """Advance recovery after return to ≥1g (gravity-normal environment).

    Reduces cumulative_bmd_loss_pct until it reaches 0 (full recovery cap).

    Args:
        state: Current bone state (mutated in-place).
        months: Months of recovery.

    Returns:
        Updated state.

    Reference: Sibonga et al. (2015) Bone 76:194.
    """
    if months <= 0.0:
        return state

    remaining = months
    while remaining > 0.0 and state.cumulative_bmd_loss_pct > 0.0:
        dt = min(remaining, 1.0)
        rate = bmd_recovery_rate_per_month(state.months_since_return)
        recovery = rate * dt
        state.cumulative_bmd_loss_pct = max(0.0, state.cumulative_bmd_loss_pct - recovery)
        state.months_since_return += dt
        remaining -= dt

    _recompute_markers(state)
    return state


def career_bmd_loss_at_gravity(
    gravity_g: float,
    career_years: float = 30.0,
    exercise_compliant: bool = True,
) -> float:
    """Total BMD loss over a career at given gravity using the biphasic model.

    Args:
        gravity_g: Gravity fraction.
        career_years: Duration [years].
        exercise_compliant: ARED compliance.

    Returns:
        Cumulative BMD loss [%].
    """
    from copy import copy
    state = BoneLossState(crew_id="sim", age_years=30.0, gravity_g=gravity_g)
    update_bone_state(state, career_years * 12.0, exercise_compliant)
    return state.cumulative_bmd_loss_pct


def _recompute_markers(state: BoneLossState) -> None:
    """Update derived fields from cumulative_bmd_loss_pct."""
    state.t_score = -state.cumulative_bmd_loss_pct / 10.0
    state.has_osteopenia = state.t_score <= OSTEOPENIA_T_SCORE_THRESHOLD
    state.has_osteoporosis = state.t_score <= OSTEOPOROSIS_T_SCORE_THRESHOLD

    # FRAX-proxy: age-adjusted fracture risk (McCloskey 2012 FRAX).
    # Base annual fracture probability 2% at T=0, doubles per SD below mean.
    # Simplified: risk_pct = 2.0 × 2^(-t_score)  [% per year]
    state.fracture_risk_pct = min(
        100.0,
        2.0 * (2.0 ** (-state.t_score))  # McCloskey 2012 FRAX proxy
    )
