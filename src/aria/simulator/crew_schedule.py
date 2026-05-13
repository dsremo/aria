"""Crew shift scheduler — circadian rhythm + productivity tracking.

A 1 000-crew ship runs 24/7 in 3 shifts of ~333 crew each. This module
tracks:

  * which crew are currently on-shift / off-shift / asleep
  * cumulative work-hours per shift band
  * productivity index (0..1) modulated by:
      - circadian phase (shift handover dip)
      - bone density (Wave-4 crew health feedback)
      - psychological cohesion (low cohesion → reduced output)
      - sleep debt (forced overtime → cumulative debt → impaired)
  * how many crew-hours are available for repair / maintenance per day
    (consumed by the 3D-printer / repair-queue module B36)

References
----------
  * Czeisler 1999 "Stability, precision, and near-24-hour period of the
    human circadian pacemaker" Science 284:2177 (circadian period model)
  * Van Dongen 2003 Sleep 26:117 (cumulative cognitive deficit from sleep loss)
  * NASA HRP 2022 Risk of Performance Errors Due to Sleep Loss (HRR-3.13)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Configuration ────────────────────────────────────────────────

SHIFT_HOURS:   float = 8.0          # 8-hr work shift (NASA HRP standard)
HANDOVER_DIP:  float = 0.15          # 15 % productivity drop during the 30 min handover
SLEEP_HOURS:   float = 8.0          # nominal sleep per 24 hr
RECREATION_HOURS: float = 8.0       # 24 - 8 - 8

# Circadian phase model — Czeisler 1999 finds endogenous period 24.18 hr;
# we use 24.0 for simplicity. Performance dip nadirs at ~03:00 local time.
CIRCADIAN_PERIOD_HR: float = 24.0
CIRCADIAN_DIP_HOUR:  float = 3.0    # nadir time within the 24-hr cycle

# Sleep-debt accumulation — Van Dongen 2003 Eq. 1 (linear approximation
# for short-duration deprivation; 4 hr/night under nominal saturates at 16 hr debt)
MAX_SLEEP_DEBT_HR: float = 24.0

# Productivity-loss factor per missed sleep hour (Van Dongen 2003 §3)
PRODUCTIVITY_PER_SLEEP_HOUR_LOST: float = 0.05    # 5 % productivity lost per missed hour


@dataclass
class ShiftBand:
    """One of three rotating shift bands."""

    band_id:    str               # 'A', 'B', 'C'
    crew_count: int
    on_duty_start_hr: float       # 0..24, when this band starts work in local time
    sleep_debt_hr:  float = 0.0   # cumulative
    productivity_index: float = 1.0   # 0..1 scaled current productivity

    def is_on_duty(self, local_hr: float) -> bool:
        """True if `local_hr` falls within this band's work shift."""
        end = (self.on_duty_start_hr + SHIFT_HOURS) % 24.0
        if self.on_duty_start_hr <= end:
            return self.on_duty_start_hr <= local_hr < end
        return local_hr >= self.on_duty_start_hr or local_hr < end

    def is_sleeping(self, local_hr: float) -> bool:
        """True if `local_hr` falls within this band's sleep block (8 hr after recreation)."""
        # Sleep starts SHIFT_HOURS + RECREATION_HOURS after on-duty start
        sleep_start = (self.on_duty_start_hr + SHIFT_HOURS + RECREATION_HOURS) % 24.0
        sleep_end   = (sleep_start + SLEEP_HOURS) % 24.0
        if sleep_start <= sleep_end:
            return sleep_start <= local_hr < sleep_end
        return local_hr >= sleep_start or local_hr < sleep_end


