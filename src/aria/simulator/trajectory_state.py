"""Live trajectory state — ship position, velocity, distance-to-target.

Bridges the static `trajectory.py` (Tsiolkovsky + propulsion options) with
the runtime simulator: integrates velocity from propulsion thermal output
each tick, accumulates distance, computes ETA + ΔV remaining.

Coordinate convention (3-D upgrade, 2026-04):
  * Position is a 3-vector in light-years, origin at Earth.
  * The initial boost axis points at the target; solar-system targets use
    +X as the default boost axis, interstellar targets look up the unit
    vector from `aria.simulator.targets.STAR_CATALOG[name].direction_unit`.
  * Velocity is a 3-vector in m/s. Thrust is a 3-vector in the ship frame,
    commanded prograde (+target_direction) during BOOST, retrograde
    (-velocity_unit) during DECEL.
  * Scalar `position_ly` / `velocity_m_s` are retained as the magnitudes
    of the vectors so existing consumers (`/api/trajectory`, comms-budget,
    narrative-log, mission-planner UI) keep their shape.
  * Time stored in years (mission-elapsed).

References
----------
  * Frisbee 2003 JPL/D-26963 §3 (continuous-burn cruise trajectory)
  * Forward 1984 "Roundtrip Interstellar Travel" (boost / coast / decel phasing)
  * Wie 2008 "Space Vehicle Dynamics and Control" AIAA, §3 (thrust vectoring)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import Phase, get_phase_controller
from aria.simulator.targets import STAR_CATALOG
from aria.simulator.trajectory import (
    C_M_PER_S, G0_M_PER_S2, INTERSTELLAR_TARGETS, LIGHTYEAR_M,
    PROPULSION_OPTIONS,
)


# ── 3-D helpers ───────────────────────────────────────────────────────────

def _vec_mag(v: tuple[float, float, float]) -> float:
    """Euclidean magnitude of a 3-vector."""
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec_unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Unit vector of a 3-vector, or (0, 0, 0) if below numerical tolerance.
    1e-12 m/s is ~ machine epsilon at the cruise-speed scale (1e6 m/s)."""
    m = _vec_mag(v)
    if m < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / m, v[1] / m, v[2] / m)


# Bridge from INTERSTELLAR_TARGETS display names to STAR_CATALOG snake_case
# slugs. The two catalogs were populated independently; this table keeps
# them in sync without a rename across the UI. Names not listed default
# to +X (solar-system bodies + generic targets).
_STAR_DIRECTION_BY_DISPLAY_NAME: dict[str, str] = {
    "Proxima Centauri":   "proxima_centauri",
    "Alpha Centauri A":   "alpha_centauri",
    "Alpha Centauri B":   "alpha_centauri",
    "Barnard's Star":     "barnards_star",
    "Wolf 359":           "wolf_359",
    "Sirius A":           "sirius",
    "Epsilon Eridani":    "epsilon_eridani",
    "TRAPPIST-1":         "trappist_1",
}


def _direction_for_target(name: str) -> tuple[float, float, float]:
    """Unit boost-axis vector for `name`.

    Solar-system targets default to +X (the simulator has no ephemeris
    for planet positions at mission start — the closed-loop controller
    only needs a stable axis to steer against). Interstellar targets
    look up the 3-D unit vector from the star catalog.
    """
    slug = _STAR_DIRECTION_BY_DISPLAY_NAME.get(name)
    if slug is not None and slug in STAR_CATALOG:
        u = STAR_CATALOG[slug].direction_unit
        vec = (float(u[0]), float(u[1]), float(u[2]))
        # STAR_CATALOG's `direction_unit` divides by `distance_ly` which
        # can drift ~2 % from ‖position_ly‖ due to independent rounding
        # in the catalog. Re-normalise here so the guidance law always
        # sees a strictly unit vector.
        mag = _vec_mag(vec)
        if mag > 0:
            return (vec[0] / mag, vec[1] / mag, vec[2] / mag)
    return (1.0, 0.0, 0.0)


