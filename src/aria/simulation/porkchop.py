"""Porkchop plot generator — launch window optimizer for interplanetary transfers.

Generates C3/Δv contour maps over a grid of departure and arrival dates
by solving Lambert's problem for every (departure, arrival) pair. This is
the standard tool for mission design used by NASA JPL, ESA, and ISRO.

The output is a 2D grid of C3 (departure energy) and v∞ (arrival speed)
that reveals optimal launch windows as valleys in the contour map.

Algorithm approach studied from poliastro PorkchopPlotter (MIT license).
Reimplemented using ARIA's own Lambert solver (lambert_izzo.py) and
astropy ephemeris.

References:
    Strange, N. et al. (2002). "Graphical Method for Gravity-Assist
    Trajectory Design." J. Spacecraft & Rockets 39(1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from aria.simulation.lambert_izzo import lambert_izzo


@dataclass
class PorkchopResult:
    """Output of a porkchop plot computation."""

    departure_days: np.ndarray    # (n_dep,) days from epoch
    arrival_days: np.ndarray      # (n_arr,) days from epoch
    c3_departure: np.ndarray      # (n_dep, n_arr) C3 in km²/s²
    v_inf_arrival: np.ndarray     # (n_dep, n_arr) arrival v∞ in km/s
    tof_days: np.ndarray          # (n_dep, n_arr) time of flight in days

    # Optimal window
    best_c3: float                # minimum C3 found
    best_dep_day: float           # departure day of minimum
    best_arr_day: float           # arrival day of minimum
    best_tof_days: float          # TOF of minimum

    valid_count: int              # number of valid Lambert solutions
    total_count: int              # total grid points attempted

    # Multi-rev: per-cell winning revolution count, and best M overall.
    # rev_grid[i, j] = -1 where no Lambert solution converged.  Default
    # values keep the dataclass back-compat with callers that only set
    # the fields above.
    rev_grid: Optional[np.ndarray] = None
    best_M: int = 0


def compute_porkchop(
    mu_central: float,
    r_departure_fn,
    r_arrival_fn,
    dep_range_days: tuple[float, float],
    arr_range_days: tuple[float, float],
    n_dep: int = 50,
    n_arr: int = 50,
    v_planet_departure_fn=None,
    v_planet_arrival_fn=None,
    c3_max_km2_s2: Optional[float] = 1000.0,
    max_revs: int = 0,
) -> PorkchopResult:
    """Compute a porkchop plot over a departure/arrival date grid.

    Args:
        mu_central: gravitational parameter of central body (m³/s²)
        r_departure_fn: callable(day) → (3,) position of departure body [m]
        r_arrival_fn: callable(day) → (3,) position of arrival body [m]
        dep_range_days: (start, end) departure window in days from epoch
        arr_range_days: (start, end) arrival window in days from epoch
        n_dep: number of departure grid points
        n_arr: number of arrival grid points
        v_planet_departure_fn: callable(day) → (3,) velocity of departure body [m/s]
        v_planet_arrival_fn: callable(day) → (3,) velocity of arrival body [m/s]
        c3_max_km2_s2: reject Lambert solutions with C3 above this value.
            Near-180° transfer geometries can produce numerically valid but
            physically impossible velocities; capping at 1000 km²/s² removes
            these without affecting real mission windows (Earth-Mars max ≈50).
            Set to None to disable filtering.
        max_revs: maximum number of complete heliocentric revolutions to
            search for. 0 = direct transfer only (the historical default,
            and what every Earth→Mars / Earth→Venus mission actually flies).
            1 or 2 enables Type-III/IV multi-rev Lambert solutions, used by
            Galileo (VEEGA-multi-rev) and outer-planet scenic routes that
            trade time-of-flight for lower C3.  Implementation:
            ``lambert_izzo`` is called for every M ∈ [0, max_revs] with
            both ``lowpath`` branches (low/high energy) — for each grid
            cell the best C3 across all (M, lowpath) candidates wins,
            and the chosen rev count is recorded in
            :attr:`PorkchopResult.rev_grid`.

    Returns:
        PorkchopResult with C3 and v∞ contour grids.
    """
    dep_days = np.linspace(dep_range_days[0], dep_range_days[1], n_dep)
    arr_days = np.linspace(arr_range_days[0], arr_range_days[1], n_arr)

    c3_grid = np.full((n_dep, n_arr), np.inf)
    vinf_grid = np.full((n_dep, n_arr), np.inf)
    tof_grid = np.full((n_dep, n_arr), np.nan)
    rev_grid = np.full((n_dep, n_arr), -1, dtype=np.int8)

    valid = 0
    total = n_dep * n_arr

    # Multi-rev candidates.  For M=0, ``lowpath`` is irrelevant (single
    # branch); for M≥1, both energy paths exist and the lower-C3 one
    # usually wins — but not always (high-path wins when arrival v∞
    # dominates the budget), so we evaluate both.
    rev_candidates: list[tuple[int, bool]] = [(0, True)]
    for m in range(1, max(0, int(max_revs)) + 1):
        rev_candidates.append((m, True))
        rev_candidates.append((m, False))

    for i, d_day in enumerate(dep_days):
        r1 = r_departure_fn(d_day)
        v_dep_body = v_planet_departure_fn(d_day) if v_planet_departure_fn else None

        for j, a_day in enumerate(arr_days):
            tof_s = (a_day - d_day) * 86400.0
            if tof_s <= 0:
                continue

            r2 = r_arrival_fn(a_day)
            best_c3_cell = np.inf
            best_vinf_cell = np.inf
            best_M_cell = -1

            # Probe each (M, lowpath) candidate; keep the one with the
            # lowest C3 that also passes the c3_max filter.  Multi-rev
            # solutions don't exist for arbitrarily short TOFs (Izzo's
            # solver raises ValueError when T < T_min(M)), so the
            # try/except naturally skips infeasible (M, TOF) pairs.
            for M, lowpath in rev_candidates:
                try:
                    v1, v2 = lambert_izzo(
                        mu_central, r1, r2, tof_s,
                        M=M, lowpath=lowpath,
                    )
                except (ValueError, RuntimeError):
                    continue

                if v_dep_body is not None:
                    v_inf_dep = v1 - v_dep_body
                    c3 = float(np.dot(v_inf_dep, v_inf_dep) / 1e6)
                else:
                    c3 = float(np.dot(v1, v1) / 1e6)

                if c3_max_km2_s2 is not None and c3 > c3_max_km2_s2:
                    continue

                if v_planet_arrival_fn is not None:
                    v_arr_body = v_planet_arrival_fn(a_day)
                    v_inf_arr = float(np.linalg.norm(v2 - v_arr_body) / 1000.0)
                else:
                    v_inf_arr = float(np.linalg.norm(v2) / 1000.0)

                if c3 < best_c3_cell:
                    best_c3_cell = c3
                    best_vinf_cell = v_inf_arr
                    best_M_cell = M

            if best_M_cell >= 0:
                c3_grid[i, j] = best_c3_cell
                vinf_grid[i, j] = best_vinf_cell
                tof_grid[i, j] = (a_day - d_day)
                rev_grid[i, j] = best_M_cell
                valid += 1

    # Find optimal
    if valid > 0:
        idx = np.unravel_index(np.argmin(c3_grid), c3_grid.shape)
        best_c3 = float(c3_grid[idx])
        best_dep = float(dep_days[idx[0]])
        best_arr = float(arr_days[idx[1]])
        best_tof = float(tof_grid[idx])
        best_M = int(rev_grid[idx])
    else:
        best_c3 = float('inf')
        best_dep = 0.0
        best_arr = 0.0
        best_tof = 0.0
        best_M = -1

    return PorkchopResult(
        departure_days=dep_days,
        arrival_days=arr_days,
        c3_departure=c3_grid,
        v_inf_arrival=vinf_grid,
        tof_days=tof_grid,
        best_c3=best_c3,
        best_dep_day=best_dep,
        best_arr_day=best_arr,
        best_tof_days=best_tof,
        valid_count=valid,
        total_count=total,
        rev_grid=rev_grid,
        best_M=best_M,
    )
