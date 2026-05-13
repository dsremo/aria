"""Hydroponic agriculture — 5-crop rotation with harvest cycles + food balance.

40 000 m² grow area split across staple crops: wheat / soy / sweet-potato /
lettuce / tilapia (aquaponic). Each tracks days-to-harvest, yield kg/m²,
caloric content, and protein content. Daily output flows into food-store;
crew daily demand (calories + protein) flows out. Net food-store change
shows whether the system is self-sufficient.

Failure modes:
  * Nutrient solution imbalance → yield drops 50 %
  * LED outage → yield drops 90 % until restored
  * Pest infestation → small random yield loss
  * Root rot in tilapia tank → 100 % loss of that crop until cleaned

References
----------
  * NASA-TP-2015-218570 BVAD §4 (crop yields per m² per day)
  * Wheeler et al. 2003 Adv. Space Res. 31:179 (CELSS crop selection)
  * Lasseur et al. 2010 J. Plant Interact. 5:223 (MELiSSA hydroponics)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Crop definitions ──────────────────────────────────────────────

@dataclass(frozen=True)
class CropSpec:
    name: str
    area_frac: float                 # 0..1 of total grow area
    days_to_harvest: int
    yield_kg_per_m2_per_cycle: float
    kcal_per_kg: float
    protein_g_per_kg: float
    citation: str


CROPS: Dict[str, CropSpec] = {
    "wheat": CropSpec(
        name="Wheat", area_frac=0.30, days_to_harvest=80,
        yield_kg_per_m2_per_cycle=4.5,                # NASA-TP-2015-218570 Table 4-101
        kcal_per_kg=3340.0, protein_g_per_kg=130.0,
        citation="NASA-TP-2015-218570 BVAD §4.6, Wheeler 2003",
    ),
    "soy": CropSpec(
        name="Soybean", area_frac=0.20, days_to_harvest=110,
        yield_kg_per_m2_per_cycle=2.2,
        kcal_per_kg=4460.0, protein_g_per_kg=360.0,
        citation="NASA-TP-2015-218570 §4.7",
    ),
    "sweet_potato": CropSpec(
        name="Sweet Potato", area_frac=0.20, days_to_harvest=120,
        yield_kg_per_m2_per_cycle=8.0,
        kcal_per_kg=860.0, protein_g_per_kg=16.0,
        citation="NASA-TP-2015-218570 §4.8; Wheeler 2003",
    ),
    "lettuce": CropSpec(
        name="Lettuce + greens", area_frac=0.15, days_to_harvest=28,
        yield_kg_per_m2_per_cycle=1.6,
        kcal_per_kg=150.0, protein_g_per_kg=14.0,
        citation="NASA-TP-2015-218570 §4.9",
    ),
    "tilapia": CropSpec(
        name="Tilapia (aquaponic)", area_frac=0.15, days_to_harvest=180,
        yield_kg_per_m2_per_cycle=4.2,                  # protein source, slower cycle
        kcal_per_kg=960.0, protein_g_per_kg=200.0,
        citation="Lasseur 2010 MELiSSA; Endut 2010 Bioresour. Technol.",
    ),
}


# Per-crew daily metabolic targets — NASA BVAD baseline
KCAL_PER_CREW_PER_DAY:    float = 2_900.0      # NASA-TP-2015-218570 §3
PROTEIN_G_PER_CREW_PER_DAY: float = 56.0       # WHO/FAO 0.83 g/kg × 67 kg


@dataclass
class CropState:
    """Live state of one crop's planting cycle."""

    crop_id: str
    days_into_cycle: float = 0.0
    yield_modifier: float = 1.0           # 0..1 — degradations from failures
    cumulative_yield_kg: float = 0.0
    last_harvest_kg: float = 0.0
    failure_active: Optional[str] = None  # name of active failure mode


