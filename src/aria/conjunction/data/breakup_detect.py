"""
Breakup / fragmentation event detection.

Detects sudden catalog growth in a localized orbital regime, indicating
a satellite breakup, collision, or explosion.

Detection method:
  1. Bin all objects by orbital regime: (altitude band, inclination band)
  2. Track the count in each bin over time
  3. Flag bins where count increased by >N objects within Δt hours

Known fragmentation events for context:
  - Cosmos 2251 / Iridium 33 (2009): +2,000 debris fragments
  - Fengyun 1C ASAT test (2007): +3,500 fragments
  - Intelsat 33e breakup (2024): ~80 fragments in GEO
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from aria.conjunction.core.types import SpaceObject

logger = logging.getLogger(__name__)


@dataclass
class BreakupAlert:
    """A detected breakup / fragmentation event."""

    altitude_band: tuple[float, float]  # (min_km, max_km)
    inclination_band: tuple[float, float]  # (min_deg, max_deg)
    new_object_count: int
    new_objects: list[SpaceObject]
    detected_at: datetime
    parent_candidate: SpaceObject | None  # likely parent body


class BreakupDetector:
    """Detect fragmentation events by monitoring catalog growth per orbital regime."""

    def __init__(
        self,
        altitude_bin_km: float = 50.0,     # ESTIMATE — 50 km altitude bin width (Liou 2010 Adv Space Res 47 136)
        inclination_bin_deg: float = 2.0,  # ESTIMATE — 2 deg inclination bin (Liou 2010)
        min_new_objects: int = 5,          # ESTIMATE — 5+ new objects = probable breakup signal
        lookback_hours: float = 48.0,      # ESTIMATE — 48 h lookback for catalog update propagation
    ):
        self.altitude_bin_km = altitude_bin_km
        self.inclination_bin_deg = inclination_bin_deg
        self.min_new_objects = min_new_objects
        self.lookback_hours = lookback_hours

        # Historical bin counts: bin_key → set of NORAD IDs
        self._previous_bins: dict[tuple, set[str]] = defaultdict(set)

    def _bin_key(self, obj: SpaceObject) -> tuple | None:
        """Compute the orbital regime bin for an object."""
        if obj.elements is None:
            return None

        import math
        alt = (obj.elements.perigee_altitude + obj.elements.apogee_altitude) / 2.0
        inc_deg = math.degrees(obj.elements.inclination)

        alt_bin = int(alt / self.altitude_bin_km) * self.altitude_bin_km
        inc_bin = int(inc_deg / self.inclination_bin_deg) * self.inclination_bin_deg

        return (alt_bin, alt_bin + self.altitude_bin_km,
                inc_bin, inc_bin + self.inclination_bin_deg)

    def check(self, current_catalog: list[SpaceObject]) -> list[BreakupAlert]:
        """Compare current catalog against previous state and detect breakups.

        Args:
            current_catalog: Current list of all space objects

        Returns:
            List of BreakupAlert for newly detected fragmentation events
        """
        # Build current bins
        current_bins: dict[tuple, list[SpaceObject]] = defaultdict(list)
        for obj in current_catalog:
            key = self._bin_key(obj)
            if key is not None:
                current_bins[key].append(obj)

        alerts = []

        for key, objects in current_bins.items():
            current_ids = {obj.norad_id for obj in objects}
            previous_ids = self._previous_bins.get(key, set())

            new_ids = current_ids - previous_ids
            if len(new_ids) >= self.min_new_objects:
                new_objects = [obj for obj in objects if obj.norad_id in new_ids]

                # Try to identify parent body: the largest non-debris object in the bin
                parent = None
                for obj in objects:
                    if obj.norad_id not in new_ids:
                        from aria.conjunction.core.types import ObjectType
                        if obj.object_type == ObjectType.PAYLOAD:
                            parent = obj
                            break

                alert = BreakupAlert(
                    altitude_band=(key[0], key[1]),
                    inclination_band=(key[2], key[3]),
                    new_object_count=len(new_ids),
                    new_objects=new_objects,
                    detected_at=datetime.utcnow(),
                    parent_candidate=parent,
                )
                alerts.append(alert)

                logger.warning(
                    f"BREAKUP DETECTED: {len(new_ids)} new objects in "
                    f"alt={key[0]:.0f}-{key[1]:.0f}km, inc={key[2]:.0f}-{key[3]:.0f}deg"
                    f"{f' (near {parent.name})' if parent else ''}"
                )

        # Update history
        for key, objects in current_bins.items():
            self._previous_bins[key] = {obj.norad_id for obj in objects}

        return alerts
