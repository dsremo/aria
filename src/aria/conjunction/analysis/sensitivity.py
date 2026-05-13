"""
Sensitivity analysis for collision probability.

Answers operator questions:
  - "What if the covariance is 2x larger? 5x?"
  - "How does Pc change as the miss distance decreases?"
  - "At what miss distance does Pc cross the RED threshold?"
  - "How sensitive is Pc to the hard-body radius estimate?"
  - "What is the Pc dilution curve for this geometry?"

Produces parameter sweep data for decision support.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aria.conjunction.core.constants import PC_RED_THRESHOLD, PC_YELLOW_THRESHOLD
from aria.conjunction.probability.foster import foster_pc


@dataclass
class SensitivityResult:
    """Result of a parameter sweep."""

    parameter_name: str
    parameter_values: np.ndarray
    pc_values: np.ndarray
    red_threshold_crossing: float | None  # parameter value where Pc crosses RED
    yellow_threshold_crossing: float | None  # parameter value where Pc crosses YELLOW

    @property
    def max_pc(self) -> float:
        return float(np.max(self.pc_values))

    @property
    def min_pc(self) -> float:
        positive = self.pc_values[self.pc_values > 0]
        return float(np.min(positive)) if len(positive) > 0 else 0.0


class PcSensitivityAnalyzer:
    """Compute Pc sensitivity to various parameters."""

    @staticmethod
    def sweep_covariance_scale(
        miss_2d: np.ndarray,
        cov_2d: np.ndarray,
        combined_radius_km: float,
        scale_range: tuple[float, float] = (0.1, 10.0),
        n_points: int = 50,
    ) -> SensitivityResult:
        """Sweep covariance scaling factor and compute Pc at each.

        Shows the DILUTION CURVE: Pc rises with covariance initially
        (more uncertainty → more overlap), then falls (too much uncertainty
        → probability spread over too large a volume).

        Args:
            miss_2d: 2D miss vector (km)
            cov_2d: 2x2 baseline covariance (km²)
            combined_radius_km: R₁ + R₂ (km)
            scale_range: (min_scale, max_scale) for σ scaling
            n_points: Number of sweep points

        Returns:
            SensitivityResult with scale factors and Pc values
        """
        scales = np.logspace(
            np.log10(scale_range[0]), np.log10(scale_range[1]), n_points
        )
        pcs = np.zeros(n_points)

        miss = np.asarray(miss_2d, dtype=np.float64)
        C = np.asarray(cov_2d, dtype=np.float64)

        for i, s in enumerate(scales):
            C_scaled = C * s**2
            pcs[i] = foster_pc(miss, C_scaled, combined_radius_km)

        red_cross = _find_threshold_crossing(scales, pcs, PC_RED_THRESHOLD)
        yellow_cross = _find_threshold_crossing(scales, pcs, PC_YELLOW_THRESHOLD)

        return SensitivityResult(
            parameter_name="covariance_scale_factor",
            parameter_values=scales,
            pc_values=pcs,
            red_threshold_crossing=red_cross,
            yellow_threshold_crossing=yellow_cross,
        )

    @staticmethod
    def sweep_miss_distance(
        cov_2d: np.ndarray,
        combined_radius_km: float,
        miss_range_km: tuple[float, float] = (0.001, 50.0),
        n_points: int = 100,
        direction_deg: float = 0.0,
    ) -> SensitivityResult:
        """Sweep miss distance and compute Pc at each.

        Args:
            cov_2d: 2x2 covariance (km²)
            combined_radius_km: R₁ + R₂ (km)
            miss_range_km: (min, max) miss distance (km)
            n_points: Number of sweep points
            direction_deg: Direction of miss vector in encounter plane (degrees)

        Returns:
            SensitivityResult
        """
        import math

        distances = np.logspace(
            np.log10(miss_range_km[0]), np.log10(miss_range_km[1]), n_points
        )
        pcs = np.zeros(n_points)

        C = np.asarray(cov_2d, dtype=np.float64)
        dir_rad = math.radians(direction_deg)
        cos_d = math.cos(dir_rad)
        sin_d = math.sin(dir_rad)

        for i, d in enumerate(distances):
            miss = np.array([d * cos_d, d * sin_d])
            pcs[i] = foster_pc(miss, C, combined_radius_km)

        red_cross = _find_threshold_crossing(distances, pcs, PC_RED_THRESHOLD)
        yellow_cross = _find_threshold_crossing(distances, pcs, PC_YELLOW_THRESHOLD)

        return SensitivityResult(
            parameter_name="miss_distance_km",
            parameter_values=distances,
            pc_values=pcs,
            red_threshold_crossing=red_cross,
            yellow_threshold_crossing=yellow_cross,
        )

    @staticmethod
    def sweep_hard_body_radius(
        miss_2d: np.ndarray,
        cov_2d: np.ndarray,
        radius_range_m: tuple[float, float] = (0.01, 100.0),
        n_points: int = 50,
    ) -> SensitivityResult:
        """Sweep combined hard-body radius and compute Pc at each.

        Shows how sensitive Pc is to the object size estimate.
        For debris with uncertain size, this reveals how much the Pc
        could change with better size data.
        """
        radii_m = np.logspace(
            np.log10(radius_range_m[0]), np.log10(radius_range_m[1]), n_points
        )
        radii_km = radii_m / 1000.0
        pcs = np.zeros(n_points)

        miss = np.asarray(miss_2d, dtype=np.float64)
        C = np.asarray(cov_2d, dtype=np.float64)

        for i, r_km in enumerate(radii_km):
            pcs[i] = foster_pc(miss, C, r_km)

        red_cross = _find_threshold_crossing(radii_m, pcs, PC_RED_THRESHOLD)
        yellow_cross = _find_threshold_crossing(radii_m, pcs, PC_YELLOW_THRESHOLD)

        return SensitivityResult(
            parameter_name="hard_body_radius_m",
            parameter_values=radii_m,
            pc_values=pcs,
            red_threshold_crossing=red_cross,
            yellow_threshold_crossing=yellow_cross,
        )

    @staticmethod
    def compute_dilution_curve(
        miss_2d: np.ndarray,
        combined_radius_km: float,
        sigma_range: tuple[float, float] = (0.001, 100.0),
        n_points: int = 100,
    ) -> SensitivityResult:
        """Compute the full Pc dilution curve (Pc vs σ).

        The dilution curve shows the fundamental relationship between
        uncertainty size and collision probability. Pc peaks when
        σ ≈ miss_distance and falls off on both sides.

        Uses isotropic (circular) covariance for clean visualization.
        """
        sigmas = np.logspace(
            np.log10(sigma_range[0]), np.log10(sigma_range[1]), n_points
        )
        pcs = np.zeros(n_points)

        miss = np.asarray(miss_2d, dtype=np.float64)

        for i, sigma in enumerate(sigmas):
            C = np.diag([sigma**2, sigma**2])
            pcs[i] = foster_pc(miss, C, combined_radius_km)

        # Find the σ where Pc is maximum (peak of dilution curve)
        np.argmax(pcs)

        return SensitivityResult(
            parameter_name="covariance_sigma_km",
            parameter_values=sigmas,
            pc_values=pcs,
            red_threshold_crossing=_find_threshold_crossing(sigmas, pcs, PC_RED_THRESHOLD),
            yellow_threshold_crossing=_find_threshold_crossing(sigmas, pcs, PC_YELLOW_THRESHOLD),
        )


def _find_threshold_crossing(
    x: np.ndarray, y: np.ndarray, threshold: float,
) -> float | None:
    """Find the x value where y first crosses the threshold (from above)."""
    above = y >= threshold
    if not np.any(above):
        return None

    # Find first index where it crosses from above to below
    transitions = np.where(above[:-1] & ~above[1:])[0]
    if len(transitions) > 0:
        idx = transitions[0]
        # Linear interpolation
        if y[idx] != y[idx + 1]:
            x_cross = x[idx] + (x[idx + 1] - x[idx]) * (threshold - y[idx]) / (y[idx + 1] - y[idx])
            return float(x_cross)
        return float(x[idx])

    # If always above, return the last x where it's above
    return float(x[np.where(above)[0][-1]])
