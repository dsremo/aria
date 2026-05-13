"""
Smart Sieve — Cascaded conjunction screening orchestrator.

Runs the 3-stage filter cascade:
  Stage 1: Apogee-Perigee (altitude band overlap) — eliminates ~95%
  Stage 2: Orbital Plane (MOID)                   — eliminates ~90% of remaining
  Stage 3: Time (phasing)                          — eliminates ~80% of remaining

Net reduction: ~450M pairs → ~500-2000 candidate pairs.

The output is a list of (primary_index, secondary_index, approximate_tca)
tuples ready for precise TCA refinement in the conjunction module.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from datetime import datetime

from aria.conjunction.core.types import SpaceObject
from aria.conjunction.screening.apogee_perigee import ApogeePerigeeFilter
from aria.conjunction.screening.orbital_plane import OrbitalPlaneFilter
from aria.conjunction.screening.spatial_index import AltitudeInclinationIndex
from aria.conjunction.screening.time_filter import TimeFilter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SieveParameters:
    """Snapshot of the active screening pipeline parameters.

    P2-E1 (Jah): Operators can't see what criteria caused PASS/FAIL.
    This struct is returned by SmartSieveScreener.get_parameters() and
    can be serialized to JSON for display in Settings → Pipeline Defaults.

    All thresholds are the MINIMUM required to proceed to the next stage.
    A pair that fails Stage 1 never reaches Stage 2, etc.
    """

    # Stage 0 — kd-tree spatial pre-filter
    spatial_index_enabled: bool
    spatial_altitude_radius_km: float | None    # None if spatial index disabled
    spatial_inclination_radius_deg: float | None

    # Stage 1 — Apogee-Perigee overlap
    altitude_pad_km: float          # altitude band must overlap within this pad

    # Stage 2 — Orbital plane / MOID
    moid_threshold_km: float        # minimum orbit intersection distance threshold
    prediction_window_hours: float  # hours ahead to screen

    # Stage 3 — Time / coarse propagation
    time_step_seconds: float        # propagation step
    coarse_distance_km: float       # maximum approach distance to pass Stage 3

    # Spatial index activation threshold
    spatial_index_min_objects: int = 500  # skip spatial index for smaller catalogs


class ExclusionList:
    """Pairs or patterns to exclude from conjunction screening.

    Use cases:
      - Intra-constellation pairs (Starlink vs Starlink)
      - Coordinated formations
      - Known benign conjunctions
    """

    def __init__(self):
        self._excluded_pairs: set[tuple[str, str]] = set()
        self._excluded_patterns: list[tuple[str, str]] = []

    def add_pair(self, norad_id_a: str, norad_id_b: str) -> None:
        """Exclude a specific pair of objects."""
        key = (min(norad_id_a, norad_id_b), max(norad_id_a, norad_id_b))
        self._excluded_pairs.add(key)

    def add_pattern(self, name_pattern_a: str, name_pattern_b: str) -> None:
        """Exclude pairs matching name glob patterns.

        Example: add_pattern("STARLINK*", "STARLINK*") excludes all Starlink-vs-Starlink.
        """
        self._excluded_patterns.append((name_pattern_a, name_pattern_b))

    def is_excluded(self, obj_a: SpaceObject, obj_b: SpaceObject) -> bool:
        """Check if a pair should be excluded from screening."""
        # Check specific pairs
        key = (min(obj_a.norad_id, obj_b.norad_id),
               max(obj_a.norad_id, obj_b.norad_id))
        if key in self._excluded_pairs:
            return True

        # Check name patterns
        for pat_a, pat_b in self._excluded_patterns:
            if ((fnmatch.fnmatch(obj_a.name.upper(), pat_a.upper())
                 and fnmatch.fnmatch(obj_b.name.upper(), pat_b.upper()))
                or (fnmatch.fnmatch(obj_b.name.upper(), pat_a.upper())
                    and fnmatch.fnmatch(obj_a.name.upper(), pat_b.upper()))):
                return True

        return False


class SmartSieveScreener:
    """Orchestrates the 3-stage conjunction screening cascade."""

    def __init__(
        self,
        altitude_pad_km: float = 10.0,            # ESTIMATE — Stage 1 apogee/perigee altitude pad (Alfano 2005)
        moid_threshold_km: float = 20.0,           # ESTIMATE — MOID threshold for Stage 2 (NASA CARA: 20 km)
        window_hours: float = 72.0,                # ESTIMATE — 3-day conjunction screening window (NASA CARA standard)
        time_step_seconds: float = 60.0,           # ESTIMATE — 60 s propagation step (Kelso 2009 Adv Astronaut Sci)
        coarse_distance_km: float = 50.0,          # ESTIMATE — 50 km coarse distance threshold for Stage 3
        exclusion_list: ExclusionList | None = None,
        use_spatial_index: bool = True,
        spatial_altitude_radius_km: float = 200.0,     # ESTIMATE — 200 km altitude band for kd-tree pre-filter
        spatial_inclination_radius_deg: float = 15.0,  # ESTIMATE — 15 deg inclination band for kd-tree pre-filter
    ):
        # P1 FIX (Panel 3 SpaceX): Add Stage 0 spatial index pre-filter.
        # At 100K+ objects the O(N²) all-pairs loop is prohibitive.
        # kd-tree on (altitude, inclination) reduces candidates by 10-100×
        # before the existing 3-stage cascade runs. O(N log N).
        self.spatial_index = (
            AltitudeInclinationIndex(
                altitude_radius_km=spatial_altitude_radius_km,
                inclination_radius_deg=spatial_inclination_radius_deg,
            )
            if use_spatial_index
            else None
        )
        self.stage1 = ApogeePerigeeFilter(pad_km=altitude_pad_km)
        self.stage2 = OrbitalPlaneFilter(threshold_km=moid_threshold_km,
                                          window_hours=window_hours)
        self.stage3 = TimeFilter(
            window_hours=window_hours,
            step_seconds=time_step_seconds,
            coarse_threshold_km=coarse_distance_km,
        )
        self.exclusions = exclusion_list
        # Store raw params for SieveParameters introspection (P2-E1)
        self._altitude_pad_km = altitude_pad_km
        self._moid_threshold_km = moid_threshold_km
        self._window_hours = window_hours
        self._time_step_seconds = time_step_seconds
        self._coarse_distance_km = coarse_distance_km
        self._spatial_altitude_radius_km = spatial_altitude_radius_km if use_spatial_index else None
        self._spatial_inclination_radius_deg = (
            spatial_inclination_radius_deg if use_spatial_index else None
        )

    def get_parameters(self) -> SieveParameters:
        """Return the active screening pipeline parameters.

        P2-E1 (Jah): Expose sieve thresholds so operators can understand
        why a pair passed or failed each stage. Use in Settings UI and API.
        """
        return SieveParameters(
            spatial_index_enabled=self.spatial_index is not None,
            spatial_altitude_radius_km=self._spatial_altitude_radius_km,
            spatial_inclination_radius_deg=self._spatial_inclination_radius_deg,
            altitude_pad_km=self._altitude_pad_km,
            moid_threshold_km=self._moid_threshold_km,
            prediction_window_hours=self._window_hours,
            time_step_seconds=self._time_step_seconds,
            coarse_distance_km=self._coarse_distance_km,
        )

    def screen(
        self,
        objects: list[SpaceObject],
        start_epoch: datetime | None = None,
    ) -> list[tuple[int, int, datetime]]:
        """Run the full 3-stage screening cascade.

        Args:
            objects: Full space object catalog
            start_epoch: Start of prediction window (default: now)

        Returns:
            List of (primary_idx, secondary_idx, approximate_tca) for
            all pairs that survive all three filters.
        """
        n = len(objects)
        total_pairs = n * (n - 1) // 2
        logger.info(f"Starting Smart Sieve screening: {n} objects, {total_pairs} total pairs")

        # Stage 0: Spatial index pre-filter (kd-tree, O(N log N)).
        # Only enabled for large catalogs where the cascade would be slow.
        # For small catalogs (<500 objects), skip — overhead isn't worth it.
        if self.spatial_index is not None and n >= 500:
            spatial_candidates = set(self.spatial_index.build_pairs(objects))
            logger.info(
                f"Stage 0 (spatial index): {total_pairs} → {len(spatial_candidates)} pairs"
            )
        else:
            spatial_candidates = None

        # Stage 1: Apogee-Perigee
        all_s1 = self.stage1.filter(objects)

        # Intersect with spatial index if active
        if spatial_candidates is not None:
            pairs_after_s1 = [p for p in all_s1 if p in spatial_candidates]
            logger.info(
                f"Stage 1 after spatial intersect: {len(all_s1)} → {len(pairs_after_s1)} pairs"
            )
        else:
            pairs_after_s1 = all_s1

        # Apply exclusion list (after Stage 1, before expensive Stage 2)
        if self.exclusions and pairs_after_s1:
            pre_excl = len(pairs_after_s1)
            pairs_after_s1 = [
                (i, j) for i, j in pairs_after_s1
                if not self.exclusions.is_excluded(objects[i], objects[j])
            ]
            excluded = pre_excl - len(pairs_after_s1)
            if excluded > 0:
                logger.info(f"Exclusion list removed {excluded} pairs")

        if not pairs_after_s1:
            logger.info("No pairs survived Stage 1")
            return []

        # Stage 2: Orbital Plane (MOID)
        pairs_after_s2 = self.stage2.filter(objects, pairs_after_s1)

        if not pairs_after_s2:
            logger.info("No pairs survived Stage 2")
            return []

        # Stage 3: Time (Phasing)
        candidates = self.stage3.filter(objects, pairs_after_s2, start_epoch)

        logger.info(
            f"Smart Sieve complete: {total_pairs} → {len(candidates)} candidates "
            f"({100 * (1 - len(candidates) / max(1, total_pairs)):.4f}% reduction)"
        )

        return candidates
