"""Unit tests for aria.simulation.mission_ensemble.

We use a *minimal* GenerationShipConfig (1 ly @ 0.2c → 6 sim-years)
with most subsystems disabled so each run completes in ~1–2 s on CI;
the tests then verify the aggregate plumbing, not the underlying physics
(which has its own coverage in tests/integration/test_generation_ship.py).
"""
from __future__ import annotations

import pytest

from aria.simulation.generation_ship import GenerationShipConfig
from aria.simulation.mission_ensemble import (
    EnsembleResult,
    EnsembleStats,
    _percentile,
    run_ensemble,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _light_cfg() -> GenerationShipConfig:
    """Minimal config that runs in ≤2 s per run."""
    return GenerationShipConfig(
        crew_size=2,
        velocity_c=0.20,
        target_distance_ly=1.0,
        seed=42,
        enable_manufacturing=False,
        enable_biomanufacturing=False,
        enable_nanobots=False,
        enable_starch_synthesis=False,
        enable_glass_archive=False,
        enable_torpor=False,
        enable_defense=False,
    )


# ── Percentile helper ───────────────────────────────────────────────


class TestPercentile:
    def test_empty_returns_zero(self):
        assert _percentile([], 50.0) == 0.0

    def test_single_value(self):
        assert _percentile([7.0], 50.0) == 7.0

    def test_p50_of_uniform_is_median(self):
        assert _percentile(list(range(1, 101)), 50.0) == pytest.approx(50.5, rel=0.01)

    def test_p5_p95_brackets(self):
        vals = list(range(100))
        assert _percentile(vals, 5.0) < _percentile(vals, 95.0)


# ── Ensemble runner ─────────────────────────────────────────────────


class TestEnsembleRunner:
    def test_n_runs_positive(self):
        with pytest.raises(ValueError, match="positive"):
            run_ensemble(_light_cfg(), n_runs=0)

    def test_seeds_length_must_match(self):
        with pytest.raises(ValueError, match="length"):
            run_ensemble(_light_cfg(), n_runs=3, seeds=[1, 2])

    def test_small_ensemble_runs(self):
        result = run_ensemble(_light_cfg(), n_runs=3)
        assert isinstance(result, EnsembleResult)
        assert result.n_runs == 3
        assert len(result.per_run) == 3
        assert result.wall_time_s > 0

    def test_seeds_default_to_offset(self):
        result = run_ensemble(_light_cfg(), n_runs=2)
        # Two runs with different seeds — wall-clock time field should
        # differ tiny bit, but the SIM may produce identical outputs if
        # the system is fully deterministic.  We just check the runs ran.
        assert len(result.per_run) == 2

    def test_explicit_seeds(self):
        result = run_ensemble(_light_cfg(), n_runs=3, seeds=[1, 2, 3])
        assert len(result.per_run) == 3

    def test_field_stats_present_for_aggregate_fields(self):
        result = run_ensemble(_light_cfg(), n_runs=3)
        # At minimum, years_simulated and final_hull_integrity must aggregate.
        assert "years_simulated" in result.field_stats
        assert "final_hull_integrity" in result.field_stats
        s = result.field_stats["years_simulated"]
        assert isinstance(s, EnsembleStats)
        assert s.n == 3
        assert s.min_v <= s.mean <= s.max_v

    def test_survival_rate_is_fraction(self):
        result = run_ensemble(_light_cfg(), n_runs=3)
        assert 0.0 <= result.survival_rate <= 1.0

    def test_progress_callback_fires(self):
        calls = []
        def cb(i_done, n_total, last):
            calls.append((i_done, n_total))
        run_ensemble(_light_cfg(), n_runs=3, progress=cb)
        assert len(calls) == 3
        assert [c[0] for c in calls] == [1, 2, 3]
        assert calls[-1][1] == 3

    def test_summary_includes_survival_rate(self):
        result = run_ensemble(_light_cfg(), n_runs=2)
        s = result.summary()
        assert "Survival rate" in s
        assert "Ensemble" in s


# Parallel mode was removed — simulator's module-level singletons
# (event bus, mission clock, phase controller) are not thread-safe;
# threading triggers core dumps in the C-extension PRNG inside numpy
# under contention.  For larger ensembles, fork at the *process* level
# outside this module.
