from __future__ import annotations
import pytest
from aria.simulation.crew_workload import (
    CrewMember, cognitive_performance, accumulate_sleep_debt,
    mission_readiness, simulate_crew_schedule,
)


def test_rested_crew_high_performance():
    assert cognitive_performance(sleep_debt_h=0, circadian_phase_h=0,
                                   current_mission_hour=20) > 0.9


def test_sleep_debt_reduces_performance():
    rested = cognitive_performance(0, 0, 12)
    tired = cognitive_performance(30, 0, 12)
    assert tired < rested


def test_sleep_debt_accumulates_under_high_workload():
    c = CrewMember(name="LMP")
    for _ in range(5):
        c = accumulate_sleep_debt(c, shift_workload_hrs=18.0)
    assert c.sleep_debt_h > 0


def test_sleep_debt_recovers_with_rest():
    c = CrewMember(name="LMP", sleep_debt_h=20.0)
    for _ in range(5):
        c = accumulate_sleep_debt(c, shift_workload_hrs=8.0)
    assert c.sleep_debt_h < 20.0


def test_mission_readiness_range():
    crew = [CrewMember("A"), CrewMember("B"), CrewMember("C")]
    r = mission_readiness(crew, 0)
    assert 0.0 <= r <= 1.0


def test_simulate_produces_daily_trace():
    crew = [CrewMember("A")]
    # 14 days of heavy workload
    traj = simulate_crew_schedule(crew, [16.0] * 14)
    assert len(traj) == 14
    # Debt should build up over time
    assert traj[-1][2] > traj[0][2]
