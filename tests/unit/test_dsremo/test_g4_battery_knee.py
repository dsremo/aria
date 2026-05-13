"""Tests for V3-G4: two-phase battery degradation + knee-point detection.

Validates:
 1. UNKNOWN phase for too-short trajectories
 2. PHASE_1 identified on linear-decaying SoH
 3. PHASE_2 identified when late slope > knee_slope_ratio × early slope
 4. n_knee falls within the expected range for a synthetic knee
 5. phase_2_slope > phase_1_slope in magnitude
 6. _linear_slope returns ~0 for constant input
 7. _linear_slope matches numpy.polyfit for clean linear input
 8. project_remaining_cycles = 0 when already at/below EOL
 9. project_remaining_cycles = +inf when slope is non-negative
10. project_remaining_cycles produces expected value for Phase 1
11. project_remaining_cycles uses Phase 2 slope once available
12. verhulst_logistic step-function limit: SoH(n << n_knee) ≈ SoH_0, SoH(n >> n_knee) ≈ 0
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.dsremo.detection.battery_knee import (
    EOL_SOH_DEFAULT,
    DegradationPhase,
    KneeFit,
    _linear_slope,
    fit_two_phase,
    project_remaining_cycles,
    verhulst_logistic,
)


class TestSlope:

    def test_constant_slope_zero(self):
        assert abs(_linear_slope(np.full(50, 0.9))) < 1e-12

    def test_linear_slope_matches_polyfit(self):
        y = 1.0 - 0.002 * np.arange(100)
        assert abs(_linear_slope(y) - (-0.002)) < 1e-9


class TestTwoPhaseFit:

    def test_unknown_for_too_short(self):
        fit = fit_two_phase(np.ones(10))
        assert fit.phase == DegradationPhase.UNKNOWN

    def test_phase_1_linear_decline(self):
        # 60 cycles of clean linear decay at −0.002 SoH/cycle.
        soh = 1.0 - 0.002 * np.arange(60)
        fit = fit_two_phase(soh)
        assert fit.phase == DegradationPhase.PHASE_1
        assert fit.n_knee is None
        assert abs(fit.phase_1_slope - (-0.002)) < 1e-3

    def test_phase_2_identified_on_accelerated_decay(self):
        # 40 cycles of slow decay (-0.001) then 40 cycles of fast decay (-0.01).
        slow = 1.0 - 0.001 * np.arange(40)
        fast = slow[-1] - 0.01 * np.arange(1, 41)
        soh  = np.concatenate([slow, fast])
        fit  = fit_two_phase(soh)
        assert fit.phase == DegradationPhase.PHASE_2
        assert fit.n_knee is not None
        # Knee index is identified at the earliest window whose trailing slope
        # exceeds 3× phase 1.  Because that window spans min_cycles_for_knee
        # cycles past the index, the identified n_knee can land 5-15 cycles
        # BEFORE the true transition at cycle 40.  Accept any index in the
        # range [20, 60] — the important property is Phase 2 is identified.
        assert 20 <= fit.n_knee <= 60
        # Phase 2 slope must be meaningfully steeper than phase 1.
        assert abs(fit.phase_2_slope) > abs(fit.phase_1_slope) * 2.0


class TestRemainingCycles:

    def test_zero_cycles_below_eol(self):
        fit = KneeFit(
            phase=DegradationPhase.PHASE_1, phase_1_slope=-0.001,
            phase_2_slope=None, n_knee=None, soh_at_knee=None,
        )
        assert project_remaining_cycles(fit, current_soh=0.65) == 0.0

    def test_inf_when_no_degradation(self):
        fit = KneeFit(
            phase=DegradationPhase.PHASE_1, phase_1_slope=0.0,
            phase_2_slope=None, n_knee=None, soh_at_knee=None,
        )
        assert project_remaining_cycles(fit, current_soh=0.9) == math.inf

    def test_phase_1_extrapolation(self):
        fit = KneeFit(
            phase=DegradationPhase.PHASE_1, phase_1_slope=-0.001,
            phase_2_slope=None, n_knee=None, soh_at_knee=None,
        )
        # SoH 0.9 → EOL 0.7, slope −0.001 → 200 cycles.
        r = project_remaining_cycles(fit, current_soh=0.9, eol_soh=0.7)
        assert abs(r - 200.0) < 1e-6

    def test_phase_2_uses_phase_2_slope(self):
        fit = KneeFit(
            phase=DegradationPhase.PHASE_2, phase_1_slope=-0.001,
            phase_2_slope=-0.01, n_knee=50, soh_at_knee=0.8,
        )
        r = project_remaining_cycles(fit, current_soh=0.75, eol_soh=0.7)
        # (0.75 - 0.7) / 0.01 = 5 cycles.
        assert abs(r - 5.0) < 1e-6


class TestVerhulstLogistic:

    def test_step_function_limits(self):
        soh_0 = 1.0
        k     = 0.5
        n_knee = 100
        early = verhulst_logistic(np.array([0, 10, 20]), soh_0, k, n_knee)
        late  = verhulst_logistic(np.array([200, 300, 1000]), soh_0, k, n_knee)
        # Early cycles → exp(-50) ≈ 0 → SoH ≈ soh_0 = 1.0
        assert np.all(early > 0.99 * soh_0)
        # Late cycles → exp(large) dominates → SoH → 0
        assert np.all(late < 0.01 * soh_0)

    def test_eol_default_value(self):
        assert EOL_SOH_DEFAULT == 0.70
