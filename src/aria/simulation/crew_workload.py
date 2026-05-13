"""Crew workload, sleep debt, and cognitive-performance model.

Integrates:
  - Van Dongen & Dinges (2003) two-process sleep-debt accumulation
  - Caldwell NASA TM-2009-215724 cognitive decrement curves
  - Mission-phase scheduling (launch / cruise / descent busy periods)

Output: per-crew performance factor [0..1] used by FDIR + LLM agents as
the multiplier on command latency and error probability.

Reference:
    Van Dongen, H. P. A. et al. (2003) "The cumulative cost of additional
        wakefulness," Sleep 26(2):117.
    Caldwell, J. A. (2005) "Fatigue in aviation," Travel Med Infect Dis.
    Czeisler, C. A. (1999) "Stability, precision, and near-24-hour
        period of the human circadian pacemaker," Science 284:2177.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class CrewMember:
    name: str
    shift: str = "A"            # A/B/C rotation band
    sleep_hours_24h: float = 7.0
    sleep_debt_h: float = 0.0   # cumulative hours lost
    circadian_phase_h: float = 0.0    # 0 = subjective day peak


def cognitive_performance(sleep_debt_h: float, circadian_phase_h: float,
                          current_mission_hour: float = 0.0) -> float:
    """Return performance [0..1]: 1 = fully rested, 0.3 = severely impaired.

    Two-process model: process S (sleep-debt) × process C (circadian).
    """
    # Process S: exponential decay with time awake beyond 16 h
    s_factor = math.exp(-sleep_debt_h / 40.0)  # 40-h debt ≈ 37% perf
    # Process C: sinusoidal circadian with trough 04:00, peak 20:00
    h_local = (current_mission_hour + circadian_phase_h) % 24
    # Peak performance at h_local=20, trough at h_local=4
    c_factor = 0.5 + 0.5 * math.cos(2 * math.pi * (h_local - 4) / 24 - math.pi)
    c_scaled = 0.75 + 0.25 * c_factor   # 0.75..1.0 range
    return s_factor * c_scaled


def accumulate_sleep_debt(crew: CrewMember, shift_workload_hrs: float,
                          dt_hours: float = 24.0) -> CrewMember:
    """Update a crew member's sleep debt after a 24-h cycle."""
    # Scheduled sleep opportunity = 24 - work - overhead (2h for meals/hygiene)
    ideal_sleep = 8.0
    actual_sleep = max(2.0, 24.0 - shift_workload_hrs - 2.0)
    deficit = max(0.0, ideal_sleep - actual_sleep)
    # Recovery: if workload < 10 and sleep > ideal, reduce debt
    if actual_sleep >= 8:
        recovery = min(crew.sleep_debt_h, (actual_sleep - 8) * 0.5 + 1.0)
        crew = CrewMember(
            name=crew.name, shift=crew.shift,
            sleep_hours_24h=actual_sleep,
            sleep_debt_h=max(0.0, crew.sleep_debt_h - recovery),
            circadian_phase_h=crew.circadian_phase_h,
        )
    else:
        crew = CrewMember(
            name=crew.name, shift=crew.shift,
            sleep_hours_24h=actual_sleep,
            sleep_debt_h=crew.sleep_debt_h + deficit,
            circadian_phase_h=crew.circadian_phase_h,
        )
    return crew


def mission_readiness(crew: List[CrewMember], mission_hour: float) -> float:
    """Fleet-average cognitive performance across the crew."""
    if not crew:
        return 0.0
    scores = [cognitive_performance(c.sleep_debt_h, c.circadian_phase_h, mission_hour)
              for c in crew]
    return sum(scores) / len(scores)


def simulate_crew_schedule(crew: List[CrewMember],
                            workload_plan: List[float],
                            ) -> List[tuple]:
    """Apply N 24-hour cycles of work. Returns (day, readiness, debt_avg)."""
    out = []
    for d, wl_hrs in enumerate(workload_plan):
        crew = [accumulate_sleep_debt(c, wl_hrs) for c in crew]
        r = mission_readiness(crew, mission_hour=d * 24)
        avg_debt = sum(c.sleep_debt_h for c in crew) / len(crew)
        out.append((d, r, avg_debt))
    return out
