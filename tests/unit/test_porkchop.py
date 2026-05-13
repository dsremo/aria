"""Unit tests for aria.simulation.porkchop.

Validates that compute_porkchop() returns physically reasonable C3 and v∞
values for Earth-Mars transfers when planetary velocity functions are provided.

Root cause of KNOWN_ISSUES bug: C3 appeared high (≈610 km²/s²) because callers
omitted v_planet_departure_fn — falling back to |v1|² instead of |v1 - v_body|².
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from aria.simulation.porkchop import compute_porkchop, PorkchopResult
from aria.simulation.mission_design import ephemeris_functions, _GM_SUN


# ── Helpers ────────────────────────────────────────────────────────────────────

def _earth_mars_result(n=20, c3_max=1000.0) -> PorkchopResult:
    er, ev = ephemeris_functions("earth")
    mr, mv = ephemeris_functions("mars")
    return compute_porkchop(
        mu_central=_GM_SUN,
        r_departure_fn=er,
        r_arrival_fn=mr,
        v_planet_departure_fn=ev,
        v_planet_arrival_fn=mv,
        dep_range_days=(0, 400),
        arr_range_days=(150, 600),
        n_dep=n,
        n_arr=n,
        c3_max_km2_s2=c3_max,
    )


# ── C3 physical range ──────────────────────────────────────────────────────────

class TestC3Range:
    def test_best_c3_within_expected_earth_mars_range(self):
        """Best C3 for Earth-Mars should be 8–50 km²/s² (Strange et al. 2002)."""
        result = _earth_mars_result()
        assert result.best_c3 < 50.0, f"Best C3 too high: {result.best_c3:.1f}"
        assert result.best_c3 > 5.0, f"Best C3 too low: {result.best_c3:.1f}"

    def test_no_garbage_c3_with_cap(self):
        """With c3_max=1000, no grid cell should exceed the cap."""
        result = _earth_mars_result(c3_max=1000.0)
        finite = result.c3_departure[np.isfinite(result.c3_departure)]
        assert float(finite.max()) <= 1000.0

    def test_missing_velocity_fn_inflates_c3(self):
        """Without v_planet_departure_fn, C3 = |v1|² — ~900 km²/s² for LEO dep."""
        er, _ = ephemeris_functions("earth")
        mr, mv = ephemeris_functions("mars")
        result_no_vel = compute_porkchop(
            mu_central=_GM_SUN,
            r_departure_fn=er,
            r_arrival_fn=mr,
            v_planet_departure_fn=None,  # intentionally omitted
            v_planet_arrival_fn=mv,
            dep_range_days=(0, 200),
            arr_range_days=(200, 400),
            n_dep=10,
            n_arr=10,
            c3_max_km2_s2=None,  # no cap so we see the full effect
        )
        finite = result_no_vel.c3_departure[np.isfinite(result_no_vel.c3_departure)]
        # |v_earth|² ≈ 887 km²/s²; without the planet's velocity subtracted,
        # C3 is always >> 100 km²/s²
        if len(finite) > 0:
            assert finite.min() > 100.0, "Expected inflated C3 without velocity fn"

    def test_best_tof_earth_mars_realistic(self):
        """Optimal TOF for Earth-Mars should be 200–500 days (Hohmann ≈259 days)."""
        result = _earth_mars_result()
        assert 150 < result.best_tof_days < 600

    def test_valid_count_majority_of_grid(self):
        """At least 50% of the grid should have valid Lambert solutions."""
        result = _earth_mars_result(n=20)
        assert result.valid_count / result.total_count >= 0.5


# ── Result structure ───────────────────────────────────────────────────────────

class TestResultStructure:
    def test_grid_shapes_match(self):
        result = _earth_mars_result(n=15)
        assert result.c3_departure.shape == (15, 15)
        assert result.v_inf_arrival.shape == (15, 15)
        assert result.tof_days.shape == (15, 15)

    def test_departure_days_is_sorted(self):
        result = _earth_mars_result(n=10)
        assert np.all(np.diff(result.departure_days) > 0)

    def test_arrival_days_is_sorted(self):
        result = _earth_mars_result(n=10)
        assert np.all(np.diff(result.arrival_days) > 0)

    def test_valid_count_lte_total_count(self):
        result = _earth_mars_result()
        assert result.valid_count <= result.total_count

    def test_best_c3_matches_grid_minimum(self):
        result = _earth_mars_result(n=15)
        finite = result.c3_departure[np.isfinite(result.c3_departure)]
        if len(finite) > 0:
            assert result.best_c3 == pytest.approx(float(finite.min()), rel=1e-6)

    def test_vinf_arrival_non_negative(self):
        result = _earth_mars_result(n=10)
        finite = result.v_inf_arrival[np.isfinite(result.v_inf_arrival)]
        assert np.all(finite >= 0.0)


# ── Other planet pairs ─────────────────────────────────────────────────────────

class TestOtherPairs:
    def test_earth_venus_c3_reasonable(self):
        er, ev = ephemeris_functions("earth")
        vr, vv = ephemeris_functions("venus")
        result = compute_porkchop(
            mu_central=_GM_SUN,
            r_departure_fn=er,
            r_arrival_fn=vr,
            v_planet_departure_fn=ev,
            v_planet_arrival_fn=vv,
            dep_range_days=(0, 600),
            arr_range_days=(0, 600),
            n_dep=15,
            n_arr=15,
        )
        # Earth-Venus min C3 ≈ 5 km²/s² (Hohmann ~145 days)
        assert result.best_c3 < 80.0

    def test_no_arrival_before_departure(self):
        er, ev = ephemeris_functions("earth")
        mr, mv = ephemeris_functions("mars")
        result = compute_porkchop(
            mu_central=_GM_SUN,
            r_departure_fn=er,
            r_arrival_fn=mr,
            v_planet_departure_fn=ev,
            v_planet_arrival_fn=mv,
            dep_range_days=(200, 400),
            arr_range_days=(0, 100),  # arrival before departure — no valid solutions
            n_dep=10,
            n_arr=10,
        )
        assert result.valid_count == 0
        assert math.isinf(result.best_c3)


# ── Multi-rev Lambert ─────────────────────────────────────────────────────────

class TestMultiRev:
    """The `max_revs` knob lets the porkchop scanner try Type-III/IV
    multi-revolution Lambert solutions (Izzo M ≥ 1).  These never *worsen*
    the result — at worst the M=0 candidate still wins per cell — so we
    test that increasing max_revs is monotone non-degrading on best C3."""

    def _result_with_revs(self, max_revs: int):
        er, ev = ephemeris_functions("earth")
        mr, mv = ephemeris_functions("mars")
        return compute_porkchop(
            mu_central=_GM_SUN,
            r_departure_fn=er, r_arrival_fn=mr,
            v_planet_departure_fn=ev, v_planet_arrival_fn=mv,
            dep_range_days=(0, 400), arr_range_days=(150, 600),
            n_dep=12, n_arr=12,
            max_revs=max_revs,
        )

    def test_max_revs_zero_is_default_behaviour(self):
        """max_revs=0 must produce the historical M=0 result."""
        r = self._result_with_revs(0)
        assert r.best_M == 0
        assert r.rev_grid is not None

    def test_max_revs_does_not_increase_best_c3(self):
        """Adding revolutions to the search can only lower or keep best C3."""
        r0 = self._result_with_revs(0)
        r2 = self._result_with_revs(2)
        # Allow a tiny float-precision slack — strict equality on the M=0
        # cell is what matters, but we test the scalar minimum here.
        assert r2.best_c3 <= r0.best_c3 + 1e-6

    def test_rev_grid_shape_matches_grid(self):
        r = self._result_with_revs(1)
        assert r.rev_grid.shape == (12, 12)

    def test_rev_grid_records_chosen_M(self):
        r = self._result_with_revs(2)
        # Every cell that has a finite C3 must have a valid M ∈ [0,2];
        # cells with no Lambert solution stay at -1.
        finite_mask = np.isfinite(r.c3_departure)
        assert finite_mask.any(), "expected at least one valid cell"
        assert (r.rev_grid[finite_mask] >= 0).all()
        assert (r.rev_grid[finite_mask] <= 2).all()

    def test_best_M_consistent_with_rev_grid(self):
        r = self._result_with_revs(2)
        if r.valid_count > 0:
            # best_M must match the cell that holds best_c3
            idx = np.unravel_index(np.argmin(r.c3_departure), r.c3_departure.shape)
            assert r.best_M == int(r.rev_grid[idx])
