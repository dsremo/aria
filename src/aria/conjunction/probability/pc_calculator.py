"""
Unified collision probability calculator.

Automatically selects the best Pc method based on encounter characteristics:

Method selection logic:
  1. Mahalanobis > 5σ → Skip (Pc ≈ 0)
  2. Check short-encounter assumption via encounter duration τ
     τ = σ_along_track / v_rel
     If τ > T_orbit / 10 → 3D Monte Carlo (short-encounter breaks down)
  3. Otherwise → 2D Foster (NASA CARA standard)

Also computes P_max to detect the dilution regime.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from aria.conjunction.core.constants import PC_RED_THRESHOLD, PC_YELLOW_THRESHOLD
from aria.conjunction.core.types import CloseApproach, RiskLevel
from aria.conjunction.probability.chan import chan_pc
from aria.conjunction.probability.covariance import (
    combine_covariances,
    generate_default_covariance,
    generate_default_covariance_rtn,
    project_covariance_to_encounter_plane,
    rotate_covariance_rtn_to_eci,
)
from aria.conjunction.probability.foster import foster_pc
from aria.conjunction.probability.mahalanobis import (
    mahalanobis_distance,
    maximum_pc,
)
from aria.conjunction.probability.monte_carlo import monte_carlo_pc, monte_carlo_pc_3d

logger = logging.getLogger(__name__)


def _encounter_duration_seconds(
    covariance_3d: np.ndarray,
    relative_velocity: np.ndarray,
) -> float:
    """Estimate encounter duration τ = σ_along_track / |v_rel|.

    The encounter duration determines whether the short-encounter (2D)
    assumption is valid. If τ is comparable to the orbital period,
    the 2D projection underestimates risk.

    Args:
        covariance_3d: 3x3 combined position covariance (km²)
        relative_velocity: Relative velocity vector (km/s)

    Returns:
        Encounter duration in seconds
    """
    v_rel = np.asarray(relative_velocity, dtype=np.float64)
    v_mag = np.linalg.norm(v_rel)
    if v_mag < 1e-10:
        return float("inf")

    # Project covariance along relative velocity direction
    v_hat = v_rel / v_mag
    C = np.asarray(covariance_3d, dtype=np.float64)
    sigma_along_sq = float(v_hat @ C @ v_hat)
    sigma_along = math.sqrt(max(0.0, sigma_along_sq))

    return sigma_along / v_mag


class PcCalculator:
    """Unified collision probability calculator with automatic method selection."""

    def __init__(
        self,
        mahalanobis_threshold: float = 5.0,      # ESTIMATE — 5σ screening threshold (Alfano 2005 JGCD 28 427 practice)
        encounter_duration_limit_s: float = 600.0,  # ESTIMATE — 10-min encounter for Chan 2D validity (Chan 1997 AIAA-97-3837)
        mc_samples: int = 1_000_000,               # ESTIMATE — 1M samples for Pc <1e-4 resolution (Casali 2018 Adv Space Res)
        covariance_scale_factor: float = 1.0,       # ESTIMATE — 1.0 = use TLE covariance as-is
        default_position_sigma_km: float = 1.0,     # ESTIMATE — 1 km default σ (LEO TLE typical; Kelso 2009 Adv Astronaut Sci)
    ):
        """
        Args:
            mahalanobis_threshold: Skip Pc if D_M exceeds this (default 5.0)
            encounter_duration_limit_s: Use 3D MC if encounter > this (default 600s)
            mc_samples: Monte Carlo sample count
            covariance_scale_factor: Realism scaling for covariances
            default_position_sigma_km: Default σ when no covariance data
        """
        self.mahalanobis_threshold = mahalanobis_threshold
        self.encounter_duration_limit = encounter_duration_limit_s
        self.mc_samples = mc_samples
        self.covariance_scale_factor = covariance_scale_factor
        self.default_position_sigma_km = default_position_sigma_km

    def calculate_all_methods(
        self,
        approach: CloseApproach,
        mc_samples_quick: int = 10_000,
    ) -> dict[str, float]:
        """Compute Pc using Foster, Chan, and Monte Carlo in parallel.

        Returns a dict with keys "foster", "chan", "monte_carlo" and their Pc values.
        Used by the API to expose method disagreement to operators.
        A disagreement of >1 order of magnitude between any two methods is flagged.

        Args:
            approach: CloseApproach event (covariances will be resolved/defaulted).
            mc_samples_quick: MC sample count for the multi-method comparison
                (lower than the full run for speed; default 10k).

        Returns:
            {"foster": float, "chan": float, "monte_carlo": float,
             "disagreement": bool, "max_ratio": float}
        """
        pc_foster = self.calculate(approach, method="foster")
        pc_chan = self.calculate(approach, method="chan")
        pc_mc = self.calculate(approach, method="monte_carlo")

        values = [v for v in (pc_foster, pc_chan, pc_mc) if v > 0.0]
        if len(values) >= 2:
            max_ratio = max(values) / min(values)
            disagreement = max_ratio > 10.0  # >1 order of magnitude
        else:
            max_ratio = 1.0
            disagreement = False

        # Store on the approach object for downstream reporting
        approach.pc_foster = pc_foster
        approach.pc_chan = pc_chan
        approach.pc_monte_carlo = pc_mc
        approach.pc_method_disagreement = disagreement

        logger.info(
            "pc_multi_method",
            foster=f"{pc_foster:.2e}",
            chan=f"{pc_chan:.2e}",
            monte_carlo=f"{pc_mc:.2e}",
            disagreement=disagreement,
            max_ratio=f"{max_ratio:.1f}x",
        )
        return {
            "foster": pc_foster,
            "chan": pc_chan,
            "monte_carlo": pc_mc,
            "disagreement": disagreement,
            "max_ratio": max_ratio,
        }

    def calculate(
        self,
        approach: CloseApproach,
        method: str = "auto",
    ) -> float:
        """Calculate collision probability for a close approach event.

        Args:
            approach: CloseApproach with miss distance and relative velocity
            method: "auto", "foster", "chan", "monte_carlo", "monte_carlo_3d"

        Returns:
            Probability of collision [0, 1]
        """
        # Get or generate covariance matrices
        cov_primary = approach.primary_covariance
        cov_secondary = approach.secondary_covariance

        # Generate default covariances in RTN frame and rotate to ECI
        if cov_primary is None:
            cov_rtn = generate_default_covariance_rtn(
                position_sigma_km=self.default_position_sigma_km
            )
            if approach.primary_state is not None:
                cov_primary = rotate_covariance_rtn_to_eci(
                    cov_rtn,
                    approach.primary_state.position,
                    approach.primary_state.velocity,
                )
            else:
                cov_primary = generate_default_covariance(
                    position_sigma_km=self.default_position_sigma_km
                )

        if cov_secondary is None:
            cov_rtn = generate_default_covariance_rtn(
                position_sigma_km=self.default_position_sigma_km
            )
            if approach.secondary_state is not None:
                cov_secondary = rotate_covariance_rtn_to_eci(
                    cov_rtn,
                    approach.secondary_state.position,
                    approach.secondary_state.velocity,
                )
            else:
                cov_secondary = generate_default_covariance(
                    position_sigma_km=self.default_position_sigma_km
                )

        # Ensure 3x3 position-only
        if cov_primary.shape[0] > 3:
            cov_primary = cov_primary[:3, :3]
        if cov_secondary.shape[0] > 3:
            cov_secondary = cov_secondary[:3, :3]

        # Apply covariance realism scaling
        if self.covariance_scale_factor != 1.0:
            from aria.conjunction.probability.covariance import scale_covariance
            cov_primary = scale_covariance(cov_primary, self.covariance_scale_factor)
            cov_secondary = scale_covariance(cov_secondary, self.covariance_scale_factor)

        # P1-E1 (Jah): Check covariance condition number.
        # A condition number > 1000 indicates a near-singular covariance (ill-conditioned),
        # which produces unreliable Pc values. This happens when along-track uncertainty
        # is orders of magnitude larger than cross-track (typical for SGP4 covariances).
        # Reference: Carpenter & Markley (2014) AAS 14-378.
        cov_primary_cnum = float(np.linalg.cond(cov_primary))
        cov_secondary_cnum = float(np.linalg.cond(cov_secondary))
        if cov_primary_cnum > 1000.0 or cov_secondary_cnum > 1000.0:
            logger.warning(
                "covariance_ill_conditioned",
                primary_norad=approach.primary.norad_id,
                secondary_norad=approach.secondary.norad_id,
                primary_cond_num=f"{cov_primary_cnum:.1e}",
                secondary_cond_num=f"{cov_secondary_cnum:.1e}",
                note="Pc may be unreliable. Consider applying covariance_scale_factor >= 1.5.",
            )

        # Combine covariances (both must be in ECI)
        cov_combined = combine_covariances(cov_primary, cov_secondary)

        # Project to encounter plane
        miss_2d, cov_2d = project_covariance_to_encounter_plane(
            approach.relative_position,
            approach.relative_velocity_vec,
            cov_combined,
        )

        combined_radius = approach.combined_radius_km

        # Store Mahalanobis distance
        d_m = mahalanobis_distance(miss_2d, cov_2d)
        approach.mahalanobis_distance = d_m

        # Pre-filter: skip if Mahalanobis distance too large
        if d_m > self.mahalanobis_threshold:
            logger.debug(
                f"Skipping Pc for {approach.primary.norad_id} vs {approach.secondary.norad_id}: "
                f"D_M = {d_m:.1f} > {self.mahalanobis_threshold}"
            )
            approach.probability_of_collision = 0.0
            approach.risk_level = RiskLevel.GREEN
            return 0.0

        # Check P_max (dilution detection)
        p_max = maximum_pc(combined_radius, cov_2d)
        if p_max < PC_YELLOW_THRESHOLD * 0.01:
            logger.debug(
                f"Dilution regime: P_max = {p_max:.2e} — covariance too large for meaningful Pc"
            )

        # Select method
        if method == "auto":
            # Check short-encounter assumption
            enc_duration = _encounter_duration_seconds(
                cov_combined, approach.relative_velocity_vec
            )
            if enc_duration > self.encounter_duration_limit:
                method = "monte_carlo_3d"
                logger.info(
                    f"Short-encounter assumption INVALID: τ = {enc_duration:.1f}s > "
                    f"{self.encounter_duration_limit}s → using 3D Monte Carlo"
                )
            else:
                method = "foster"

        # Compute Pc
        if method == "foster":
            pc = foster_pc(miss_2d, cov_2d, combined_radius)
        elif method == "chan":
            pc = chan_pc(miss_2d, cov_2d, combined_radius)
        elif method == "monte_carlo":
            pc = monte_carlo_pc(miss_2d, cov_2d, combined_radius, self.mc_samples)
        elif method == "monte_carlo_3d":
            pc = monte_carlo_pc_3d(
                approach.relative_position,
                cov_combined,
                combined_radius,
                approach.relative_velocity_vec,
                n_samples=self.mc_samples,
            )
        else:
            raise ValueError(f"Unknown method: {method}")

        # Store results
        approach.probability_of_collision = pc
        approach.risk_level = self._classify_risk(pc)

        logger.info(
            f"Pc({approach.primary.norad_id} vs {approach.secondary.norad_id}) = {pc:.2e} "
            f"[{method}] D_M={d_m:.2f} miss={approach.miss_distance_km:.3f}km "
            f"-> {approach.risk_level.value}"
        )

        return pc

    @staticmethod
    def _classify_risk(pc: float) -> RiskLevel:
        if pc >= PC_RED_THRESHOLD:
            return RiskLevel.RED
        elif pc >= PC_YELLOW_THRESHOLD:
            return RiskLevel.YELLOW
        return RiskLevel.GREEN