@dataclass
class AgricultureYieldState:
    """Top-level agriculture state."""

    total_area_m2: float = 40_000.0       # parameters.agriculture_area_m2

    # R8 (2026-04-24, sync refactor): crew_size now reads from
    # MissionState — was a hardcoded 1000 with no propagation from
    # the actual crew lifecycle.  Every food-demand calculation now
    # uses the live crew count.
    @property
    def crew_size(self) -> int:
        from aria.core.mission_state import get_mission_state
        return get_mission_state().crew_alive

    # Buffer of harvested food
    food_store_kg: float = 50_000.0       # initial 50 t buffer (parameters)

    # Per-crop tick state
    crops: Dict[str, CropState] = field(default_factory=dict)

    # Cumulative
    total_kcal_produced: float = 0.0
    total_kcal_consumed: float = 0.0
    total_protein_g_produced: float = 0.0
    total_protein_g_consumed: float = 0.0
    days_short_kcal: int = 0
    # Fractional accumulator: prior implementation did `int(dt_days)`
    # which truncated to 0 for sub-day tick steps, so `days_short_kcal`
    # stayed at 0 while the `% 30 == 0` guard fired every tick. Now we
    # accumulate as a float and promote to the int counter only once
    # per whole-day crossing, then fire the warning on 30-day boundaries.
    _days_short_accum: float = 0.0
    _next_shortage_day_threshold: int = 0

    def __post_init__(self) -> None:
        if not self.crops:
            self.crops = {cid: CropState(crop_id=cid) for cid in CROPS}

    # ── derived ──────────────────────────────────────────────────

    def daily_kcal_demand(self) -> float:
        return self.crew_size * KCAL_PER_CREW_PER_DAY

    def daily_protein_demand(self) -> float:
        return self.crew_size * PROTEIN_G_PER_CREW_PER_DAY

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        dt_days = dt_s / 86_400.0

        # Crew metabolic scale (skeleton crew during PRELAUNCH)
        crew_scale = phase.spec().crew_metabolic_frac

        # Sum kcal + protein produced this tick across all crops
        kcal_produced = 0.0
        protein_produced_g = 0.0
        for cid, st in self.crops.items():
            spec = CROPS[cid]
            st.days_into_cycle += dt_days
            # Multi-cycle catch-up: a long mission tick (e.g. +1 yr or
            # century auto-tick) can span many harvest cycles. The old
            # `if` only harvested once per tick, leaving days_into_cycle
            # to overflow into the millions while the crew starved.
            # A single bus event rolls up all the cycles so we don't
            # fire one `agriculture.harvest.lettuce` per cycle for a
            # 100-year tick (would spam 1200× in a single call).
            harvests_this_tick = 0
            harvest_kg_this_tick = 0.0
            while st.days_into_cycle >= spec.days_to_harvest:
                area_m2 = self.total_area_m2 * spec.area_frac
                harvest_kg = area_m2 * spec.yield_kg_per_m2_per_cycle * st.yield_modifier
                st.cumulative_yield_kg += harvest_kg
                st.last_harvest_kg = harvest_kg
                st.days_into_cycle -= spec.days_to_harvest    # restart cycle
                self.food_store_kg += harvest_kg
                kcal_produced += harvest_kg * spec.kcal_per_kg
                protein_produced_g += harvest_kg * spec.protein_g_per_kg
                harvests_this_tick += 1
                harvest_kg_this_tick += harvest_kg
            if harvests_this_tick > 0:
                bus.publish(f"agriculture.harvest.{cid}",
                            severity="info", source="agriculture_yield",
                            payload={"crop": spec.name,
                                     "harvests": harvests_this_tick,
                                     "harvest_kg": round(harvest_kg_this_tick, 1),
                                     "kcal": round(harvest_kg_this_tick * spec.kcal_per_kg, 0),
                                     "yield_modifier": round(st.yield_modifier, 3)},
                            sim_time_yr=phase.elapsed_yr)

        # Crew daily consumption (apportioned per-tick by dt_days fraction)
        kcal_demand = self.daily_kcal_demand() * dt_days * crew_scale
        protein_demand_g = self.daily_protein_demand() * dt_days * crew_scale
        # Burn from food_store as caloric mass (rough kcal->kg back-conversion)
        avg_kcal_per_kg = 2200.0     # rough mixed-diet average (NASA-TP-2015-218570)
        avg_protein_g_per_kg = 110.0 # rough mixed-diet average (NASA-TP-2015-218570 Table 4.6)
        kg_to_consume = min(self.food_store_kg, kcal_demand / avg_kcal_per_kg)
        self.food_store_kg -= kg_to_consume
        kcal_actually_consumed = kg_to_consume * avg_kcal_per_kg
        # Track ACTUAL protein consumed (scaled by what was available),
        # not demand. Old bug logged full demand in the cumulative total
        # even when the food store was depleted, so a century run with
        # recurring shortages showed consumed_protein ≫ produced_protein
        # while the crew was actually starving. Mass/energy balance now
        # matches between produced/consumed.
        protein_actually_consumed_g = kg_to_consume * avg_protein_g_per_kg

        self.total_kcal_produced     += kcal_produced
        self.total_kcal_consumed     += kcal_actually_consumed
        self.total_protein_g_produced += protein_produced_g
        self.total_protein_g_consumed += protein_actually_consumed_g

        if kcal_actually_consumed < kcal_demand * 0.95:
            self._days_short_accum += dt_days
            self.days_short_kcal = int(self._days_short_accum)
            # Fire a warning every ~30 calendar days of sustained shortage.
            # Previous bug: the '% 30 == 0' check fired EVERY tick while
            # days_short_kcal stayed at 0 (sub-day dt got truncated), so a
            # single mission year produced ~thousand identical 'Food shortage
            # — 0 days short' entries. One-shot threshold is now in real days.
            if self.days_short_kcal >= self._next_shortage_day_threshold and self.days_short_kcal > 0:
                self._next_shortage_day_threshold = self.days_short_kcal + 30
                bus.publish("agriculture.shortage",
                            severity="critical", source="agriculture_yield",
                            payload={"food_store_kg": round(self.food_store_kg, 0),
                                     "days_short": self.days_short_kcal},
                            sim_time_yr=phase.elapsed_yr)
        else:
            # Reset hysteresis once the store recovers to ≥ 95 % of demand
            # so the next shortage episode fires cleanly from day 0.
            if self.days_short_kcal > 0:
                self._days_short_accum = 0.0
                self.days_short_kcal = 0
                self._next_shortage_day_threshold = 30

    # ── operator API: failure modes ─────────────────────────────

    def trigger_failure(self, crop_id: str, failure_mode: str) -> None:
        """Apply a yield modifier corresponding to a failure mode."""
        if crop_id not in self.crops:
            return
        st = self.crops[crop_id]
        st.failure_active = failure_mode
        if failure_mode == "nutrient_imbalance":
            st.yield_modifier = 0.5
        elif failure_mode == "led_outage":
            st.yield_modifier = 0.1
        elif failure_mode == "pest":
            st.yield_modifier = 0.7
        elif failure_mode == "root_rot":
            st.yield_modifier = 0.0
        bus = get_event_bus()
        bus.publish(f"agriculture.failure.{crop_id}.{failure_mode}",
                    severity="warning", source="agriculture_yield",
                    payload={"crop": crop_id, "failure": failure_mode,
                             "new_yield_modifier": st.yield_modifier},
                    sim_time_yr=get_phase_controller().elapsed_yr)

    def restore_crop(self, crop_id: str) -> None:
        if crop_id not in self.crops:
            return
        self.crops[crop_id].yield_modifier = 1.0
        self.crops[crop_id].failure_active = None

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "total_area_m2": self.total_area_m2,
            "crew_size":     self.crew_size,
            "food_store_kg": round(self.food_store_kg, 1),
            "daily_kcal_demand":    round(self.daily_kcal_demand(), 0),
            "daily_protein_demand_g": round(self.daily_protein_demand(), 0),
            "totals": {
                "kcal_produced":   round(self.total_kcal_produced, 0),
                "kcal_consumed":   round(self.total_kcal_consumed, 0),
                "protein_g_produced": round(self.total_protein_g_produced, 0),
                "protein_g_consumed": round(self.total_protein_g_consumed, 0),
                "days_short_kcal": self.days_short_kcal,
            },
            "crops": [
                {
                    "id":              cid,
                    "name":            CROPS[cid].name,
                    "area_m2":         round(self.total_area_m2 * CROPS[cid].area_frac, 0),
                    "days_to_harvest": CROPS[cid].days_to_harvest,
                    "days_into_cycle": round(st.days_into_cycle, 1),
                    "cycle_progress_pct": round(100.0 * st.days_into_cycle / CROPS[cid].days_to_harvest, 1),
                    "yield_kg_per_m2_per_cycle": CROPS[cid].yield_kg_per_m2_per_cycle,
                    "yield_modifier": st.yield_modifier,
                    "cumulative_yield_kg": round(st.cumulative_yield_kg, 1),
                    "last_harvest_kg": round(st.last_harvest_kg, 1),
                    "kcal_per_kg":     CROPS[cid].kcal_per_kg,
                    "protein_g_per_kg": CROPS[cid].protein_g_per_kg,
                    "failure_active":  st.failure_active,
                    "citation":        CROPS[cid].citation,
                }
                for cid, st in self.crops.items()
            ],
        }


_DEFAULT: Optional[AgricultureYieldState] = None


def get_agriculture() -> AgricultureYieldState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = AgricultureYieldState()
    return _DEFAULT


def reset_agriculture() -> None:
    global _DEFAULT
    _DEFAULT = AgricultureYieldState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("agriculture_yield", get_agriculture().tick, order=49)
