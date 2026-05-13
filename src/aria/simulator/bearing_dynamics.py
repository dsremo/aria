"""Habitat-ring bearing dynamics — magnetic-levitation primary + roller backup.

The 54 Mt habitat ring spins relative to the non-rotating hull. Two
bearing technologies are modelled:

  * **Magnetic-bearing** (primary)  — Earnshaw 1842 + active control,
    no mechanical contact, no wear in nominal operation, but consumes
    continuous magnet power and trips off on any of: power loss, sensor
    fault, plasma transient.
  * **Roller-bearing** (backup)     — angular-contact ball bearing in a
    Hertzian-contact loading regime, lubricated by a fluoropolymer (Krytox)
    film. Wears according to L₁₀ life equation (Lundberg-Palmgren 1947).

When the magnetic bearing trips, load transfers to rollers — usable but
on a clock; rollers wear, lubricant degrades, eventual failure if maglev
is not restored.

References
----------
  * Earnshaw, S. 1842, "On the nature of molecular forces" — magnetic levitation
  * Lundberg, G. & Palmgren, A. 1947, "Dynamic capacity of rolling bearings",
    Acta Polytech. — L₁₀ life equation
  * Harris, T.A. 2001, "Rolling Bearing Analysis" 4e — EHL film thickness
  * SKF General Catalogue Ch. 3 — ball-bearing design data
  * Hamrock & Dowson 1981, "Ball Bearing Lubrication" — EHL chart
  * Schweitzer, G. & Maslen, E.H. 2009, "Magnetic Bearings" — controller bandwidth limits
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Constants ──────────────────────────────────────────────────────

# Habitat ring mass + geometry from ShipParameters defaults
RING_MASS_KG: float = 5.49e7         # 54.9 Mt — habitat ring (parameters.py mass budget)
RING_RPM: float = 1.0                 # parameters.habitat_rpm
RING_RADIUS_M: float = 500.0          # parameters.habitat_ring_radius_m

# ── Magnetic bearing (Schweitzer & Maslen 2009 §6, AMB design) ──────
MAGNETIC_BEARING_POWER_W: float = 5.0e4          # 50 kW continuous (~1 kW per Mt rotor mass × 50 Mt; Schweitzer 2009 Table 6.1)
MAGNETIC_BEARING_MAX_LOAD_N: float = 1.0e7       # 10 MN — Earnshaw + active control limit (Schweitzer 2009 Eq. 6.18)
MAGNETIC_BEARING_TRIP_RATE_PER_YR: float = 1.5e-2  # ~1 trip per 67 yr (Boeing 1996 maglev wheel data, scaled)

# ── Roller bearing (Lundberg-Palmgren / Harris 2001) ────────────────
ROLLER_DYNAMIC_LOAD_RATING_N: float = 1.0e7      # Custom spherical roller for 55 Mt ring — 10 MN rating (Harris 2001 Ch. 9 scaling: 4 MN SKF 240/750 × 2.5× larger bore). Per-station load 5 MN → C/P=2.0 → L10 life ≈ 15 yr of continuous roller operation, enough to survive the ~1 maglev trip per decade seen on long missions without burning to EOL on a single trip.
ROLLER_LIFE_EXPONENT: float = 10.0 / 3.0          # Lundberg-Palmgren exponent for roller bearings
ROLLER_LUBE_TEMP_K: float = 300.0                 # nominal operating temp (rejected to thermal loop)
ROLLER_LUBE_VISCOSITY_PA_S: float = 0.045         # Krytox 143AC at 300 K (DuPont 2009 datasheet)
# Number of bearing stations distributed around the ring. A monolithic
# ring bearing can't carry a 55 Mt rotor's 300 MN centripetal load on a
# single roller (rating 4 MN) — real designs segment the ring into 40–60
# stations with load-sharing trusses (Schweitzer & Maslen 2009 §6.3).
# Without this, a single maglev trip burns all rollers to EOL in one tick
# because the naive per-bearing load is 75× the rating.
BEARING_STATION_COUNT: int = 60                  # segmented ring: 60 stations (Schweitzer 2009 §6.3)


class BearingMode(str, Enum):
    """What's currently carrying the ring's weight."""

    MAGNETIC = "magnetic"        # nominal — primary maglev online
    ROLLER   = "roller"          # maglev tripped, fallback to mechanical
    OFF      = "off"             # both unavailable — ring spinning down on inertia


@dataclass
class BearingState:
    """Real-time state of the habitat-ring bearing system."""

    # Configuration
    ring_mass_kg: float = RING_MASS_KG
    ring_rpm: float = RING_RPM
    ring_radius_m: float = RING_RADIUS_M

    # Mode
    mode: BearingMode = BearingMode.MAGNETIC
    maglev_powered: bool = True

    # Magnetic-bearing wear (electromagnet de-rating, near-zero in nominal use)
    # Equilibrium temperature from Q_ohmic = Q_coolant at 320K coolant:
    # I²R(T_eq) = h*A*(T_eq - T_cool) → T_eq ≈ 320.5K (computed from model params)
    magnet_winding_temp_k: float = 320.5
    magnet_total_powered_hours: float = 0.0

    # Roller-bearing wear: cumulative revolutions on the rollers
    roller_revolutions: float = 0.0
    roller_life_consumed_frac: float = 0.0   # 0..1, where 1.0 = end of L₁₀ life
    roller_lube_film_um: float = 1.0         # EHL film thickness in microns
    roller_temperature_k: float = 300.0

    # Operational stats
    last_trip_at_yr: Optional[float] = None
    total_trips: int = 0
    total_alarms: int = 0

    # ── derived properties ─────────────────────────────────────

    @property
    def static_load_n(self) -> float:
        """Total centripetal load on the ring (distributed across all stations).

        F_total = m·ω²·R  where ω = 2π·rpm/60.
        """
        omega = 2.0 * math.pi * self.ring_rpm / 60.0
        return self.ring_mass_kg * omega * omega * self.ring_radius_m

    @property
    def per_station_load_n(self) -> float:
        """Centripetal load carried by a single bearing station (total / N)."""
        return self.static_load_n / max(1, BEARING_STATION_COUNT)

    @property
    def loading_factor(self) -> float:
        """0..1 fraction of rated load (per bearing station, not total)."""
        return min(1.0, self.per_station_load_n / ROLLER_DYNAMIC_LOAD_RATING_N)

    @property
    def operational(self) -> bool:
        return self.mode in (BearingMode.MAGNETIC, BearingMode.ROLLER)

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        """Advance the bearing state by `dt_s` seconds."""
        bus = get_event_bus()
        phase = get_phase_controller()

        # In OFF mode, the ring is coasting — model as no-load on bearings.
        # No wear accumulates, but if maglev is suddenly restored we transition back.
        if self.mode == BearingMode.OFF:
            if self.maglev_powered:
                self._transition(BearingMode.MAGNETIC, "Maglev restored — re-engaging primary")
            return

        if self.mode == BearingMode.MAGNETIC:
            # First-principles maglev coil thermal model:
            #   dT/dt = (Q_ohmic - Q_coolant) / (m_coil * c_p)
            #
            # Q_ohmic: resistive losses in copper windings
            #   P = I²R, where R increases with temperature: R(T) = R_ref * (1 + α*(T - T_ref))
            #   Typical AMB: I=50A, R_ref=0.5Ω at 300K (Schweitzer 2009 §6.3)
            #   α_Cu = 0.00393 /K (CRC Handbook, copper)
            #
            # Q_coolant: active cooling via NaK loop
            #   Q = h*A*(T_coil - T_coolant)
            #   h ~ 5000 W/m²/K for forced NaK convection (Lyon 1949 Chem Eng Prog)
            #   A ~ 0.5 m² coil surface area (ESTIMATE — 8 coils × 0.06 m² each)
            #   T_coolant = 320 K (thermal_management.py NaK outlet)
            #
            self.magnet_total_powered_hours += dt_s / 3600.0

            # Operating parameters
            i_coil_a = 50.0         # coil current (Schweitzer 2009 §6.3)
            r_ref_ohm = 0.5         # reference resistance at 300K
            t_ref_k = 300.0         # reference temperature
            alpha_cu = 0.00393      # Cu temperature coefficient (CRC Handbook)
            m_coil_kg = 200.0       # total coil mass (8 coils × 25 kg, ESTIMATE)
            cp_cu = 385.0           # specific heat Cu (J/kg/K, NIST)
            h_coolant = 5000.0      # NaK convection coefficient (Lyon 1949)
            a_surface_m2 = 0.48     # coil cooling surface (ESTIMATE — 8 × 0.06 m²)
            t_coolant_k = 320.0     # NaK outlet temperature

            # Linearise the resistive heating around the current
            # winding temperature so the ODE is dT/dt = a − b·T, which has
            # an exact closed-form solution.  Forward Euler (T += dT·dt)
            # is unstable for substeps much larger than the thermal time
            # constant τ = m·cp / (h·A) ≈ 32 s, so a 10-day mission tick
            # used to drive the temperature to absurd values (87 000 K).
            # The exponential update below is unconditionally stable and
            # exact in the linearised model.  See
            # tests/integration/test_mission_end_to_end.py
            # ::test_maglev_winding_temperature_equilibrates.
            T = self.magnet_winding_temp_k

            # Linearise R(T) at current T to keep the closed form clean;
            # alpha is small enough (0.4 % / K) that re-linearising every
            # tick is plenty accurate even at large dt.
            r_coil = r_ref_ohm * (1.0 + alpha_cu * (T - t_ref_k))
            q_ohmic_w = i_coil_a ** 2 * r_coil

            # Cooling rate at current T (used to determine equilibrium)
            q_coolant_w = h_coolant * a_surface_m2 * (T - t_coolant_k)

            # Equilibrium temperature where Q_ohmic = Q_cool, with R(T_eq)
            # held at the linearised-around-T value (consistent with the
            # closed-form integrator below).
            denom_w_per_k = h_coolant * a_surface_m2
            if denom_w_per_k > 1e-9:
                t_eq_k = t_coolant_k + q_ohmic_w / denom_w_per_k
                tau_s = (m_coil_kg * cp_cu) / denom_w_per_k
                # T(t+dt) = T_eq + (T - T_eq) * exp(-dt/τ)
                import math as _m
                self.magnet_winding_temp_k = (
                    t_eq_k + (T - t_eq_k) * _m.exp(-dt_s / tau_s)
                )
            else:
                # Fall back to forward Euler if cooling is degenerate.
                dt_coil = (q_ohmic_w - q_coolant_w) / (m_coil_kg * cp_cu)
                self.magnet_winding_temp_k += dt_coil * dt_s
            # Random-failure rate — Poisson per yr → per-tick probability
            rate_per_s = MAGNETIC_BEARING_TRIP_RATE_PER_YR / (365.25 * 24 * 3600)
            # Use fast linear approximation; for short dt this matches Poisson well
            if rate_per_s * dt_s > self._random_seed():
                self._trip("Maglev controller fault (random)")

            # If the magnet winding exceeds 400 K → safety trip
            if self.magnet_winding_temp_k > 400.0:
                self._trip(f"Magnet winding overtemp ({self.magnet_winding_temp_k:.0f} K)")

        elif self.mode == BearingMode.ROLLER:
            # Each revolution wears the bearing per L₁₀ life equation:
            #   L = (C / P)^p × 10^6  (revolutions to 10% failure probability)
            # Track fractional life consumption per tick.
            revs_this_tick = self.ring_rpm * (dt_s / 60.0)
            self.roller_revolutions += revs_this_tick
            # L₁₀ is computed per-station: each bearing carries only
            # (total / N_stations) so a distributed 60-station ring lasts
            # many decades even under fallback roller mode, instead of
            # burning out in seconds on the first maglev trip.
            P = self.per_station_load_n         # per-bearing load
            C = ROLLER_DYNAMIC_LOAD_RATING_N    # dynamic rating
            # Guard: at zero RPM the centripetal load is 0 → no bearing wear.
            if P <= 0:
                return
            life_revs = (C / P) ** ROLLER_LIFE_EXPONENT * 1e6
            if life_revs > 0:
                self.roller_life_consumed_frac += revs_this_tick / life_revs
                self.roller_life_consumed_frac = min(1.0, self.roller_life_consumed_frac)

            # EHL film thinning under continuous load (Hamrock & Dowson 1981)
            # Simplified: film shrinks linearly with cumulative revolutions until
            # it falls below 0.1 µm — boundary lubrication regime → rapid wear.
            self.roller_lube_film_um = max(0.1, 1.0 - self.roller_revolutions / 1.0e10)

            # Roller bearings dissipate friction heat — modelled as ΔT
            self.roller_temperature_k = ROLLER_LUBE_TEMP_K + 30.0 * self.loading_factor

            # End-of-life triggers
            if self.roller_life_consumed_frac >= 0.95 and not self._already_alarmed("eol"):
                self._alarm("Roller bearing >95% L10 life consumed", critical=True, alarm_id="eol")
            if self.roller_lube_film_um <= 0.15 and not self._already_alarmed("lube"):
                self._alarm("EHL film below 0.15 µm — boundary lubrication regime", critical=True, alarm_id="lube")

            # Auto-recovery: try to reinstate maglev every tick once the
            # coil has cooled. The old modulus-on-revolutions gate fired
            # at arbitrary intervals and could miss entirely for small
            # sub-minute substeps — live backend showed mode stuck on
            # ROLLER for 2 sim-yr after a trip even with winding cooled.
            if self.maglev_powered and self._can_restart_maglev():
                self._transition(BearingMode.MAGNETIC,
                                 "Maglev re-acquired after roller backup")

    # ── operator actions ───────────────────────────────────────

    def force_trip(self, reason: str) -> None:
        """Operator-initiated maglev trip (e.g. drill scenario)."""
        self._trip(reason)

    def restore_maglev_power(self) -> None:
        self.maglev_powered = True

    def cut_maglev_power(self) -> None:
        self.maglev_powered = False
        if self.mode == BearingMode.MAGNETIC:
            self._trip("Maglev power cut by operator")

    # ── internal helpers ───────────────────────────────────────

    _random_state: int = 0
    _alarm_log: set = field(default_factory=set)

    def _random_seed(self) -> float:
        """Deterministic LCG so tests reproduce."""
        self._random_state = (self._random_state * 6364136223846793005 + 1) & ((1 << 64) - 1)
        return (self._random_state >> 11) / (1 << 53)

    def _can_restart_maglev(self) -> bool:
        """Maglev can come back if power available + winding cooled."""
        return self.maglev_powered and self.magnet_winding_temp_k < 380.0

    def _trip(self, reason: str) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        self.total_trips += 1
        self.last_trip_at_yr = phase.elapsed_yr
        if self.maglev_powered and self.mode == BearingMode.MAGNETIC:
            self._transition(BearingMode.ROLLER, f"Maglev trip → roller backup. {reason}")
        else:
            self._transition(BearingMode.OFF, f"All bearings offline. {reason}")

    def _transition(self, new_mode: BearingMode, reason: str) -> None:
        if new_mode == self.mode:
            return
        bus = get_event_bus()
        phase = get_phase_controller()
        old = self.mode
        self.mode = new_mode
        severity = "critical" if new_mode == BearingMode.OFF else "warning"
        bus.publish(
            f"bearing.transition.{new_mode.value}",
            severity=severity,
            source="bearing_dynamics",
            payload={"from": old.value, "to": new_mode.value,
                     "reason": reason, "loading_factor": round(self.loading_factor, 3)},
            sim_time_yr=phase.elapsed_yr,
        )

    def _alarm(self, msg: str, *, critical: bool, alarm_id: str) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()
        self.total_alarms += 1
        self._alarm_log.add(alarm_id)
        bus.publish(
            f"bearing.alarm.{alarm_id}",
            severity="critical" if critical else "warning",
            source="bearing_dynamics",
            payload={"message": msg, "life_consumed": round(self.roller_life_consumed_frac, 3)},
            sim_time_yr=phase.elapsed_yr,
        )

    def _already_alarmed(self, alarm_id: str) -> bool:
        return alarm_id in self._alarm_log

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "config": {
                "ring_mass_kg": self.ring_mass_kg,
                "ring_rpm": self.ring_rpm,
                "ring_radius_m": self.ring_radius_m,
                "static_load_n": round(self.static_load_n, 1),
                "station_count": BEARING_STATION_COUNT,
                "per_station_load_n": round(self.per_station_load_n, 1),
                "loading_factor": round(self.loading_factor, 4),
            },
            "mode": self.mode.value,
            "operational": self.operational,
            "maglev": {
                "powered": self.maglev_powered,
                "winding_temp_k": round(self.magnet_winding_temp_k, 1),
                "total_powered_hours": round(self.magnet_total_powered_hours, 2),
                "trip_rate_per_yr": MAGNETIC_BEARING_TRIP_RATE_PER_YR,
            },
            "roller": {
                "revolutions": round(self.roller_revolutions, 1),
                "life_consumed_pct": round(100.0 * self.roller_life_consumed_frac, 3),
                "lube_film_um": round(self.roller_lube_film_um, 3),
                "temperature_k": round(self.roller_temperature_k, 1),
                "loading_factor": round(self.loading_factor, 3),
            },
            "stats": {
                "total_trips": self.total_trips,
                "last_trip_at_yr": self.last_trip_at_yr,
                "total_alarms": self.total_alarms,
            },
        }


# ── Module singleton + tick-engine hook ────────────────────────

_DEFAULT: Optional[BearingState] = None


def get_bearing_state() -> BearingState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = BearingState()
    return _DEFAULT


def reset_bearing_state() -> None:
    global _DEFAULT
    _DEFAULT = BearingState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("bearing_dynamics", get_bearing_state().tick, order=44)
