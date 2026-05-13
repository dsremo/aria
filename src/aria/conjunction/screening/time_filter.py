"""
Stage 3: Time (Phasing) Filter.

Even if two orbits intersect geometrically (pass Stages 1 and 2),
the objects must arrive at the intersection region at the same time.

OPTIMIZED APPROACH:
  1. Pre-compute ALL positions for ALL unique objects at all time steps ONCE
     → stored in (N_objects, N_timesteps, 3) array
  2. For each candidate pair, compute vectorized distance across all timesteps
  3. If minimum distance < threshold → pair survives

This avoids redundant SGP4 calls. For 5,000 objects over 72h at 60s steps:
  - Old: 21.6M individual SGP4 calls
  - New: 5,000 × 4,320 = 21.6M calls BUT done once, reused for all pairs
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np

from aria.conjunction.core.types import SpaceObject
from aria.conjunction.propagation.sgp4_propagator import SGP4Propagator

logger = logging.getLogger(__name__)

COARSE_DISTANCE_THRESHOLD_KM = 50.0


class TimeFilter:
    """Filter pairs by temporal proximity at orbital intersection."""

    def __init__(
        self,
        window_hours: float = 72.0,
        step_seconds: float = 60.0,
        coarse_threshold_km: float = COARSE_DISTANCE_THRESHOLD_KM,
    ):
        self.window_hours = window_hours
        self.step_seconds = step_seconds
        self.coarse_threshold_km = coarse_threshold_km

    def filter(
        self,
        objects: list[SpaceObject],
        candidate_pairs: list[tuple[int, int]],
        start_epoch: datetime | None = None,
    ) -> list[tuple[int, int, datetime]]:
        """Filter pairs by checking temporal proximity.

        Uses pre-computed ephemeris for all unique objects to avoid
        redundant SGP4 evaluations.

        Args:
            objects: Full object list
            candidate_pairs: Pairs surviving Stages 1 and 2
            start_epoch: Start of prediction window (default: now)

        Returns:
            List of (i, j, approximate_tca) for pairs that pass
        """
        if start_epoch is None:
            start_epoch = datetime.utcnow()

        if not candidate_pairs:
            return []

        # Build time array
        n_steps = int(self.window_hours * 3600 / self.step_seconds) + 1
        epochs = [start_epoch + timedelta(seconds=k * self.step_seconds)
                  for k in range(n_steps)]

        # Identify unique objects involved in candidate pairs
        unique_indices = sorted(set(
            idx for pair in candidate_pairs for idx in pair
        ))
        # Map from object index → position in ephemeris array
        idx_map = {obj_idx: arr_idx for arr_idx, obj_idx in enumerate(unique_indices)}

        n_objects = len(unique_indices)
        logger.info(
            f"Time filter: pre-computing ephemeris for {n_objects} objects "
            f"× {n_steps} steps = {n_objects * n_steps:,} SGP4 calls"
        )

        # Pre-compute ALL positions: (n_objects, n_steps, 3)
        positions = np.full((n_objects, n_steps, 3), np.nan, dtype=np.float64)

        for arr_idx, obj_idx in enumerate(unique_indices):
            obj = objects[obj_idx]
            if obj.satellite is None:
                continue
            # Use batch propagation for efficiency
            states = SGP4Propagator.propagate_batch(
                obj, epochs[0], epochs[-1], self.step_seconds,
            )
            for t_idx, state in enumerate(states):
                if t_idx < n_steps:
                    positions[arr_idx, t_idx] = state.position

        # Check each candidate pair using vectorized distance
        surviving: list[tuple[int, int, datetime]] = []
        threshold_sq = self.coarse_threshold_km**2

        for i, j in candidate_pairs:
            arr_i = idx_map.get(i)
            arr_j = idx_map.get(j)
            if arr_i is None or arr_j is None:
                continue

            pos_i = positions[arr_i]  # (n_steps, 3)
            pos_j = positions[arr_j]  # (n_steps, 3)

            # Vectorized distance computation
            diff = pos_i - pos_j  # (n_steps, 3)

            # Skip rows where either is NaN
            valid = ~np.any(np.isnan(diff), axis=1)
            if not np.any(valid):
                continue

            dist_sq = np.sum(diff[valid]**2, axis=1)
            min_dist_sq = np.min(dist_sq)

            if min_dist_sq <= threshold_sq:
                # Find approximate TCA
                min_local_idx = np.argmin(dist_sq)
                valid_indices = np.where(valid)[0]
                global_idx = valid_indices[min_local_idx]
                approx_tca = epochs[global_idx]
                surviving.append((i, j, approx_tca))

        eliminated = len(candidate_pairs) - len(surviving)
        logger.info(
            f"Time filter: {len(candidate_pairs)} pairs -> {len(surviving)} pairs "
            f"(eliminated {eliminated}, "
            f"{100 * eliminated / max(1, len(candidate_pairs)):.1f}% reduction)"
        )

        return surviving
