"""
Stage 1: Apogee-Perigee Filter (APS).

The simplest and most effective screening filter. Eliminates pairs whose
altitude bands (radial ranges) do not overlap. No propagation needed —
apogee and perigee are computed directly from TLE orbital elements.

For an object with semi-major axis a and eccentricity e:
  apogee_radius  = a * (1 + e)
  perigee_radius = a * (1 - e)

Two objects can only conjunct if their radial ranges overlap:
  perigee_1 - pad ≤ apogee_2 + pad  AND  perigee_2 - pad ≤ apogee_1 + pad

This filter typically eliminates ~95% of all pairs.

Implementation uses a sweep-line algorithm:
  1. Sort all objects by perigee radius
  2. For each object, only compare against objects whose perigee is within
     range of the current object's apogee + padding
  This reduces the comparison from O(N²) to O(N·K) where K << N.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aria.conjunction.core.constants import (
    DEFAULT_SCREENING_ALTITUDE_PAD_KM,
)
from aria.conjunction.core.types import SpaceObject

logger = logging.getLogger(__name__)


@dataclass
class AltitudeBand:
    """Radial range of an orbit."""

    norad_id: str
    perigee_radius: float  # km from Earth center
    apogee_radius: float  # km from Earth center
    index: int  # position in the original object list


class ApogeePerigeeFilter:
    """Filter pairs by altitude band overlap using sweep-line algorithm."""

    def __init__(self, pad_km: float = DEFAULT_SCREENING_ALTITUDE_PAD_KM):
        self.pad_km = pad_km

    def filter(self, objects: list[SpaceObject]) -> list[tuple[int, int]]:
        """Return indices of object pairs that pass the apogee-perigee filter.

        Args:
            objects: List of SpaceObjects with populated orbital elements

        Returns:
            List of (i, j) index pairs where i < j, representing objects
            whose altitude bands overlap.
        """
        # Extract altitude bands
        bands: list[AltitudeBand] = []
        for idx, obj in enumerate(objects):
            if obj.elements is None:
                continue
            bands.append(AltitudeBand(
                norad_id=obj.norad_id,
                perigee_radius=obj.elements.perigee_radius,
                apogee_radius=obj.elements.apogee_radius,
                index=idx,
            ))

        if len(bands) < 2:
            return []

        # Sort by perigee radius (ascending)
        bands.sort(key=lambda b: b.perigee_radius)

        # Sweep-line: for each band, compare with subsequent bands
        # whose perigee is within range of current band's apogee + pad
        pairs: list[tuple[int, int]] = []
        n = len(bands)

        for i in range(n):
            max_reach = bands[i].apogee_radius + self.pad_km

            for j in range(i + 1, n):
                # Since sorted by perigee, once perigee_j > max_reach, done
                if bands[j].perigee_radius - self.pad_km > max_reach:
                    break

                # Check overlap: ranges intersect if both conditions hold
                j_per = bands[j].perigee_radius - self.pad_km
                i_apo = bands[i].apogee_radius + self.pad_km
                i_per = bands[i].perigee_radius - self.pad_km
                j_apo = bands[j].apogee_radius + self.pad_km
                if j_per <= i_apo and i_per <= j_apo:
                    # Use original indices, ensure i < j
                    idx_a = min(bands[i].index, bands[j].index)
                    idx_b = max(bands[i].index, bands[j].index)
                    pairs.append((idx_a, idx_b))

        logger.info(
            f"Apogee-Perigee filter: {len(bands)} objects → {len(pairs)} candidate pairs "
            f"(eliminated {n * (n-1) // 2 - len(pairs)} pairs, "
            f"{100 * (1 - len(pairs) / max(1, n * (n-1) // 2)):.1f}% reduction)"
        )

        return pairs
