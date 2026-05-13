"""In-flight 3D printer + repair task queue.

Combines two related capabilities:

  1. **3D printer feedstock** — a buffer of metal/polymer powder consumed
     by repair tasks. Refilled from cargo manifest (currently a fixed
     starting allocation; could integrate with cargo tracking later).
  2. **Repair task queue** — pulls pending repair tasks from
     `hull_damage` and other subsystems, assigns crew-hours from
     `crew_schedule`, completes tasks based on print time + complexity.

Each repair task has:
  * source subsystem (hull region / part)
  * crew-hours required
  * feedstock kg required
  * priority (critical = patch hull breach; routine = scheduled service)

The 3D printer auto-pulls from the queue each tick if both feedstock
and crew-hours are available.

References
----------
  * Made-In-Space ZBLAN study (NASA TM-2018-219859) — orbital 3D-print
    feedstock requirements
  * NASA HRP 2022 Risk of Inadequate EVA Operations (HRR-3.7) for crew-hour
    repair-budget rationale
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Configuration ────────────────────────────────────────────────

INITIAL_FEEDSTOCK_KG: float = 5_000.0     # 5 t starting buffer (cargo manifest allocation)
PRINTER_THROUGHPUT_KG_PER_HR: float = 0.5  # NASA TM-2018-219859 typical FDM rate
PRINTER_POWER_W: float = 5_000.0           # 5 kW print head + thermal control

# Cost per hull-region repair task — derived from Whipple bumper specs
HULL_REPAIR_FEEDSTOCK_KG: float = 8.0    # ESTIMATE — patch + welding feedstock
HULL_REPAIR_CREW_HOURS:   float = 4.0    # ESTIMATE — single crew shift per patch


class TaskStatus(str, Enum):
    PENDING    = "pending"
    PRINTING   = "printing"
    INSTALLING = "installing"
    COMPLETE   = "complete"
    FAILED     = "failed"


@dataclass
class RepairTask:
    task_id: str
    source: str               # 'hull_zone_3' / 'shield_layer_2' / etc.
    label: str
    feedstock_kg: float
    crew_hours: float
    priority: int = 50        # higher = more critical
    status: TaskStatus = TaskStatus.PENDING
    progress_pct: float = 0.0
    created_at_yr: float = 0.0
    completed_at_yr: Optional[float] = None
    note: str = ""


@dataclass
class RepairQueueState:
    """Top-level state."""

    feedstock_kg: float = INITIAL_FEEDSTOCK_KG
    feedstock_capacity_kg: float = INITIAL_FEEDSTOCK_KG * 2  # could refill up to here from cargo
    queue: List[RepairTask] = field(default_factory=list)
    next_id: int = 1
    cumulative_completed: int = 0
    cumulative_failed:    int = 0
    cumulative_feedstock_used_kg: float = 0.0
    cumulative_crew_hours_used:   float = 0.0
    auto_pull_from_hull: bool = True   # automatically enqueue hull-damage repair tasks

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        dt_hr = dt_s / 3600.0

        # 1. Auto-pull pending hull-damage repair tasks
        if self.auto_pull_from_hull:
            try:
                from aria.simulator.hull_damage import get_hull_damage
                hd = get_hull_damage()
                for region in hd.regions.values():
                    # For each pending repair we don't yet have a task for, create one
                    open_for_region = sum(1 for t in self.queue
                                          if t.source == region.region_id
                                          and t.status not in (TaskStatus.COMPLETE, TaskStatus.FAILED))
                    deficit = region.repair_queue_depth - open_for_region
                    for _ in range(deficit):
                        self._enqueue_hull_repair(region.region_id, region.label)
            except Exception:
                pass

        # 2. Drain crew-hours budget for this tick from crew_schedule
        try:
            from aria.simulator.crew_schedule import get_crew_schedule
            cs = get_crew_schedule()
            available_crew_hours = cs.consume_repair_hours(dt_hr * 50)  # up to 50 crew on repairs
        except Exception:
            available_crew_hours = dt_hr * 10  # fallback if crew_schedule isn't registered

        # 3. Process the queue in priority order
        sorted_q = sorted(
            (t for t in self.queue if t.status in (TaskStatus.PENDING, TaskStatus.PRINTING, TaskStatus.INSTALLING)),
            key=lambda t: -t.priority,
        )
        for task in sorted_q:
            if available_crew_hours <= 0:
                break

            if task.status == TaskStatus.PENDING:
                # Try to start printing — needs feedstock
                if self.feedstock_kg < task.feedstock_kg:
                    task.note = f"Awaiting {task.feedstock_kg - self.feedstock_kg:.1f} kg feedstock"
                    continue
                self.feedstock_kg -= task.feedstock_kg
                self.cumulative_feedstock_used_kg += task.feedstock_kg
                task.status = TaskStatus.PRINTING
                task.created_at_yr = phase.elapsed_yr
                task.note = ""

            if task.status == TaskStatus.PRINTING:
                # Print time = feedstock / throughput
                print_time_hr = task.feedstock_kg / PRINTER_THROUGHPUT_KG_PER_HR
                # Use 20 % of crew-hours just to babysit the printer
                consumed = min(available_crew_hours, dt_hr * 0.2)
                available_crew_hours -= consumed
                self.cumulative_crew_hours_used += consumed
                # Progress proportional to print time elapsed
                # Guard: feedstock_kg==0 would otherwise div/0 — jump straight to install.
                if print_time_hr > 0.0:
                    task.progress_pct = min(50.0, task.progress_pct + 100.0 * (consumed / print_time_hr) * 0.5)
                else:
                    task.progress_pct = 50.0
                if task.progress_pct >= 50.0:
                    task.status = TaskStatus.INSTALLING

            if task.status == TaskStatus.INSTALLING:
                # Now install — consume the bulk of crew_hours
                consumed = min(available_crew_hours, task.crew_hours)
                available_crew_hours -= consumed
                self.cumulative_crew_hours_used += consumed
                # Progress: 50→100 % over crew_hours
                # Guard: crew_hours==0 would otherwise div/0 — complete immediately.
                if task.crew_hours > 0.0:
                    task.progress_pct = min(100.0, task.progress_pct + 100.0 * (consumed / task.crew_hours) * 0.5)
                else:
                    task.progress_pct = 100.0
                if task.progress_pct >= 100.0:
                    self._complete_task(task)

    # ── completion ───────────────────────────────────────────

    def _complete_task(self, task: RepairTask) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        task.status = TaskStatus.COMPLETE
        task.completed_at_yr = phase.elapsed_yr
        self.cumulative_completed += 1
        # If hull task, clear one repair from that region
        if task.source.startswith("hull_") or task.source == "bow_shield" or task.source == "stern_nozzle":
            try:
                from aria.simulator.hull_damage import get_hull_damage
                get_hull_damage().repair_one(task.source)
            except Exception:
                pass
        bus.publish(f"repair.complete.{task.source}",
                    severity="info", source="repair_queue",
                    payload={"task_id": task.task_id, "source": task.source,
                             "feedstock_kg": task.feedstock_kg,
                             "crew_hours": task.crew_hours},
                    sim_time_yr=phase.elapsed_yr)

    def _enqueue_hull_repair(self, region_id: str, region_label: str) -> RepairTask:
        task = RepairTask(
            task_id=f"task_{self.next_id:05d}",
            source=region_id,
            label=f"Patch {region_label}",
            feedstock_kg=HULL_REPAIR_FEEDSTOCK_KG,
            crew_hours=HULL_REPAIR_CREW_HOURS,
            priority=80,
            created_at_yr=get_phase_controller().elapsed_yr,
        )
        self.next_id += 1
        self.queue.append(task)
        return task

    # ── operator API ──────────────────────────────────────────

    def enqueue_custom(self, source: str, label: str, feedstock_kg: float,
                       crew_hours: float, priority: int = 50) -> RepairTask:
        task = RepairTask(
            task_id=f"task_{self.next_id:05d}",
            source=source, label=label,
            feedstock_kg=feedstock_kg, crew_hours=crew_hours, priority=priority,
            created_at_yr=get_phase_controller().elapsed_yr,
        )
        self.next_id += 1
        self.queue.append(task)
        return task

    def cancel(self, task_id: str) -> bool:
        for t in self.queue:
            if t.task_id == task_id and t.status in (TaskStatus.PENDING, TaskStatus.PRINTING):
                # Refund feedstock if we'd already consumed it
                if t.status == TaskStatus.PRINTING:
                    self.feedstock_kg += t.feedstock_kg
                    self.cumulative_feedstock_used_kg -= t.feedstock_kg
                t.status = TaskStatus.FAILED
                t.note = "Cancelled by operator"
                self.cumulative_failed += 1
                return True
        return False

    def refill_feedstock(self, kg: float) -> float:
        space = self.feedstock_capacity_kg - self.feedstock_kg
        added = min(kg, space)
        self.feedstock_kg += added
        return added

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        active = [t for t in self.queue if t.status not in (TaskStatus.COMPLETE, TaskStatus.FAILED)]
        return {
            "feedstock_kg": round(self.feedstock_kg, 2),
            "feedstock_capacity_kg": self.feedstock_capacity_kg,
            "feedstock_pct": round(100.0 * self.feedstock_kg / self.feedstock_capacity_kg, 1),
            "throughput_kg_per_hr": PRINTER_THROUGHPUT_KG_PER_HR,
            "auto_pull_from_hull": self.auto_pull_from_hull,
            "stats": {
                "total_tasks":       len(self.queue),
                "active_tasks":      len(active),
                "completed":         self.cumulative_completed,
                "failed":            self.cumulative_failed,
                "feedstock_used_kg": round(self.cumulative_feedstock_used_kg, 2),
                "crew_hours_used":   round(self.cumulative_crew_hours_used, 2),
            },
            "tasks": [
                {
                    "task_id":         t.task_id,
                    "source":          t.source,
                    "label":           t.label,
                    "feedstock_kg":    t.feedstock_kg,
                    "crew_hours":      t.crew_hours,
                    "priority":        t.priority,
                    "status":          t.status.value,
                    "progress_pct":    round(t.progress_pct, 1),
                    "created_at_yr":   round(t.created_at_yr, 4),
                    "completed_at_yr": round(t.completed_at_yr, 4) if t.completed_at_yr is not None else None,
                    "note":            t.note,
                }
                for t in self.queue[-30:]
            ],
        }


_DEFAULT: Optional[RepairQueueState] = None


def get_repair_queue() -> RepairQueueState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = RepairQueueState()
    return _DEFAULT


def reset_repair_queue() -> None:
    global _DEFAULT
    _DEFAULT = RepairQueueState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("repair_queue", get_repair_queue().tick, order=56)
