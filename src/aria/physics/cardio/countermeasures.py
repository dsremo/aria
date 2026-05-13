"""Exercise countermeasure effectiveness (§4.6 of K2 scope).

Lee et al. 2015 *Aviat Space Environ Med* 86 A1 compared the ISS
ARED (Advanced Resistive Exercise Device) + treadmill + cycle
ergometer triad against earlier iRED protocols and reported ~40 %
reduction in the cardiovascular decrement. ARIA uses the multiplier
`(1 − effectiveness)` to scale down deconditioning amplitudes
(ΔPV, Δm_heart, SANS rate) when the crew meets the weekly exercise
minimum.
"""

from __future__ import annotations

# Lee et al. 2015 *Aviat Space Environ Med* 86 A1 (ARED + treadmill
# + cycle).
ARED_EFFECTIVENESS_FRACTION: float = 0.40
# Weekly exercise threshold (ISS baseline, Lee 2015).
MIN_EXERCISE_HOURS_WEEK: float = 2.0


def apply_countermeasure_reduction(
    baseline_decrement: float,
    weekly_exercise_hours: float,
    max_effectiveness: float = ARED_EFFECTIVENESS_FRACTION,
    min_hours: float = MIN_EXERCISE_HOURS_WEEK,
    saturation_hours: float = 7.0,
) -> float:
    """Reduce a baseline decrement by the ARED effectiveness curve.

    Piecewise-linear ramp:
        hours < min_hours   → 0 reduction (decrement unchanged)
        hours ≥ saturation  → max_effectiveness reduction
        otherwise            → linear in (hours − min_hours)

    Effective decrement = baseline · (1 − fraction_effective).

    Args:
        baseline_decrement: the unmodified compartment decrement
            amplitude (dimensionless, ≥ 0).
        weekly_exercise_hours: crew-reported exercise hours/week.
        max_effectiveness: Lee 2015 ~0.40 ceiling.
        min_hours: ISS baseline minimum before any reduction (2 h/wk).
        saturation_hours: hours above which no further benefit.

    Returns:
        Effective decrement amplitude (dimensionless, ≥ 0).
    """
    if baseline_decrement < 0.0:
        raise ValueError("baseline_decrement must be non-negative")
    if weekly_exercise_hours < 0.0:
        raise ValueError("weekly_exercise_hours must be non-negative")
    if not (0.0 <= max_effectiveness < 1.0):
        raise ValueError("max_effectiveness must be in [0, 1)")
    if saturation_hours <= min_hours:
        raise ValueError("saturation_hours must exceed min_hours")
    if weekly_exercise_hours <= min_hours:
        fraction = 0.0
    elif weekly_exercise_hours >= saturation_hours:
        fraction = max_effectiveness
    else:
        fraction = (
            max_effectiveness
            * (weekly_exercise_hours - min_hours)
            / (saturation_hours - min_hours)
        )
    return baseline_decrement * (1.0 - fraction)
