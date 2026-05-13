"""
Close approach event builder.

Constructs CloseApproach objects from TCA finder and miss distance results.
Handles the full pipeline from raw (primary, secondary, approximate_tca)
to a fully-populated CloseApproach dataclass.
"""

from __future__ import annotations

from datetime import datetime

from aria.conjunction.conjunction.miss_distance import compute_miss_distance
from aria.conjunction.conjunction.tca_finder import TCAFinder
from aria.conjunction.core.types import CloseApproach, SpaceObject


def build_close_approach(
    primary: SpaceObject,
    secondary: SpaceObject,
    approximate_tca: datetime,
    tca_finder: TCAFinder | None = None,
) -> CloseApproach | None:
    """Build a CloseApproach event from two objects and an approximate TCA.

    1. Refines TCA using Brent's method
    2. Computes miss distance and RTN decomposition
    3. Computes relative velocity

    Args:
        primary: Primary space object
        secondary: Secondary space object
        approximate_tca: Approximate TCA from screening
        tca_finder: TCAFinder instance (created with defaults if None)

    Returns:
        CloseApproach event, or None if TCA refinement fails
    """
    if tca_finder is None:
        tca_finder = TCAFinder()

    # Refine TCA
    tca_results = tca_finder.find_tca(primary, secondary, approximate_tca)
    if not tca_results:
        return None

    # Take the closest approach
    tca, _ = tca_results[0]

    # Compute full miss distance and relative state
    miss_km, miss_rtn, rel_vel, rel_speed, state1, state2 = compute_miss_distance(
        primary, secondary, tca
    )

    rel_pos = state2.position - state1.position

    return CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=tca,
        miss_distance_km=miss_km,
        miss_distance_rtn=miss_rtn,
        relative_velocity_km_s=rel_speed,
        relative_position=rel_pos,
        relative_velocity_vec=rel_vel,
        primary_state=state1,
        secondary_state=state2,
    )


def build_close_approaches_batch(
    objects: list[SpaceObject],
    candidates: list[tuple[int, int, datetime]],
    tca_finder: TCAFinder | None = None,
) -> list[CloseApproach]:
    """Build CloseApproach events for a batch of screening candidates.

    Args:
        objects: Full object list
        candidates: List of (primary_idx, secondary_idx, approx_tca) from screener
        tca_finder: TCAFinder instance

    Returns:
        List of successfully built CloseApproach events
    """
    if tca_finder is None:
        tca_finder = TCAFinder()

    approaches = []
    for i, j, approx_tca in candidates:
        approach = build_close_approach(objects[i], objects[j], approx_tca, tca_finder)
        if approach is not None:
            approaches.append(approach)

    return approaches
