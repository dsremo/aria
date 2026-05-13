"""
SGP4/SDP4 orbital propagator wrapper.

Uses Brandon Rhodes' sgp4 package (MIT, C++ backend) for TLE propagation.
SGP4 outputs position/velocity in the TEME (True Equator Mean Equinox) frame.

Key limitations:
  - Accuracy degrades ~10 km/day in LEO due to atmospheric drag uncertainty
  - TLEs older than 24-48h are effectively noise for conjunction assessment
  - SGP4 is a GP (General Perturbations) model — NOT suitable for high-fidelity work
  - MUST use SGP4 with TLEs (not numerical integrators — that's mathematically inconsistent)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
from sgp4.api import jday

from aria.conjunction.core.types import CoordinateFrame, SpaceObject, StateVector

logger = logging.getLogger(__name__)

# P0 FIX (Panel 7 IIT + Panel 1 ESA): TLE age thresholds.
# Above WARN_AGE_DAYS, position error exceeds ~1 km (TLE epoch drift).
# Above MAX_AGE_DAYS, the TLE is operationally unusable for Pc computation;
# a conjunction event at this age could be off by tens of km.
_TLE_WARN_AGE_DAYS = 3.0   # ESTIMATE — warn at 3 days (NASA CARA operational practice: Kelso 2009)
_TLE_MAX_AGE_DAYS = 7.0    # ESTIMATE — max 7 days; error ~10+ km LEO (Kelso 2009 AIAA 2009-6173)


def check_tle_age(obj: SpaceObject, propagation_epoch: datetime) -> None:
    """Check that the TLE epoch is recent enough for reliable conjunction assessment.

    P0 FIX (Panel 1 ESA, Panel 7 IIT): The system previously mixed
    old TLEs (30+ days) with current TLEs without any warning. A Pc
    computed from a 30-day-old TLE is numerically precise but physically
    meaningless — the true position uncertainty dwarfs the miss distance.

    Args:
        obj: Space object being propagated.
        propagation_epoch: The time to which we are propagating.

    Raises:
        StaleTLEError: If the TLE age exceeds MAX_AGE_DAYS.
    """
    if obj.elements is None:
        return  # no epoch available — skip check, propagate() will fail on missing satellite
    tle_epoch = obj.elements.epoch
    age_days = abs((propagation_epoch - tle_epoch).total_seconds()) / 86400.0

    if age_days > _TLE_MAX_AGE_DAYS:
        raise StaleTLEError(
            f"TLE for {obj.norad_id} ({obj.name!r}) is {age_days:.1f} days old "
            f"(epoch: {tle_epoch.isoformat()}, propagating to: {propagation_epoch.isoformat()}). "
            f"Maximum allowed age for Pc computation is {_TLE_MAX_AGE_DAYS} days. "
            f"Position error exceeds ~10 km in LEO — larger than typical miss distances. "
            f"Fetch a fresh TLE from Space-Track before computing conjunction probability."
        )
    if age_days > _TLE_WARN_AGE_DAYS:
        logger.warning(
            "tle_age_warning norad_id=%s age_days=%.1f threshold=%.1f "
            "position_error_estimate_km=%.1f",
            obj.norad_id, age_days, _TLE_WARN_AGE_DAYS, age_days * 1.0,
        )


class SGP4Error(Exception):
    """Raised when SGP4 propagation fails."""


class StaleTLEError(SGP4Error):
    """Raised when a TLE is too old for reliable conjunction assessment."""


class SGP4Propagator:
    """Propagate TLE-based space objects using SGP4/SDP4."""

    @staticmethod
    def propagate(
        obj: SpaceObject,
        epoch: datetime,
        check_age: bool = True,
    ) -> StateVector:
        """Propagate a single object to a specific epoch.

        Args:
            obj: SpaceObject with a valid sgp4 Satrec
            epoch: Target datetime (UTC)
            check_age: If True (default), raise StaleTLEError if the TLE is
                older than MAX_AGE_DAYS. Set False only for historical replay
                or when you explicitly accept stale data with wider uncertainty.

        Returns:
            StateVector in TEME frame (km, km/s)

        Raises:
            StaleTLEError: If TLE is too old for reliable Pc computation.
            SGP4Error: If propagation fails (decayed orbit, bad TLE, etc.)
        """
        # P0 FIX (Panel 1 ESA): Reject stale TLEs before computing anything.
        if check_age:
            check_tle_age(obj, epoch)

        if obj.satellite is None:
            raise SGP4Error(f"No Satrec for object {obj.norad_id}")

        jd, fr = jday(
            epoch.year, epoch.month, epoch.day,
            epoch.hour, epoch.minute,
            epoch.second + epoch.microsecond / 1e6,
        )

        error_code, position, velocity = obj.satellite.sgp4(jd, fr)

        if error_code != 0:
            error_messages = {
                1: "mean elements, ecc >= 1.0 or ecc < -0.001 or a < 0.95",
                2: "mean motion less than 0.0",
                3: "pert elements, ecc < 0.0 or ecc > 1.0",
                4: "semi-latus rectum < 0.0",
                5: "epoch elements are sub-orbital (decayed)",
                6: "satellite has decayed",
            }
            msg = error_messages.get(error_code, f"Unknown error code {error_code}")
            raise SGP4Error(f"SGP4 error for {obj.norad_id}: {msg}")

        return StateVector(
            position=np.array(position, dtype=np.float64),
            velocity=np.array(velocity, dtype=np.float64),
            epoch=epoch,
            frame=CoordinateFrame.TEME,
        )

    @staticmethod
    def propagate_batch(
        obj: SpaceObject,
        start: datetime,
        end: datetime,
        step_seconds: float = 60.0,
    ) -> list[StateVector]:
        """Propagate a single object across a time range.

        Args:
            obj: SpaceObject
            start: Start of propagation window
            end: End of propagation window
            step_seconds: Time step between evaluations

        Returns:
            List of StateVectors at each time step
        """
        states = []
        current = start
        step = timedelta(seconds=step_seconds)

        while current <= end:
            try:
                state = SGP4Propagator.propagate(obj, current)
                states.append(state)
            except SGP4Error:
                pass  # skip failed epochs (near decay)
            current += step

        return states

    @staticmethod
    def propagate_many(
        objects: list[SpaceObject],
        epoch: datetime,
    ) -> dict[str, StateVector]:
        """Propagate multiple objects to the same epoch.

        Args:
            objects: List of SpaceObjects
            epoch: Target datetime

        Returns:
            Dict mapping norad_id → StateVector (skips failed objects)
        """
        results = {}
        for obj in objects:
            try:
                results[obj.norad_id] = SGP4Propagator.propagate(obj, epoch)
            except SGP4Error:
                continue
        return results

    @staticmethod
    def propagate_many_batch(
        objects: list[SpaceObject],
        epochs: list[datetime],
    ) -> np.ndarray:
        """Propagate N objects to M epochs using sgp4 array API for maximum speed.

        Returns:
            np.ndarray of shape (N, M, 6) where [:,:,:3] is position and [:,:,3:] is velocity.
            NaN for failed propagations.
        """
        n = len(objects)
        m = len(epochs)
        result = np.full((n, m, 6), np.nan, dtype=np.float64)

        # Convert epochs to JD arrays
        jd_array = np.empty(m, dtype=np.float64)
        fr_array = np.empty(m, dtype=np.float64)
        for j, ep in enumerate(epochs):
            jd, fr = jday(
                ep.year, ep.month, ep.day,
                ep.hour, ep.minute,
                ep.second + ep.microsecond / 1e6,
            )
            jd_array[j] = jd
            fr_array[j] = fr

        for i, obj in enumerate(objects):
            if obj.satellite is None:
                continue
            for j in range(m):
                error_code, pos, vel = obj.satellite.sgp4(jd_array[j], fr_array[j])
                if error_code == 0:
                    result[i, j, :3] = pos
                    result[i, j, 3:] = vel

        return result
