"""Propulsion thermal feedback loop — nozzle-plume heat returning to the hull.

When the magnetic nozzle fires, ~95 % of the plasma is steered into the
exhaust column by the magnetic field. The remaining 5 % escapes the field
and impacts the back of the hull — that fraction of the engine's thermal
power must be rejected by the radiator system, *on top of* the reactor's
own heat. If the combined load exceeds radiator capacity, the system
must throttle the nozzle (reducing Isp + thrust) or accept hull-skin
overtemperature.

This module:
  * Computes the back-radiated flux as a function of main_thrust_frac
  * Adds it to the ambient thermal load
  * Triggers `propulsion.thermal.overrun` events when capacity is exceeded
  * Auto-throttles the effective thrust fraction when needed

References
----------
  * Frisbee 2003 JPL/D-26963 §4.3 (magnetic nozzle plasma deflection efficiency)
  * Sutton & Biblarz 2016 Ch. 7 (rocket-nozzle thermal balance)
  * Stefan-Boltzmann radiation: σ·A·ε·T⁴
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Physics constants ──────────────────────────────────────────────

SIGMA_SB: float = 5.670374419e-8     # Stefan-Boltzmann (CODATA)

# Reactor + nozzle peak thermal output at full thrust (parameters)
REACTOR_PEAK_THERMAL_W: float = 1.0e8   # 100 MW thermal (Frisbee 2003 generation-ship reactor scale)

# Plasma deflection efficiency — fraction of plasma kept in exhaust column
PLASMA_DEFLECTION_EFFICIENCY: float = 0.95   # Frisbee 2003 §4.3 — 95 % typical for B = 12 T magnetic nozzle

# Hull aft-cap area exposed to direct plume back-radiation (m²)
HULL_AFT_CAP_AREA_M2: float = math.pi * (12.616 ** 2)   # hull radius² × π = 500 m²

# Nozzle-to-hull view factor (geometric — fraction of escaped plasma that
# actually impacts the hull aft cap, not free space). Computed from
# Howell 2010 "Thermal Radiation Heat Transfer" Appendix C — disc-to-disc:
# at 60 m separation, 12 m hull radius, 50 m exit radius → ~0.18.
NOZZLE_TO_HULL_VIEW_FACTOR: float = 0.18

# Hull material limit before structural concern — Ti-6Al-4V β-transus 1268 K;
# we keep a wide margin and warn at 600 K.
HULL_AFT_CAP_TEMP_LIMIT_K: float = 600.0


@dataclass
class PropulsionThermalState:
    """Tracks plume back-radiation + auto-throttle response."""

    # Live readings
    requested_thrust_frac: float = 0.0       # what mission phase / operator wants
    actual_thrust_frac:    float = 0.0       # what we deliver after throttling
    back_radiated_w:       float = 0.0       # heat returning to hull aft cap
    hull_aft_cap_temp_k:   float = 290.0
    radiator_capacity_w:   float = 1.59e8    # 159 MW total — Stefan-Boltzmann at 500 K, 50 000 m²
    radiator_used_w:       float = 0.0
    margin_w:              float = 0.0

    # Stats
    total_throttle_events:    int   = 0
    cumulative_throttle_loss: float = 0.0    # sum of (requested - actual) over time

    # Operator override
    auto_throttle_enabled:    bool  = True
    # One-shot gate so `propulsion.thermal.hull_overtemp` doesn't fire
    # every tick while the aft cap stays above the 600 K limit. Reset
    # once the temperature drops 20 K below (hysteresis) so the next
    # over-temp episode fires cleanly.
    _overtemp_fired:          bool  = False

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        spec = phase.spec()
        self.requested_thrust_frac = spec.main_thrust_frac

        # Heat budget at requested thrust
        plasma_power_w = REACTOR_PEAK_THERMAL_W * self.requested_thrust_frac
        escaped_w = plasma_power_w * (1.0 - PLASMA_DEFLECTION_EFFICIENCY)
        back_at_hull_w = escaped_w * NOZZLE_TO_HULL_VIEW_FACTOR

        # Reactor's own thermal waste also flows to radiator (efficiency proxy)
        reactor_waste_w = REACTOR_PEAK_THERMAL_W * spec.thermal_load_frac
        # Habitat metabolic + life-support load (constant baseline)
        habitat_baseline_w = 5.0e6   # 5 MW baseline (1000 crew + ECLSS + lighting)

        total_load_w = reactor_waste_w + back_at_hull_w + habitat_baseline_w
        self.margin_w = self.radiator_capacity_w - total_load_w

        # Auto-throttle if margin negative
        if self.auto_throttle_enabled and self.margin_w < 0:
            # Reduce thrust until back-radiation closes the deficit
            # Solve: target back_at_hull_w = back_at_hull_w + margin_w (= radiator capacity left for plume)
            available_for_plume = self.radiator_capacity_w - reactor_waste_w - habitat_baseline_w
            if available_for_plume > 0:
                # back_at_hull = available  →  plasma · (1-η) · vf = available
                allowed_plasma = available_for_plume / ((1.0 - PLASMA_DEFLECTION_EFFICIENCY) * NOZZLE_TO_HULL_VIEW_FACTOR)
                self.actual_thrust_frac = max(0.0, min(self.requested_thrust_frac,
                                                        allowed_plasma / REACTOR_PEAK_THERMAL_W))
            else:
                self.actual_thrust_frac = 0.0
            if self.actual_thrust_frac < self.requested_thrust_frac - 1e-3:
                self.total_throttle_events += 1
                self.cumulative_throttle_loss += (self.requested_thrust_frac - self.actual_thrust_frac) * dt_s
                bus.publish(
                    "propulsion.thermal.throttle",
                    severity="warning",
                    source="propulsion_thermal",
                    payload={
                        "requested": round(self.requested_thrust_frac, 3),
                        "actual":    round(self.actual_thrust_frac, 3),
                        "margin_w":  round(self.margin_w, 0),
                        "reason":    "thermal_overrun",
                    },
                    sim_time_yr=phase.elapsed_yr,
                )
        else:
            self.actual_thrust_frac = self.requested_thrust_frac

        # Update derived state with the actual (possibly throttled) thrust
        actual_plasma_w = REACTOR_PEAK_THERMAL_W * self.actual_thrust_frac
        actual_escaped_w = actual_plasma_w * (1.0 - PLASMA_DEFLECTION_EFFICIENCY)
        self.back_radiated_w = actual_escaped_w * NOZZLE_TO_HULL_VIEW_FACTOR
        self.radiator_used_w = (REACTOR_PEAK_THERMAL_W * spec.thermal_load_frac
                                + self.back_radiated_w + habitat_baseline_w)
        self.margin_w = self.radiator_capacity_w - self.radiator_used_w

        # Hull-cap equilibrium temp from Stefan-Boltzmann balance
        # Q_in = ε·σ·A·T⁴ at steady state → T = (Q / (ε·σ·A))^¼
        if self.back_radiated_w > 0 and HULL_AFT_CAP_AREA_M2 > 0:
            equil_t = (self.back_radiated_w / (0.85 * SIGMA_SB * HULL_AFT_CAP_AREA_M2)) ** 0.25
        else:
            equil_t = 290.0
        # First-order lag toward equilibrium. Time constant τ = C/(hA)
        # where C = ρ·V·cp for the aft cap (Ti-6Al-4V, 500 m², 0.05 m
        # thick → ~110 t, cp ≈ 526 J/kg·K → C ≈ 5.8e7 J/K) and
        # h·A at 600 K equilibrium ≈ 4·ε·σ·T³·A ≈ 4.2e4 W/K → τ ≈ 1400 s.
        # The old τ = 60 s was 20× too fast and produced spurious
        # hull-temp swings + throttle events on long substeps.
        tau_s = 1400.0    # ~23 min thermal lag (Ti-6Al-4V aft cap, Sutton 2016 Ch.7)
        alpha = min(1.0, dt_s / tau_s)
        self.hull_aft_cap_temp_k += (equil_t - self.hull_aft_cap_temp_k) * alpha

        if self.hull_aft_cap_temp_k > HULL_AFT_CAP_TEMP_LIMIT_K and not self._overtemp_fired:
            self._overtemp_fired = True
            bus.publish(
                "propulsion.thermal.hull_overtemp",
                severity="critical",
                source="propulsion_thermal",
                payload={"temp_k": round(self.hull_aft_cap_temp_k, 1),
                         "limit_k": HULL_AFT_CAP_TEMP_LIMIT_K},
                sim_time_yr=phase.elapsed_yr,
            )
        elif self.hull_aft_cap_temp_k < HULL_AFT_CAP_TEMP_LIMIT_K - 20.0 and self._overtemp_fired:
            # 20 K hysteresis — reset the one-shot once temp drops well
            # below the limit so the NEXT over-temp episode fires cleanly.
            self._overtemp_fired = False

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "thrust": {
                "requested_frac": round(self.requested_thrust_frac, 3),
                "actual_frac":    round(self.actual_thrust_frac, 3),
                "throttle_active": self.actual_thrust_frac < self.requested_thrust_frac - 1e-3,
            },
            "thermal": {
                "back_radiated_w":     round(self.back_radiated_w, 1),
                "radiator_capacity_w": round(self.radiator_capacity_w, 1),
                "radiator_used_w":     round(self.radiator_used_w, 1),
                "margin_w":            round(self.margin_w, 1),
                "hull_aft_cap_temp_k": round(self.hull_aft_cap_temp_k, 1),
                "hull_temp_limit_k":   HULL_AFT_CAP_TEMP_LIMIT_K,
            },
            "config": {
                "plasma_deflection_efficiency": PLASMA_DEFLECTION_EFFICIENCY,
                "nozzle_to_hull_view_factor":  NOZZLE_TO_HULL_VIEW_FACTOR,
                "hull_aft_cap_area_m2":         round(HULL_AFT_CAP_AREA_M2, 1),
                "auto_throttle_enabled":        self.auto_throttle_enabled,
            },
            "stats": {
                "total_throttle_events":    self.total_throttle_events,
                "cumulative_throttle_loss_s": round(self.cumulative_throttle_loss, 1),
            },
        }


_DEFAULT: Optional[PropulsionThermalState] = None


def get_propulsion_thermal() -> PropulsionThermalState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = PropulsionThermalState()
    return _DEFAULT


def reset_propulsion_thermal() -> None:
    global _DEFAULT
    _DEFAULT = PropulsionThermalState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("propulsion_thermal", get_propulsion_thermal().tick, order=33)
