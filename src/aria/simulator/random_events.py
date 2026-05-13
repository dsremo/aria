"""Stochastic mission events — MMOD strikes, solar flares, equipment faults.

Each event class has a Poisson arrival rate (per simulation year). On
each tick, we draw the expected count `λ·dt` and roll Poisson; for each
arrival, we route to the appropriate subsystem:

  * MMOD strike       → hull_damage.record_impact()
  * Solar flare       → bumps shielding factor (worsens SEU rate)
  * Equipment fault   → triggers a random failure_injector scenario

The intent is to make a multi-year cruise *eventful* — without random
events, an auto-tick run is just a smooth velocity ramp.

References
----------
  * Drolshagen 2008 "Comparison of meteoroid flux models", Adv. Space Res.
    — MMOD flux for ~mm-scale particles, ~100 strikes/m²/yr at LEO
  * NOAA Space Weather Prediction Center, GOES X-ray climatology —
    M-class flare rate ~5/yr at solar max
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Event-rate constants ──────────────────────────────────────────

# Effective MMOD rate the ship sees after passive deflection. Calibrated
# to ~1 hit/yr at cruise (interstellar dust is sparse, well below LEO
# rates) — Hörz 2003 LDEF retrieval data + Frisbee 2003 estimate.
MMOD_STRIKES_PER_YEAR: float = 1.0

# Solar flare rate during BOOST (close to Sol). Far less in cruise.
FLARE_RATE_PER_YEAR_AT_BOOST: float = 5.0
FLARE_RATE_PER_YEAR_AT_CRUISE: float = 0.05

# Equipment-fault rate (random subsystem failure). Drives surprise drills.
FAULT_RATE_PER_YEAR: float = 0.5


@dataclass
class RandomEventsState:
    """Driver for stochastic mission events."""

    enabled: bool = True
    seed: int = 42
    _rng: random.Random = field(default_factory=lambda: random.Random(42))

    # Counters
    mmod_count: int = 0
    flare_count: int = 0
    fault_count: int = 0
    cumulative_yr: float = 0.0

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        if not self.enabled:
            return
        bus = get_event_bus()
        phase = get_phase_controller()
        dt_yr = dt_s / (365.25 * 24 * 3600)
        self.cumulative_yr += dt_yr

        # MMOD strikes
        n_mmod = self._poisson(MMOD_STRIKES_PER_YEAR * dt_yr)
        for _ in range(n_mmod):
            self._mmod_strike()

        # Solar flares — phase-dependent. BOOST + DECELERATION happen
        # close to the source star (Sol on departure, Proxima on arrival),
        # so flux is high. CRUISE + ARRIVAL + ORBIT are far from the
        # active star of the moment, so flux is low. Previous conditional
        # flipped this — orbit around Proxima was treated as BOOST-class,
        # producing 21 700 flares over an 11 000-yr Proxima orbit
        # (39× over spec). Restore the correct set.
        flare_rate = (FLARE_RATE_PER_YEAR_AT_BOOST
                      if phase.current.value in ("prelaunch", "boost", "deceleration")
                      else FLARE_RATE_PER_YEAR_AT_CRUISE)
        n_flare = self._poisson(flare_rate * dt_yr)
        if n_flare > 0:
            # Roll up into a single bus event per tick with a count —
            # century-scale ticks can draw hundreds of flares at once,
            # and the old loop published N separate warnings per tick,
            # dominating the narrative log + event ring buffer.
            self._solar_flare_batch(n_flare)

        # Equipment faults
        n_fault = self._poisson(FAULT_RATE_PER_YEAR * dt_yr)
        for _ in range(n_fault):
            self._equipment_fault()

    # ── handlers ───────────────────────────────────────────────

    def _mmod_strike(self) -> None:
        from aria.simulator.hull_damage import REGION_DEFS, get_hull_damage
        # Pick a random region weighted toward the hull centre + bow
        region_weights = {
            "bow_shield": 0.20, "hull_zone_7": 0.10, "hull_zone_6": 0.10,
            "hull_zone_5": 0.10, "hull_zone_4": 0.10, "hull_zone_3": 0.08,
            "hull_zone_2": 0.08, "hull_zone_1": 0.06, "hull_zone_0": 0.05,
            "stern_nozzle": 0.13,
        }
        regions = list(region_weights.keys())
        weights = [region_weights[r] for r in regions]
        rid = self._rng.choices(regions, weights=weights, k=1)[0]
        # Energy: log-uniform 100 J – 100 kJ (NASA TM-2017-219818 distribution)
        log_e = self._rng.uniform(2.0, 5.0)
        energy_j = 10 ** log_e
        impact = get_hull_damage().record_impact(rid, energy_j, note="MMOD strike (random)")
        self.mmod_count += 1

    def _solar_flare(self) -> None:
        # Kept for operator force_flare() API. Runtime calls go through
        # _solar_flare_batch so century-scale ticks don't spam the bus.
        self._solar_flare_batch(1)

    def _solar_flare_batch(self, count: int) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        from aria.simulator.computing_radiation import (
            SHIELDED_FLUX_FACTOR, get_computing_radiation,
        )
        cr = get_computing_radiation()
        flare_factor = SHIELDED_FLUX_FACTOR * 50.0   # 50× nominal GCR flux (ESTIMATE — Parker 1958 class-X envelope)
        cap = SHIELDED_FLUX_FACTOR * 100.0
        cr.current_shielding_factor = min(cap, max(cr.current_shielding_factor, flare_factor))
        self.flare_count += count
        bus.publish("env.solar_flare",
                    severity="warning", source="random_events",
                    payload={"shielding_factor_after": round(cr.current_shielding_factor, 6),
                             "flare_count": self.flare_count,
                             "count_this_tick": count},
                    sim_time_yr=phase.elapsed_yr)

    def _equipment_fault(self) -> None:
        # Pick a random failure_injector scenario, but skip the very
        # disruptive ones (radiator_loss, eclss_scrubber_fault) to avoid
        # mission-ending random hits.
        from aria.simulator.failure_injector import SCENARIOS, trigger
        safe = [sid for sid in SCENARIOS
                if sid not in ("radiator_loss", "eclss_scrubber_fault")]
        sid = self._rng.choice(safe)
        trigger(sid)
        self.fault_count += 1

    # ── Poisson sampler ───────────────────────────────────────

    def _poisson(self, mean: float) -> int:
        if mean <= 0:
            return 0
        if mean > 30:
            # Normal approximation
            return max(0, int(round(self._rng.gauss(mean, mean ** 0.5))))
        # Knuth
        L = 2.718281828459045 ** -mean
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self._rng.random()
            if p <= L:
                return k - 1

    # ── operator API ──────────────────────────────────────────

    def force_mmod(self, region_id: str = "hull_zone_4", energy_j: float = 5_000.0) -> None:
        from aria.simulator.hull_damage import get_hull_damage
        get_hull_damage().record_impact(region_id, energy_j, note="MMOD (operator-forced)")
        self.mmod_count += 1

    def force_flare(self) -> None:
        self._solar_flare()

    def set_seed(self, seed: int) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "seed":    self.seed,
            "rates": {
                "mmod_per_yr":  MMOD_STRIKES_PER_YEAR,
                "flare_boost":  FLARE_RATE_PER_YEAR_AT_BOOST,
                "flare_cruise": FLARE_RATE_PER_YEAR_AT_CRUISE,
                "fault_per_yr": FAULT_RATE_PER_YEAR,
            },
            "counts": {
                "mmod":  self.mmod_count,
                "flare": self.flare_count,
                "fault": self.fault_count,
                "elapsed_yr": round(self.cumulative_yr, 3),
            },
        }


_DEFAULT: Optional[RandomEventsState] = None


def get_random_events() -> RandomEventsState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = RandomEventsState()
    return _DEFAULT


def reset_random_events() -> None:
    global _DEFAULT
    _DEFAULT = RandomEventsState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("random_events", get_random_events().tick, order=58)
