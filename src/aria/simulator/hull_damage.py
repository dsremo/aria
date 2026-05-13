"""Hull damage tracker — per-region impact log + fatigue index.

Splits the 712 m hull into 8 axial zones plus the bow shield + stern
nozzle for a total of 10 trackable regions. Each region holds:

  * cumulative micrometeoroid (MMOD) impacts
  * cumulative MMOD-impact energy [J]
  * fatigue index 0..1 (Miner's-rule sum of damage from all impacts)
  * repair queue depth (tasks pending)
  * health % (100 - fatigue × 100)

Impacts can be added by:
  * `random_events.py` (MMOD strikes during cruise)
  * `failure_injector.py` (operator-driven scenarios)
  * direct API call

Repair tasks are simple: each impact above an energy threshold creates
a "patch needed" task; operator (or auto-repair) clears the queue.

References
----------
  * Miner 1945 "Cumulative damage in fatigue", J. Appl. Mech.
  * NASA TM-2017-219818 §6 (MMOD environment + impact energy distribution)
  * NASA-STD-7009 (shield design ballistic limit equations)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Region definitions ────────────────────────────────────────────

REGION_DEFS: List[tuple[str, str, float, float]] = [
    # (region_id, label, x_start_m, x_end_m)   relative to ship centre
    ("bow_shield",      "Bow Shield Cone",      356.0, 410.0),
    ("hull_zone_7",     "Hull Zone 7 (bow)",    267.0, 356.0),
    ("hull_zone_6",     "Hull Zone 6",          178.0, 267.0),
    ("hull_zone_5",     "Hull Zone 5",           89.0, 178.0),
    ("hull_zone_4",     "Hull Zone 4 (mid+)",     0.0,  89.0),
    ("hull_zone_3",     "Hull Zone 3 (mid-)",   -89.0,   0.0),
    ("hull_zone_2",     "Hull Zone 2",         -178.0, -89.0),
    ("hull_zone_1",     "Hull Zone 1",         -267.0, -178.0),
    ("hull_zone_0",     "Hull Zone 0 (stern)", -356.0, -267.0),
    ("stern_nozzle",    "Stern Nozzle",        -423.0, -356.0),
]

# Energy threshold above which an impact creates a repair task (per NASA STD-7009)
REPAIR_ENERGY_THRESHOLD_J: float = 5.0e3   # 5 kJ — typical Whipple penetration energy

# Fatigue contribution per joule of impact (Miner's-rule coefficient).
# Calibrated so a ship taking ~10⁵ impacts at 1 kJ each over the mission
# accumulates ~10 % fatigue per region — roughly NASA-LDEF-derived.
FATIGUE_J_TO_FRAC: float = 1.0e-9


@dataclass
class ImpactEvent:
    impact_id: str
    region_id: str
    energy_j: float
    sim_time_yr: float
    note: str = ""


@dataclass
class RegionState:
    region_id: str
    label: str
    x_start_m: float
    x_end_m: float

    impact_count: int = 0
    cumulative_energy_j: float = 0.0
    fatigue_index: float = 0.0
    repair_queue_depth: int = 0
    last_impact_at_yr: Optional[float] = None

    @property
    def health_pct(self) -> float:
        return max(0.0, 100.0 * (1.0 - self.fatigue_index))


@dataclass
class HullDamageState:
    """Top-level damage tracker."""

    regions: Dict[str, RegionState] = field(default_factory=dict)
    impacts: List[ImpactEvent] = field(default_factory=list)   # rolling log, last N
    impact_log_size: int = 200
    next_impact_id: int = 1
    cumulative_repairs: int = 0

    def __post_init__(self) -> None:
        if not self.regions:
            for rid, label, xs, xe in REGION_DEFS:
                self.regions[rid] = RegionState(region_id=rid, label=label, x_start_m=xs, x_end_m=xe)

    # ── public API ─────────────────────────────────────────────

    def record_impact(self, region_id: str, energy_j: float, note: str = "") -> ImpactEvent:
        """Register an MMOD/debris impact. Updates region fatigue + emits event."""
        bus = get_event_bus()
        phase = get_phase_controller()
        if region_id not in self.regions:
            # default to mid-hull if invalid region
            region_id = "hull_zone_4"
        region = self.regions[region_id]
        impact = ImpactEvent(
            impact_id=f"imp_{self.next_impact_id:05d}",
            region_id=region_id,
            energy_j=float(energy_j),
            sim_time_yr=phase.elapsed_yr,
            note=note,
        )
        self.next_impact_id += 1
        # Update region
        region.impact_count += 1
        region.cumulative_energy_j += energy_j
        region.fatigue_index = min(1.0, region.fatigue_index + energy_j * FATIGUE_J_TO_FRAC)
        region.last_impact_at_yr = phase.elapsed_yr
        if energy_j >= REPAIR_ENERGY_THRESHOLD_J:
            region.repair_queue_depth += 1
        # Roll the impact log
        self.impacts.append(impact)
        if len(self.impacts) > self.impact_log_size:
            self.impacts.pop(0)
        # Publish to bus. Severity tiers by *either* cumulative fatigue
        # or single-impact energy: the old rule only fired critical after
        # fatigue > 0.3, so a 98 kJ single strike on a pristine region
        # (≈20× Whipple penetration energy) still reported as `warning`.
        # Real ops need a critical ping on any shield-penetrating hit.
        CRITICAL_SINGLE_IMPACT_J = 5.0 * REPAIR_ENERGY_THRESHOLD_J   # 25 kJ — shield penetration envelope
        if region.fatigue_index > 0.3 or energy_j >= CRITICAL_SINGLE_IMPACT_J:
            sev = "critical"
        elif energy_j > REPAIR_ENERGY_THRESHOLD_J:
            sev = "warning"
        else:
            sev = "info"
        bus.publish(f"hull.impact.{region_id}",
                    severity=sev, source="hull_damage",
                    payload={"impact_id": impact.impact_id, "energy_j": energy_j,
                             "fatigue_index": round(region.fatigue_index, 4),
                             "health_pct": round(region.health_pct, 2),
                             "queue_depth": region.repair_queue_depth},
                    sim_time_yr=phase.elapsed_yr)
        return impact

    def repair_one(self, region_id: str) -> bool:
        """Clear one repair task in `region_id`. Returns True if anything cleared."""
        if region_id not in self.regions:
            return False
        region = self.regions[region_id]
        if region.repair_queue_depth <= 0:
            return False
        region.repair_queue_depth -= 1
        # Repair restores some fatigue (not fully — repaired patches aren't
        # as good as virgin hull — Miner 1945 §3 residual damage)
        region.fatigue_index = max(0.0, region.fatigue_index - 0.005)
        self.cumulative_repairs += 1
        bus = get_event_bus()
        phase = get_phase_controller()
        bus.publish(f"hull.repair.{region_id}",
                    severity="info", source="hull_damage",
                    payload={"region_id": region_id,
                             "queue_depth": region.repair_queue_depth,
                             "fatigue_index": round(region.fatigue_index, 4)},
                    sim_time_yr=phase.elapsed_yr)
        return True

    def repair_all(self, region_id: str) -> int:
        """Clear all pending repair tasks in `region_id`."""
        if region_id not in self.regions:
            return 0
        n = self.regions[region_id].repair_queue_depth
        for _ in range(n):
            self.repair_one(region_id)
        return n

    def total_repairs_pending(self) -> int:
        return sum(r.repair_queue_depth for r in self.regions.values())

    def worst_fatigue_region(self) -> RegionState:
        return max(self.regions.values(), key=lambda r: r.fatigue_index)

    # ── tick (no-op for now; impacts are pushed externally) ────

    def tick(self, dt_s: float) -> None:
        # Damage tracking is event-driven, not time-integrated.
        # Tick exists so the module is uniform with the rest.
        return

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "regions": [
                {
                    "region_id":          r.region_id,
                    "label":              r.label,
                    "x_start_m":          r.x_start_m,
                    "x_end_m":            r.x_end_m,
                    "impact_count":       r.impact_count,
                    "cumulative_energy_j": round(r.cumulative_energy_j, 1),
                    "fatigue_index":      round(r.fatigue_index, 5),
                    "health_pct":         round(r.health_pct, 2),
                    "repair_queue_depth": r.repair_queue_depth,
                    "last_impact_at_yr":  r.last_impact_at_yr,
                }
                for r in self.regions.values()
            ],
            "next_impact_id":       self.next_impact_id,
            "cumulative_repairs":   self.cumulative_repairs,
            "recent_impacts": [
                {"impact_id": i.impact_id, "region_id": i.region_id,
                 "energy_j": i.energy_j, "sim_time_yr": round(i.sim_time_yr, 4),
                 "note": i.note}
                for i in self.impacts[-30:]
            ],
            "stats": {
                # Sum per-region counters — self.impacts is a 200-slot
                # ring buffer, not a cumulative counter. Old total read
                # the ring length (200) instead of the 11 060 actual
                # impacts recorded on a century-long Proxima run.
                "total_impacts":    sum(r.impact_count for r in self.regions.values()),
                "total_repairs":    self.cumulative_repairs,
                "repairs_pending":  self.total_repairs_pending(),
                "worst_region":     self.worst_fatigue_region().region_id,
                "worst_fatigue":    round(self.worst_fatigue_region().fatigue_index, 4),
            },
        }

    def restore_from_dict(self, saved: dict) -> list[str]:
        """Custom restore: the on-wire shape uses a *list* of region dicts
        (for UI convenience) but the in-memory attribute is a Dict[str, RegionState].
        The generic setattr loop in mission_persistence can't bridge that gap,
        so this method rebuilds RegionState + ImpactEvent objects explicitly."""
        applied: list[str] = []
        for rdict in saved.get("regions", []) or []:
            rid = rdict.get("region_id")
            if rid and rid in self.regions:
                r = self.regions[rid]
                r.impact_count        = int(rdict.get("impact_count", 0))
                r.cumulative_energy_j = float(rdict.get("cumulative_energy_j", 0.0))
                r.fatigue_index       = float(rdict.get("fatigue_index", 0.0))
                r.repair_queue_depth  = int(rdict.get("repair_queue_depth", 0))
                r.last_impact_at_yr   = rdict.get("last_impact_at_yr")
        applied.append("regions")
        # Impacts log is ephemeral (rolling 30); restore only the counters.
        self.impacts.clear()
        for idict in saved.get("recent_impacts", []) or []:
            try:
                self.impacts.append(ImpactEvent(
                    impact_id=str(idict.get("impact_id", "")),
                    region_id=str(idict.get("region_id", "")),
                    energy_j=float(idict.get("energy_j", 0.0)),
                    sim_time_yr=float(idict.get("sim_time_yr", 0.0)),
                    note=str(idict.get("note", "")),
                ))
            except (TypeError, ValueError):
                continue
        applied.append("impacts")
        self.next_impact_id     = int(saved.get("next_impact_id", self.next_impact_id))
        self.cumulative_repairs = int(saved.get("cumulative_repairs", 0))
        applied.extend(["next_impact_id", "cumulative_repairs"])
        return applied


_DEFAULT: Optional[HullDamageState] = None


def get_hull_damage() -> HullDamageState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = HullDamageState()
    return _DEFAULT


def reset_hull_damage() -> None:
    global _DEFAULT
    _DEFAULT = HullDamageState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("hull_damage", get_hull_damage().tick, order=55)
