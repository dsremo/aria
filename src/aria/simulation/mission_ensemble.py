"""Monte Carlo ensemble runner for generation-ship simulations.

Why this exists
---------------
A single generation-ship run with one PRNG seed says "this exact roll
of the dice produced this outcome".  For mission-design honesty we
want **percentile bands**: "across 1000 stochastic realisations of the
same config, the crew survival rate is 92 %, the 5th-percentile fuel
margin is 12 %, the median final γ is 1.005".  ARIA already exposes a
``seed`` knob on ``GenerationShipConfig`` — this module fans out N
runs and aggregates the field distributions.

The runner is *sequential* by design — the underlying simulator uses
module-level singletons (event bus, mission clock, phase controller,
trajectory state) which are not thread-safe; running multiple
``GenerationShipSimulation`` instances in threads causes core dumps
when subsystems race on the singleton state machine.  Sequential N=100
runs takes ~10 minutes for an Alpha-Centauri config — fine for nightly
CI.  For larger ensembles, fork at the *process* level outside this
module (each process gets its own singleton namespace).

Outputs
-------
* ``EnsembleStats`` per numeric field — min, max, mean, median, P5, P95, std.
* ``survival_rate`` — fraction of runs where ``ship_survived``.
* ``failure_reasons`` — Counter over ``failure_reason`` strings.
* ``per_run`` — list of every individual ``GenerationShipResults`` for
  ad-hoc downstream slicing.

References
----------
* Ross, S.  *Simulation*, 5th ed., Academic Press 2013 — basic Monte
  Carlo error bounds: σ_mean ≈ σ_pop / √N.  At N=100 the 95 % CI on a
  proportion is ±10 %, at N=1000 it's ±3 %.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from aria.simulation.generation_ship import (
    GenerationShipConfig,
    GenerationShipResults,
    GenerationShipSimulation,
)


@dataclass
class EnsembleStats:
    """Distribution summary for a single numeric field."""
    field_name: str
    n: int
    mean: float
    median: float
    std: float
    min_v: float
    max_v: float
    p05: float
    p95: float


@dataclass
class EnsembleResult:
    """Full output of a Monte Carlo ensemble run."""
    config_mode: str
    n_runs: int
    wall_time_s: float
    survival_rate: float
    failure_reasons: dict[str, int] = field(default_factory=dict)
    field_stats: dict[str, EnsembleStats] = field(default_factory=dict)
    per_run: list[GenerationShipResults] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{'='*62}",
            f"  Ensemble: {self.config_mode}, N={self.n_runs} runs",
            f"  Wall time: {self.wall_time_s:.1f} s",
            f"  Survival rate: {self.survival_rate:.1%}",
            f"{'='*62}",
            f"  {'field':<30} {'mean':>10} {'P5':>10} {'P95':>10}",
        ]
        for name, s in self.field_stats.items():
            lines.append(f"  {name:<30} {s.mean:>10.3f} {s.p05:>10.3f} {s.p95:>10.3f}")
        if self.failure_reasons:
            lines.append(f"  Top failure reasons:")
            for reason, count in sorted(self.failure_reasons.items(),
                                         key=lambda kv: -kv[1])[:5]:
                lines.append(f"    {count:4d}× {reason}")
        return "\n".join(lines)


# ── Field discovery ─────────────────────────────────────────────────


# Numeric fields on GenerationShipResults that are worth aggregating.
# We hard-code the list because Python's dataclass introspection picks
# up dict / set / list fields too, and aggregating those is meaningless.
_AGGREGATE_FIELDS = (
    "years_simulated",
    "total_events",
    "wall_time_s",
    "final_fuel_fraction",
    "final_hull_integrity",
    "final_crew_count",
    "final_crew_generation",
    "final_food_production_ratio",
    "challenges_terminal",
    "lorentz_gamma",
    "ship_time_years",
    "earth_time_years",
    "cumulative_dose_msv",
    "clock_consensus_error_s",
    "operational_clocks",
    "electrical_efficiency",
    "structural_fatigue_damage",
    "co2_ppm",
    "archive_intact",
    "nanobot_repairs",
    "torpor_food_saved_pct",
)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation percentile.  ``p`` in [0, 100]."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _aggregate_field(field_name: str, values: list[float]) -> EnsembleStats:
    sorted_vals = sorted(values)
    return EnsembleStats(
        field_name=field_name,
        n=len(values),
        mean=statistics.fmean(values) if values else 0.0,
        median=statistics.median(values) if values else 0.0,
        std=statistics.pstdev(values) if len(values) > 1 else 0.0,
        min_v=min(values) if values else 0.0,
        max_v=max(values) if values else 0.0,
        p05=_percentile(sorted_vals, 5.0),
        p95=_percentile(sorted_vals, 95.0),
    )


# ── Public runner ───────────────────────────────────────────────────


def run_ensemble(
    base_config: GenerationShipConfig,
    n_runs: int = 100,
    seeds: Optional[list[int]] = None,
    years: Optional[int] = None,
    progress: Optional[callable] = None,
) -> EnsembleResult:
    """Run ``n_runs`` independent simulations and aggregate the outputs.

    Parameters
    ----------
    base_config : GenerationShipConfig
        Template config.  ``seed`` is overridden per-run.
    n_runs : int
        Number of independent realisations.  N=100 → ±10 % CI on
        survival proportion; N=1000 → ±3 %; N=30 is a smoke-test
        floor.
    seeds : list[int], optional
        Explicit seeds.  If None we use ``base_config.seed + i`` for
        i in [0, n_runs) so the output is reproducible.
    years : int, optional
        Override total_years for every run; defaults to the config's
        natural ``target_distance_ly / velocity_c``.
    progress : callable, optional
        Optional callback ``progress(i_done, n_total, last_result)``
        invoked after each run completes.  Used by the SSE streaming
        endpoint in Phase E.

    Returns
    -------
    EnsembleResult with field_stats keyed by field name.
    """
    if n_runs <= 0:
        raise ValueError("n_runs must be positive")

    if seeds is None:
        seeds = [base_config.seed + i for i in range(n_runs)]
    elif len(seeds) != n_runs:
        raise ValueError(f"seeds length {len(seeds)} != n_runs {n_runs}")

    t0 = time.time()
    runs: list[GenerationShipResults] = []

    def _one_run(seed: int) -> GenerationShipResults:
        # Deep-copy the config via dataclass replace by re-instantiating
        # with the fields that matter.  GenerationShipConfig is a
        # dataclass so we can use the trick of constructing a new
        # config with the original __dict__ + override.
        cfg_dict = {**base_config.__dict__, "seed": seed}
        cfg = GenerationShipConfig(**cfg_dict)
        sim = GenerationShipSimulation(cfg)
        return sim.run(years=years)

    for i, seed in enumerate(seeds, 1):
        r = _one_run(seed)
        runs.append(r)
        if progress is not None:
            progress(i, n_runs, r)

    # Aggregate
    survived = sum(1 for r in runs if r.ship_survived)
    survival_rate = survived / len(runs)

    failure_counter: Counter[str] = Counter()
    for r in runs:
        if not r.ship_survived and r.failure_reason:
            failure_counter[r.failure_reason] += 1

    field_stats: dict[str, EnsembleStats] = {}
    for fname in _AGGREGATE_FIELDS:
        vals = [getattr(r, fname, None) for r in runs]
        vals = [float(v) for v in vals if v is not None]
        if vals:
            field_stats[fname] = _aggregate_field(fname, vals)

    return EnsembleResult(
        config_mode=runs[0].config_mode if runs else "UNKNOWN",
        n_runs=len(runs),
        wall_time_s=time.time() - t0,
        survival_rate=survival_rate,
        failure_reasons=dict(failure_counter),
        field_stats=field_stats,
        per_run=runs,
    )
