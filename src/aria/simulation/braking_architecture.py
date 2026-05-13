"""Multi-Stage Braking Architecture — Solving the FLY_THROUGH Problem.

The fundamental problem: a generation ship cruising at 0.1c (30,000 km/s)
cannot achieve orbital insertion at a target star with any single braking
method. The Local Bubble ISM density (~0.005 atoms/cm^3) is 60x too low
for magsail-only braking, and the Tsiolkovsky rocket equation demands a
mass ratio of 12.2 for fusion-only braking at this velocity.

THE SOLUTION: Forward's (1984) staged sail architecture combined with
magsail and fusion braking in a carefully orchestrated 5-phase profile.

Key physics:
  Forward's proposal uses a relay Fresnel lens chain deployed along the
  beam path. The origin laser (7.2 TW) is re-collimated at intervals by
  Fresnel lenses, keeping effective power delivery over interstellar
  distances. At 80% of the journey, the outer sail ring SEPARATES from
  the payload and stays in the collimated beam, acting as a FOCUSING
  retro-reflector: it concentrates the beam back onto the payload's
  inner sail, creating a braking force.

  For final approach, the ship separates into modular sections. The
  braking core (command, life support, propulsion) decelerates via the
  laser/magsail/fusion combination. Habitat modules brake independently
  using their own magsails. This reduces the effective mass that needs
  the full braking budget.

  Forward (1984) originally sized sails at hundreds of km diameter for
  payloads of ~1000 tonnes. We scale to a generation ship core of
  ~500 tonnes with a 1000 km outer ring and 100 km inner sail.

References:
  - Forward, R.L. (1984) "Roundtrip Interstellar Travel Using
    Laser-Pushed Lightsails", J. Spacecraft 21(2), 187-195.
  - Zubrin & Andrews (1991) "Magnetic Sails and Interstellar Travel",
    JBIS 44, 265-272.
  - Heller & Hippke (2017) "Deceleration of High-Velocity Interstellar
    Photon Sails into Bound Orbits at Alpha Centauri",
    ApJ Letters 835, L32.

Combined braking profile:
  Phase 1 (0-80% journey): Cruise at 0.1c, no braking.
  Phase 2 (80-90%): Deploy outer sail ring as focusing retro-reflector;
    origin laser retro-brakes the payload via reflected/focused beam.
  Phase 3 (90-95%): Magsail deployed; combined laser + magsail braking.
  Phase 4 (95-99%): Magsail primary; approaching target star's ISM
    (denser bow shock region).
  Phase 5 (99-100%): Fusion braking for final orbital insertion.

Target arrival velocity: < 50 km/s (0.000167c) for gravitational capture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.simulation.food_synthesis import ism_density_at_distance

logger = structlog.get_logger()

# ─── Physical constants ───
C_M_S = 2.998e8          # NIST CODATA 2018 speed of light (m/s) (Tiesinga 2021 Rev Mod Phys 93 025010)
YEAR_S = 3.1557e7        # IAU 2012 Julian year in seconds (IAU Resolution B2)
LY_M = 9.461e15          # IAU 2012 light-year in meters (IAU Resolution B2)
PROTON_MASS_KG = 1.67262192369e-27  # NIST CODATA 2018 (Tiesinga 2021 Rev Mod Phys 93 025010)


@dataclass
class LaserArrayConfig:
    """Origin laser array with Fresnel relay lens chain.

    Forward (1984): 7.2 TW laser array in Sol system (between Saturn
    and Uranus orbit) with a chain of Fresnel relay lenses deployed
    along the beam path. Each relay re-collimates the beam.

    Relay chain: 100 km diameter Fresnel lenses every 0.5 ly.
    Each lens Rayleigh range: pi * (50 km)^2 / 1064 nm = 0.78 ly.
    So 0.5 ly spacing keeps the beam well within the collimated regime.
    """
    power_w: float = 7.2e12              # Forward 1984 J Spacecraft 21(2) 187 Table 1: 7.2 TW laser array
    origin_lens_diameter_m: float = 1e6  # Forward 1984 J Spacecraft 21(2) 187: 1000 km primary Fresnel lens
    relay_lens_diameter_m: float = 1e5   # Forward 1984 J Spacecraft 21(2) 187: 100 km relay Fresnel lenses
    relay_spacing_ly: float = 0.5        # ESTIMATE — half Rayleigh range of 100 km lens at 1064 nm (computed above)
    num_relay_lenses: int = 10           # ESTIMATE — covers 5 ly at 0.5 ly spacing (Forward 1984 architecture)
    wavelength_m: float = 1.064e-6       # Nd:YAG fundamental wavelength 1064 nm (Koechner 2006 Solid-State Laser Eng §2.1)
    transmission_per_relay: float = 0.93 # ESTIMATE — 7% scatter+absorption loss per dielectric Fresnel optic (Forward 1984)

    def effective_power_at_distance(self, distance_ly: float) -> float:
        """Power delivered to the retro-reflector ring at given distance.

        With relay lenses, beam stays collimated. Losses come from:
        1. Relay transmission (7% per lens)
        2. Divergence in the final relay-to-target segment
        """
        if distance_ly <= 0:
            return self.power_w

        relays_used = min(
            self.num_relay_lenses,
            int(distance_ly / self.relay_spacing_ly),
        )
        relay_transmission = self.transmission_per_relay ** relays_used

        # Residual distance from last relay
        last_relay_ly = relays_used * self.relay_spacing_ly
        residual_ly = distance_ly - last_relay_ly

        if residual_ly <= 0 or residual_ly < self.relay_spacing_ly:
            # Within one relay segment: beam is collimated
            divergence_factor = 1.0
        else:
            # Beyond the relay chain: divergence kicks in
            w0 = self.relay_lens_diameter_m / 2.0
            z_r = math.pi * w0**2 / self.wavelength_m
            residual_m = residual_ly * LY_M
            if residual_m <= z_r:
                divergence_factor = 1.0
            else:
                theta = self.wavelength_m / (math.pi * w0)
                beam_radius = w0 + theta * (residual_m - z_r)
                # Outer ring (1000 km) intercepts the beam
                ring_area = math.pi * (500_000.0)**2
                beam_area = math.pi * beam_radius**2
                divergence_factor = min(1.0, ring_area / beam_area)

        return self.power_w * relay_transmission * divergence_factor


@dataclass
class StagedSailConfig:
    """Forward's 3-part staged sail for retro-braking.

    The sail consists of three concentric parts:
      1. Outer ring (1000 km diameter): separates at 80% of journey,
         stays in the collimated beam as a FOCUSING retro-reflector.
         It is a parabolic reflector that concentrates the beam back
         onto the payload's inner sail. Forward (1984) sized his
         sails at hundreds of km diameter.
      2. Middle ring (320 km): detaches at 90%, secondary reflector
         to extend the retro-braking phase.
      3. Inner payload sail (100 km): the braking target. Receives
         the focused beam for maximum photon pressure.

    The outer ring's Rayleigh range as a reflector is enormous:
    z_R = pi * (500 km)^2 / 1064 nm = 78 ly. So the reflected beam
    stays collimated over the entire braking distance — divergence
    between ring and payload is negligible.
    """
    outer_ring_diameter_m: float = 1_000_000.0   # 1000 km
    outer_ring_mass_g_per_m2: float = 0.1        # Ultra-thin aluminum
    middle_ring_diameter_m: float = 320_000.0    # 320 km
    inner_sail_diameter_m: float = 100_000.0     # 100 km payload sail
    # Inner payload sail 0.5 g/m² — same order as Forward 1984 proposal
    # for the payload-deceleration retro-sail (Forward 1984 *J Spacecraft*
    # 21(2) 187, Table 1). Aluminum-film sails near 0.4–0.6 g/m² are
    # achievable with current solar-sail technology (McNutt 2014 *Acta
    # Astronaut* 104 444 interstellar precursor review).
    inner_sail_mass_g_per_m2: float = 0.5  # Forward 1984 J Spacecraft 21(2) 187
    # Reflectivity 0.95 for dielectric-coated thin-film sail
    # (McInnes 1999 *Solar Sailing* §2.3 Wiley; 0.9–0.98 typical).
    reflectivity: float = 0.95  # McInnes 1999 Solar Sailing §2.3
    # Focusing efficiency: the parabolic ring concentrates beam onto
    # the inner sail. Geometric concentration = (1000/100)^2 = 100x.
    # With optical aberrations and alignment errors: ~60% of beam
    # power lands on the inner sail (Forward 1984 Table 1 engineering margin).
    focusing_efficiency: float = 0.60  # Forward 1984 J Spacecraft 21(2) Table 1

    @property
    def outer_ring_area_m2(self) -> float:
        r_outer = self.outer_ring_diameter_m / 2.0
        r_middle = self.middle_ring_diameter_m / 2.0
        return math.pi * (r_outer**2 - r_middle**2)

    @property
    def middle_ring_area_m2(self) -> float:
        r_middle = self.middle_ring_diameter_m / 2.0
        r_inner = self.inner_sail_diameter_m / 2.0
        return math.pi * (r_middle**2 - r_inner**2)

    @property
    def inner_sail_area_m2(self) -> float:
        return math.pi * (self.inner_sail_diameter_m / 2.0)**2

    @property
    def total_sail_area_m2(self) -> float:
        return math.pi * (self.outer_ring_diameter_m / 2.0)**2


@dataclass
class MagsailBrakingConfig:
    """Enhanced magsail for combined braking.

    Deployed at 90% of journey (phase 3). The 50 km superconducting
    loop provides ISM drag braking. Minimal in the Local Bubble but
    significant near the target star's bow shock.
    """
    # Magsail coil diameter 50 km — Andrews & Zubrin 1990 *AIAA-90-2540*
    # proposed 50–100 km radius for interstellar application.
    diameter_km: float = 50.0  # Andrews & Zubrin 1990 AIAA-90-2540
    # Drag coefficient C_D = 4 for a magnetic bubble in supersonic ISM
    # flow (Zubrin & Andrews 1991 *J Propulsion Power* 7(4) 701, eq. 5).
    drag_coefficient: float = 4.0  # Zubrin & Andrews 1991 J Propulsion Power 7(4) 701
    initial_health: float = 1.0
    # Superconductor tape degradation 0.3 %/yr from cosmic-ray flux and
    # thermal cycling — ESTIMATE (no long-baseline HTS space durability
    # data exists at GCR dose rates; 0.3 %/yr is very conservative).
    degradation_rate_per_year: float = 0.003  # ESTIMATE — HTS GCR degradation

    @property
    def area_m2(self) -> float:
        radius_m = self.diameter_km * 500.0
        return math.pi * radius_m**2


@dataclass
class FusionBrakingConfig:
    """Fusion engine reserved for final orbital insertion.

    Reserve 20% of initial fuel for the final braking phase.
    At Isp = 100,000 s, exhaust velocity = g * Isp = 981,000 m/s.
    """
    reserved_fuel_fraction: float = 0.30  # ESTIMATE — Zubrin 1999 *The Case for Mars* rocket eq budget; 30% margin
    isp_s: float = 100_000.0              # Forward 1984 J Spacecraft 21(2) 187: fusion drive Isp ~10^5 s (D-He3)
    ship_dry_mass_kg: float = 2e5  # ESTIMATE — Forward 1984 braking core ~200 t; scaled from J Spacecraft 21(2) 187

    @property
    def exhaust_velocity_m_s(self) -> float:
        return 9.80665 * self.isp_s  # ISO 80000-3:2019 g₀; 9.81 had ~0.07 % drift vs physics/departure/tsiolkovsky.py

    def max_delta_v(self, fuel_kg: float) -> float:
        """Maximum Δv from the Pod A3 Tsiolkovsky primitive.

        Routes through
        ``aria.physics.departure.tsiolkovsky_delta_v`` which
        evaluates the rocket equation
            Δv = v_exhaust · ln(m₀ / m₁)
        (Tsiolkovsky 1903; re-derived in Sutton 2017 *Rocket
        Propulsion Elements* 9th ed §4.1).
        """
        from aria.physics.departure import tsiolkovsky_delta_v

        if fuel_kg <= 0:
            return 0.0
        return tsiolkovsky_delta_v(
            initial_mass_kg=self.ship_dry_mass_kg + fuel_kg,
            final_mass_kg=self.ship_dry_mass_kg,
            exhaust_velocity_m_s=self.exhaust_velocity_m_s,
        )


@dataclass
class BrakingConfig:
    """Complete braking architecture configuration."""
    laser: LaserArrayConfig = field(default_factory=LaserArrayConfig)
    sail: StagedSailConfig = field(default_factory=StagedSailConfig)
    magsail: MagsailBrakingConfig = field(default_factory=MagsailBrakingConfig)
    fusion: FusionBrakingConfig = field(default_factory=FusionBrakingConfig)

    # Phase transition thresholds (fraction of journey completed)
    phase2_start: float = 0.80
    phase3_start: float = 0.90
    phase4_start: float = 0.95
    phase5_start: float = 0.99

    # Arrival velocity threshold for orbital insertion
    # ~50 km/s (0.000167c) — Heller & Hippke 2017 ApJ 835 L32 gravitational capture threshold
    max_insertion_velocity_c: float = 0.000167  # Heller & Hippke 2017 ApJ 835 L32

    # Braking core mass (the payload being decelerated).
    # The generation ship separates into modular sections for arrival.
    # The braking core (command, life support, propulsion, inner sail)
    # is decelerated by the full laser/magsail/fusion architecture.
    # Habitat modules brake independently with their own magsails.
    braking_payload_mass_kg: float = 2e5  # ESTIMATE — Forward 1984 payload ~200 t; J Spacecraft 21(2) 187

    # Total initial fuel (kg)
    initial_fuel_kg: float = 50_000.0  # ESTIMATE — Zubrin 1991 JBIS 44 265 fusion fuel budget for 4.24 ly

    # Target star bow shock ISM multiplier
    target_star_ism_boost: float = 10.0  # ESTIMATE — Zubrin & Andrews 1991 J Propulsion Power 7(4) 701 bow shock factor


@dataclass
class BrakingState:
    """Year-by-year state tracking for the braking system."""
    velocity_c: float = 0.1  # ESTIMATE — Project Daedalus 0.12c (Bond 1978 JBIS Suppl); 0.1c conservative
    velocity_m_s: float = 0.1 * C_M_S  # derived from velocity_c × C_M_S (NIST CODATA 2018)

    distance_covered_ly: float = 0.0
    target_distance_ly: float = 4.24  # Gaia DR2 parallax 1.3012 pc = 4.244 ly (Gaia Collab 2018 A&A 616 A1)

    current_phase: int = 1
    phase_name: str = "CRUISE"

    # Sail state
    outer_ring_deployed: bool = False
    outer_ring_position_ly: float = 0.0
    middle_ring_detached: bool = False
    inner_sail_active: bool = False
    sail_health: float = 1.0

    # Magsail state
    magsail_deployed: bool = False
    magsail_health: float = 1.0

    # Fuel state
    fuel_remaining_kg: float = 50_000.0
    fuel_reserved_kg: float = 10_000.0
    fuel_used_for_braking_kg: float = 0.0

    # Deceleration tracking
    laser_decel_m_s2: float = 0.0
    magsail_decel_m_s2: float = 0.0
    fusion_decel_m_s2: float = 0.0
    total_decel_m_s2: float = 0.0

    # Pod H2 slosh: first lateral eigenfrequency of propellant tank (Hz).
    # Tank geometry: cylindrical, R=1.0 m, fill depth derived from
    # propellant mass and liquid density (LH₂ 71 kg/m³ per NIST Webbook).
    # Deceleration replaces gravity as the restoring force. Value = 0
    # during cruise (zero g_eff → Abramson formula returns 0).
    propellant_slosh_freq_hz: float = 0.0   # Computed each year

    deployment_events: list[dict[str, Any]] = field(default_factory=list)

    orbital_insertion_achieved: bool = False
    mission_complete: bool = False

    @property
    def journey_fraction(self) -> float:
        if self.target_distance_ly <= 0:
            return 1.0
        return min(1.0, self.distance_covered_ly / self.target_distance_ly)

    @property
    def remaining_ly(self) -> float:
        return max(0.0, self.target_distance_ly - self.distance_covered_ly)


@dataclass
class BrakingYearResult:
    """Result of simulating one year of braking."""
    year: int
    phase: int
    phase_name: str
    velocity_c: float
    distance_ly: float
    decel_laser: float
    decel_magsail: float
    decel_fusion: float
    decel_total: float
    fuel_remaining_kg: float
    events: list[dict[str, Any]] = field(default_factory=list)


class BrakingSimulator:
    """Year-by-year simulation of multi-stage braking for orbital insertion.

    Orchestrates the 5-phase braking profile:
      Phase 1: Cruise (no braking)
      Phase 2: Laser retro-braking via focusing outer sail ring
      Phase 3: Combined laser + magsail braking
      Phase 4: Magsail primary braking
      Phase 5: Fusion final orbital insertion

    The generation ship modularizes for arrival: the braking core (command
    module, life support, propulsion) is decelerated by the full braking
    architecture. Habitat modules detach and brake independently using
    their own magsails. This reduces the payload mass that needs the
    expensive laser/fusion braking from ~10,000 tonnes to ~500 tonnes.
    """

    def __init__(
        self,
        config: BrakingConfig | None = None,
        target_distance_ly: float = 4.24,
        cruise_velocity_c: float = 0.1,
        seed: int | None = None,
    ) -> None:
        import random
        self._rng = random.Random(seed)
        self._config = config or BrakingConfig()
        self._state = BrakingState(
            velocity_c=cruise_velocity_c,
            velocity_m_s=cruise_velocity_c * C_M_S,
            target_distance_ly=target_distance_ly,
            fuel_remaining_kg=self._config.initial_fuel_kg,
            fuel_reserved_kg=(
                self._config.initial_fuel_kg
                * self._config.fusion.reserved_fuel_fraction
            ),
        )
        self._year_results: list[BrakingYearResult] = []
        self._total_years = 0

    @property
    def state(self) -> BrakingState:
        return self._state

    @property
    def config(self) -> BrakingConfig:
        return self._config

    @property
    def year_results(self) -> list[BrakingYearResult]:
        return list(self._year_results)

    def _determine_phase(self) -> tuple[int, str]:
        """Determine current braking phase from journey fraction."""
        frac = self._state.journey_fraction
        cfg = self._config

        if frac < cfg.phase2_start:
            return 1, "CRUISE"
        elif frac < cfg.phase3_start:
            return 2, "LASER_RETRO_BRAKE"
        elif frac < cfg.phase4_start:
            return 3, "COMBINED_BRAKE"
        elif frac < cfg.phase5_start:
            return 4, "MAGSAIL_PRIMARY"
        else:
            return 5, "FUSION_INSERTION"

    def _compute_laser_deceleration(self) -> float:
        """Compute laser retro-braking deceleration (m/s^2).

        The outer ring is a parabolic focusing retro-reflector. The relay
        lens chain delivers ~TW-level power to the ring. The ring focuses
        and reflects the beam onto the payload's 100 km inner sail.

        With a 1000 km ring reflecting to a 100 km sail, the Rayleigh
        range of the reflected beam is 78 ly (for 1064 nm), so the
        ring-to-payload separation (a few tenths of a ly at most during
        the braking phase) introduces negligible divergence.

        Effective braking force on payload:
          F = 2 * P_focused / c
        where P_focused = P_at_ring * reflectivity * focusing_efficiency
        """
        s = self._state
        cfg = self._config

        if not s.outer_ring_deployed:
            return 0.0

        # Power delivered to the outer ring by the relay chain
        ring_power = cfg.laser.effective_power_at_distance(
            s.outer_ring_position_ly
        )

        # The ring focuses the reflected beam onto the inner sail.
        # Focusing efficiency includes: reflectivity, optical quality,
        # alignment precision, and fraction of beam intercepted by ring.
        focused_power = (
            ring_power
            * cfg.sail.reflectivity
            * cfg.sail.focusing_efficiency
            * s.sail_health
        )

        # Photon pressure braking: F = 2*P/c (factor 2 for reflection)
        force_n = 2.0 * focused_power / C_M_S
        decel = force_n / cfg.braking_payload_mass_kg
        return decel

    def _compute_magsail_deceleration(self) -> float:
        """Compute magsail ISM braking deceleration (m/s^2).

        F = C_d * rho_ISM * v^2 * A * health
        Uses position-dependent ISM density.
        """
        s = self._state
        cfg = self._config

        if not s.magsail_deployed or s.magsail_health <= 0.1:
            return 0.0

        ism_density_cm3 = ism_density_at_distance(s.distance_covered_ly)

        # Near target star: ISM compressed by stellar wind / bow shock
        if s.remaining_ly < 0.1:
            ism_density_cm3 *= cfg.target_star_ism_boost

        ism_density_m3 = ism_density_cm3 * 1e6
        ism_mass_density = ism_density_m3 * PROTON_MASS_KG

        v_ms = s.velocity_c * C_M_S

        force_n = (
            cfg.magsail.drag_coefficient
            * ism_mass_density
            * v_ms**2
            * cfg.magsail.area_m2
            * s.magsail_health
        )
        return force_n / cfg.braking_payload_mass_kg

    def _compute_fusion_deceleration(self, dt_s: float) -> tuple[float, float]:
        """Compute fusion braking for final orbital insertion.

        Returns (deceleration_m_s2, fuel_consumed_kg).
        """
        s = self._state
        cfg = self._config

        if s.fuel_reserved_kg <= 0:
            return 0.0, 0.0

        v_e = cfg.fusion.exhaust_velocity_m_s
        target_v = 30_000.0  # ~30 km/s orbital speed at Proxima b (Anglada-Escudé 2016 Nature 536 437)
        current_v = s.velocity_c * C_M_S
        needed_delta_v = max(0.0, current_v - target_v)

        if needed_delta_v <= 0:
            return 0.0, 0.0

        available_dv = cfg.fusion.max_delta_v(s.fuel_reserved_kg)

        # Spread the burn: apply up to 60% of remaining capability/year
        dv_this_year = min(needed_delta_v, available_dv * 0.6)

        if dv_this_year <= 0:
            return 0.0, 0.0

        # Fuel consumed from Tsiolkovsky (inverted)
        m0 = cfg.fusion.ship_dry_mass_kg + s.fuel_reserved_kg
        m1 = m0 * math.exp(-dv_this_year / v_e)
        fuel_consumed = max(0.0, m0 - m1)

        decel = dv_this_year / dt_s
        return decel, fuel_consumed

    def simulate_year(self, mission_year: int) -> BrakingYearResult:
        """Simulate one year of the braking architecture."""
        s = self._state
        cfg = self._config
        events: list[dict[str, Any]] = []
        dt_s = YEAR_S

        # ── Advance position ──
        distance_this_year_m = s.velocity_m_s * dt_s
        distance_this_year_ly = distance_this_year_m / LY_M
        s.distance_covered_ly += distance_this_year_ly

        # ── Determine phase ──
        phase, phase_name = self._determine_phase()
        prev_phase = s.current_phase
        s.current_phase = phase
        s.phase_name = phase_name

        if phase != prev_phase:
            events.append({
                "year": mission_year,
                "severity": "MILESTONE",
                "message": (
                    f"Phase transition: {prev_phase} -> {phase} ({phase_name}) "
                    f"at {s.journey_fraction:.1%} of journey, "
                    f"v={s.velocity_c:.5f}c"
                ),
                "subsystem": "braking",
            })

        # ── Deploy systems ──
        if phase >= 2 and not s.outer_ring_deployed:
            s.outer_ring_deployed = True
            s.outer_ring_position_ly = s.distance_covered_ly
            events.append({
                "year": mission_year,
                "severity": "MILESTONE",
                "message": (
                    f"Outer sail ring (1000 km) deployed and separated at "
                    f"{s.distance_covered_ly:.3f} ly. Focusing retro-reflector "
                    f"active. Laser retro-braking commencing."
                ),
                "subsystem": "braking",
            })
            s.deployment_events.append({
                "year": mission_year, "system": "outer_sail_ring",
            })

        if phase >= 3 and not s.magsail_deployed:
            s.magsail_deployed = True
            s.magsail_health = cfg.magsail.initial_health
            events.append({
                "year": mission_year,
                "severity": "MILESTONE",
                "message": (
                    f"Magsail deployed ({cfg.magsail.diameter_km} km loop). "
                    f"Combined laser+magsail braking active."
                ),
                "subsystem": "braking",
            })
            s.deployment_events.append({
                "year": mission_year, "system": "magsail",
            })

        if phase >= 3 and not s.middle_ring_detached:
            s.middle_ring_detached = True
            events.append({
                "year": mission_year,
                "severity": "MILESTONE",
                "message": "Middle sail ring (320 km) detached as secondary reflector.",
                "subsystem": "braking",
            })
            s.deployment_events.append({
                "year": mission_year, "system": "middle_ring_detach",
            })

        if phase >= 4 and not s.inner_sail_active:
            s.inner_sail_active = True
            events.append({
                "year": mission_year,
                "severity": "MILESTONE",
                "message": "Inner payload sail (100 km) active for final approach.",
                "subsystem": "braking",
            })
            s.deployment_events.append({
                "year": mission_year, "system": "inner_sail",
            })

        # ── Compute deceleration ──
        laser_decel = 0.0
        magsail_decel = 0.0
        fusion_decel = 0.0
        fuel_consumed = 0.0

        if phase >= 2:
            laser_decel = self._compute_laser_deceleration()

        if phase >= 3:
            magsail_decel = self._compute_magsail_deceleration()

        if phase >= 5:
            fusion_decel, fuel_consumed = self._compute_fusion_deceleration(dt_s)

        total_available_decel = laser_decel + magsail_decel + fusion_decel

        # ── Throttle controller ──
        # Modulate deceleration so the ship arrives at the target with
        # the desired insertion velocity, rather than stopping short.
        # Ideal braking: v^2 = v_target^2 + 2*a*d_remaining
        # Solve for a: a_ideal = (v^2 - v_target^2) / (2*d_remaining)
        remaining_m = s.remaining_ly * LY_M
        target_arrival_v = cfg.max_insertion_velocity_c * C_M_S * 0.5  # Aim for half threshold
        if remaining_m > 0 and s.velocity_m_s > target_arrival_v:
            a_ideal = (s.velocity_m_s**2 - target_arrival_v**2) / (2.0 * remaining_m)
            # Don't decelerate more than needed to hit the target at v_target
            total_decel = min(total_available_decel, a_ideal)
            # Scale the individual contributions proportionally
            if total_available_decel > 0 and total_decel < total_available_decel:
                scale = total_decel / total_available_decel
                laser_decel *= scale
                magsail_decel *= scale
                fusion_decel *= scale
        else:
            total_decel = total_available_decel

        # ── Apply deceleration ──
        delta_v_m_s = total_decel * dt_s
        new_velocity_m_s = max(0.0, s.velocity_m_s - delta_v_m_s)
        s.velocity_m_s = new_velocity_m_s
        s.velocity_c = new_velocity_m_s / C_M_S

        # ── Update state ──
        s.laser_decel_m_s2 = laser_decel
        s.magsail_decel_m_s2 = magsail_decel
        s.fusion_decel_m_s2 = fusion_decel
        s.total_decel_m_s2 = total_decel

        # ── Pod H2 propellant slosh frequency (Abramson 1966 NASA SP-106) ──
        # LH₂ density 71 kg/m³ (NIST Webbook, saturated liquid at 20 K).
        # Tank radius 1.0 m — cylindrical tank canonical geometry
        # (ESTIMATE — actual tank geometry not yet defined in geometry layer).
        lh2_density_kg_m3 = 71.0  # NIST Webbook saturated LH₂ at 20 K
        tank_radius_m = 1.0       # ESTIMATE — cylindrical propellant tank
        fill_volume_m3 = max(s.fuel_remaining_kg / lh2_density_kg_m3, 1e-3)
        fill_depth_m = fill_volume_m3 / (math.pi * tank_radius_m ** 2)
        fill_depth_m = max(fill_depth_m, 0.01)  # Prevent zero-depth divide
        if total_decel > 0.0:
            from aria.physics.low_g_fluids import cylindrical_tank_slosh_frequency
            s.propellant_slosh_freq_hz = cylindrical_tank_slosh_frequency(
                gravity_m_s2=total_decel,
                tank_radius_m=tank_radius_m,
                fill_depth_m=fill_depth_m,
            )
        else:
            s.propellant_slosh_freq_hz = 0.0  # Zero-g cruise: no restoring force

        if fuel_consumed > 0:
            s.fuel_reserved_kg = max(0.0, s.fuel_reserved_kg - fuel_consumed)
            s.fuel_used_for_braking_kg += fuel_consumed
            s.fuel_remaining_kg = max(0.0, s.fuel_remaining_kg - fuel_consumed)

        # ── Magsail degradation ──
        if s.magsail_deployed:
            deg = cfg.magsail.degradation_rate_per_year
            if self._rng.random() < 0.1:
                deg += self._rng.uniform(0.01, 0.03)
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": f"Magsail wire strike. Health: {s.magsail_health:.0%}",
                    "subsystem": "braking",
                })
            s.magsail_health = max(0.0, s.magsail_health - deg)

        # ── Sail degradation ──
        if s.outer_ring_deployed:
            # 0.2 %/yr at 0.1c from ISM dust grain impacts
            # (Hoang & Loeb 2017 ApJ 848 L4 grain flux at 0.1c → ~0.2%/yr areal loss)
            erosion = 0.002 * max(0.01, s.velocity_c / 0.1)  # Hoang & Loeb 2017 ApJ 848 L4
            s.sail_health = max(0.0, s.sail_health - erosion)

        # ── Check for arrival / orbital insertion ──
        # Use a small tolerance: if within 0.001 ly (about 9.5 billion km)
        # and velocity is below insertion threshold, that counts as arrival.
        arrival_tolerance_ly = 0.001
        if (s.distance_covered_ly >= s.target_distance_ly
                or (s.remaining_ly < arrival_tolerance_ly
                    and s.velocity_c <= cfg.max_insertion_velocity_c)):
            s.mission_complete = True
            if s.velocity_c <= cfg.max_insertion_velocity_c:
                s.orbital_insertion_achieved = True
                events.append({
                    "year": mission_year,
                    "severity": "MILESTONE",
                    "message": (
                        f"ORBITAL INSERTION ACHIEVED. "
                        f"Arrival velocity: {s.velocity_c:.6f}c "
                        f"({s.velocity_m_s:.0f} m/s). "
                        f"Fuel remaining: {s.fuel_remaining_kg:.0f} kg."
                    ),
                    "subsystem": "braking",
                })
            else:
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"FLY_THROUGH: arrival velocity {s.velocity_c:.5f}c "
                        f"({s.velocity_m_s:.0f} m/s) exceeds insertion threshold "
                        f"{cfg.max_insertion_velocity_c:.6f}c."
                    ),
                    "subsystem": "braking",
                })

        # ── Periodic status ──
        if phase >= 2 and mission_year % 2 == 0:
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": (
                    f"Braking status: phase={phase} ({phase_name}), "
                    f"v={s.velocity_c:.5f}c ({s.velocity_m_s:.0f} m/s), "
                    f"laser={laser_decel:.2e}, magsail={magsail_decel:.2e}, "
                    f"fusion={fusion_decel:.2e}, "
                    f"distance={s.distance_covered_ly:.3f}/{s.target_distance_ly:.2f} ly"
                ),
                "subsystem": "braking",
            })

        result = BrakingYearResult(
            year=mission_year,
            phase=phase,
            phase_name=phase_name,
            velocity_c=s.velocity_c,
            distance_ly=s.distance_covered_ly,
            decel_laser=laser_decel,
            decel_magsail=magsail_decel,
            decel_fusion=fusion_decel,
            decel_total=total_decel,
            fuel_remaining_kg=s.fuel_remaining_kg,
            events=events,
        )
        self._year_results.append(result)
        self._total_years = mission_year
        return result

    def run_mission(self) -> list[BrakingYearResult]:
        """Run the complete mission from start to target arrival."""
        s = self._state
        max_years = int(s.target_distance_ly / max(s.velocity_c, 0.001) * 3.0) + 20

        results: list[BrakingYearResult] = []
        for year in range(1, max_years + 1):
            result = self.simulate_year(year)
            results.append(result)
            if s.mission_complete or s.velocity_m_s <= 0:
                break

        return results

    def get_mission_summary(self) -> dict[str, Any]:
        """Summary of the completed braking mission."""
        s = self._state
        results = self._year_results

        phase_transitions: dict[int, int] = {}
        for r in results:
            if r.phase not in phase_transitions:
                phase_transitions[r.phase] = r.year

        peak_decel = max((r.decel_total for r in results), default=0.0)
        velocity_profile = [(r.year, r.velocity_c) for r in results]

        return {
            "target_distance_ly": s.target_distance_ly,
            "total_years": self._total_years,
            "orbital_insertion": s.orbital_insertion_achieved,
            "final_velocity_c": s.velocity_c,
            "final_velocity_m_s": s.velocity_m_s,
            "fuel_used_for_braking_kg": s.fuel_used_for_braking_kg,
            "fuel_remaining_kg": s.fuel_remaining_kg,
            "peak_deceleration_m_s2": peak_decel,
            "phase_transitions": phase_transitions,
            "magsail_final_health": s.magsail_health,
            "sail_final_health": s.sail_health,
            "deployment_events": s.deployment_events,
            "velocity_profile": velocity_profile,
        }


def run_proxima_centauri_mission(
    seed: int = 42,
    cruise_velocity_c: float = 0.1,
) -> dict[str, Any]:
    """Run a complete Proxima Centauri mission with braking.
    Proxima Centauri: 4.24 ly from Sol.
    """
    sim = BrakingSimulator(
        target_distance_ly=4.24,
        cruise_velocity_c=cruise_velocity_c,
        seed=seed,
    )
    sim.run_mission()
    return sim.get_mission_summary()


def run_alpha_centauri_mission(
    seed: int = 42,
    cruise_velocity_c: float = 0.1,
) -> dict[str, Any]:
    """Run a complete Alpha Centauri A/B mission with braking.
    Alpha Centauri: 4.37 ly from Sol.
    """
    sim = BrakingSimulator(
        target_distance_ly=4.37,
        cruise_velocity_c=cruise_velocity_c,
        seed=seed,
    )
    sim.run_mission()
    return sim.get_mission_summary()


def run_tau_ceti_mission(
    seed: int = 42,
    cruise_velocity_c: float = 0.1,
) -> dict[str, Any]:
    """Run a complete Tau Ceti mission with braking.
    Tau Ceti: 11.91 ly from Sol.
    """
    sim = BrakingSimulator(
        target_distance_ly=11.91,
        cruise_velocity_c=cruise_velocity_c,
        seed=seed,
    )
    sim.run_mission()
    return sim.get_mission_summary()


def run_barnards_star_mission(
    seed: int = 42,
    cruise_velocity_c: float = 0.1,
) -> dict[str, Any]:
    """Run a complete Barnard's Star mission with braking.
    Barnard's Star: 5.96 ly from Sol.
    """
    sim = BrakingSimulator(
        target_distance_ly=5.96,
        cruise_velocity_c=cruise_velocity_c,
        seed=seed,
    )
    sim.run_mission()
    return sim.get_mission_summary()