# Thrust delivered by the magnetic nozzle at full main_thrust_frac.
# Frisbee 2003 — fusion direct-drive, 1 MN (1e6 N) baseline at 100 MWth
# reactor with 10⁴ s Isp ≈ 100 km/s exhaust velocity, ~ 10 kg/s mass-flow
# and 10⁶ s "ideal" Isp at 1 MWth. We pick fusion_magnetic for nominal.
NOMINAL_THRUST_N: float = 1.0e6           # 1 MN thrust at full burn (Frisbee 2003 Table 4)
NOMINAL_ISP_S:    float = PROPULSION_OPTIONS["fusion_magnetic"].isp_s  # 10 000 s

# Below this β, Lorentz corrections are < 1 ppm — skip them to guarantee
# bit-identical results for chemical / fusion-magnetic regimes
# (β ≈ 6.2e-4 at the 10⁴-s-Isp ceiling). Above this we apply the
# longitudinal acceleration contraction a' = a·(1−β²)^(3/2) and integrate
# ship-proper-time dτ = dt·√(1−β²). See Rindler 2006 "Relativity" §3.5
# (Special Rel. dynamics) and Frisbee 2003 §3 (relativistic cruise).
_RELATIVISTIC_THRESHOLD_BETA: float = 1.0e-3
# Warning threshold — above this the sim's chemistry/fusion
# approximations (Frisbee 2003, fixed-Isp Tsiolkovsky) are outside
# their published regime; flag in the event bus once per crossing.
_RELATIVISTIC_WARN_BETA: float = 0.9


