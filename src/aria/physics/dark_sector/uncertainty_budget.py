"""Shared uncertainty-budget propagation (§4.3 of M1 scope).

M1, M2, and M3 each emit one or more :class:`UncertaintyBudgetRow`
entries. Downstream pods (navigation A1/A4, clock I1) can combine
them in quadrature — appropriate because the sources are treated as
statistically independent upper bounds, matching the PDG convention
for unobserved-channel budgets (Workman et al. 2022 §39.3).

The quadrature formula for an ensemble of independent 1σ rows is

    σ_total² = Σ_k σ_k²                                      [same units²]

and the ballistic position error from a sustained acceleration
perturbation `δa` over a leg of duration `Δt` is

    σ_x = (1/2) · δa · Δt²                                   [m]

(classical free-fall position spread, used throughout NASA-STD-7009A
§5.5 navigation budgets).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class UncertaintyBudgetRow:
    """A single line of an error budget.

    Attributes:
        name: short identifier, e.g. "DM_drag_XENONnT_30GeV".
        effect_category: free-form tag ("DM", "EP", "varying_alpha"…)
        perturbation_value: magnitude of the bounded effect in the
            appropriate units (typically m/s² for M1/M2, dimensionless
            for M3 clock-shift rows).
        units: human-readable unit string.
        source: citation for the published bound.
    """

    name: str
    effect_category: str
    perturbation_value: float
    units: str
    source: str


def quadrature_sum_rows(
    rows: Iterable[UncertaintyBudgetRow],
    unit_filter: str | None = None,
) -> float:
    """Combine rows in quadrature, optionally restricting to one unit.

    Args:
        rows: iterable of UncertaintyBudgetRow.
        unit_filter: if given, only rows whose `units` exactly match
            are included (e.g. "m/s²" to pull only acceleration rows).

    Returns:
        √(Σ σ_k²) in the common unit.
    """
    total_sq = 0.0
    for row in rows:
        if unit_filter is not None and row.units != unit_filter:
            continue
        if row.perturbation_value < 0.0:
            raise ValueError(
                f"row {row.name!r} has negative perturbation_value"
            )
        total_sq += row.perturbation_value * row.perturbation_value
    return math.sqrt(total_sq)


def propagate_position_uncertainty_m(
    acceleration_perturbation_m_s2: float,
    leg_duration_s: float,
) -> float:
    """Ballistic position error σ_x = (1/2) δa · Δt².

    This is the standard free-fall propagation of a constant
    acceleration bias over a single mission leg. For a time-varying
    perturbation (e.g. when δa itself depends on ship velocity) the
    caller should integrate externally and pass an RMS-equivalent
    amplitude.
    """
    if acceleration_perturbation_m_s2 < 0.0:
        raise ValueError("acceleration_perturbation_m_s2 must be non-negative")
    if leg_duration_s < 0.0:
        raise ValueError("leg_duration_s must be non-negative")
    return 0.5 * acceleration_perturbation_m_s2 * leg_duration_s * leg_duration_s
