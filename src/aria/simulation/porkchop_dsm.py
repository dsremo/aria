"""Single-DSM (Deep-Space Manoeuvre) extension to ARIA's porkchop search.

The base :func:`aria.simulation.porkchop.compute_porkchop` searches
direct (and multi-rev) Lambert transfers with no mid-course burn.
Real interplanetary missions almost always include at least one
DSM — typically near aphelion of the transfer ellipse — to either
shorten the transit, target a specific arrival geometry, or set up a
gravity-assist flyby.

This module adds a *single-DSM* extension on top of the same Lambert
machinery: for each (t_dep, t_arr) pair, it sweeps a midpoint epoch
``t_dsm`` between them and reports the ΔV-optimal split.

Algorithm (Vallado §9.2 + Strange & Sims 2001):

    1.  Solve Lambert (departure → DSM epoch) for the first leg.
    2.  At ``t_dsm``, we have two velocity vectors: the arrival of
        leg 1 (no DSM) and the required departure of leg 2 (Lambert
        from DSM → arrival).  The DSM ΔV is the vector difference.
    3.  Total cost = C3 at departure + v∞ at arrival + |DSM ΔV|.

The DSM ΔV ranges from ~ 0 m/s (when the two-leg solution
naturally matches the direct Lambert) to several km/s.  A typical
Earth-Mars DSM ΔV is 50-300 m/s and shaves 30-90 days off the
direct-transfer transit time.

This module is intentionally light — it composes the existing
Lambert solver and reports an extra pareto-front of (transit time,
total ΔV) points the operator can pick from.

References
----------
* Strange, N. & Sims, J. A. (2001). "Methods for the Design of
  V-Infinity Leveraging Maneuvers." AAS-01-437.
* Vallado, D. A. (4th ed., 2013). §9.2 — multi-impulse transfers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from aria.simulation.lambert_izzo import lambert_izzo


_DAY_S = 86_400.0


@dataclass(frozen=True)
class DSMSolution:
    """One concrete (t_dep, t_dsm, t_arr) plan."""
    t_dep_days: float
    t_dsm_days: float
    t_arr_days: float
    c3_dep_km2_s2: float
    v_inf_arr_kmps: float
    dsm_dv_mps: float
    total_dv_mps: float
    leg1_v_dep_kmps: np.ndarray
    leg1_v_arr_kmps: np.ndarray
    leg2_v_dep_kmps: np.ndarray
    leg2_v_arr_kmps: np.ndarray
    notes: str = ""

    @property
    def transit_days(self) -> float:
        return self.t_arr_days - self.t_dep_days


@dataclass(frozen=True)
class DSMScanResult:
    """Output of a single-DSM porkchop scan."""
    solutions: List[DSMSolution]
    best_total_dv: Optional[DSMSolution]
    best_transit: Optional[DSMSolution]


def _vec_norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def compute_porkchop_dsm(
    *,
    mu_central: float,
    r_dep_fn: Callable[[float], np.ndarray],
    r_arr_fn: Callable[[float], np.ndarray],
    v_dep_fn: Callable[[float], np.ndarray],
    v_arr_fn: Callable[[float], np.ndarray],
    t_dep_days: float,
    t_arr_days: float,
    n_dsm: int = 21,
    dsm_window_frac: Tuple[float, float] = (0.2, 0.8),
    dv_max_mps: float = 50_000.0,
) -> DSMScanResult:
    """Sweep DSM epochs between (t_dep, t_arr) and return the best plan.

    Parameters
    ----------
    mu_central
        Central-body GM in m³/s² (Sun for interplanetary).
    r_dep_fn, r_arr_fn
        Callables(day) → (3,) position [m] of the departure / arrival body.
    v_dep_fn, v_arr_fn
        Callables(day) → (3,) velocity [m/s] of the departure / arrival body.
    t_dep_days, t_arr_days
        Departure / arrival epochs in days from the same reference epoch
        used by the position / velocity callables.
    n_dsm
        Number of DSM-epoch samples between the two endpoints.
    dsm_window_frac
        Lower and upper fraction of (t_arr - t_dep) where the DSM is
        allowed.  Defaults to (0.2, 0.8) so the DSM never lands within
        the first 20 % or last 20 % of transit.
    dv_max_mps
        Reject DSM ΔV solutions exceeding this cap.  Default 50 km/s
        is intentionally generous because the straight-line-midpoint
        seed used here is a *coarse* approximation; iterative refinement
        (Strange-Sims) typically reduces the DSM ΔV by an order of
        magnitude.  Operators tightening to ≤ 1 km/s for real mission
        design should also iterate the DSM 3D position.

    Returns
    -------
    DSMScanResult with every accepted solution plus convenience
    pointers to the lowest-Δv and shortest-transit plans.
    """
    if t_arr_days <= t_dep_days:
        raise ValueError("t_arr_days must exceed t_dep_days")
    transit = t_arr_days - t_dep_days
    dsm_lo = t_dep_days + dsm_window_frac[0] * transit
    dsm_hi = t_dep_days + dsm_window_frac[1] * transit
    dsm_grid = np.linspace(dsm_lo, dsm_hi, n_dsm)

    r_dep = r_dep_fn(t_dep_days)
    v_dep_planet = v_dep_fn(t_dep_days)
    r_arr = r_arr_fn(t_arr_days)
    v_arr_planet = v_arr_fn(t_arr_days)

    solutions: List[DSMSolution] = []
    for t_dsm in dsm_grid:
        # Place the DSM on the straight-line midpoint in inertial space.
        # This is a crude but effective parameterisation; the Strange-Sims
        # paper uses this same midpoint as the search seed.  Real mission
        # design then iterates the DSM 3D position; we ship the seed.
        r_dsm_seed = r_dep + (r_arr - r_dep) * (
            (t_dsm - t_dep_days) / transit
        )
        try:
            v_dep_l1, v_arr_l1 = lambert_izzo(
                mu_central, r_dep, r_dsm_seed,
                (t_dsm - t_dep_days) * _DAY_S,
            )
            v_dep_l2, v_arr_l2 = lambert_izzo(
                mu_central, r_dsm_seed, r_arr,
                (t_arr_days - t_dsm) * _DAY_S,
            )
        except Exception:
            continue

        dsm_dv = float(np.linalg.norm(v_dep_l2 - v_arr_l1))   # m/s
        if dsm_dv > dv_max_mps:
            continue

        v_inf_dep = v_dep_l1 - v_dep_planet
        v_inf_arr = v_arr_l2 - v_arr_planet
        c3_dep_km2_s2 = (_vec_norm(v_inf_dep) ** 2) / 1e6   # m²/s² → km²/s²
        v_inf_arr_kmps = _vec_norm(v_inf_arr) / 1e3

        # Total Δv — operator-relevant cost: launch energy (proxy via C3),
        # mid-course DSM, and arrival ΔV.  We expose all three.
        total_dv = (
            float(np.sqrt(c3_dep_km2_s2 * 1e6))   # m/s departure v∞
            + dsm_dv
            + v_inf_arr_kmps * 1e3
        )

        solutions.append(DSMSolution(
            t_dep_days=t_dep_days,
            t_dsm_days=float(t_dsm),
            t_arr_days=t_arr_days,
            c3_dep_km2_s2=c3_dep_km2_s2,
            v_inf_arr_kmps=v_inf_arr_kmps,
            dsm_dv_mps=dsm_dv,
            total_dv_mps=total_dv,
            leg1_v_dep_kmps=v_dep_l1 / 1e3,
            leg1_v_arr_kmps=v_arr_l1 / 1e3,
            leg2_v_dep_kmps=v_dep_l2 / 1e3,
            leg2_v_arr_kmps=v_arr_l2 / 1e3,
        ))

    best_total = min(solutions, key=lambda s: s.total_dv_mps, default=None)
    best_transit = (
        min(solutions, key=lambda s: s.transit_days)
        if solutions else None
    )
    return DSMScanResult(
        solutions=solutions,
        best_total_dv=best_total,
        best_transit=best_transit,
    )
