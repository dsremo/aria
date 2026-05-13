"""
Time of Closest Approach (TCA) finder.

TCA is the moment of local minimum distance between two orbiting objects.
Mathematically: TCA is a root of f(t) = r_rel(t) · v_rel(t) = 0
(the relative position and velocity vectors are perpendicular).

Algorithm:
  1. Coarse search: evaluate distance at fixed intervals (10s steps)
     around the approximate TCA from screening
  2. Find local minima in the distance time series
  3. Refine each minimum using Brent's method (robust, no derivatives)
  4. Optional Newton-Raphson polish for sub-millisecond precision

Handles multiple close approaches per pair within the search window.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import minimize_scalar

from aria.conjunction.core.types import SpaceObject
from aria.conjunction.propagation.sgp4_propagator import SGP4Error, SGP4Propagator

logger = logging.getLogger(__name__)


class TCAFinder:
    """Find precise Time(s) of Closest Approach between two objects."""

    def __init__(
        self,
        coarse_step_s: float = 10.0,
        search_window_minutes: float = 60.0,
        refinement_tol_s: float = 1e-3,
    ):
        """
        Args:
            coarse_step_s: Time step for coarse distance evaluation (seconds)
            search_window_minutes: Window around approximate TCA to search (±minutes)
            refinement_tol_s: Brent's method convergence tolerance (seconds)
        """
        self.coarse_step_s = coarse_step_s
        self.search_window_minutes = search_window_minutes
        self.refinement_tol_s = refinement_tol_s

    def find_tca(
        self,
        primary: SpaceObject,
        secondary: SpaceObject,
        approx_tca: datetime,
    ) -> list[tuple[datetime, float]]:
        """Find precise TCA(s) near an approximate time.

        Args:
            primary: Primary space object
            secondary: Secondary space object
            approx_tca: Approximate TCA from screening stage

        Returns:
            List of (tca_datetime, miss_distance_km) for each local minimum found,
            sorted by miss distance (closest first).
        """
        # Define search window
        half_window = timedelta(minutes=self.search_window_minutes)
        t_start = approx_tca - half_window
        t_end = approx_tca + half_window

        # Phase 1: Coarse search — evaluate distance at fixed intervals
        step = timedelta(seconds=self.coarse_step_s)
        times: list[float] = []  # seconds from t_start
        distances: list[float] = []

        t = t_start
        t_offset = 0.0
        while t <= t_end:
            try:
                state1 = SGP4Propagator.propagate(primary, t)
                state2 = SGP4Propagator.propagate(secondary, t)
                dist = float(np.linalg.norm(state1.position - state2.position))
                times.append(t_offset)
                distances.append(dist)
            except SGP4Error:
                pass
            t += step
            t_offset += self.coarse_step_s

        if len(times) < 3:
            return []

        times_arr = np.array(times)
        dist_arr = np.array(distances)

        # Phase 2: Find local minima in the coarse distance series
        local_minima_indices = []
        for k in range(1, len(dist_arr) - 1):
            if dist_arr[k] < dist_arr[k - 1] and dist_arr[k] < dist_arr[k + 1]:
                local_minima_indices.append(k)

        # Also check if the overall minimum is at the edges
        if len(local_minima_indices) == 0:
            # No interior minimum — use the global minimum point
            local_minima_indices = [int(np.argmin(dist_arr))]

        # Phase 3: Refine each local minimum using Brent's method
        results: list[tuple[datetime, float]] = []

        for min_idx in local_minima_indices:
            # Bracket: [times[min_idx - 1], times[min_idx + 1]]
            left = max(0, min_idx - 1)
            right = min(len(times_arr) - 1, min_idx + 1)

            t_left = times_arr[left]
            t_right = times_arr[right]

            # Distance function: seconds offset → distance
            def dist_func(t_offset_s: float) -> float:
                epoch = t_start + timedelta(seconds=t_offset_s)
                try:
                    s1 = SGP4Propagator.propagate(primary, epoch)
                    s2 = SGP4Propagator.propagate(secondary, epoch)
                    return float(np.linalg.norm(s1.position - s2.position))
                except SGP4Error:
                    return 1e12  # large distance if propagation fails

            # Minimize using golden section (bounded, derivative-free)
            result = minimize_scalar(
                dist_func,
                bounds=(t_left, t_right),
                method="bounded",
                options={"xatol": self.refinement_tol_s},
            )

            tca_epoch = t_start + timedelta(seconds=result.x)
            miss_dist = result.fun

            results.append((tca_epoch, miss_dist))

        # Sort by miss distance (closest first)
        results.sort(key=lambda x: x[1])
        return results

    def find_all_tca(
        self,
        primary: SpaceObject,
        secondary: SpaceObject,
        start: datetime,
        end: datetime,
        coarse_step_s: float = 60.0,
    ) -> list[tuple[datetime, float]]:
        """Find ALL close approaches in a time window (not just near one approximate TCA).

        This is used when no approximate TCA is available (e.g., for a full catalog scan).
        Uses half-period sub-interval partitioning to catch multiple passes.

        Args:
            primary: Primary object
            secondary: Secondary object
            start: Start of search window
            end: End of search window
            coarse_step_s: Coarse step size (seconds)

        Returns:
            List of (tca, miss_distance_km) sorted by time
        """
        step = timedelta(seconds=coarse_step_s)
        times_s: list[float] = []
        distances: list[float] = []

        t = start
        t_offset = 0.0
        while t <= end:
            try:
                s1 = SGP4Propagator.propagate(primary, t)
                s2 = SGP4Propagator.propagate(secondary, t)
                dist = float(np.linalg.norm(s1.position - s2.position))
                times_s.append(t_offset)
                distances.append(dist)
            except SGP4Error:
                pass
            t += step
            t_offset += coarse_step_s

        if len(times_s) < 3:
            return []

        dist_arr = np.array(distances)

        # Find all local minima
        results = []
        for k in range(1, len(dist_arr) - 1):
            if dist_arr[k] < dist_arr[k - 1] and dist_arr[k] < dist_arr[k + 1]:
                # Only refine if distance is below a generous threshold
                if dist_arr[k] < 200.0:  # km
                    approx = start + timedelta(seconds=times_s[k])
                    refined = self.find_tca(primary, secondary, approx)
                    results.extend(refined)

        # De-duplicate close results (within 60s of each other)
        if not results:
            return []

        results.sort(key=lambda x: x[0])
        deduped = [results[0]]
        for tca, dist in results[1:]:
            if (tca - deduped[-1][0]).total_seconds() > 60:
                deduped.append((tca, dist))
            elif dist < deduped[-1][1]:
                deduped[-1] = (tca, dist)

        return deduped
