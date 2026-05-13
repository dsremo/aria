"""V3-W2: Quaternion normalization constraint monitor for ADCS telemetry.

ADCS quaternion (q_x, q_y, q_z, q_w) must satisfy ||q|| = 1.0 (unit
quaternion).  A deviation indicates a corrupted attitude estimate —
numerical error in the ADCS computer (integer overflow, precision loss,
or software fault).

For a 0.003 norm deviation, attitude error can be ~1.7 deg — significant
for pointing-critical missions.  This is a zero-false-positive check:
nominal ADCS always maintains unit norm to float precision.

Reference: Markley, F.L. & Crassidis, J.L. (2014). Fundamentals of
           Spacecraft Attitude Determination and Control. Springer. §2.2.
"""

from __future__ import annotations

import structlog

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


class QuaternionMonitor:
    """Detects quaternion normalization violations in ADCS telemetry.

    Maintains latest quaternion components per satellite and checks the
    unit-norm constraint whenever all 4 components are available.

    Thresholds (derived from ECSS-E-ST-60-10C §5.3.4):
        norm_error > 1e-4  → WATCH   (numerical precision warning)
        norm_error > 1e-3  → WARNING (ADCS computer issue likely)
        norm_error > 0.01  → CRITICAL (attitude estimate invalid)
    """

    # Recognized quaternion parameter names.
    QUATERNION_PARAMS: frozenset[str] = frozenset({
        "quaternion_q1", "quaternion_q2", "quaternion_q3", "quaternion_q4",
        "q_x", "q_y", "q_z", "q_w",
        "q1", "q2", "q3", "q4",
    })

    def __init__(self) -> None:
        # satellite_id → {parameter_name: latest_value}
        self._components: dict[str, dict[str, float]] = {}

    def update(
        self,
        satellite_id: str,
        parameter: str,
        value: float,
    ) -> DetectorResult | None:
        """Update a quaternion component and check norm if 4 components ready.

        Returns None for non-quaternion parameters or when fewer than 4
        components are available.
        """
        if parameter not in self.QUATERNION_PARAMS:
            return None

        sat_state = self._components.setdefault(satellite_id, {})
        sat_state[parameter] = value

        # Need exactly 4 quaternion components to check norm.
        quat_params = [p for p in sat_state if p in self.QUATERNION_PARAMS]
        if len(quat_params) < 4:
            return None

        # Take the first 4 quaternion components found.
        q_vals = [sat_state[p] for p in sorted(quat_params)[:4]]
        norm_sq = sum(v * v for v in q_vals)
        norm_error = abs(norm_sq - 1.0)

        if norm_error > 0.01:
            severity = Severity.CRITICAL
        elif norm_error > 1e-3:
            severity = Severity.WARNING
        elif norm_error > 1e-4:
            severity = Severity.WATCH
        else:
            return DetectorResult(
                detector_name="quaternion_norm",
                is_anomaly=False,
                score=0.0,
                severity=Severity.NOMINAL,
                details={
                    "norm_error": round(norm_error, 8),
                    "norm": round(norm_sq ** 0.5, 8),
                },
            )

        logger.warning(
            "quaternion_norm_violation",
            satellite=satellite_id,
            norm_error=round(norm_error, 6),
            severity=severity.value,
        )

        return DetectorResult(
            detector_name="quaternion_norm",
            is_anomaly=True,
            score=min(1.0, norm_error * 1000),
            severity=severity,
            details={
                "reason": "quaternion_normalization_violation",
                "norm_error": round(norm_error, 8),
                "norm": round(norm_sq ** 0.5, 8),
            },
        )

    def reset(self, satellite_id: str | None = None) -> None:
        """Clear state for one or all satellites."""
        if satellite_id:
            self._components.pop(satellite_id, None)
        else:
            self._components.clear()
