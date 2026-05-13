"""V3-W3: Reaction wheel momentum saturation tracking.

Each reaction wheel has a maximum angular momentum capacity.  As momentum
accumulates from unbalanced environmental torques, wheels approach saturation.
Signs: wheel speed trending toward RPM_max, desaturation frequency increasing.

Typical lead time to saturation: 5-14 days — entirely predictable with early
warning.

Reference: Wertz, J.R. (1978). Spacecraft Attitude Determination and Control.
           §12.4: momentum wheel management.
"""

from __future__ import annotations

import structlog

from aria.dsremo.core.models import DetectorResult, Severity

logger = structlog.get_logger()


class MomentumMonitor:
    """Tracks reaction wheel momentum storage for saturation prediction.

    Monitors wheel speed channels and alerts when momentum approaches
    the wheel's maximum capacity, enabling timely desaturation maneuvers.
    """

    WHEEL_PARAMS: frozenset[str] = frozenset({
        "wheel_speed_x", "wheel_speed_y", "wheel_speed_z",
        "reaction_wheel_speed", "rw_speed_1", "rw_speed_2",
        "rw_speed_3", "rw_speed_4",
    })

    def __init__(
        self,
        max_wheel_speed_rpm: float = 6000.0,  # ESTIMATE — 6000 RPM small-sat reaction wheel (Wertz 1978 §12.4)
        wheel_inertia_kgm2: float = 0.01,     # ESTIMATE — 0.01 kg m² for ~100 g·cm² class wheel (Wertz 1978 §12.4)
        watch_pct: float = 0.70,              # ESTIMATE — 70% momentum utilization → WATCH (Wertz 1978 §12.4)
        warning_pct: float = 0.90,            # ESTIMATE — 90% → WARNING (Wertz 1978 §12.4)
        critical_pct: float = 0.95,           # ESTIMATE — 95% → CRITICAL (imminent saturation)
    ) -> None:
        self._max_rpm = max_wheel_speed_rpm
        self._inertia = wheel_inertia_kgm2
        self._watch_pct = watch_pct
        self._warning_pct = warning_pct
        self._critical_pct = critical_pct
        # satellite_id → {param: latest_rpm}
        self._speeds: dict[str, dict[str, float]] = {}
        # satellite_id → cumulative zero-crossing count
        self._zero_crossings: dict[str, int] = {}
        self._prev_signs: dict[str, dict[str, int]] = {}

    def update(
        self,
        satellite_id: str,
        parameter: str,
        value: float,
    ) -> DetectorResult | None:
        """Update wheel speed and check momentum utilization.

        Args:
            value: Wheel speed in RPM.
        """
        if parameter not in self.WHEEL_PARAMS:
            return None

        sat_speeds = self._speeds.setdefault(satellite_id, {})
        sat_speeds[parameter] = value

        # Track zero-crossings (RPM reversals = bearing fatigue).
        prev_signs = self._prev_signs.setdefault(satellite_id, {})
        current_sign = 1 if value >= 0 else -1
        if parameter in prev_signs and prev_signs[parameter] != current_sign:
            self._zero_crossings[satellite_id] = (
                self._zero_crossings.get(satellite_id, 0) + 1
            )
        prev_signs[parameter] = current_sign

        # Compute total momentum magnitude across all wheels.
        rpm_to_rads = 2.0 * 3.14159265 / 60.0
        total_h_sq = 0.0
        for rpm in sat_speeds.values():
            h = self._inertia * abs(rpm) * rpm_to_rads
            total_h_sq += h * h
        total_h = total_h_sq ** 0.5

        max_h = self._inertia * self._max_rpm * rpm_to_rads
        utilization = total_h / max_h if max_h > 0 else 0.0

        if utilization >= self._critical_pct:
            severity = Severity.CRITICAL
            score = 1.0
        elif utilization >= self._warning_pct:
            severity = Severity.WARNING
            score = 0.8
        elif utilization >= self._watch_pct:
            severity = Severity.WATCH
            score = 0.5
        else:
            return DetectorResult(
                detector_name="momentum_monitor",
                is_anomaly=False,
                score=utilization,
                severity=Severity.NOMINAL,
                details={
                    "momentum_utilization_pct": round(utilization * 100, 1),
                    "total_momentum_nms": round(total_h, 6),
                },
            )

        return DetectorResult(
            detector_name="momentum_monitor",
            is_anomaly=True,
            score=score,
            severity=severity,
            details={
                "reason": "momentum_saturation_approaching",
                "momentum_utilization_pct": round(utilization * 100, 1),
                "total_momentum_nms": round(total_h, 6),
                "max_momentum_nms": round(max_h, 6),
                "zero_crossings": self._zero_crossings.get(satellite_id, 0),
            },
        )

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id:
            self._speeds.pop(satellite_id, None)
            self._zero_crossings.pop(satellite_id, None)
            self._prev_signs.pop(satellite_id, None)
        else:
            self._speeds.clear()
            self._zero_crossings.clear()
            self._prev_signs.clear()
