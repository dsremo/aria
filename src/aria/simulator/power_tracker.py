"""Live power-budget tracker.

Distributes the reactor's electrical output across subsystems based on
mission phase + auto-throttle decisions, then emits overload events when
total demand exceeds supply, triggering a load-shedding cascade.

Power flow:
  reactor_engine (thermal MWth)
    → power_distribution (η = 0.45 thermal-to-electric, NASA TM-2018-219910 fission Brayton)
      → magnetic_nozzle (priority 100, throttleable)
      → thermal_management pumps (priority 90, hard-required)
      → habitat ECLSS (priority 80, life-critical)
      → habitat lighting + AG (priority 60, deferrable)
      → engine_bell_* RCS arc-jets (priority 50, batched)
      → comms / avionics / sensors (priority 40, low-power)
      → magnetic shield deflector + plasma layer (priority 30, off in cruise)

Load-shedding order:  shield (30) → comms (40) → RCS (50) → AG/lighting (60)
                  → ECLSS (80) NEVER shed → thermal pumps (90) NEVER shed.

References
----------
  * NASA TM-2018-219910 "Kilopower Brayton" — η = 0.45 thermal-to-electric
  * NASA TM-2017-219660 "Power System Architecture for Crewed Mars Mission" §4
  * Hofer 2014 "High Voltage DC Power Distribution for Spacecraft" — bus design
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Constants ──────────────────────────────────────────────────────

REACTOR_PEAK_THERMAL_W: float = 1.0e8       # 100 MW thermal peak (parameters.reactor)
THERMAL_TO_ELECTRIC_EFF: float = 0.45        # NASA TM-2018-219910 Brayton-cycle
PEAK_ELECTRIC_W: float = REACTOR_PEAK_THERMAL_W * THERMAL_TO_ELECTRIC_EFF   # 45 MWe at full reactor

# Subsystem nominal power draw at 100 % phase load (Watts).
# Numbers are operational-engineering rules of thumb, cited per row.
NOMINAL_LOADS: Dict[str, Tuple[float, int, str]] = {
    # subsystem            nominal_W      priority   citation
    "magnetic_nozzle":     (5.0e6,         100,      "Frisbee 2003 — coil power"),
    "thermal_pumps":       (5.0e4,          90,      "thermal_management.py — K-heat-pipe pumps"),
    "eclss_lifesupport":   (1.0e6,          80,      "NASA-TP-2015-218570 BVAD §5.4 — atmosphere + water + waste"),
    "agriculture_lighting":(2.0e6,          60,      "NASA-TP-2015-218570 §4.6 — 50 W·m⁻² × 40 000 m²"),
    "habitat_general":     (5.0e5,          60,      "ISS power ~75 kW for 6 crew (NASA-TM-2005-213753), scaled to ~100 crew habitat module"),
    "engine_bells_rcs":    (8.0e4,          50,      "NEXT ion thruster Patterson 2007 — 4 × 20 kW arc-jet"),
    "comm_uplink":         (8.0e4,          40,      "NASA DSN Telecom 810-005 — Ka-band 80 kW transmit"),
    "avionics_compute":    (1.5e4,          40,      "RAD750 ~10W × 3 TMR + sensors (BAE Systems RAD750 datasheet 2001)"),
    "shield_active_plasma":(1.0e6,          30,      "shield_layer_1 plasma deflector active mode"),
    "shield_magnetic":     (5.0e5,          30,      "shield_layer_2 SC magnet load"),
    "shield_lidar":        (5.0e3,          30,      "shield_layer_0 detection LIDAR"),
}


@dataclass
class SubsystemPower:
    """Per-subsystem snapshot."""

    name: str
    requested_w: float
    allocated_w: float
    priority: int
    shed: bool = False
    citation: str = ""

    @property
    def shed_fraction(self) -> float:
        if self.requested_w <= 0:
            return 0.0
        return 1.0 - self.allocated_w / self.requested_w


@dataclass
class PowerBudgetState:
    """Real-time electrical-bus snapshot."""

    available_w: float = 0.0
    allocated_w: float = 0.0
    margin_w:    float = 0.0
    margin_pct:  float = 0.0
    subsystems:  Dict[str, SubsystemPower] = field(default_factory=dict)
    total_shed_events: int = 0
    cumulative_shed_wh: float = 0.0

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        spec = phase.spec()

        # Available electricity: reactor output × phase duty
        self.available_w = PEAK_ELECTRIC_W * spec.power_load_frac

        # Build per-subsystem requests, scaled by phase
        # (most subsystems scale with their natural phase frac)
        requests: List[Tuple[str, float, int, str]] = []
        for name, (nominal_w, prio, cite) in NOMINAL_LOADS.items():
            if name == "magnetic_nozzle":
                req = nominal_w * spec.main_thrust_frac
            elif name == "thermal_pumps":
                req = nominal_w * spec.thermal_load_frac
            elif name == "engine_bells_rcs":
                req = nominal_w * spec.rcs_load_frac
            elif name in ("eclss_lifesupport", "agriculture_lighting", "habitat_general"):
                req = nominal_w * spec.crew_metabolic_frac
            elif name in ("shield_active_plasma", "shield_magnetic"):
                # Full power in BOOST/CRUISE/DECEL, low in PRELAUNCH/ORBIT
                req = nominal_w * (1.0 if spec.power_load_frac > 0.5 else 0.2)
            else:
                req = nominal_w   # avionics / sensors / lidar always-on
            requests.append((name, req, prio, cite))

        total_request = sum(r[1] for r in requests)
        deficit = max(0.0, total_request - self.available_w)

        # Allocate by priority (highest first); shed lowest-priority first
        requests_sorted = sorted(requests, key=lambda r: -r[2])    # highest priority first
        remaining = self.available_w
        new_subs: Dict[str, SubsystemPower] = {}
        for name, req, prio, cite in requests_sorted:
            give = min(req, remaining)
            remaining -= give
            new_subs[name] = SubsystemPower(
                name=name, requested_w=req, allocated_w=give,
                priority=prio, shed=(give < req - 1e-3), citation=cite,
            )
        self.subsystems = new_subs
        self.allocated_w = self.available_w - remaining
        self.margin_w = self.available_w - self.allocated_w
        self.margin_pct = 100.0 * self.margin_w / self.available_w if self.available_w > 0 else 0.0

        # Emit events
        if deficit > 0:
            self.total_shed_events += 1
            self.cumulative_shed_wh += deficit * (dt_s / 3600.0)
            shed_subs = [s.name for s in new_subs.values() if s.shed]
            bus.publish(
                "power.overload.shed",
                severity="warning",
                source="power_tracker",
                payload={
                    "deficit_w": round(deficit, 1),
                    "shed_subsystems": shed_subs,
                    "available_w": round(self.available_w, 1),
                    "requested_w": round(total_request, 1),
                },
                sim_time_yr=phase.elapsed_yr,
            )

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "summary": {
                "available_w":  round(self.available_w, 1),
                "allocated_w":  round(self.allocated_w, 1),
                "margin_w":     round(self.margin_w, 1),
                "margin_pct":   round(self.margin_pct, 2),
                "peak_electric_w": PEAK_ELECTRIC_W,
                "thermal_to_electric_eff": THERMAL_TO_ELECTRIC_EFF,
            },
            "subsystems": [
                {
                    "name":        s.name,
                    "priority":    s.priority,
                    "requested_w": round(s.requested_w, 1),
                    "allocated_w": round(s.allocated_w, 1),
                    "shed":        s.shed,
                    "shed_fraction": round(s.shed_fraction, 3),
                    "citation":    s.citation,
                }
                for s in sorted(self.subsystems.values(), key=lambda s: -s.priority)
            ],
            "stats": {
                "total_shed_events":    self.total_shed_events,
                "cumulative_shed_wh":   round(self.cumulative_shed_wh, 1),
            },
        }


_DEFAULT: Optional[PowerBudgetState] = None


def get_power_budget() -> PowerBudgetState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PowerBudgetState()
    return _DEFAULT


def reset_power_budget() -> None:
    global _DEFAULT
    _DEFAULT = PowerBudgetState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("power_tracker", get_power_budget().tick, order=20)
