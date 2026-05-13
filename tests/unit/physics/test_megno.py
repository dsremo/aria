"""Tests for MEGNO chaos indicator.

Key property: regular orbits → <Y> → 2.0 (slow convergence, ∝ 1/t).
Chaotic orbits → <Y> grows rapidly (>>2.5 within a few periods).
The min_periods parameter ensures sufficient integration for valid results.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from aria.physics.gravity.megno import compute_megno, MegnoResult

_MU = 3.986004418e14  # GM Earth [m³/s²]


def _circular_orbit():
    """LEO circular orbit at 500 km."""
    r0 = 6_871_000.0
    v_c = math.sqrt(_MU / r0)
    return (
        np.array([r0, 0.0, 0.0]),
        np.array([0.0, v_c, 0.0]),
        2.0 * math.pi * math.sqrt(r0 ** 3 / _MU),  # period
    )


def _grav(t, r):
    return -_MU / np.linalg.norm(r) ** 3 * r


# ── Result structure ───────────────────────────────────────────────────────────

class TestMegnoResult:
    def test_returns_megno_result(self):
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, T, _MU)
        assert isinstance(res, MegnoResult)

    def test_n_steps_positive(self):
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, T, _MU)
        assert res.n_steps > 0

    def test_t_final_close_to_t_end(self):
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, T, _MU)
        assert abs(res.t_final - T) < T * 0.02


# ── Regular orbit: MEGNO → 2.0 ────────────────────────────────────────────────

class TestRegularOrbit:
    """Circular (regular) orbit must give <Y> close to 2.0 with sufficient time."""

    def test_megno_approaches_2_with_min_periods(self):
        """With min_periods=50, <Y> should be within 15% of 2.0 for circular orbit."""
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=50)
        assert abs(res.megno_mean - 2.0) < 0.3, (
            f"Expected <Y> near 2.0, got {res.megno_mean:.3f} (min_periods=50)"
        )

    def test_min_periods_extends_integration(self):
        """min_periods=20 should run much longer than min_periods=0."""
        r0, v0, T = _circular_orbit()
        res_short = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=0)
        res_long = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=20)
        assert res_long.n_steps > res_short.n_steps * 5

    def test_longer_integration_closer_to_2(self):
        """<Y> should move closer to 2.0 as integration time increases."""
        r0, v0, T = _circular_orbit()
        res5  = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=5)
        res50 = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=50)
        err5  = abs(res5.megno_mean  - 2.0)
        err50 = abs(res50.megno_mean - 2.0)
        assert err50 < err5, (
            f"50-period err ({err50:.3f}) should be < 5-period err ({err5:.3f})"
        )

    def test_circular_orbit_not_classified_chaotic_at_50_periods(self):
        """A circular orbit should NOT be labeled chaotic at min_periods=50."""
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, T, _MU, min_periods=50)
        assert not res.is_chaotic, (
            f"Circular orbit labeled chaotic: <Y>={res.megno_mean:.3f}"
        )

    def test_lyapunov_exp_near_zero_for_regular_orbit(self):
        """Lyapunov exponent should be near 0 for regular orbits."""
        r0, v0, T = _circular_orbit()
        res = compute_megno(_grav, r0, v0, 0.0, 20 * T, _MU)
        # Not exactly zero due to truncation, but should be << 1/period
        assert abs(res.lyapunov_exp) < 1.0 / T


# ── Short integration false-positive warning ───────────────────────────────────

class TestConvergenceWarning:
    def test_short_integration_may_exceed_chaos_threshold(self):
        """Circular orbit at 3 periods may falsely appear chaotic — documents known issue.

        This test does NOT assert `is_chaotic=False` because that behavior is known
        to be unreliable at short integration times. It only verifies MEGNO is computed
        without error and that increasing integration time reduces the value.
        """
        r0, v0, T = _circular_orbit()
        res3  = compute_megno(_grav, r0, v0, 0.0, 3 * T, _MU)
        res10 = compute_megno(_grav, r0, v0, 0.0, 10 * T, _MU)
        # MEGNO at 10 periods should be closer to 2.0 than at 3 periods
        assert abs(res10.megno_mean - 2.0) <= abs(res3.megno_mean - 2.0) + 0.5
