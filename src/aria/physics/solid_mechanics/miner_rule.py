"""Miner's cumulative damage rule (§4.4 of F2 scope).

Palmgren 1924 / Miner 1945 linear cumulative damage:

    D = Σ_i  n_i / N_f,i                                 [dimensionless]

where `n_i` is the number of applied cycles at amplitude `σ_{a,i}`
and `N_f,i` is the cycles-to-failure at that amplitude from the
material's S-N curve. Failure is predicted when D reaches unity.

This is the most famous and most second-guessed rule in fatigue
engineering. Its known limitations (Suresh 1998 §7.5, ISBN
978-0521578479):

  1. **Ignores loading sequence** — a high-then-low sequence is
     more damaging than low-then-high for most metals.
  2. **Scatter** — experimental D at failure ranges from ~0.3 to
     ~3 in large fatigue datasets.
  3. **No interaction** — crack retardation from overload cycles
     (Wheeler model) is not captured.

Despite these caveats Miner's rule remains the default engineering
approximation because the alternatives (nonlinear cumulative damage,
continuum damage mechanics) require many more material constants and
are rarely available for new alloys.
"""

from __future__ import annotations

from typing import Iterable


def miner_cumulative_damage(
    cycles_per_block: Iterable[float],
    cycles_to_failure_per_block: Iterable[float],
) -> float:
    """Palmgren-Miner cumulative damage `D = Σ n_i / N_f,i`.

    Args:
        cycles_per_block: iterable of applied cycle counts n_i at
            each block in the load history. Must be non-negative.
        cycles_to_failure_per_block: iterable of failure lives N_f,i
            from the S-N curve at the same amplitudes. Must all be
            strictly positive.

    Returns:
        Cumulative damage fraction D. D ≥ 1 means failure predicted.
    """
    n_list = list(cycles_per_block)
    nf_list = list(cycles_to_failure_per_block)
    if len(n_list) != len(nf_list):
        raise ValueError(
            "cycles_per_block and cycles_to_failure_per_block must have "
            "the same length"
        )
    total = 0.0
    for n_i, nf_i in zip(n_list, nf_list):
        if n_i < 0.0:
            raise ValueError("cycles_per_block entries must be non-negative")
        if nf_i <= 0.0:
            raise ValueError(
                "cycles_to_failure_per_block entries must be positive"
            )
        total += n_i / nf_i
    return total