@dataclass
class CrewScheduleState:
    """Top-level shift state for the whole crew."""

    # R8 (2026-04-24, sync refactor): see crew_health / agriculture_yield.
    # Was a literal 1000 here with no link to the rest of the codebase;
    # shifted to MissionState so a population change propagates to
    # shift sizing automatically.
    @property
    def crew_size(self) -> int:
        from aria.core.mission_state import get_mission_state
        return get_mission_state().crew_alive

    # Three rotating bands offset by 8 hr each
    bands: Dict[str, ShiftBand] = field(default_factory=dict)

    # Local "ship time" in hours since mission day 0 — increments with sim ticks
    local_clock_hr: float = 0.0

    # Cumulative
    total_work_hours_delivered: float = 0.0
    total_repair_hours_used:    float = 0.0

    # Per-tick output
    on_duty_now: int = 0
    sleeping_now: int = 0
    recreation_now: int = 0
    crew_hours_per_day_available: float = 0.0
    avg_productivity: float = 1.0

    def __post_init__(self) -> None:
        if not self.bands:
            third = self.crew_size // 3
            self.bands = {
                "A": ShiftBand(band_id="A", crew_count=third,            on_duty_start_hr=0.0),
                "B": ShiftBand(band_id="B", crew_count=third,            on_duty_start_hr=8.0),
                "C": ShiftBand(band_id="C", crew_count=self.crew_size - 2*third, on_duty_start_hr=16.0),
            }

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        # Convert dt_s to ship-local hours
        dt_hr = dt_s / 3600.0
        self.local_clock_hr = (self.local_clock_hr + dt_hr) % 24.0

        # Crew metabolic scale from phase (skeleton crew during PRELAUNCH)
        crew_active_frac = phase.spec().crew_metabolic_frac

        # Read crew health from Wave-4 module
        try:
            from aria.simulator.crew_health import get_crew_health
            ch = get_crew_health()
            health_factor = max(0.5, ch.bone_density_pct / 100.0)
            psych_factor  = max(0.4, ch.psych_cohesion_pct / 100.0)
        except Exception:
            health_factor = 1.0
            psych_factor  = 1.0

        # Compute per-band metrics
        on_duty = 0
        sleeping = 0
        recreation = 0
        crew_hours_today = 0.0
        prod_sum = 0.0

        for band in self.bands.values():
            scaled_count = int(band.crew_count * crew_active_frac)
            if band.is_on_duty(self.local_clock_hr):
                on_duty += scaled_count
                # Productivity: circadian × handover × health × psych × sleep-debt
                circ = self._circadian_factor(self.local_clock_hr)
                handover = self._handover_factor(self.local_clock_hr, band)
                debt = max(0.0, 1.0 - band.sleep_debt_hr * PRODUCTIVITY_PER_SLEEP_HOUR_LOST)
                band.productivity_index = circ * handover * health_factor * psych_factor * debt
                crew_hours_today += scaled_count * dt_hr * band.productivity_index
                prod_sum += band.productivity_index
            elif band.is_sleeping(self.local_clock_hr):
                sleeping += scaled_count
                # Sleeping refunds debt: 1 hr sleep refunds up to 1 hr debt
                band.sleep_debt_hr = max(0.0, band.sleep_debt_hr - dt_hr)
                band.productivity_index = 0.0
            else:
                recreation += scaled_count
                band.productivity_index = 0.0

        self.on_duty_now = on_duty
        self.sleeping_now = sleeping
        self.recreation_now = recreation
        self.total_work_hours_delivered += crew_hours_today
        self.crew_hours_per_day_available = crew_hours_today * (24.0 / max(dt_hr, 0.001))
        self.avg_productivity = prod_sum / 3.0
        # Per-tick budget for consume_repair_hours(). Previously the cap
        # was `crew_hours_per_day_available − total_repair_hours_used`,
        # which meant the repair queue got at most ~1594 hr across the
        # ENTIRE mission — after the first few ticks total_repair_hours
        # exceeded the daily budget and every subsequent tick granted 0.
        # Reset a tick-local budget so repair throughput scales with
        # the actual crew-hours generated each tick (not a daily cap).
        self._repair_budget_this_tick_hr = crew_hours_today

    # ── operator API ──────────────────────────────────────────

    def consume_repair_hours(self, hours: float) -> float:
        """Called by the 3D printer / repair queue. Returns hours actually
        granted (up to this tick's generated crew-hours budget)."""
        available = getattr(self, "_repair_budget_this_tick_hr", 0.0)
        granted = max(0.0, min(hours, available))
        self._repair_budget_this_tick_hr = available - granted
        self.total_repair_hours_used += granted
        return granted

    def force_overtime(self, band_id: str, extra_hours: float) -> None:
        """Operator can pull a band onto extra work, accruing sleep debt."""
        if band_id not in self.bands:
            return
        band = self.bands[band_id]
        band.sleep_debt_hr = min(MAX_SLEEP_DEBT_HR, band.sleep_debt_hr + extra_hours)
        bus = get_event_bus()
        phase = get_phase_controller()
        bus.publish("crew.overtime",
                    severity="warning", source="crew_schedule",
                    payload={"band": band_id, "extra_hours": extra_hours,
                             "new_debt_hr": round(band.sleep_debt_hr, 2)},
                    sim_time_yr=phase.elapsed_yr)

    # ── circadian model ──────────────────────────────────────

    def _circadian_factor(self, local_hr: float) -> float:
        """Performance multiplier 0..1 based on time of day. Czeisler 1999
        model — sinusoidal with min at CIRCADIAN_DIP_HOUR (~03:00)."""
        phase = 2 * math.pi * (local_hr - CIRCADIAN_DIP_HOUR) / CIRCADIAN_PERIOD_HR
        # 0.85 .. 1.0 range
        return 0.925 + 0.075 * math.cos(phase)

    def _handover_factor(self, local_hr: float, band: ShiftBand) -> float:
        """During the first 30 min of a shift, productivity is reduced
        (handover briefing, context-switch)."""
        time_in_shift = (local_hr - band.on_duty_start_hr) % 24.0
        if 0.0 <= time_in_shift < 0.5:
            return 1.0 - HANDOVER_DIP
        return 1.0

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "crew_size": self.crew_size,
            "local_clock_hr": round(self.local_clock_hr, 2),
            "on_duty_now":   self.on_duty_now,
            "sleeping_now":  self.sleeping_now,
            "recreation_now": self.recreation_now,
            "avg_productivity": round(self.avg_productivity, 4),
            "crew_hours_per_day_available": round(self.crew_hours_per_day_available, 1),
            "total_work_hours_delivered":   round(self.total_work_hours_delivered, 1),
            "total_repair_hours_used":      round(self.total_repair_hours_used, 1),
            "bands": [
                {
                    "band_id":     b.band_id,
                    "crew_count":  b.crew_count,
                    "on_duty_start_hr": b.on_duty_start_hr,
                    "is_on_duty":  b.is_on_duty(self.local_clock_hr),
                    "is_sleeping": b.is_sleeping(self.local_clock_hr),
                    "sleep_debt_hr": round(b.sleep_debt_hr, 2),
                    "productivity_index": round(b.productivity_index, 4),
                }
                for b in self.bands.values()
            ],
        }


_DEFAULT: Optional[CrewScheduleState] = None


def get_crew_schedule() -> CrewScheduleState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CrewScheduleState()
    return _DEFAULT


def reset_crew_schedule() -> None:
    global _DEFAULT
    _DEFAULT = CrewScheduleState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("crew_schedule", get_crew_schedule().tick, order=47)
