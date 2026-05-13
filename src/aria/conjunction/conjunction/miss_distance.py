"""
Miss distance computation at TCA.

Computes:
  - Total miss distance (km)
  - RTN (Radial-Transverse-Normal) decomposition
  - Relative velocity vector and magnitude

The RTN decomposition is critical for understanding conjunction geometry:
  - Radial (R): smallest component typically
  - Transverse (T): largest component — dominated by timing uncertainty
  - Normal (N): driven by orbital plane differences
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from aria.conjunction.core.types import SpaceObject, StateVector
from aria.conjunction.propagation.frames import transform_to_rtn
from aria.conjunction.propagation.sgp4_propagator import SGP4Propagator


def compute_miss_distance(
    primary: SpaceObject,
    secondary: SpaceObject,
    tca: datetime,
    check_tle_age: bool = True,
) -> tuple[float, np.ndarray, np.ndarray, float, StateVector, StateVector]:
    """Compute miss distance and relative state at TCA.

    Args:
        primary: Primary space object
        secondary: Secondary space object
        tca: Time of closest approach
        check_tle_age: Reject TLEs older than 7 days (default True).
            Set False for unit tests with synthetic/historical TLEs.

    Returns:
        Tuple of:
          - miss_distance_km: total miss distance (km)
          - miss_vector_rtn: [R, T, N] components (km)
          - relative_velocity_vec: relative velocity (km/s, ECI)
          - relative_speed: magnitude of relative velocity (km/s)
          - primary_state: StateVector at TCA
          - secondary_state: StateVector at TCA
    """
    state1 = SGP4Propagator.propagate(primary, tca, check_age=check_tle_age)
    state2 = SGP4Propagator.propagate(secondary, tca, check_age=check_tle_age)

    # Relative state (secondary relative to primary)
    rel_pos = state2.position - state1.position
    rel_vel = state2.velocity - state1.velocity

    # Total miss distance
    miss_distance = float(np.linalg.norm(rel_pos))

    # Relative speed
    rel_speed = float(np.linalg.norm(rel_vel))

    # RTN decomposition (relative to primary's frame)
    rtn_pos, rtn_vel = transform_to_rtn(
        rel_pos, rel_vel,
        state1.position, state1.velocity,
    )

    return miss_distance, rtn_pos, rel_vel, rel_speed, state1, state2


def compute_miss_distance_rtn(
    primary_state: StateVector,
    secondary_state: StateVector,
) -> tuple[float, np.ndarray]:
    """Compute miss distance from pre-computed state vectors.

    Args:
        primary_state: Primary StateVector at TCA
        secondary_state: Secondary StateVector at TCA

    Returns:
        (miss_distance_km, miss_vector_rtn)
    """
    rel_pos = secondary_state.position - primary_state.position
    rel_vel = secondary_state.velocity - primary_state.velocity

    miss_distance = float(np.linalg.norm(rel_pos))

    rtn_pos, _ = transform_to_rtn(
        rel_pos, rel_vel,
        primary_state.position, primary_state.velocity,
    )

    return miss_distance, rtn_pos
