"""
Collision avoidance maneuver planning.

Given a CloseApproach event with Pc above threshold:
  1. Compute optimal burn time and direction
  2. Estimate ΔV and fuel cost
  3. Verify post-maneuver Pc drops below threshold

Planning rules:
  - Minimum lead time: 2 hours (below this, ΔV becomes prohibitive)
  - Preferred lead time: 12-24 hours (Starlink standard)
  - Target post-maneuver miss distance: 5x current miss distance or 10 km, whichever is larger
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from aria.conjunction.core.types import CloseApproach, RiskLevel
from aria.conjunction.maneuver.delta_v import BurnRecommendation, optimal_burn_direction
from aria.conjunction.maneuver.fuel_cost import fuel_mass_required

logger = logging.getLogger(__name__)


@dataclass
class ManeuverPlan:
    """Complete collision avoidance maneuver plan."""

    approach: CloseApproach
    burn: BurnRecommendation
    burn_epoch: datetime
    fuel_mass_kg: float  # estimated fuel consumption
    target_miss_distance_km: float
    pre_maneuver_pc: float
    notes: str = ""


class ManeuverPlanner:
    """Plan collision avoidance maneuvers for high-risk close approaches."""

    def __init__(
        self,
        min_lead_hours: float = 2.0,
        preferred_lead_hours: float = 24.0,
        target_miss_km: float = 10.0,
        target_miss_multiplier: float = 5.0,
        spacecraft_dry_mass_kg: float = 250.0,
        isp_seconds: float = 220.0,  # monopropellant hydrazine
    ):
        self.min_lead_hours = min_lead_hours
        self.preferred_lead_hours = preferred_lead_hours
        self.target_miss_km = target_miss_km
        self.target_miss_multiplier = target_miss_multiplier
        self.spacecraft_dry_mass_kg = spacecraft_dry_mass_kg
        self.isp_seconds = isp_seconds

    def plan(
        self,
        approach: CloseApproach,
        current_time: datetime | None = None,
    ) -> ManeuverPlan | None:
        """Generate a maneuver plan for a close approach event.

        Args:
            approach: CloseApproach event
            current_time: Current time (for lead time calculation)

        Returns:
            ManeuverPlan, or None if maneuver is not needed or not feasible
        """
        if current_time is None:
            current_time = datetime.utcnow()

        # Check if maneuver is needed
        pc = approach.probability_of_collision or 0.0
        if approach.risk_level == RiskLevel.GREEN:
            return None

        # Calculate available lead time
        available_lead_s = (approach.tca - current_time).total_seconds()
        if available_lead_s < self.min_lead_hours * 3600:
            logger.warning(
                f"Insufficient lead time for maneuver: "
                f"{available_lead_s/3600:.1f}h < {self.min_lead_hours}h minimum"
            )
            lead_h = available_lead_s / 3600
            notes = f"CRITICAL: Only {lead_h:.1f}h available. Emergency burn required."
        else:
            notes = ""

        # Determine burn lead time
        lead_s = min(available_lead_s, self.preferred_lead_hours * 3600)
        lead_s = max(lead_s, 60.0)  # at least 1 minute

        # Determine target miss distance
        target_miss = max(
            self.target_miss_km,
            approach.miss_distance_km * self.target_miss_multiplier,
        )

        # Get semi-major axis from primary object
        sma = 7000.0  # default ~630 km altitude
        if approach.primary.elements:
            sma = approach.primary.elements.semi_major_axis

        # Compute optimal burn
        burn = optimal_burn_direction(target_miss, lead_s, sma)

        # Compute burn epoch
        burn_epoch = approach.tca - timedelta(seconds=lead_s)

        # Estimate fuel cost
        fuel_kg = fuel_mass_required(
            delta_v_m_s=burn.delta_v_m_s,
            dry_mass_kg=self.spacecraft_dry_mass_kg,
            isp_s=self.isp_seconds,
        )

        plan = ManeuverPlan(
            approach=approach,
            burn=burn,
            burn_epoch=burn_epoch,
            fuel_mass_kg=fuel_kg,
            target_miss_distance_km=target_miss,
            pre_maneuver_pc=pc,
            notes=notes,
        )

        logger.info(
            f"Maneuver plan: {burn.direction} burn of {burn.delta_v_m_s:.4f} m/s "
            f"at {burn_epoch.isoformat()} ({lead_s/3600:.1f}h before TCA) "
            f"→ target {target_miss:.1f} km separation, fuel: {fuel_kg:.4f} kg"
        )

        return plan

    def plan_batch(
        self,
        approaches: list[CloseApproach],
        current_time: datetime | None = None,
    ) -> list[ManeuverPlan]:
        """Generate maneuver plans for multiple close approaches.

        Only plans maneuvers for YELLOW and RED risk levels.
        """
        plans = []
        for approach in approaches:
            plan = self.plan(approach, current_time)
            if plan is not None:
                plans.append(plan)
        return plans
