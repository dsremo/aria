"""Range-only observability diagnostic for batch least-squares orbit
determination.

KNOWN_ISSUES flagged: "range-only BLS divergence is an observability
problem, not a bug — needs angle or Doppler measurements added."

This module gives the operator a quantitative tool:

  1. Compute the observability Gramian from a series of range
     measurements over time
  2. Return a rank + smallest-singular-value metric
  3. Flag when the batch is under-observable (rank < 6)
  4. Suggest which measurement to add (range-rate / line-of-sight angle)

Reference:
    Tapley, Schutz, Born (2004) "Statistical Orbit Determination" §4.
    Vallado (2013) §10.6 "Observability."
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class RangeMeasurement:
    t_s: float
    observer_pos: np.ndarray   # (3,)
    range_m: float
    sigma_m: float = 10.0


@dataclass
class ObservabilityReport:
    rank: int
    smallest_sv: float
    condition_number: float
    observable: bool
    missing_dof: int       # 6 - rank
    recommendation: str
    gramian: np.ndarray = None


def range_jacobian_row(state: np.ndarray, obs_pos: np.ndarray) -> np.ndarray:
    """∂r/∂state for a 6-DOF state (3 position + 3 velocity).

    r = |r_sat - r_obs|, so ∂r/∂r_sat = (r_sat - r_obs) / r
    and ∂r/∂v_sat = 0 (instantaneous, no velocity dependence).
    """
    rel = state[:3] - obs_pos
    r = np.linalg.norm(rel)
    if r < 1e-9:
        return np.zeros(6)
    H = np.zeros(6)
    H[:3] = rel / r
    return H


def assess_observability(
    state0: np.ndarray,
    measurements: List[RangeMeasurement],
) -> ObservabilityReport:
    """Build the information matrix Λ = H^T W H over all measurements.

    Rank(Λ) < 6 means the system is underdetermined: no unique orbit
    can be recovered from range alone.
    """
    if len(measurements) < 6:
        return ObservabilityReport(
            rank=0, smallest_sv=0.0, condition_number=float("inf"),
            observable=False, missing_dof=6,
            recommendation="Need at least 6 measurements for 6-DOF state",
        )
    H_rows = []
    W = []
    for m in measurements:
        H_rows.append(range_jacobian_row(state0, m.observer_pos))
        W.append(1.0 / max(m.sigma_m, 1e-6) ** 2)
    H = np.vstack(H_rows)
    W_diag = np.diag(W)
    Lambda = H.T @ W_diag @ H
    # SVD on Λ
    U, s, Vt = np.linalg.svd(Lambda)
    rank = int(np.sum(s > s[0] * 1e-10))
    smallest_sv = float(s[-1])
    cond = float(s[0] / max(s[-1], 1e-30))
    observable = rank >= 6
    missing = 6 - rank
    if observable:
        rec = "System is fully observable"
    elif rank < 3:
        rec = "Severe deficiency — add angle and range-rate measurements"
    else:
        rec = f"Add range-rate or angle measurement to observe {missing} missing DOF"
    return ObservabilityReport(
        rank=rank, smallest_sv=smallest_sv, condition_number=cond,
        observable=observable, missing_dof=missing,
        recommendation=rec, gramian=Lambda,
    )