@dataclass
class TrajectoryState:
    """3-D trajectory state along the cruise axis.

    Scalar fields (``position_ly``, ``velocity_m_s``) are the magnitudes
    of the vector fields and are preserved for API-schema compatibility.
    """

    # BUG-016 (2026-04-24): default flipped to Moon.  The walkthrough
    # landing page and the default Trajectory render should show the
    # cislunar shakedown, not a 4.37-ly line where the ship sits pinned
    # at Earth.  Alpha Centauri A remains selectable from the dropdown.
    target: str = "Moon"
    distance_total_ly: float = INTERSTELLAR_TARGETS["Moon"]

    # Live state — scalar magnitudes (backward-compat API shape)
    position_ly: float = 0.0          # ‖position_vec‖ in light-years
    velocity_m_s: float = 0.0         # ‖velocity_vec‖ in m/s (≥ 0)
    # R7 (2026-04-24, sync refactor): `elapsed_yr` is a property reading
    # from the central MissionClock — see the @property below.  Was a
    # locally-incremented field in `tick()`; this caused two clocks to
    # leak (BUG-019).  `proper_elapsed_yr` is intentionally local — it
    # is the relativistic ship-frame clock, physically distinct from
    # the ground/mission clock and only meaningful relative to it.
    proper_elapsed_yr: float = 0.0    # ship-proper (crew) clock — ∫ dt·√(1−β²)

    # Live state — 3-D vectors (new GN&C additions)
    position_vec_ly: tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity_vec_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)
    thrust_vec: tuple[float, float, float] = (0.0, 0.0, 0.0)     # last commanded, ship frame
    target_direction: tuple[float, float, float] = (1.0, 0.0, 0.0)   # unit vector

    # Cumulative deltas (for diagnostics)
    cumulative_dv_m_s: float = 0.0    # total ΔV expended
    cumulative_burn_s: float = 0.0    # total seconds at non-zero thrust

    # Propulsion config
    nominal_thrust_n: float = NOMINAL_THRUST_N
    isp_s: float = NOMINAL_ISP_S
    ship_dry_mass_kg: float = 1.5e7   # ESTIMATE — 15 Mt dry (15 % of 100 Mt wet)
    ship_wet_mass_kg: float = 1.0e8   # 100 Mt wet (parameters.ship_mass_kg)
    propellant_mass_kg: float = 8.5e7 # 85 % of total — generation-ship mass-fraction (Frisbee 2003)

    # ── R7 sync refactor — `elapsed_yr` reads from MissionClock ──
    # Setter exists so legacy save/restore paths still work; it
    # delegates to MissionClock.reset() (the only sanctioned writer).
    @property
    def elapsed_yr(self) -> float:
        from aria.core.mission_clock import get_mission_clock
        return get_mission_clock().elapsed_yr

    @elapsed_yr.setter
    def elapsed_yr(self, value: float) -> None:
        from aria.core.mission_clock import get_mission_clock
        get_mission_clock().reset(to_yr=float(value))

    # One-shot event gates so milestones + fuel warnings don't spam the
    # bus when a long tick advances past multiple thresholds at once.
    _milestones_fired: set = field(default_factory=set)
    _fuel_low_fired: bool = False
    # Track previous tick's phase so we can detect operator-driven
    # re-boosts from a parked ARRIVAL / ORBIT state and reset the
    # position to 0 (start a fresh leg). Without this, a force-
    # transition BOOST from ARRIVAL lasts one tick before auto-
    # arrival re-fires (position is already clamped at distance)
    # and the UI reports "boost doesn't work" when the user clicks it.
    _prev_phase: str = ""
    # One-shot gate for the β > 0.9 "outside calibration range" warning.
    _relativistic_warn_fired: bool = False
    # Time (sim-years) at which the ship first entered ARRIVAL in the
    # current mission leg. Used to auto-transition ARRIVAL → ORBIT after
    # a short stabilisation window instead of parking indefinitely.
    _arrival_entered_yr: float = -1.0

    def __post_init__(self) -> None:
        # Seed the default target's direction so the vector fields stay
        # coherent with the scalar fields even before the first
        # set_target() call.
        self.target_direction = _direction_for_target(self.target)

    # ── derived ──────────────────────────────────────────────────

    @property
    def remaining_distance_ly(self) -> float:
        return max(0.0, self.distance_total_ly - self.position_ly)

    @property
    def fraction_complete(self) -> float:
        return min(1.0, self.position_ly / self.distance_total_ly) if self.distance_total_ly > 0 else 0.0

    @property
    def beta(self) -> float:
        """v/c — fractional speed of light."""
        return self.velocity_m_s / C_M_PER_S

    @property
    def eta_years(self) -> float:
        """Years until target at current speed (assumes constant velocity)."""
        if self.velocity_m_s <= 0:
            return float("inf")
        m_remaining = self.remaining_distance_ly * LIGHTYEAR_M
        return (m_remaining / self.velocity_m_s) / (365.25 * 24 * 3600)

    @property
    def propellant_remaining_kg(self) -> float:
        """Mass of propellant remaining.

        R7 (2026-04-24, sync refactor): now reads from `fuel_inventory`
        — the singleton that the failure injector and tank-burn logic
        actually mutate.  Used to be a Tsiolkovsky-inverse computed
        from `cumulative_dv_m_s`, which silently ignored injected fuel
        leaks (operator inject `fuel_leak_a` → tank empties → this
        property returned the unchanged Tsiolkovsky number).  The
        Tsiolkovsky inverse is preserved as a fallback if the fuel
        inventory is unavailable (test fixtures, restored snapshots).
        """
        try:
            from aria.simulator.fuel_tracker import get_fuel_inventory
            return float(get_fuel_inventory().total_main_kg)
        except Exception:
            v_e = self.isp_s * G0_M_PER_S2
            if v_e <= 0:
                return self.propellant_mass_kg  # no engine → no fuel burned
            burned = self.ship_wet_mass_kg * (1.0 - math.exp(-self.cumulative_dv_m_s / v_e))
            return max(0.0, self.propellant_mass_kg - burned)

    @property
    def propellant_fraction_remaining(self) -> float:
        # R7: derive from fuel_inventory's main_fill_pct directly so
        # this fraction can never disagree with `propellant_remaining_kg`.
        try:
            from aria.simulator.fuel_tracker import get_fuel_inventory
            return float(get_fuel_inventory().main_fill_pct) / 100.0
        except Exception:
            if self.propellant_mass_kg <= 0:
                return 0.0
            return self.propellant_remaining_kg / self.propellant_mass_kg

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        """Advance trajectory by `dt_s` simulation seconds."""
        bus = get_event_bus()
        phase = get_phase_controller()
        spec = phase.spec()

        # ── Operator-driven re-boost from a parked arrival ─────────
        # When phase transitions from ARRIVAL/ORBIT back into BOOST
        # (the user clicking the BOOST button while the ship is parked
        # at the target), clear position + velocity so the next leg
        # starts from 0. Without this, auto-arrival fires again on the
        # very next tick because position is still clamped at the
        # target's distance, making the BOOST button look inert.
        cur_phase_name = phase.current.value if hasattr(phase.current, "value") else str(phase.current)
        if cur_phase_name == "boost" and self._prev_phase in ("arrival", "orbit"):
            self.position_ly = 0.0
            self.velocity_m_s = 0.0
            self.position_vec_ly = (0.0, 0.0, 0.0)
            self.velocity_vec_m_s = (0.0, 0.0, 0.0)
            self._milestones_fired = set()
            bus.publish("trajectory.reboost_from_parked",
                        severity="info", source="trajectory_state",
                        payload={"target": self.target, "from_phase": self._prev_phase},
                        sim_time_yr=self.elapsed_yr)
        self._prev_phase = cur_phase_name

        # ── Scalar ↔ vector reconciliation ─────────────────────────
        # Back-compat: callers that bypass set_target() (tests, mission
        # restore, manual overrides) may set `velocity_m_s`/`position_ly`
        # scalar without touching the vectors. Detect the mismatch and
        # project the scalar onto `target_direction` so the 3-D integrator
        # sees a coherent state. Tolerance 1e-6 m/s absorbs float rounding.
        v_vec_mag = _vec_mag(self.velocity_vec_m_s)
        if abs(v_vec_mag - self.velocity_m_s) > 1e-6:
            self.velocity_vec_m_s = (self.target_direction[0] * self.velocity_m_s,
                                     self.target_direction[1] * self.velocity_m_s,
                                     self.target_direction[2] * self.velocity_m_s)
        p_vec_mag = _vec_mag(self.position_vec_ly)
        if abs(p_vec_mag - self.position_ly) > 1e-18:
            self.position_vec_ly = (self.target_direction[0] * self.position_ly,
                                    self.target_direction[1] * self.position_ly,
                                    self.target_direction[2] * self.position_ly)

        # Effective thrust: use propulsion_thermal's auto-throttled value
        # *only if* it has actually ticked at least once (otherwise its
        # actual_thrust_frac is the initial 0). If trajectory_state ticks
        # before propulsion_thermal in the same engine.advance() call, fall
        # back to the phase spec so we still get sane physics.
        try:
            from aria.simulator.propulsion_thermal import get_propulsion_thermal
            pt = get_propulsion_thermal()
            if pt.actual_thrust_frac == 0.0 and spec.main_thrust_frac > 0:
                thrust_frac = spec.main_thrust_frac    # not yet ticked
            else:
                thrust_frac = pt.actual_thrust_frac
        except Exception:
            thrust_frac = spec.main_thrust_frac

        # Auto-throttle can only reduce thrust below the commanded spec,
        # never exceed it. Clamping here prevents a stale non-zero
        # actual_thrust_frac (e.g. left over from a prior BOOST run) from
        # producing acceleration during PRELAUNCH / CRUISE / ARRIVAL.
        if thrust_frac > spec.main_thrust_frac:
            thrust_frac = spec.main_thrust_frac

        # Effective mass (wet at start, decreases as propellant burns)
        m_now = self.ship_dry_mass_kg + self.propellant_remaining_kg
        if m_now <= 0:
            m_now = self.ship_dry_mass_kg

        # ── Fuel-exhaustion gate ────────────────────────────────────
        # Tsiolkovsky bounds ΔV at Isp·g0·ln(wet/dry). Without this the
        # ship would keep accelerating on 'thrust' long after the tank
        # was empty — α Centauri shakedown showed v hitting 0.11 c with
        # propellant at 0 %, well beyond the fuel budget. Zero out
        # thrust when the tank is dry.
        if self.propellant_remaining_kg <= 0.0:
            thrust_frac = 0.0
            # Auto-transition BOOST → CRUISE when the tank empties —
            # otherwise the mission stays in 'boost' phase forever while
            # the ship coasts, confusing the UI. (Proxima shakedown: at
            # 186 km/s Tsiolkovsky bound, the trip takes ~6 800 yr; the
            # ship was stuck in BOOST the whole time.)
            if phase.current == Phase.BOOST:
                try:
                    phase.transition(Phase.CRUISE, force=True)
                    bus.publish("trajectory.fuel_depleted",
                                severity="warning",
                                source="trajectory_state",
                                payload={"velocity_m_s": round(self.velocity_m_s, 1),
                                         "remaining_ly": round(self.remaining_distance_ly, 6)},
                                sim_time_yr=self.elapsed_yr)
                except Exception:
                    pass

        # ── Closed-loop DECELERATION ────────────────────────────────
        # Previously DECEL was open-loop retrograde (thrust_frac = -|spec|)
        # which burns until velocity hits zero regardless of where you
        # stop. A real mission wants v = 0 AT the destination, not 1
        # million km short or past it.
        #
        # Kinematics: v² = v₀² + 2·a·s. Solve for the acceleration
        # magnitude that brings v → 0 over the remaining distance s:
        #     a_req = -v₀² / (2 s)        (negative = retrograde)
        # Convert to a thrust fraction and clamp to the engine's capability.
        if phase.current == Phase.DECELERATION and self.velocity_m_s > 0:
            remaining_m = max(0.0, self.remaining_distance_ly * LIGHTYEAR_M)
            if remaining_m > 1.0:   # guard near-target
                a_req = -(self.velocity_m_s ** 2) / (2.0 * remaining_m)   # m/s²
                required_thrust_n = a_req * m_now
                thrust_frac = max(-1.0, min(0.0, required_thrust_n / self.nominal_thrust_n))
            else:
                # At the destination with residual velocity — slam-brake.
                thrust_frac = -1.0

        # ── Commanded thrust direction (unit vector, ship frame) ───
        # BOOST (thrust_frac > 0) → fly toward target_direction.
        # DECEL (thrust_frac < 0) → fly retrograde (−velocity_unit).
        if thrust_frac > 0:
            cmd_dir = self.target_direction
        elif thrust_frac < 0:
            if self.velocity_m_s > 1e-9:
                vu = _vec_unit(self.velocity_vec_m_s)
                cmd_dir = (-vu[0], -vu[1], -vu[2])
            else:
                # No velocity to retro against — fall back to −target_direction.
                cmd_dir = (-self.target_direction[0],
                           -self.target_direction[1],
                           -self.target_direction[2])
        else:
            cmd_dir = (0.0, 0.0, 0.0)

        # Record the commanded thrust vector (signed scalar × direction,
        # same sign convention as the old scalar thrust_frac).
        self.thrust_vec = (cmd_dir[0] * abs(thrust_frac),
                           cmd_dir[1] * abs(thrust_frac),
                           cmd_dir[2] * abs(thrust_frac))

        # Newtonian acceleration MAGNITUDE (signed — retains the sign of
        # thrust_frac so the relativistic-correction branch below keeps
        # its original shape). Apply direction after the γ³ correction.
        a_newton = self.nominal_thrust_n * thrust_frac / m_now    # m/s² (signed)

        # ── Relativistic correction ────────────────────────────────
        # For longitudinal thrust the proper-frame force transforms to
        # ground-frame acceleration as
        #     a = F/(γ³·m)  =  a_newton · (1 − β²)^(3/2)
        # (Rindler 2006 eq. 3.29; Jackson "Classical Electrodynamics"
        # §11.10). Below β = 1e-3 the factor is < 1 ppm off unity, so
        # we take the exact Newtonian branch — guarantees bit-identical
        # results with the pre-relativistic sim for chemical / fusion
        # regimes. Above β = 0.9 the sim is outside the calibration
        # range of its Tsiolkovsky / Frisbee approximations; warn once.
        beta_now = abs(self.velocity_m_s) / C_M_PER_S
        if beta_now < _RELATIVISTIC_THRESHOLD_BETA:
            # Newtonian fast-path — identical to pre-relativistic code.
            a_eff = a_newton
            gamma_inv = 1.0         # √(1−β²) ≈ 1 to 5·10⁻⁷
        else:
            one_minus_beta_sq = max(0.0, 1.0 - beta_now * beta_now)
            gamma_inv = math.sqrt(one_minus_beta_sq)              # 1/γ
            a_eff = a_newton * one_minus_beta_sq * gamma_inv      # (1−β²)^(3/2)
            if (beta_now > _RELATIVISTIC_WARN_BETA
                    and not self._relativistic_warn_fired):
                self._relativistic_warn_fired = True
                bus.publish(
                    "trajectory.relativistic_regime",
                    severity="warning",
                    source="trajectory_state",
                    payload={
                        "beta": round(beta_now, 4),
                        "gamma": round(1.0 / gamma_inv, 3) if gamma_inv > 0 else None,
                        "note": "β > 0.9 — outside Frisbee/Tsiolkovsky calibration",
                    },
                    sim_time_yr=self.elapsed_yr,
                )
        # Hysteresis reset — allow re-firing if the ship ever drops back
        # below the warn band (e.g. decel brings β below 0.85).
        if beta_now < _RELATIVISTIC_WARN_BETA - 0.05:
            self._relativistic_warn_fired = False

        # ── Integrate velocity (3-D) ───────────────────────────────
        # a_eff carries the sign of thrust_frac; |a_eff| is the magnitude
        # of the applied acceleration and cmd_dir is its direction.
        a_vec = (cmd_dir[0] * abs(a_eff),
                 cmd_dir[1] * abs(a_eff),
                 cmd_dir[2] * abs(a_eff))
        vx, vy, vz = self.velocity_vec_m_s
        vx += a_vec[0] * dt_s
        vy += a_vec[1] * dt_s
        vz += a_vec[2] * dt_s

        # DECEL zero-crossing guard — the scalar model clamped negative
        # velocity to zero; in 3-D, when decelerating, if the component
        # along the original target_direction has gone through zero we
        # snap the vector to zero so residual thrust doesn't reverse us.
        if thrust_frac < 0:
            v_along_target = (vx * self.target_direction[0]
                              + vy * self.target_direction[1]
                              + vz * self.target_direction[2])
            if v_along_target < 0.0:
                vx = vy = vz = 0.0

        self.velocity_vec_m_s = (vx, vy, vz)
        self.velocity_m_s = _vec_mag(self.velocity_vec_m_s)

        # ── Integrate position (3-D) ───────────────────────────────
        px, py, pz = self.position_vec_ly
        px += (vx * dt_s) / LIGHTYEAR_M
        py += (vy * dt_s) / LIGHTYEAR_M
        pz += (vz * dt_s) / LIGHTYEAR_M
        self.position_vec_ly = (px, py, pz)
        self.position_ly = _vec_mag(self.position_vec_ly)

        # ΔV bookkeeping — we log the ground-frame Δv actually applied
        # (a_eff·dt), not the Newtonian target, so propellant-remaining
        # stays consistent with Tsiolkovsky at non-relativistic speeds
        # and continues to decline during relativistic coast-thrust.
        if abs(thrust_frac) > 1e-3:
            self.cumulative_dv_m_s += abs(a_eff * dt_s)
            self.cumulative_burn_s += dt_s

        # R7 (2026-04-24, sync refactor): the local `elapsed_yr +=` was
        # removed — `elapsed_yr` is now a property that reads from
        # MissionClock, the single mission-time authority.  Auto-tick
        # advances MissionClock once per iteration; trajectory_state
        # only reads the result.  Ship-proper (crew) time IS still
        # locally integrated because relativistic dilation is
        # computed FROM the ground clock, not equal to it.
        self.proper_elapsed_yr += dt_s * gamma_inv / (365.25 * 24.0 * 3600.0)

        # Significant-event publishing — milestone 25 % / 50 % / 75 % / arrival.
        # Each milestone is a one-shot (tracked on self._milestones_fired)
        # so it can't spam even if auto-tick advances many km per step.
        for milestone in (0.25, 0.5, 0.75, 1.0):
            milestone_ly = milestone * self.distance_total_ly
            if self.position_ly >= milestone_ly and milestone not in self._milestones_fired:
                self._milestones_fired.add(milestone)
                bus.publish(
                    f"trajectory.milestone.{int(milestone * 100)}pct",
                    severity="info",
                    source="trajectory_state",
                    payload={
                        "milestone_pct": int(milestone * 100),
                        "position_ly": round(self.position_ly, 4),
                        "velocity_m_s": round(self.velocity_m_s, 1),
                        "elapsed_yr": round(self.elapsed_yr, 2),
                    },
                    sim_time_yr=self.elapsed_yr,
                )
                if milestone == 1.0:
                    # Arrival is a success milestone, not a failure.
                    # Was severity="critical" — showed up in the Alarms
                    # panel as a red tile, indistinguishable from a real
                    # emergency.  "info" is the correct level: the
                    # StatusStrip and AlarmsPanel filter >=warning, so
                    # it still surfaces in "all events" views without
                    # polluting the critical count.
                    bus.publish("trajectory.arrival",
                                severity="info",
                                source="trajectory_state",
                                payload={"target": self.target},
                                sim_time_yr=self.elapsed_yr)

        # Auto-transition to ARRIVAL the moment we reach the target —
        # independent of the milestone one-shots above. Previously the
        # milestone-based detector missed overshoots that happened in a
        # single auto-tick step, leaving the ship burning past the target
        # until fuel was exhausted.
        #
        # BUG-039 (2026-04-24, walkthrough): for short cislunar targets
        # (Moon at 4e-8 ly) this used to fire on the very first tick
        # while phase was still PRELAUNCH or BOOST, so the mission
        # skipped directly to ARRIVAL without ever passing through
        # BOOST/CRUISE/DECELERATION.  Gate the auto-arrival on the
        # natural predecessor phases (DECELERATION is the nominal one;
        # CRUISE + BOOST are accepted for generation-ship "overshoot"
        # cases where the decel burn was skipped) so PRELAUNCH always
        # runs the phase chain through in order.
        if (self.position_ly >= self.distance_total_ly
                and phase.current in (Phase.BOOST, Phase.CRUISE, Phase.DECELERATION)):
            try:
                phase.transition(Phase.ARRIVAL, force=True)
            except Exception:
                pass

        # Clamp state once arrived: sit parked at the target with zero
        # velocity. Without this, DECEL still accumulates position past
        # destination before velocity hits zero, and ARRIVAL leaves the
        # ship drifting away from the target on residual velocity.
        if phase.current in (Phase.ARRIVAL, Phase.ORBIT) and self.position_ly >= self.distance_total_ly:
            self.position_ly = self.distance_total_ly
            self.velocity_m_s = 0.0
            # Snap the 3-D state too — park on the target_direction ray
            # at exactly distance_total_ly so vector consumers also see
            # "parked at destination".
            self.position_vec_ly = (self.target_direction[0] * self.distance_total_ly,
                                    self.target_direction[1] * self.distance_total_ly,
                                    self.target_direction[2] * self.distance_total_ly)
            self.velocity_vec_m_s = (0.0, 0.0, 0.0)
            self.thrust_vec = (0.0, 0.0, 0.0)

        # Auto-transition ARRIVAL → ORBIT once trim is done. Without this
        # the ship sits in ARRIVAL indefinitely, the `phase_orbit` mission
        # objective never completes (mission progress caps at 13/14 =
        # 92.86 %), and operators have no clear "mission complete" signal.
        # Stabilisation window: 1 sim-day — long enough for an RCS trim
        # pass, short enough that operators don't wonder why the phase
        # is stuck.
        if phase.current == Phase.ARRIVAL:
            if self._arrival_entered_yr < 0:
                self._arrival_entered_yr = self.elapsed_yr
            elif self.elapsed_yr - self._arrival_entered_yr >= (1.0 / 365.25):
                try:
                    phase.transition(Phase.ORBIT)
                    bus.publish("trajectory.orbit_achieved",
                                severity="info", source="trajectory_state",
                                payload={"target": self.target,
                                         "elapsed_yr": round(self.elapsed_yr, 3)},
                                sim_time_yr=self.elapsed_yr)
                    self._arrival_entered_yr = -1.0
                except Exception:
                    pass
        else:
            # Reset on any non-ARRIVAL phase so a re-boost+re-arrival
            # cycle triggers the stabilisation window fresh.
            self._arrival_entered_yr = -1.0

        # Out-of-fuel warning — one-shot (crosses 5 % threshold once).
        # Previously fired every tick after fuel exhausted, flooding the
        # bus history.
        if (self.propellant_fraction_remaining < 0.05
                and not self._fuel_low_fired
                and abs(thrust_frac) > 0.01):
            self._fuel_low_fired = True
            bus.publish("trajectory.fuel_low",
                        severity="warning",
                        source="trajectory_state",
                        payload={"remaining_frac": round(self.propellant_fraction_remaining, 4)},
                        sim_time_yr=self.elapsed_yr)
        elif self.propellant_fraction_remaining >= 0.10:
            # Hysteresis reset so a refuel → drain cycle fires the warning again.
            self._fuel_low_fired = False

    # ── operator actions ──────────────────────────────────────

    def set_target(self, target: str) -> None:
        if target not in INTERSTELLAR_TARGETS:
            raise ValueError(f"Unknown target {target}")
        self.target = target
        self.distance_total_ly = INTERSTELLAR_TARGETS[target]
        # Reset position + per-mission gates — without this, switching
        # from Mars (2.4e-5 ly travelled) to Jupiter left position at
        # Mars's exit spot so the new mission immediately read as past
        # destination. Milestones + fuel warning also reset so the new
        # mission's events fire fresh.
        self.position_ly = 0.0
        self.velocity_m_s = 0.0
        self.position_vec_ly = (0.0, 0.0, 0.0)
        self.velocity_vec_m_s = (0.0, 0.0, 0.0)
        self.thrust_vec = (0.0, 0.0, 0.0)
        self.target_direction = _direction_for_target(target)
        self.cumulative_dv_m_s = 0.0
        self.cumulative_burn_s = 0.0
        self.proper_elapsed_yr = 0.0
        self._milestones_fired = set()
        self._fuel_low_fired = False
        self._relativistic_warn_fired = False

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        # Solar-system targets sit at ~1e-8 — 1e-4 ly; rounding to 4 decimals
        # would clip them to 0. Use 10 decimals so Moon (4.06e-8) survives.
        return {
            "target": self.target,
            "distance_total_ly":      round(self.distance_total_ly, 10),
            "position_ly":            round(self.position_ly, 10),
            "remaining_distance_ly":  round(self.remaining_distance_ly, 10),
            "fraction_complete":      round(self.fraction_complete, 6),
            "velocity_m_s":           round(self.velocity_m_s, 2),
            "beta":                   round(self.beta, 8),
            "eta_yr":                 round(self.eta_years, 2) if self.eta_years != float("inf") else None,
            "elapsed_yr":             round(self.elapsed_yr, 3),
            "proper_elapsed_yr":      round(self.proper_elapsed_yr, 3),
            "cumulative_dv_m_s":      round(self.cumulative_dv_m_s, 2),
            "cumulative_burn_s":      round(self.cumulative_burn_s, 1),
            "propellant_remaining_kg": round(self.propellant_remaining_kg, 1),
            "propellant_fraction_remaining": round(self.propellant_fraction_remaining, 6),
            # ── 3-D GN&C additions (new consumers only) ────────────
            "position_vec_ly":    [round(c, 10) for c in self.position_vec_ly],
            "velocity_vec_m_s":   [round(c, 3)  for c in self.velocity_vec_m_s],
            "thrust_vec":         [round(c, 6)  for c in self.thrust_vec],
            "target_direction":   [round(c, 8)  for c in self.target_direction],
            "config": {
                "nominal_thrust_n": self.nominal_thrust_n,
                "isp_s": self.isp_s,
                "ship_dry_mass_kg": self.ship_dry_mass_kg,
                "ship_wet_mass_kg": self.ship_wet_mass_kg,
                "propellant_mass_kg": self.propellant_mass_kg,
            },
        }


_DEFAULT: Optional[TrajectoryState] = None


def get_trajectory_state() -> TrajectoryState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TrajectoryState()
    return _DEFAULT


def reset_trajectory_state() -> None:
    global _DEFAULT
    _DEFAULT = TrajectoryState()
    # `elapsed_yr` is a property that reads from the singleton
    # MissionClock — resetting the trajectory state alone leaves the
    # clock pointing at whatever the previous test advanced it to, and
    # the next test sees a fresh trajectory but a non-zero elapsed_yr.
    # Reset the clock too so test isolation actually works.
    try:
        from aria.core.mission_clock import reset_mission_clock
        reset_mission_clock()
    except Exception:
        pass


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("trajectory_state", get_trajectory_state().tick, order=35)
