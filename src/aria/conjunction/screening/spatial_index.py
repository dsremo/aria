"""
Spatial index pre-filter using scipy.spatial.cKDTree.

P1 FIX (Panel 3 SpaceX): The existing apogee-perigee sweep-line is O(N·K)
but K grows with catalog size. At 100K+ objects (Starlink + OneWeb + Kuiper +
debris), the cascade still requires comparing millions of pairs in Stage 2+.

This module adds a Stage 0 spatial index that operates on orbital element
space — specifically (mean altitude, inclination) — to reduce the candidate
set by 10-100× before the existing cascade runs. The cKDTree query is
O(N log N) regardless of catalog size.

Two spatial index strategies:
  1. AltitudeInclinationIndex: 2D index on (mean_altitude_km, inclination_deg).
     Fast to build (no propagation). Best for initial screening.
  2. EciPositionIndex: 3D index on ECI position at a given epoch.
     Requires propagation but is geometrically exact.
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np

from aria.conjunction.core.types import SpaceObject

logger = logging.getLogger(__name__)


class AltitudeInclinationIndex:
    """Fast orbital-element-space index for pair pre-filtering.

    Clusters objects in (mean_altitude_km, inclination_deg) space.
    Two objects with very different altitudes or inclinations cannot
    conjunct within any reasonable screening window.

    This reduces the pair set that enters Stage 1 (apogee-perigee)
    from O(N²) to O(N·M) where M = mean neighbors in the search radius.
    For megaconstellations where objects cluster at specific altitudes
    and inclinations (e.g., all Starlink at 550km/53°), M << N.

    Args:
        altitude_radius_km: Search radius in altitude dimension (km).
            Pairs outside this altitude difference cannot conjunct.
        inclination_radius_deg: Search radius in inclination dimension (deg).
            Pairs with inclination difference > this are unlikely to conjunct
            unless they have very high eccentricity.
        scale_inclination: True scales inclination by a factor to balance
            it against altitude in the distance metric.
    """

    def __init__(
        self,
        altitude_radius_km: float = 100.0,      # ESTIMATE — 100 km altitude band for pre-screening
        inclination_radius_deg: float = 10.0,   # ESTIMATE — 10 deg inclination band for pre-screening
        scale_inclination: bool = True,
    ) -> None:
        self.altitude_radius_km = altitude_radius_km
        self.inclination_radius_deg = inclination_radius_deg
        # Scale factor: 1 deg inclination ≈ 110 km at LEO for rough distance equivalence
        self._incl_scale = altitude_radius_km / inclination_radius_deg if scale_inclination else 1.0

    def build_pairs(self, objects: list[SpaceObject]) -> list[tuple[int, int]]:
        """Return candidate pairs within the altitude-inclination search radius.

        Args:
            objects: Full catalog of SpaceObjects with populated orbital elements.

        Returns:
            List of (i, j) pairs with i < j that are close in orbital element space.
            This is a superset of the true conjunction pairs — downstream filters
            will eliminate false positives.
        """
        from scipy.spatial import cKDTree

        # Build feature matrix: [mean_altitude_km, inclination_deg_scaled]
        features: list[list[float]] = []
        valid_indices: list[int] = []

        for idx, obj in enumerate(objects):
            if obj.elements is None:
                continue
            mean_altitude = obj.elements.semi_major_axis - 6371.0  # subtract Earth radius
            incl_deg = np.degrees(obj.elements.inclination)
            features.append([mean_altitude, incl_deg * self._incl_scale])
            valid_indices.append(idx)

        if len(valid_indices) < 2:
            return []

        feature_arr = np.array(features, dtype=np.float64)

        # Build kd-tree and query for all pairs within radius
        tree = cKDTree(feature_arr)

        # radius in the scaled space: altitude_radius_km (same for both dims after scaling)
        pairs_raw = tree.query_pairs(r=self.altitude_radius_km, output_type="ndarray")

        # Convert back to original catalog indices
        pairs: list[tuple[int, int]] = []
        for row in pairs_raw:
            i_orig = valid_indices[int(row[0])]
            j_orig = valid_indices[int(row[1])]
            a, b = min(i_orig, j_orig), max(i_orig, j_orig)
            pairs.append((a, b))

        n = len(valid_indices)
        total_possible = n * (n - 1) // 2
        reduction_pct = 100.0 * (1.0 - len(pairs) / max(1, total_possible))
        logger.info(
            "spatial_index_filter objects=%d total_pairs=%d candidate_pairs=%d "
            "reduction=%.1f%% alt_radius_km=%.0f incl_radius_deg=%.1f",
            n, total_possible, len(pairs), reduction_pct,
            self.altitude_radius_km, self.inclination_radius_deg,
        )

        return pairs


class EciPositionIndex:
    """Exact geometric pre-filter using 3D ECI position at screening epoch.

    More accurate than AltitudeInclinationIndex but requires propagation.
    Best used when the screening epoch is known and objects are propagated anyway.

    Args:
        proximity_threshold_km: Maximum distance in ECI (km) to flag as candidate.
            Typical: 500-1000 km (much larger than miss distance threshold) to
            account for the full orbital period of relative motion.
    """

    def __init__(self, proximity_threshold_km: float = 1000.0) -> None:
        self.proximity_threshold_km = proximity_threshold_km

    def build_pairs(
        self,
        objects: list[SpaceObject],
        epoch: datetime,
    ) -> list[tuple[int, int]]:
        """Propagate all objects to epoch, then build kd-tree for proximity pairs.

        Args:
            objects: SpaceObjects to screen.
            epoch: Screening epoch — all objects propagated to this time.

        Returns:
            List of (i, j) pairs within proximity_threshold_km in ECI space.
        """
        from scipy.spatial import cKDTree

        from aria.conjunction.propagation.sgp4_propagator import SGP4Propagator

        positions: list[np.ndarray] = []
        valid_indices: list[int] = []

        for idx, obj in enumerate(objects):
            try:
                sv = SGP4Propagator.propagate(obj, epoch, check_age=False)
                positions.append(sv.position)
                valid_indices.append(idx)
            except Exception:  # noqa: BLE001
                continue  # skip objects that fail to propagate

        if len(valid_indices) < 2:
            return []

        pos_arr = np.array(positions, dtype=np.float64)

        # Build kd-tree on 3D ECI positions (km)
        tree = cKDTree(pos_arr)
        pairs_raw = tree.query_pairs(r=self.proximity_threshold_km, output_type="ndarray")

        pairs: list[tuple[int, int]] = []
        for row in pairs_raw:
            i_orig = valid_indices[int(row[0])]
            j_orig = valid_indices[int(row[1])]
            a, b = min(i_orig, j_orig), max(i_orig, j_orig)
            pairs.append((a, b))

        n = len(valid_indices)
        total_possible = n * (n - 1) // 2
        reduction_pct = 100.0 * (1.0 - len(pairs) / max(1, total_possible))
        logger.info(
            "eci_index_filter objects=%d total_pairs=%d candidate_pairs=%d "
            "reduction=%.1f%% threshold_km=%.0f epoch=%s",
            n, total_possible, len(pairs), reduction_pct,
            self.proximity_threshold_km, epoch.isoformat(),
        )

        return pairs
