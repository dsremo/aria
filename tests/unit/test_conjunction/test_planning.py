"""Tests for collision avoidance maneuver planning."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from aria.conjunction.core.types import (
    CloseApproach,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
)
from aria.conjunction.maneuver.planning import ManeuverPlan, ManeuverPlanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    miss_km: float = 0.5,
    pc: float = 5e-4,
    risk: RiskLevel = RiskLevel.RED,
    tca: datetime | None = None,
    primary_sma: float = 7000.0,
) -> CloseApproach:
    if tca is None:
        tca = datetime(2024, 3, 15, 12, 0, 0)
    primary = SpaceObject(
        norad_id="25544", name="ISS",
        tle_line1="", tle_line2="",
        object_type=ObjectType.PAYLOAD, radius_m=50.0,
        elements=OrbitalElements(primary_sma, 0.001, 0.9, 0.0, 0.0, 0.0, tca),
    )
    secondary = SpaceObject(
        norad_id="99999", name="DEBRIS",
        tle_line1="", tle_line2="",
        object_type=ObjectType.DEBRIS, radius_m=0.1,
        elements=OrbitalElements(7002, 0.001, 0.9, 0.01, 0, 0, tca),
    )
    return CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=tca,
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([0.1, miss_km, 0.1]),
        relative_velocity_km_s=7.5,
        relative_position=np.array([miss_km, 0, 0]),
        relative_velocity_vec=np.array([0, 7.5, 0]),
        probability_of_collision=pc,
        risk_level=risk,
    )


# ---------------------------------------------------------------------------
# ManeuverPlanner.plan
# ---------------------------------------------------------------------------

class TestManeuverPlannerPlan:

    def test_green_event_returns_none(self):
        """GREEN risk level → no maneuver needed."""
        planner = ManeuverPlanner()
        approach = _make_approach(risk=RiskLevel.GREEN, pc=1e-7)
        current_time = datetime(2024, 3, 15, 0, 0, 0)  # 12h before TCA
        result = planner.plan(approach, current_time=current_time)
        assert result is None

    def test_red_event_returns_plan(self):
        """RED risk level → maneuver plan generated."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, pc=5e-4, tca=tca)
        current_time = tca - timedelta(hours=24)
        result = planner.plan(approach, current_time=current_time)
        assert result is not None
        assert isinstance(result, ManeuverPlan)

    def test_yellow_event_returns_plan(self):
        """YELLOW risk level → maneuver plan generated."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.YELLOW, pc=5e-5, tca=tca)
        current_time = tca - timedelta(hours=24)
        result = planner.plan(approach, current_time=current_time)
        assert result is not None

    def test_plan_has_positive_fuel_mass(self):
        """Fuel mass should be positive."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan.fuel_mass_kg > 0.0

    def test_plan_target_miss_distance_minimum(self):
        """Target miss distance should be at least the configured minimum."""
        planner = ManeuverPlanner(target_miss_km=10.0)
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, miss_km=0.5, tca=tca)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan.target_miss_distance_km >= 10.0

    def test_plan_target_miss_distance_multiplier(self):
        """Target should be at least 5x current miss distance."""
        planner = ManeuverPlanner(target_miss_km=0.0, target_miss_multiplier=5.0)
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, miss_km=3.0, tca=tca)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan.target_miss_distance_km >= 15.0  # 5x 3.0 km

    def test_burn_epoch_before_tca(self):
        """Burn should happen before TCA."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan.burn_epoch < tca

    def test_insufficient_lead_time_notes(self):
        """Very short lead time → notes should mention 'emergency'."""
        planner = ManeuverPlanner(min_lead_hours=2.0)
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        # Only 30 minutes available
        current_time = tca - timedelta(minutes=30)
        plan = planner.plan(approach, current_time=current_time)
        assert plan is not None
        assert "emergency" in plan.notes.lower() or "critical" in plan.notes.lower()

    def test_plan_uses_sma_from_primary(self):
        """Plan should use primary object's SMA for burn calculation."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca, primary_sma=7500.0)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan is not None  # uses 7500 SMA, not default 7000

    def test_plan_without_primary_elements(self):
        """If primary has no elements, plan uses default SMA."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        approach.primary.elements = None  # remove elements
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan is not None

    def test_plan_current_time_defaults_to_utcnow(self):
        """When current_time is None, should use utcnow."""
        planner = ManeuverPlanner()
        tca = datetime.utcnow() + timedelta(hours=24)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        plan = planner.plan(approach, current_time=None)
        assert plan is not None

    def test_plan_pre_maneuver_pc_stored(self):
        """plan.pre_maneuver_pc should match approach.probability_of_collision."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        approach = _make_approach(risk=RiskLevel.RED, pc=2.5e-4, tca=tca)
        current_time = tca - timedelta(hours=24)
        plan = planner.plan(approach, current_time=current_time)
        assert plan.pre_maneuver_pc == pytest.approx(2.5e-4)


# ---------------------------------------------------------------------------
# ManeuverPlanner.plan_batch
# ---------------------------------------------------------------------------

class TestManeuverPlannerBatch:

    def test_batch_empty(self):
        planner = ManeuverPlanner()
        result = planner.plan_batch([], current_time=datetime.utcnow())
        assert result == []

    def test_batch_filters_green(self):
        """GREEN events should not produce plans."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        green = _make_approach(risk=RiskLevel.GREEN, pc=1e-7, tca=tca)
        red = _make_approach(risk=RiskLevel.RED, pc=5e-4, tca=tca)
        current_time = tca - timedelta(hours=24)
        plans = planner.plan_batch([green, red], current_time=current_time)
        assert len(plans) == 1
        assert plans[0].pre_maneuver_pc == pytest.approx(5e-4)

    def test_batch_multiple_red(self):
        """Multiple RED events → multiple plans."""
        planner = ManeuverPlanner()
        tca = datetime(2024, 3, 15, 12, 0, 0)
        current_time = tca - timedelta(hours=24)
        approaches = [_make_approach(risk=RiskLevel.RED, pc=5e-4, tca=tca) for _ in range(3)]
        plans = planner.plan_batch(approaches, current_time=current_time)
        assert len(plans) == 3

    def test_batch_current_time_none(self):
        """plan_batch with current_time=None should work."""
        planner = ManeuverPlanner()
        tca = datetime.utcnow() + timedelta(hours=12)
        approach = _make_approach(risk=RiskLevel.RED, tca=tca)
        plans = planner.plan_batch([approach], current_time=None)
        assert len(plans) == 1
