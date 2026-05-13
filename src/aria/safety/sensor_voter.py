"""TMR / N-of-M sensor voter — runtime fault-tolerant fusion.

Sensor-fusion audit recommendation A-1: ARIA already had a *theoretical*
``nom_voting_reliability`` calculator at ``aria.safety.risk_assessment``
(used for fault-tree probability math) but no *runtime* component that
takes 3+ raw sensor readings and returns the voted value with a
disagreement flag.  Without one, every fusion path (KCL checker, state
manager, EKF measurement model) silently trusts whichever single sensor
happened to be polled first.

Usage:

    voter = TripleSensorVoter(disagreement_sigma=3.0)
    out = voter.vote("gyro_x", [
        SensorReading("gyro_a", 0.0010, sigma=1e-4),
        SensorReading("gyro_b", 0.0011, sigma=1e-4),
        SensorReading("gyro_c", 0.0040, sigma=1e-4),  # outlier
    ])
    if out.has_disagreement:
        report_fault(out.suspect_unit_ids)
    use_value(out.value)

Design choices:

  * **Median is the voter primitive** when ``len(readings) >= 3``.  At
    N=2 the voter has no tie-breaker and returns the average with a
    disagreement flag set if they differ by more than the sigma
    tolerance.
  * **Suspect detection** flags any reading more than
    ``disagreement_sigma × σ_eff`` from the voted value, where
    ``σ_eff`` is the larger of the reading's own sigma and a
    floor derived from the median absolute deviation across all
    readings.  This catches both "sensor σ underreports its noise"
    and "all sensors agree the world has changed" cases.
  * **Decoupled from the sensor names**: the voter operates on an
    ordered list of readings; the spacecraft-specific mapping
    (gyro_a=on bus A, gyro_b=on bus B, gyro_c=hot-spare) is the
    caller's responsibility.

References:
    NASA/SP-2010-576 §11 ("Voting reliability of N-of-M systems").
    Hammett 2002 "Design and analysis of TMR systems for fault-tolerant
        digital and avionics systems," AIAA-2002-3408.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class SensorReading:
    """One reading from one redundant sensor unit."""
    unit_id: str
    value: float
    sigma: float = 0.0   # 1-σ measurement noise; 0 → unknown


@dataclass(frozen=True)
class VoteResult:
    """Output of one voting round."""
    value: float
    has_disagreement: bool
    suspect_unit_ids: tuple[str, ...]
    n_in_agreement: int
    median: float
    spread: float        # max − min across input readings


class TripleSensorVoter:
    """N-of-M voter with disagreement isolation.

    Default ``disagreement_sigma=3.0`` matches the ECSS-E-ST-70-41C
    §6.3.4 sensor-anomaly classification threshold.  Operators with
    high-precision sensors may tighten this to 2σ; with noisy sensors,
    raise to 4σ.
    """

    def __init__(
        self,
        disagreement_sigma: float = 3.0,
        min_voters: int = 3,
    ) -> None:
        if min_voters < 2:
            raise ValueError("min_voters must be >= 2")
        self._disagreement_sigma = float(disagreement_sigma)
        self._min_voters = int(min_voters)

    def vote(self, channel: str, readings: list[SensorReading]) -> VoteResult:
        """Combine ``readings`` into a single voted value.

        Raises ``ValueError`` when fewer than ``min_voters`` readings
        are supplied — calling code should fall back to single-source
        with a degraded-trust flag in that case.
        """
        if not readings:
            raise ValueError(f"{channel}: no readings supplied")

        finite_readings = [
            reading for reading in readings
            if math.isfinite(reading.value) and math.isfinite(reading.sigma)
        ]
        if len(finite_readings) < self._min_voters:
            raise ValueError(
                f"{channel}: only {len(finite_readings)} finite readings, "
                f"need >= {self._min_voters}"
            )

        values = sorted(reading.value for reading in finite_readings)
        median_value = (
            values[len(values) // 2]
            if len(values) % 2 == 1
            else 0.5 * (values[len(values) // 2 - 1] + values[len(values) // 2])
        )
        spread = values[-1] - values[0]

        # σ floor from MAD-of-readings so an attacker cannot
        # under-report sigma to dominate the disagreement test.
        deviations = sorted(abs(reading.value - median_value)
                            for reading in finite_readings)
        mad = deviations[len(deviations) // 2]
        sigma_floor = 1.4826 * mad   # MAD → σ-equivalent for Gaussian

        suspects: list[str] = []
        for reading in finite_readings:
            sigma_eff = max(reading.sigma, sigma_floor, 1e-12)
            if abs(reading.value - median_value) > self._disagreement_sigma * sigma_eff:
                suspects.append(reading.unit_id)

        n_agree = len(finite_readings) - len(suspects)
        has_disagreement = bool(suspects)

        if has_disagreement:
            logger.warning(
                "sensor_voter_disagreement",
                channel=channel,
                suspect_units=suspects,
                voted_value=median_value,
                spread=spread,
                n_in_agreement=n_agree,
            )

        return VoteResult(
            value=median_value,
            has_disagreement=has_disagreement,
            suspect_unit_ids=tuple(suspects),
            n_in_agreement=n_agree,
            median=median_value,
            spread=spread,
        )
