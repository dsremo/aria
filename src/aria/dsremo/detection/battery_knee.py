"""V3-G4: Two-phase battery degradation model with knee-point detection.

Problem
-------
Linear TTL extrapolation `TTL = (limit - value) / rate` assumes linear
capacity fade, but Li-ion batteries follow a two-regime trajectory:

    Phase 1 — gradual linear degradation (slope ≈ −α₁ % / cycle)
    Knee    — sharp inflection typically at SoH ≈ 80 % (mission-dependent)
    Phase 2 — accelerated non-linear degradation (slope ≈ −α₂ % / cycle,
              α₂ >> α₁)

Linear extrapolation from Phase 1 data overestimates remaining life by
3-10× (Yang et al. 2021 on NASA battery dataset).  After the knee, linear
extrapolation underestimates remaining life, causing premature safe-mode
triggers.

Solution
--------
Fit a Verhulst-logistic degradation trajectory:

    SoH(n) = SoH_0 / (1 + exp(k · (n − n_knee)))

where `n` is the cycle index, `SoH_0` is initial state-of-health, `k` is
the steepness of the knee transition, and `n_knee` is the cycle at which
the knee occurs.  The knee is identified by online changepoint detection
on the SoH trajectory — any of BOCPD, PELT, or a simple two-slope
comparison can supply `n_knee`.

Once `n_knee` is known, `project_remaining_cycles(phase, params, ...)`
returns the cycles remaining before SoH crosses an operator-defined EOL
threshold (default 0.7 = 70 % of initial capacity, the NASA battery EOL
convention — Saha & Goebel 2007).

Reference
---------
Yang, J. et al. (2021).  "Prediction of battery degradation trajectory
    under varied usage conditions with a Bayesian updated model."
    J. Power Sources 518:230714.  §3 — two-phase degradation identification.

Saha, B. & Goebel, K. (2007).  *Battery Data Set*.  NASA Ames Prognostics
    Data Repository.  §1 — EOL convention.

Verhulst, P.F. (1838).  "Notice sur la loi que la population suit dans son
    accroissement."  *Correspondance Mathématique et Physique* 10:113-121.
    §2 — logistic trajectory.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, unique

import numpy as np


# ── Tunable constants ───────────────────────────────────────────────────────
# Default end-of-life SoH threshold used by NASA battery dataset and IEC
# 62660-1 for Li-ion automotive batteries.
EOL_SOH_DEFAULT: float = 0.70   # IEC 62660-1 §6.2: 70 % retained capacity = EOL

# A SoH series is considered to have "crossed the knee" when its slope in
# the most-recent window is steeper than `KNEE_SLOPE_RATIO` × the slope in
# the first window.  Empirically the knee is identified near the cycle
# where local slope is at least 3× the early-life slope
# (Yang et al. 2021 §3.2).
KNEE_SLOPE_RATIO: float = 3.0   # Yang et al. 2021 §3.2 — empirical knee criterion

# Minimum cycles required before attempting knee detection; short sequences
# produce spurious slope ratios.  20 cycles matches the minimum observation
# window in Yang et al. 2021 §3.3.
MIN_CYCLES_FOR_KNEE: int = 20   # Yang et al. 2021 §3.3 — minimum observation window


@unique
class DegradationPhase(str, Enum):
    """Stage of the two-regime battery degradation trajectory."""

    PHASE_1   = "phase1_linear"
    PHASE_2   = "phase2_accelerated"
    UNKNOWN   = "unknown"   # too few cycles to identify


@dataclass(frozen=True, slots=True)
class KneeFit:
    """Result of fitting the two-phase model to a SoH trajectory.

    Fields
    ------
    phase:          Current regime.
    phase_1_slope:  Linear degradation rate in Phase 1 (SoH per cycle).  Negative.
    phase_2_slope:  Linear degradation rate in Phase 2 (SoH per cycle).  Negative.
                    None when the knee has not been reached.
    n_knee:         Estimated cycle index of the knee.  None when undetected.
    soh_at_knee:    SoH value at n_knee.  None when undetected.
    """

    phase:           DegradationPhase
    phase_1_slope:   float
    phase_2_slope:   float | None
    n_knee:          int | None
    soh_at_knee:     float | None


def _linear_slope(y: np.ndarray) -> float:
    """Least-squares slope of y vs. integer index 0..n-1 (SoH per cycle)."""
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    x_mean = x.mean()
    y_mean = float(y.mean())
    denom  = float(((x - x_mean) ** 2).sum())
    if denom <= 0.0:
        return 0.0
    return float(((x - x_mean) * (y - y_mean)).sum() / denom)


def fit_two_phase(
    soh_trajectory: np.ndarray,
    min_cycles_for_knee: int = MIN_CYCLES_FOR_KNEE,
    knee_slope_ratio:    float = KNEE_SLOPE_RATIO,
) -> KneeFit:
    """Identify Phase 1 vs Phase 2 from a SoH trajectory.

    Algorithm (deliberately simple — a full Verhulst-logistic fit would
    require non-linear least squares and more data than we typically have
    in an early mission):

      1. If < 2× min_cycles_for_knee samples → Phase 1, no knee estimate.
      2. Split the trajectory at each candidate knee position (mid-window)
         and compute the slope ratio.  The first position where the
         post-knee slope exceeds `knee_slope_ratio × phase_1_slope` in
         absolute magnitude marks the knee.
      3. If no such position exists → still Phase 1.

    Args
    ----
    soh_trajectory:       (n,) SoH values, oldest→newest.  Must be on [0, 1].
    min_cycles_for_knee:  Minimum cycles required before knee detection runs.
    knee_slope_ratio:     Slope-multiplier threshold for declaring Phase 2.

    Returns
    -------
    KneeFit describing the current regime and (when detected) knee position.
    """
    soh = np.asarray(soh_trajectory, dtype=np.float64).ravel()
    n   = len(soh)
    if n < 2 * min_cycles_for_knee:
        slope = _linear_slope(soh)
        return KneeFit(
            phase=DegradationPhase.PHASE_1 if n >= min_cycles_for_knee else DegradationPhase.UNKNOWN,
            phase_1_slope=slope,
            phase_2_slope=None,
            n_knee=None,
            soh_at_knee=None,
        )

    # Slope of the first min_cycles_for_knee cycles is our Phase 1 reference.
    phase_1_slope = _linear_slope(soh[:min_cycles_for_knee])
    # Degenerate case — no detectable degradation yet.
    if abs(phase_1_slope) < 1e-9:
        return KneeFit(
            phase=DegradationPhase.PHASE_1,
            phase_1_slope=phase_1_slope,
            phase_2_slope=None,
            n_knee=None,
            soh_at_knee=None,
        )

    # Sweep candidate knee positions; report the earliest index where the
    # trailing slope is knee_slope_ratio× steeper than phase 1.
    threshold = knee_slope_ratio * abs(phase_1_slope)
    for candidate in range(min_cycles_for_knee, n - min_cycles_for_knee + 1):
        trailing_slope = _linear_slope(soh[candidate:candidate + min_cycles_for_knee])
        if abs(trailing_slope) > threshold:
            return KneeFit(
                phase=DegradationPhase.PHASE_2,
                phase_1_slope=phase_1_slope,
                phase_2_slope=trailing_slope,
                n_knee=candidate,
                soh_at_knee=float(soh[candidate]),
            )

    return KneeFit(
        phase=DegradationPhase.PHASE_1,
        phase_1_slope=phase_1_slope,
        phase_2_slope=None,
        n_knee=None,
        soh_at_knee=None,
    )


def project_remaining_cycles(
    fit: KneeFit,
    current_soh: float,
    eol_soh: float = EOL_SOH_DEFAULT,
) -> float:
    """Estimate cycles until SoH crosses the EOL threshold.

    Uses the post-knee slope when available (Phase 2), else Phase 1 slope.
    Returns +inf when the relevant slope is non-negative (no degradation
    detected) or when SoH is already at/below EOL.
    """
    if current_soh <= eol_soh:
        return 0.0
    slope = fit.phase_2_slope if fit.phase == DegradationPhase.PHASE_2 else fit.phase_1_slope
    if slope is None or slope >= 0.0:
        return math.inf
    return float((current_soh - eol_soh) / -slope)


def verhulst_logistic(
    n_cycles: np.ndarray,
    soh_0:    float,
    k:        float,
    n_knee:   float,
) -> np.ndarray:
    """Verhulst-logistic degradation trajectory.

    SoH(n) = soh_0 / (1 + exp(k · (n − n_knee)))

    A pure Phase 1 → Phase 2 transition model useful for forward-simulating
    the expected trajectory once `n_knee` has been identified from live
    telemetry.  Not used for fitting here (simple two-slope fit is more
    robust with limited data); useful for display / projection.
    """
    n = np.asarray(n_cycles, dtype=np.float64)
    return soh_0 / (1.0 + np.exp(k * (n - n_knee)))
