"""Per-tank propellant inventory + burn-rate tracking.

Three cryo D/He-3 tanks (A/B/C) for the magnetic nozzle, plus a small
xenon reservoir for the four RCS arc-jets. Propellant is drained from
all three main tanks proportionally during boost / decel; xenon is drained
during attitude manoeuvres.

Refuelling not currently modelled (interstellar = no refuel for the
foreseeable future).

References
----------
  * Frisbee 2003 JPL/D-26963 §3.4 (D/He-3 mass-fraction budget)
  * Patterson & Benson 2007 NASA/TM-2014-218232 (NEXT ion thruster Xe usage)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Constants ──────────────────────────────────────────────────────

# Total fuel mass split across 3 tanks (Frisbee 2003 §3.4 budget)
PROPELLANT_TOTAL_KG: float = 8.5e7         # 85 Mt — 85 % of 100 Mt wet
PROPELLANT_PER_MAIN_TANK_KG: float = PROPELLANT_TOTAL_KG / 3

# Xenon for RCS arc-jets (NASA TM-2014-218232 — typical 1 t Xe per 1 yr full-time burn)
RCS_XENON_TOTAL_KG: float = 5.0e3           # 5 t total xenon — multi-decade RCS budget

# Nominal mass flow at full thrust
MAIN_BURN_RATE_KG_S: float = 10.0           # 10 kg/s — fusion magnetic nozzle (Frisbee 2003)
RCS_BURN_RATE_KG_S: float = 0.05            # 50 g/s per arc-jet × 4 thrusters at full RCS = 0.2 kg/s
RCS_NOMINAL_MASS_FLOW_KG_S: float = 4 * RCS_BURN_RATE_KG_S


@dataclass
class TankState:
    """One propellant tank."""

    tank_id: str
    label: str
    capacity_kg: float
    contents_kg: float
    fuel_type: str        # 'D-He3' or 'Xenon'
    cumulative_drawn_kg: float = 0.0
    # Mass lost to non-burn events (failure_injector leak drills).
    # Kept separate from cumulative_drawn_kg so the conservation
    # invariant (contents + drawn + leaked == capacity) stays explicit.
    cumulative_leaked_kg: float = 0.0

    @property
    def fill_fraction(self) -> float:
        if self.capacity_kg <= 0:
            return 0.0
        return self.contents_kg / self.capacity_kg


@dataclass
class FuelInventoryState:
    """Top-level fuel inventory for the ship."""

    tanks: Dict[str, TankState] = field(default_factory=dict)
    main_burn_rate_kg_s: float = 0.0    # current main-engine flow
    rcs_burn_rate_kg_s:  float = 0.0    # current RCS flow
    main_alarm_low: bool = False        # any main tank below 5 %
    main_alarm_crit: bool = False       # any main tank empty

    def __post_init__(self) -> None:
        if not self.tanks:
            for label in ("A", "B", "C"):
                tid = f"main_tank_{label.lower()}"
                self.tanks[tid] = TankState(
                    tank_id=tid, label=f"Main D/He-3 Tank {label}",
                    capacity_kg=PROPELLANT_PER_MAIN_TANK_KG,
                    contents_kg=PROPELLANT_PER_MAIN_TANK_KG,
                    fuel_type="D-He3",
                )
            self.tanks["rcs_xenon"] = TankState(
                tank_id="rcs_xenon", label="RCS Xenon Reservoir",
                capacity_kg=RCS_XENON_TOTAL_KG,
                contents_kg=RCS_XENON_TOTAL_KG,
                fuel_type="Xenon",
            )

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        spec = phase.spec()

        # Use propulsion-thermal actual thrust frac (so auto-throttle reflected),
        # but fall back to spec when propulsion_thermal hasn't ticked yet.
        try:
            from aria.simulator.propulsion_thermal import get_propulsion_thermal
            pt = get_propulsion_thermal()
            if pt.actual_thrust_frac == 0.0 and spec.main_thrust_frac > 0:
                main_frac = spec.main_thrust_frac
            else:
                main_frac = pt.actual_thrust_frac
        except Exception:
            main_frac = spec.main_thrust_frac

        # Auto-throttle can only reduce thrust below the commanded spec —
        # clamp so a stale propulsion_thermal.actual_thrust_frac (e.g. left
        # over from a prior BOOST run) never causes fuel to burn during
        # non-thrusting phases like PRELAUNCH.
        if main_frac > spec.main_thrust_frac:
            main_frac = spec.main_thrust_frac

        rcs_frac = spec.rcs_load_frac

        # Main burn — drained across the 3 tanks with shortfall roll-over.
        # Naive `per_tank = main_consumed / 3` leaves any empty-tank
        # shortfall unpicked (if tank_a has only 5 kg when per_tank wants
        # 100, the other 95 kg silently disappears from the burn budget
        # and trajectory_state drifts away from fuel_tracker's total).
        # Distribute proportionally to current fill, then redistribute
        # any residual to tanks that still have capacity.
        self.main_burn_rate_kg_s = MAIN_BURN_RATE_KG_S * main_frac
        main_consumed = self.main_burn_rate_kg_s * dt_s
        remaining = main_consumed
        # Up to 3 passes so a residual from an empty tank can cascade
        # onto the surviving tanks in the same tick.
        for _pass in range(3):
            if remaining <= 0.0:
                break
            live = [self.tanks[tid]
                    for tid in ("main_tank_a", "main_tank_b", "main_tank_c")
                    if self.tanks[tid].contents_kg > 0]
            if not live:
                break
            per_tank = remaining / len(live)
            remaining = 0.0
            for t in live:
                draw = min(per_tank, t.contents_kg)
                t.contents_kg -= draw
                t.cumulative_drawn_kg += draw
                remaining += (per_tank - draw)   # cascade unfilled share

        # RCS burn from xenon
        self.rcs_burn_rate_kg_s = RCS_NOMINAL_MASS_FLOW_KG_S * rcs_frac
        xenon_consumed = self.rcs_burn_rate_kg_s * dt_s
        rcs = self.tanks["rcs_xenon"]
        draw = min(xenon_consumed, rcs.contents_kg)
        rcs.contents_kg -= draw
        rcs.cumulative_drawn_kg += draw

        # Alarm checks
        new_low = any(t.fill_fraction < 0.05 for t in self._main_tanks())
        new_crit = any(t.contents_kg <= 0 for t in self._main_tanks())
        if new_low and not self.main_alarm_low:
            bus.publish("fuel.main.low",
                        severity="warning", source="fuel_tracker",
                        payload={"tanks": [t.tank_id for t in self._main_tanks() if t.fill_fraction < 0.05]},
                        sim_time_yr=phase.elapsed_yr)
        if new_crit and not self.main_alarm_crit:
            bus.publish("fuel.main.empty",
                        severity="critical", source="fuel_tracker",
                        payload={"tanks": [t.tank_id for t in self._main_tanks() if t.contents_kg <= 0]},
                        sim_time_yr=phase.elapsed_yr)
        self.main_alarm_low = new_low
        self.main_alarm_crit = new_crit

    def _main_tanks(self) -> List[TankState]:
        return [self.tanks[k] for k in ("main_tank_a", "main_tank_b", "main_tank_c")]

    # ── derived ──────────────────────────────────────────────────

    @property
    def total_main_kg(self) -> float:
        return sum(t.contents_kg for t in self._main_tanks())

    @property
    def main_fill_pct(self) -> float:
        cap = sum(t.capacity_kg for t in self._main_tanks())
        return 100.0 * self.total_main_kg / cap if cap > 0 else 0.0

    def time_to_empty_main_s(self) -> float:
        if self.main_burn_rate_kg_s <= 0:
            return float("inf")
        return self.total_main_kg / self.main_burn_rate_kg_s

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        tte = self.time_to_empty_main_s()
        return {
            "tanks": [
                {
                    "tank_id":               t.tank_id,
                    "label":                 t.label,
                    "fuel_type":             t.fuel_type,
                    "capacity_kg":           t.capacity_kg,
                    "contents_kg":           round(t.contents_kg, 1),
                    "fill_fraction":         round(t.fill_fraction, 6),
                    "cumulative_drawn_kg":   round(t.cumulative_drawn_kg, 1),
                    "cumulative_leaked_kg":  round(getattr(t, "cumulative_leaked_kg", 0.0), 1),
                }
                for t in self.tanks.values()
            ],
            "summary": {
                "main_total_kg":          round(self.total_main_kg, 1),
                "main_fill_pct":          round(self.main_fill_pct, 3),
                "main_burn_rate_kg_s":    round(self.main_burn_rate_kg_s, 3),
                "rcs_burn_rate_kg_s":     round(self.rcs_burn_rate_kg_s, 4),
                "time_to_empty_main_s":   tte if tte != float("inf") else None,
                "time_to_empty_main_yr":  (tte / (365.25 * 24 * 3600)) if tte != float("inf") else None,
                "alarm_low":              self.main_alarm_low,
                "alarm_critical":         self.main_alarm_crit,
            },
        }


_DEFAULT: Optional[FuelInventoryState] = None


def get_fuel_inventory() -> FuelInventoryState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = FuelInventoryState()
    return _DEFAULT


def reset_fuel_inventory() -> None:
    global _DEFAULT
    _DEFAULT = FuelInventoryState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("fuel_tracker", get_fuel_inventory().tick, order=37)
