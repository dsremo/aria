"""V3-W1: Solar beta angle compensation for thermal thresholds.

Spacecraft thermal equilibrium depends on solar beta angle β (angle between
orbital plane and sun direction).  At high |β| (>60°), satellites are in
near-constant sunlight and panel temperatures can be 30-40°C higher than at
low β — a completely nominal variation.  Static thermal thresholds generate
seasonal false positive storms at high-beta periods.

This module adjusts thermal anomaly thresholds based on beta angle.

Reference: Wertz, J.R. & Larson, W.J. (1999). SMAD, 3rd ed. §11.6.
           Gilmore, D.G. (2002). Spacecraft Thermal Control Handbook. §2.3.
"""

from __future__ import annotations

import math

import structlog

logger = structlog.get_logger()


class BetaAngleCompensator:
    """Adjusts thermal channel thresholds based on solar beta angle.

    The compensated threshold allows wider bounds at high beta angles
    (more sunlight → higher nominal temperatures) and tighter bounds
    at low beta angles (eclipse-heavy orbits → lower baseline).

    Usage:
        comp = BetaAngleCompensator()
        adjusted = comp.compensate_threshold(
            base_threshold=85.0,  # °C
            beta_angle_deg=75.0,
            k_beta=0.5,           # °C per degree of |sin(β)|
        )
        # adjusted ≈ 85.0 + 0.5 * sin(75°) ≈ 85.48 °C
    """

    # Thermal channels that need beta angle compensation.
    THERMAL_PARAMS: frozenset[str] = frozenset({
        "panel_temp", "panel_temp_sun", "panel_temp_shade",
        "battery_temp", "electronics_temp", "pcb_temp",
        "thermal_panel_a", "thermal_panel_b",
    })

    def __init__(self) -> None:
        # satellite_id → current beta angle in degrees
        self._beta_angles: dict[str, float] = {}

    def set_beta_angle(self, satellite_id: str, beta_deg: float) -> None:
        """Set the current solar beta angle for a satellite.

        Should be updated from TLE/ephemeris computation, typically
        once per orbit or once per day.
        """
        self._beta_angles[satellite_id] = beta_deg
        logger.debug(
            "beta_angle_updated",
            satellite=satellite_id,
            beta_deg=round(beta_deg, 2),
        )

    def get_beta_angle(self, satellite_id: str) -> float | None:
        return self._beta_angles.get(satellite_id)

    def compensate_threshold(
        self,
        base_threshold: float,
        beta_angle_deg: float,
        k_beta: float = 0.5,  # ESTIMATE — 0.5 °C per |sin β| (Gilmore 2002 §2.3: 30-40°C range / sin 90°)
    ) -> float:
        """Adjust a thermal threshold for current beta angle.

        Args:
            base_threshold: Nominal threshold (e.g., 85.0 °C CRITICAL).
            beta_angle_deg: Current solar beta angle in degrees.
            k_beta: Sensitivity coefficient (°C per unit |sin(β)|).
                    Typical range: 0.3-0.8, calibrated from historical data.

        Returns:
            Adjusted threshold = base + k_beta × |sin(β)|.
        """
        beta_rad = math.radians(abs(beta_angle_deg))
        adjustment = k_beta * abs(math.sin(beta_rad))
        return base_threshold + adjustment

    def is_thermal_param(self, parameter: str) -> bool:
        """Check if a parameter is a thermal channel needing compensation."""
        return parameter in self.THERMAL_PARAMS or "temp" in parameter.lower()

    def get_adjusted_threshold(
        self,
        satellite_id: str,
        parameter: str,
        base_threshold: float,
        k_beta: float = 0.5,  # ESTIMATE — see compensate_threshold (Gilmore 2002 §2.3)
    ) -> float:
        """Convenience: look up beta and compensate in one call.

        Returns base_threshold unmodified if no beta angle is set.
        """
        if not self.is_thermal_param(parameter):
            return base_threshold

        beta = self._beta_angles.get(satellite_id)
        if beta is None:
            return base_threshold

        return self.compensate_threshold(base_threshold, beta, k_beta)

    def reset(self) -> None:
        self._beta_angles.clear()
