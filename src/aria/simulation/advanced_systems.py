"""Advanced Generation Ship Systems — Engineering the Impossible.

Five mission-critical systems that make interstellar travel survivable.
Each is grounded in real research with quantitative degradation models.

SYSTEM 1: ACTIVE RADIATION SHIELDING
  Superconducting MgB2 magnet coils (CERN SR2S project) deflect 90%+ of
  charged particles (GCR + SPE). Electrostatic field handles positive ions.
  Passive backup: water tanks + polyethylene (10,000 kg).
  Combined active+passive = 95%+ radiation reduction.
  Reference: CERN SR2S, NASA MAARSS study

SYSTEM 2: ARTIFICIAL GRAVITY (O'Neill Cylinder)
  Rotating habitat: 500m radius, 1 RPM = ~0.56g centripetal acceleration.
  Prevents bone loss (1-2%/month in zero-G), muscle atrophy, cardiovascular
  deconditioning. Coriolis effects at head height calculable from omega*v.
  Bearing degradation is the century-scale bottleneck.
  Reference: O'Neill (1977), Stanford Torus study (1975)

SYSTEM 3: NUCLEAR FISSION REACTOR (Kilopower/MegaPower)
  2 MW fission reactor, heatpipe cooled, 3 tonnes LEU (16-19% enriched).
  Core replacement every 30 years from spare fuel rods. Backup: RTGs
  (Pu-238, t_half=87.7 yr). Tertiary: fusion reactor (existing sim).
  Reference: NASA Kilopower/KRUSTY (2018), MegaPower concept (LANL)

SYSTEM 4: DEEP SPACE LASER COMMUNICATION
  10W laser transmitter at 1550nm (near-infrared). Data rate follows
  inverse-square law. At 1 ly: bits/second; at 10 ly: effectively zero.
  Quantum key distribution within range. Store-and-forward messaging.
  One-way light delay: distance_ly * 1 year.
  Reference: NASA DSOC (Psyche mission, 2023-2024)

SYSTEM 5: WASTE PROCESSING & CLOSED-LOOP RECYCLING
  Pyrolysis (500-900C), Sabatier reaction (CO2+4H2 -> CH4+2H2O),
  electrolysis (H2O -> H2+O2), urine processing (93% recovery).
  Target: 98%+ mass closure per cycle.
  Reference: ISS ECLSS, NASA WRS, ESA MELiSSA project
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class SystemSeverity(Enum):
    """Event severity levels for all advanced systems."""
    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


# ════════════════════════════════════════════════════════════════
#  1. ACTIVE RADIATION SHIELDING
#     CERN SR2S project, NASA MAARSS study
# ════════════════════════════════════════════════════════════════

@dataclass
class RadiationShieldState:
    """Active + passive radiation shielding state.

    Active shielding: superconducting MgB2 magnet coils generate a
    magnetic dipole that deflects charged particles (GCR protons,
    helium nuclei, SPE flux). Operating temperature ~25K requires
    cryocooler power. Electrostatic field deflects remaining ions.

    Passive shielding: water tanks (hydrogen-rich, excellent neutron
    moderator) + polyethylene blocks around crew quarters.

    Combined: 95%+ reduction in biological dose equivalent.

    Reference:
      - CERN SR2S: doi:10.1016/j.lssr.2015.01.002
      - NASA MAARSS: NASA/TM-2005-213688
    """
    # Active: superconducting magnets
    magnet_coil_count: int = 6             # ESTIMATE — 6-coil toroidal array (Battiston 2015 CERN SR2S)
    coil_health: list[float] = field(default_factory=lambda: [1.0] * 6)
    operating_temp_k: float = 25.0        # MgB2 Tc = 39 K (Nagamatsu 2001 Nature 410 63); operate at 25 K
    critical_temp_k: float = 39.0         # Nagamatsu 2001 Nature 410 63: MgB2 Tc = 39 K
    magnetic_field_strength_t: float = 1.5  # ESTIMATE — CERN SR2S prototype 1-2 T bore field (Battiston 2015)
    magnet_deflection_efficiency: float = 0.90  # ESTIMATE — CERN SR2S (doi:10.1016/j.lssr.2015.01.002)
    cryocooler_health: float = 1.0
    cryocooler_power_kw: float = 50.0     # ESTIMATE — ~50 kW to maintain 25 K at multi-tonne MgB2 scale (Batiston 2015)
    quench_events_total: int = 0
    quench_recovery_time_days: float = 7.0  # ESTIMATE — LHC magnet quench recovery: 3-14 days (Mess 1996 CERN 96-03)

    # Active: electrostatic field
    # 10 MV sphere potential for GCR proton deflection (Spillantini 2010
    # *Adv Space Res* 45 900: electrostatic active shielding >10 MV needed
    # for >1 GeV/nucleon primary GCR suppression).
    electrostatic_voltage_mv: float = 10.0   # Spillantini 2010 Adv Space Res 45 900
    electrostatic_health: float = 1.0
    # 20 kW maintains 10 MV on a conducting sphere of radius R_eff via
    # leakage current compensation (ESTIMATE — no operational data;
    # Winglee 2000 *J Geophys Res* 105 21067 plasma magnet analogue).
    electrostatic_power_kw: float = 20.0  # ESTIMATE — Winglee 2000 J Geophys Res analogue

    # Passive: water + polyethylene
    water_shield_mass_kg: float = 7000.0   # ESTIMATE — 7 t water around crew hab (~10 g/cm² areal density)
    polyethylene_mass_kg: float = 3000.0   # ESTIMATE — 3 t PE supplemental shielding (Cucinotta 2006 Radiat Res 166 809)
    passive_reduction_factor: float = 0.50  # Cucinotta 2006 Radiat Res 166 809 Fig.3: 10 g/cm² Al-eq → 50% dose reduction

    # Water radiolysis (Pod J2 — Elliot & Bartels 2009 Spinks & Woods 1990).
    # Tracks H₂ outgassing from the water-shield compartment at the
    # local GCR dose rate (G(H₂) ≈ 0.45 molec/100 eV low-LET).
    h2_outgas_mol_s: float = 0.0
    h2_cumulative_mol: float = 0.0

    # Combined metrics
    total_dose_reduction: float = 0.95     # Combined active magnetic (Spillantini 2010) + passive 10 g/cm²
    cumulative_crew_dose_sv: float = 0.0   # Sieverts accumulated
    # Unshielded annual crew dose at 1 AU sourced from the Pod E2
    # transport primitive gcr_annual_unshielded_dose() which
    # evaluates Cucinotta 2014 NASA/TP-2013-217375 Table 5-1
    # (0.42 Sv/yr solar min, 0.21 Sv/yr solar max). Default uses
    # the solar-min value for conservative bookkeeping.
    gcr_annual_unshielded_sv: float = 0.42
    spe_events_total: int = 0


class RadiationShieldSimulator:
    """Simulates active + passive radiation shielding over centuries.

    The superconducting magnets are the workhorse but require constant
    cryogenic cooling. A quench (sudden loss of superconductivity) is
    recoverable but leaves the crew exposed during recovery.

    GCR (Galactic Cosmic Rays): constant ~0.6 Sv/year unshielded.
    SPE (Solar Particle Events): rare but intense bursts. Decrease
    with distance from Sol — negligible beyond ~2 AU.

    Career dose limit (NASA): 1 Sv. Without shielding, exceeded in <2 years.
    With 95% shielding: 0.03 Sv/year → 33 years to reach 1 Sv.
    """

    def __init__(
        self,
        seed: int | None = None,
        solar_modulation_mv: float | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.state = RadiationShieldState()
        # Override the default gcr_annual_unshielded_sv with the
        # Pod E2 transport primitive's Cucinotta 2014 evaluation
        # so any future update to the primitive propagates here.
        from aria.physics.transport import gcr_annual_unshielded_dose

        if solar_modulation_mv is not None:
            self.state.gcr_annual_unshielded_sv = gcr_annual_unshielded_dose(
                phi_sm_mv=solar_modulation_mv
            )
        else:
            self.state.gcr_annual_unshielded_sv = gcr_annual_unshielded_dose()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # Cryocooler mechanical degradation (Stirling cycle).
        # MIL-HDBK-217F Notice 2 Section 12.1 p.12-2 gives
        # λ = 10.3 failures/10⁶ hr for a general-purpose motor
        # (0.090 failures/yr). Ross 2004 *Cryogenics* 44 509
        # reports a ~9× higher bearing-limited rate for Stirling
        # cryocooler compressors vs general motors, giving an
        # effective ~0.8 %/yr health decrement. The max() clamp
        # keeps the simulator well-posed after full wear-out.
        s.cryocooler_health = max(0.0, s.cryocooler_health - 0.008)

        # If cryocooler degrades, operating temp rises
        if s.cryocooler_health < 0.5:
            temp_rise = (1.0 - s.cryocooler_health) * 20.0  # Up to +20K
            s.operating_temp_k = 25.0 + temp_rise
        else:
            s.operating_temp_k = 25.0 + (1.0 - s.cryocooler_health) * 5.0

        # ── Quench check ──
        # If operating temp approaches Tc, risk of quench increases
        margin = s.critical_temp_k - s.operating_temp_k
        quench_probability = 0.0
        if margin < 5.0:
            quench_probability = (5.0 - margin) / 5.0 * 0.3  # Up to 30%
        if margin <= 0:
            quench_probability = 1.0  # Guaranteed quench

        if self._rng.random() < quench_probability:
            s.quench_events_total += 1
            # Quench damages the coil that quenched
            quench_coil = self._rng.randint(0, s.magnet_coil_count - 1)
            damage = self._rng.uniform(0.05, 0.15)
            s.coil_health[quench_coil] = max(0.0, s.coil_health[quench_coil] - damage)

            # Individual quench events are WARNING (each is one incident).
            # A separate latched CRITICAL fires the first time the cumulative
            # quench count crosses the design threshold.
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": (
                    f"Magnet quench event #{s.quench_events_total} on coil {quench_coil}. "
                    f"Operating temp {s.operating_temp_k:.1f}K (Tc={s.critical_temp_k}K). "
                    f"Recovery: {s.quench_recovery_time_days:.0f} days. "
                    f"Coil health: {s.coil_health[quench_coil]:.0%}"
                ),
                "subsystem": "radiation_shielding",
            })
            if s.quench_events_total > 3 and not getattr(self, "_quench_burst_latched", False):
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"Quench event rate exceeds design threshold "
                        f"({s.quench_events_total} total). Magnet reliability margin eroding."
                    ),
                    "subsystem": "radiation_shielding",
                })
                self._quench_burst_latched = True

        # ── Magnet coil degradation (thermal cycling, radiation damage) ──
        for i in range(s.magnet_coil_count):
            s.coil_health[i] = max(0.0, s.coil_health[i] - 0.002)

        # ── Calculate active shielding effectiveness ──
        operational_coils = sum(1 for h in s.coil_health if h > 0.1)
        avg_coil_health = sum(s.coil_health) / s.magnet_coil_count
        # Deflection scales with number of operational coils and their health
        s.magnet_deflection_efficiency = min(
            0.90, 0.90 * (operational_coils / s.magnet_coil_count) * avg_coil_health
        )

        # ── Electrostatic field degradation ──
        s.electrostatic_health = max(0.0, s.electrostatic_health - 0.005)
        electrostatic_eff = 0.10 * s.electrostatic_health  # Up to 10% extra

        # ── Passive shielding: water can be consumed, PE is stable ──
        # Small water loss to life support leakage.
        s.water_shield_mass_kg = max(0.0, s.water_shield_mass_kg - 5.0)

        # Convert water + polyethylene mass to effective Al-equivalent
        # areal density for the Cucinotta 2014 shielded-dose helper.
        # Both water (H=11 wt%) and PE (H=14 wt%) are much better
        # neutron moderators than Al per unit mass — Slaba 2013
        # NASA/TP-2013-217390 §3.2 gives the dose-equivalence
        # factors: water ≈ 1.35× Al, PE ≈ 1.52× Al. Spread over a
        # 50 m² crew-quarters surface area gives the areal density.
        crew_quarters_area_m2 = 50.0
        water_al_equiv_kg = 1.35 * s.water_shield_mass_kg
        pe_al_equiv_kg = 1.52 * s.polyethylene_mass_kg
        # kg → g, m² → cm² (10000 cm²/m²)
        passive_areal_g_cm2 = (
            (water_al_equiv_kg + pe_al_equiv_kg) * 1000.0
            / (crew_quarters_area_m2 * 10000.0)
        )

        # Passive dose reduction via the Pod E2 Cucinotta 2014
        # engineering model.
        from aria.physics.transport import cucinotta_shielded_dose

        passive_shielded_dose_unit = cucinotta_shielded_dose(
            unshielded_dose_sv_yr=1.0,
            shield_depth_g_cm2=passive_areal_g_cm2,
        )
        s.passive_reduction_factor = 1.0 - passive_shielded_dose_unit

        # ── Combined dose reduction ──
        # Cucinotta 2014 stiff-spectrum HZE floor: even an infinitely
        # thick passive shield cannot reduce the dose below 35 % of
        # unshielded (cucinotta_shielded_dose asymptotes at 0.35).
        # The active magnetic deflector handles the charged component
        # that the passive shield cannot block; the electrostatic
        # grid contributes a small additional fraction on the low-
        # energy tail.
        s.electrostatic_health = max(0.0, s.electrostatic_health - 0.005)
        electrostatic_eff_fraction = 0.10 * s.electrostatic_health
        active_pass_through = max(0.30, 1.0 - s.magnet_deflection_efficiency)
        electro_pass_through = max(0.95, 1.0 - electrostatic_eff_fraction * 0.5)
        combined_pass = (
            active_pass_through
            * electro_pass_through
            * passive_shielded_dose_unit
        )
        # Cap at 65 % dose reduction (Cucinotta 2014 realistic
        # ceiling for GCR at PDR tech level).
        s.total_dose_reduction = min(0.65, 1.0 - combined_pass)

        # ── Annual crew dose ──
        annual_dose = s.gcr_annual_unshielded_sv * (1.0 - s.total_dose_reduction)
        s.cumulative_crew_dose_sv += annual_dose

        # ── Water-shield radiolysis (Pod J2) ──
        # The dose that's absorbed in the water (not deflected) drives
        # H₂ generation via Spinks & Woods 1990 G(H₂) ≈ 0.45 molec/100
        # eV. Convert Sv/year → Gy/s (assume Q=1 for GCR for the
        # low-LET approximation — J2 has an LET-weighted version for
        # heavier species but this is the low-LET floor).
        if s.water_shield_mass_kg > 0.0:
            from aria.physics.radchem import hydrogen_outgas_rate_mol_s

            water_volume_m3 = s.water_shield_mass_kg / 997.0
            dose_rate_gy_s = s.gcr_annual_unshielded_sv / (365.25 * 86400.0)
            s.h2_outgas_mol_s = hydrogen_outgas_rate_mol_s(
                dose_rate_gy_s=dose_rate_gy_s,
                water_volume_m3=water_volume_m3,
            )
            s.h2_cumulative_mol += s.h2_outgas_mol_s * (365.25 * 86400.0)

        # ── SPE events (decrease with distance from Sol) ──
        # NASA: ~4.3 major SPE events per 11-year solar cycle → ~0.39/yr near 1 AU
        # (Shea & Smart 2012, "Space Weather and Particle Events", Adv. Space Res.)
        # SPE flux falls as 1/r² from Sol; beyond ~1 ly, negligible
        distance_ly = mission_year * 0.1
        spe_probability = max(0.0, 0.39 * math.exp(-distance_ly / 0.01))
        if self._rng.random() < spe_probability:
            s.spe_events_total += 1
            # SPE dose: 0.01-0.5 Sv unshielded (Cucinotta 2014, Oct 1989 event = 0.46 Sv)
            spe_dose = self._rng.uniform(0.01, 0.46) * (1.0 - s.total_dose_reduction)
            s.cumulative_crew_dose_sv += spe_dose
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": (
                    f"Solar particle event detected. Additional dose: {spe_dose:.3f} Sv "
                    f"(shielded). Cumulative: {s.cumulative_crew_dose_sv:.2f} Sv"
                ),
                "subsystem": "radiation_shielding",
            })

        # ── Cryocooler replacement (latched) ──
        if s.cryocooler_health < 0.2 and not getattr(self, "_cryo_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": (
                    f"Cryocooler health {s.cryocooler_health:.0%} — superconducting magnets "
                    f"at risk. Operating temp {s.operating_temp_k:.1f}K. "
                    "Schedule cryocooler rebuild from spares."
                ),
                "subsystem": "radiation_shielding",
            })
            self._cryo_low_latched = True
        elif s.cryocooler_health >= 0.3:
            self._cryo_low_latched = False

        # ── Dose alert (tier-latched: each Sv threshold fires once) ──
        # Career dose grows monotonically, so naive ">0.5" refires every year.
        # Report milestones at 0.5, 1.0, 2.0, 5.0 Sv instead.
        if not hasattr(self, "_dose_tier_reported"):
            self._dose_tier_reported = 0
        dose = s.cumulative_crew_dose_sv
        next_tier = (0.5, 1.0, 2.0, 5.0)
        for i, thr in enumerate(next_tier, start=1):
            if dose >= thr and self._dose_tier_reported < i:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING" if thr < 1.0 else "CRITICAL",
                    "message": (
                        f"Cumulative crew radiation dose passed {thr:.1f} Sv "
                        f"(now {dose:.2f} Sv). NASA career limit: 1.0 Sv. "
                        f"Shield effectiveness: {s.total_dose_reduction:.0%}"
                    ),
                    "subsystem": "radiation_shielding",
                })
                self._dose_tier_reported = i

        # ── Coil failure alert (latched per coil count transition) ──
        if operational_coils < 4 and getattr(self, "_last_coil_report", 99) != operational_coils:
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY" if operational_coils < 2 else "CRITICAL",
                "message": (
                    f"Only {operational_coils}/{s.magnet_coil_count} magnet coils operational. "
                    f"Deflection efficiency: {s.magnet_deflection_efficiency:.0%}. "
                    "Crew should shelter in passive-shielded zones."
                ),
                "subsystem": "radiation_shielding",
            })
            self._last_coil_report = operational_coils
        elif operational_coils >= 4:
            self._last_coil_report = 99

        return events

    def reset_cryocooler(self) -> None:
        """Simulate cryocooler rebuild/replacement from spares."""
        self.state.cryocooler_health = 0.95
        self.state.operating_temp_k = 25.0


# ════════════════════════════════════════════════════════════════
#  2. ARTIFICIAL GRAVITY — O'Neill Cylinder
#     Reference: O'Neill (1977), Stanford Torus (1975)
# ════════════════════════════════════════════════════════════════

@dataclass
class ArtificialGravityState:
    """Rotating habitat section for centripetal artificial gravity.

    Physics:
      a = omega^2 * r
      omega = 2*pi*RPM/60
      At r=500m, 1 RPM: omega = 0.1047 rad/s, a = 5.48 m/s^2 = 0.56g

    Coriolis acceleration on a moving object:
      a_cor = 2 * omega * v
      At head height (2m above floor), walking at 1.5 m/s:
      a_cor = 2 * 0.1047 * 1.5 = 0.314 m/s^2 (~3.2% of g)
      Noticeable but tolerable at 1 RPM, debilitating above 2 RPM.

    Reference:
      - O'Neill, G.K. (1977) "The High Frontier"
      - NASA SP-413: Space Settlements: A Design Study (1975)
    """
    radius_m: float = 500.0          # NASA SP-413 §4: 500 m radius O'Neill cylinder baseline
    rpm: float = 1.0                 # NASA SP-413 §4: 1 RPM → 0.56g at 500 m (above 0.5g health threshold)
    omega_rad_s: float = 0.0         # Computed from RPM
    centripetal_g: float = 0.0       # Computed: omega^2 * r / 9.81
    coriolis_at_head_ms2: float = 0.0  # At 2m height, 1.5 m/s walk

    # Structural
    bearing_health: float = 1.0      # Main rotation bearings
    bearing_count: int = 4           # ESTIMATE — 4 redundant main bearings (O'Neill 1977 §7)
    bearing_individual: list[float] = field(default_factory=lambda: [1.0] * 4)
    structural_integrity: float = 1.0  # Cylinder structure
    seal_health: float = 1.0         # Rotating seal (atmosphere retention)

    # Power
    # Spin-up energy: E = 0.5 * I * ω² = 0.5 * 5e7 * 500² * (2π/60)² ≈ 690 GJ → 500 kW for ~16 days
    spin_up_power_kw: float = 500.0  # ESTIMATE — kinetic energy budget for 500 m, 1 RPM ring
    # Maintenance power: overcoming magnetic-bearing drag (~10 kW ESTIMATE — analogous to ISS CDRA)
    maintenance_power_kw: float = 10.0  # ESTIMATE — magnetic bearing drag compensation

    # Coriolis-illusion angular acceleration magnitude from the
    # Pod C2 vestibular cross-coupling primitive for a 1 rad/s
    # head tilt about an axis orthogonal to the ring spin. Values
    # above ~0.1 rad/s² produce overt motion sickness in 50 % of
    # naive subjects per Young 1986 NASA TM-88328 (SDTC data).
    coriolis_illusion_alpha_rad_s2: float = 0.0

    # Pod C4 dual-spin gyroscopic reaction torque (N·m).
    # When the ship slews at ship_slew_rate_rad_s about an axis
    # perpendicular to the ring spin axis, the ring's angular
    # momentum (I_∥ ω_ring) reacts on the non-rotating hull via
    # τ_gyro = Ω_bus × L_ring  (Wie 1998 §7.3).
    #
    # Ring inertia (thin-ring approx): I = M_ring * R²
    # M_ring = 5e7 kg — habitat shell + interior for 1000-person
    # O'Neill cylinder per NASA SP-413 Table 4-1 mass estimates.
    ring_mass_kg: float = 5.0e7       # NASA SP-413 Table 4-1
    gyroscopic_reaction_torque_nm: float = 0.0  # Computed in _update_physics

    # Pod C3 torque-free precession rate (rad/s).
    # When the spin axis is perturbed, the habitat ring precesses as
    # a torque-free symmetric top at Ω_p = (I∥-I⊥)/I⊥ × ω_spin
    # (Goldstein 2002 §5.7). For a thin-walled O'Neill cylinder:
    #   I∥  = M R²
    #   I⊥  = M(R²/2 + L²/12), L = 2R (NASA SP-413 L/D ≈ 1 proportion)
    #   → (I∥-I⊥)/I⊥ = (R²/2 - L²/12)/(R²/2 + L²/12)
    # With L=2R: (0.5 - 4/12)/(0.5 + 4/12) = (0.5-0.333)/(0.5+0.333) = 0.2
    # so Ω_p ≈ 0.2 ω_spin — a stable oblate rotator.
    ring_length_m: float = 1000.0    # NASA SP-413 Table 4-1 L/D ≈ 1, R=500m
    ring_precession_rate_rad_s: float = 0.0  # Computed in _update_physics

    # Health effects tracking
    bone_density_retention: float = 1.0   # 1.0 = Earth-normal
    muscle_mass_retention: float = 1.0
    cardiovascular_health: float = 1.0

    # Degradation counters
    years_operational: int = 0
    bearing_replacements: int = 0
    emergency_stops: int = 0


class ArtificialGravitySimulator:
    """Simulates O'Neill cylinder rotation for artificial gravity.

    The habitat section rotates to produce centripetal acceleration
    perceived as gravity by inhabitants. At 500m radius and 1 RPM,
    this produces 0.56g — enough to prevent the worst physiological
    effects of zero-G while keeping Coriolis effects tolerable.

    The century-scale challenge is bearing wear. Main bearings support
    the entire rotating mass and operate continuously for centuries.
    Even with magnetic bearings, degradation is inevitable.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = ArtificialGravityState()
        self._update_physics()

    def _update_physics(self) -> None:
        """Recalculate derived physics from RPM and radius."""
        import numpy as np

        from aria.physics.vestibular import cross_coupled_angular_acceleration

        s = self.state
        s.omega_rad_s = 2.0 * math.pi * s.rpm / 60.0
        s.centripetal_g = (s.omega_rad_s ** 2 * s.radius_m) / 9.81
        # Coriolis at head height (2 m), walking speed 1.5 m/s.
        s.coriolis_at_head_ms2 = 2.0 * s.omega_rad_s * 1.5
        # Pod C2 Coriolis-illusion angular acceleration for a 1 rad/s
        # head tilt orthogonal to the ring spin axis (Guedry &
        # Benson 1978 *Aviat Space Environ Med* 49(1) 29).
        omega_ring = np.array([0.0, 0.0, s.omega_rad_s])
        omega_head = np.array([1.0, 0.0, 0.0])  # canonical head tilt
        alpha_cross = cross_coupled_angular_acceleration(omega_ring, omega_head)
        s.coriolis_illusion_alpha_rad_s2 = float(np.linalg.norm(alpha_cross))

        # Pod C4 gyroscopic reaction torque (Wie 1998 §7.3).
        # I_parallel = M_ring * R²  (thin-ring, spin-axis parallel, Goldstein 2002 §5.6)
        i_parallel = s.ring_mass_kg * s.radius_m ** 2
        l_ring = np.array([0.0, 0.0, i_parallel * s.omega_rad_s])  # ring angular momentum
        # Canonical attitude maneuver: 0.1 deg/s (1.745e-3 rad/s) about the x-axis.
        # Representative slew for an interstellar course correction
        # (ESTIMATE — no published standard; conservative navigation budget value).
        ship_slew_rad_s = 1.745e-3  # ESTIMATE — 0.1 deg/s canonical maneuver rate
        omega_bus = np.array([ship_slew_rad_s, 0.0, 0.0])
        from aria.physics.attitude import gyroscopic_reaction_torque
        tau_gyro = gyroscopic_reaction_torque(
            bus_angular_velocity_rad_s=omega_bus,
            ring_angular_momentum_bus_frame=l_ring,
        )
        s.gyroscopic_reaction_torque_nm = float(np.linalg.norm(tau_gyro))

        # Pod C3 torque-free precession of the ring spin axis
        # (Goldstein 2002 §5.7; Landau-Lifshitz Mechanics §33).
        # O'Neill cylinder modelled as a hollow thin-wall cylinder:
        #   I∥ = M R²
        #   I⊥ = M (R²/2 + L²/12)   (axis through CoM, perpendicular to spin)
        i_perp = s.ring_mass_kg * (s.radius_m ** 2 / 2 + s.ring_length_m ** 2 / 12)
        from aria.physics.rigid_body import torque_free_precession_rate
        s.ring_precession_rate_rad_s = torque_free_precession_rate(
            I_parallel_kg_m2=i_parallel,
            I_perpendicular_kg_m2=i_perp,
            spin_rate_rad_s=s.omega_rad_s,
        )

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state
        s.years_operational += 1

        self._update_physics()

        # ── Bearing degradation ──
        # Main bearings: ~0.1% per year under continuous load
        # Accelerated by vibration, thermal cycling, particulate contamination
        for i in range(s.bearing_count):
            wear_rate = 0.001 + self._rng.uniform(0.0, 0.0005)
            # Older bearings wear faster (fatigue accumulation)
            if s.bearing_individual[i] < 0.5:
                wear_rate *= 2.0
            s.bearing_individual[i] = max(0.0, s.bearing_individual[i] - wear_rate)

        # Overall bearing health = worst bearing (weakest link)
        s.bearing_health = min(s.bearing_individual)

        # ── Bearing replacement at 20% health ──
        for i in range(s.bearing_count):
            if s.bearing_individual[i] < 0.2:
                # Replace bearing (requires temporary spin-down of that section)
                s.bearing_individual[i] = 0.95
                s.bearing_replacements += 1
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": (
                        f"Bearing assembly {i} replaced (#{s.bearing_replacements} total). "
                        f"Temporary gravity reduction during maintenance."
                    ),
                    "subsystem": "artificial_gravity",
                })

        s.bearing_health = min(s.bearing_individual)

        # ── Seal degradation ──
        # Rotating seals between habitat and non-rotating sections
        s.seal_health = max(0.0, s.seal_health - 0.003)
        if s.seal_health < 0.3:
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": (
                    f"Rotating seal health {s.seal_health:.0%} — atmosphere leakage increasing. "
                    "Schedule seal replacement."
                ),
                "subsystem": "artificial_gravity",
            })
            # Replace seal
            if s.seal_health < 0.15:
                s.seal_health = 0.90
                events.append({
                    "year": mission_year,
                    "severity": "NOMINAL",
                    "message": "Rotating seal replaced. Atmosphere retention restored.",
                    "subsystem": "artificial_gravity",
                })

        # ── Structural integrity ──
        # Centripetal stress on cylinder walls is continuous
        # Fatigue cracks develop over centuries
        s.structural_integrity = max(0.5, s.structural_integrity - 0.0005)

        # ── RPM adjustment for bearing health ──
        # If bearings are degraded, reduce RPM to reduce load
        if s.bearing_health < 0.4:
            s.rpm = max(0.5, s.rpm * 0.99)  # Slowly reduce RPM
            self._update_physics()
            if s.centripetal_g < 0.3:
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"Gravity reduced to {s.centripetal_g:.2f}g due to bearing degradation. "
                        f"Bone loss risk increasing. RPM: {s.rpm:.2f}"
                    ),
                    "subsystem": "artificial_gravity",
                })

        # ── Cardiovascular health effects (routes through Pod K2) ──
        # Uses aria.physics.cardio.plasma_volume_fraction and
        # cardiac_mass_retention, which are closed-form analytic
        # compartment models fitted to Convertino 1996, Perhonen
        # 2001, and Pavy-Le Traon 2007 HDT bed-rest data. The
        # fraction (1 - g/g0) scales the decrement, so a 0.56g
        # habitat sees exactly 44 % of the 0g decrement at steady
        # state.
        from aria.physics.cardio import (
            cardiac_mass_retention,
            plasma_volume_fraction,
        )

        local_g_m_s2 = s.centripetal_g * 9.80665
        cumulative_time_days = float(s.years_operational) * 365.25
        cumulative_time_hours = cumulative_time_days * 24.0

        # Plasma volume fraction from Convertino 1996 biphasic fit.
        pv_fraction = plasma_volume_fraction(
            time_hours=cumulative_time_hours, local_g_m_s2=local_g_m_s2
        )
        # Cardiac mass retention from Perhonen 2001 first-order
        # atrophy (21-day time constant, 10 % asymptote at 0g).
        cardiac_retention = cardiac_mass_retention(
            time_days=cumulative_time_days, local_g_m_s2=local_g_m_s2
        )
        # Report cardiovascular_health as the geometric mean of the
        # two retention fractions — a handbook-style composite that
        # collapses the two to a single 0..1 number for the engine.
        s.cardiovascular_health = math.sqrt(pv_fraction * cardiac_retention)
        # Bone and muscle retention: Frost 1987 mechanostat threshold
        # model. Centrifuge animal data (Wronski 1980, Turner 2009)
        # and Mars-analog bed-rest studies show a threshold around
        # 0.5g above which mechanical loading is sufficient to
        # maintain bone density. Below the threshold the Sibonga
        # 2007 *Bone* 41 973 microgravity rate applies (1-2 %/month
        # bone, 2-3 %/month muscle at 0g), scaled linearly by the
        # (threshold - g) / threshold deficit.
        g_threshold = 0.5
        if s.centripetal_g >= g_threshold:
            # Adequate loading — retention recovers toward baseline.
            s.bone_density_retention = min(
                1.0, s.bone_density_retention + 0.001
            )
            s.muscle_mass_retention = min(
                1.0, s.muscle_mass_retention + 0.002
            )
        else:
            # Below threshold — Sibonga 2007 loss rates scaled
            # linearly by the sub-threshold deficit.
            deficit = (g_threshold - s.centripetal_g) / g_threshold
            s.bone_density_retention = max(
                0.3, s.bone_density_retention - deficit * 0.005
            )
            s.muscle_mass_retention = max(
                0.3, s.muscle_mass_retention - deficit * 0.003
            )

        if s.centripetal_g < 0.3:
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": (
                    f"Gravity at {s.centripetal_g:.2f}g — below safe threshold. "
                    f"K2 model: cardiovascular={s.cardiovascular_health:.0%}, "
                    f"PV={pv_fraction:.0%}, cardiac mass={cardiac_retention:.0%}. "
                    "Mandatory exercise protocol activated."
                ),
                "subsystem": "artificial_gravity",
            })

        # ── Power cost (friction compensation) ──
        # Increases as bearings wear
        friction_factor = 1.0 + (1.0 - s.bearing_health) * 3.0
        s.maintenance_power_kw = 10.0 * friction_factor

        # ── Emergency stop event (rare) ──
        if self._rng.random() < 0.001:  # 0.1% per year
            s.emergency_stops += 1
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": (
                    f"Emergency rotation stop #{s.emergency_stops} — vibration anomaly detected. "
                    f"Gravity at zero for {self._rng.randint(2, 48)} hours during inspection."
                ),
                "subsystem": "artificial_gravity",
            })

        return events

    def get_gravity_report(self) -> dict[str, float]:
        """Return current gravity and health metrics."""
        s = self.state
        return {
            "centripetal_g": round(s.centripetal_g, 3),
            "rpm": round(s.rpm, 3),
            "coriolis_ms2": round(s.coriolis_at_head_ms2, 4),
            "bearing_health": round(s.bearing_health, 3),
            "seal_health": round(s.seal_health, 3),
            "bone_density": round(s.bone_density_retention, 3),
            "muscle_mass": round(s.muscle_mass_retention, 3),
            "power_kw": round(s.maintenance_power_kw, 1),
        }


# ════════════════════════════════════════════════════════════════
#  3. NUCLEAR FISSION REACTOR — Kilopower / MegaPower
#     Reference: NASA Kilopower/KRUSTY (2018), LANL MegaPower
# ════════════════════════════════════════════════════════════════

@dataclass
class FissionReactorState:
    """Nuclear fission reactor for primary ship power.

    Design based on NASA Kilopower (demonstrated 2018, KRUSTY test)
    scaled to MegaPower concept (LANL, 2 MW thermal).

    Fuel: Low-Enriched Uranium (LEU), 16-19% U-235.
    Cooling: Sodium/potassium heatpipes (no pumps = no moving parts in core).
    Conversion: Stirling engines or thermoelectric (Stirling = 25% efficiency).
    Output: 2 MW thermal → 500 kW electrical.

    Core lifetime: ~30 years before fuel depletion requires replacement.
    Spare fuel rods: 3 tonnes LEU supports ~10 core replacements
    = 300 years of fission power.

    Reference:
      - Gibson et al. (2018) "Kilopower Reactor Using Stirling Technology"
      - McClure & Poston (2013) "Design of Megawatt-class Fission Reactors"
    """
    # Core
    # 300 kg HALEU core: ESTIMATE — scaled from Gibson 2018 KRUSTY (32 kg for 1 kWe)
    # ×15 for 15 kWe sub-system → 480 kg; we use 300 kg (more compact design)
    core_fuel_mass_kg: float = 300.0      # ESTIMATE — Gibson 2018 KRUSTY core scaling
    # 19.75% is HALEU regulatory limit (NRC 10 CFR 50, Appendix A); use 19% for margin
    core_enrichment_pct: float = 19.0     # NRC 10 CFR 50 Appendix A: HALEU ≤19.75% U-235
    core_burnup_fraction: float = 0.0     # 0=fresh, 1=depleted
    core_age_years: int = 0
    core_replacement_number: int = 0

    # Spare fuel
    spare_fuel_mass_kg: float = 2700.0    # ESTIMATE — 2700 kg spare = 9 more cores (HALEU budget)
    fuel_rod_count: int = 9               # ESTIMATE — pre-fabricated spare cores

    # Thermal output
    thermal_power_mw: float = 2.0         # ESTIMATE — 2 MWt core (McClure & Poston 2013 design space)
    electrical_power_kw: float = 500.0    # ESTIMATE — 500 kWe at 25% Stirling efficiency
    stirling_engine_health: float = 1.0
    stirling_engine_count: int = 4        # Redundant Stirling converters

    # Heatpipe cooling
    heatpipe_health: float = 1.0
    coolant_loop_health: float = 1.0
    radiator_health: float = 1.0          # Heat rejection radiator panels

    # Control
    control_rod_health: float = 1.0
    reactor_scrams_total: int = 0
    is_critical: bool = True              # Reactor at criticality

    # Backup: RTGs
    rtg_count: int = 4                    # ESTIMATE — 4 RTGs provides ~2 kWe backup margin
    rtg_pu238_mass_kg: float = 20.0       # ESTIMATE — ~5 kg Pu-238 per RTG (GPHS module: 2.7 kg Pu per unit; Bennett 2006 Acta Astronautica 59 358)
    rtg_power_kw: float = 2.0             # ESTIMATE — 4× ~500 We units (Cassini: 285 We per GPHS-RTG, Bennett 2006)
    rtg_half_life_years: float = 87.7     # Pu-238 half-life: Audi 2017 Chinese Phys C 41 030301

    # Safety
    containment_integrity: float = 1.0
    radiation_leakage_usv_hr: float = 0.5  # ESTIMATE — 0.5 µSv/hr at hull surface (shielding design target)


class FissionReactorSimulator:
    """Simulates nuclear fission reactor operations over centuries.

    The reactor is the beating heart of the generation ship. Without
    it, everything else fails. Design philosophy: extreme redundancy
    and simplicity (heatpipes = no pumps, passive safety).

    KRUSTY demonstrated the concept in 2018 — a uranium core with
    heatpipes that passively removes heat even during shutdown.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = FissionReactorState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        if s.is_critical:
            s.core_age_years += 1

            # ── Fuel burnup ──
            # ~3.3% per year for a 30-year core
            burnup_rate = 1.0 / 30.0
            s.core_burnup_fraction = min(1.0, s.core_burnup_fraction + burnup_rate)

            # Power output degrades with burnup (fission products absorb neutrons)
            burnup_penalty = 1.0 - (s.core_burnup_fraction * 0.4)  # Up to 40% reduction
            s.thermal_power_mw = 2.0 * burnup_penalty
            s.electrical_power_kw = s.thermal_power_mw * 1000 * 0.25 * s.stirling_engine_health

            # ── Stirling engine degradation ──
            s.stirling_engine_health = max(0.3, s.stirling_engine_health - 0.003)

            # ── Heatpipe degradation ──
            s.heatpipe_health = max(0.5, s.heatpipe_health - 0.001)

            # ── Control rod wear ──
            s.control_rod_health = max(0.3, s.control_rod_health - 0.002)

            # ── Core replacement check ──
            if s.core_burnup_fraction >= 0.95:
                if s.fuel_rod_count > 0:
                    # Replace core
                    s.fuel_rod_count -= 1
                    s.spare_fuel_mass_kg -= 300.0
                    s.core_burnup_fraction = 0.0
                    s.core_age_years = 0
                    s.core_replacement_number += 1
                    s.control_rod_health = 0.95  # New control rods with new core
                    events.append({
                        "year": mission_year,
                        "severity": "NOMINAL",
                        "message": (
                            f"Fission core #{s.core_replacement_number + 1} installed. "
                            f"{s.fuel_rod_count} spare cores remaining. "
                            f"Estimated fuel endurance: {s.fuel_rod_count * 30} years."
                        ),
                        "subsystem": "fission_reactor",
                    })
                else:
                    # No spare fuel — reactor must shut down
                    s.is_critical = False
                    s.thermal_power_mw = 0.0
                    s.electrical_power_kw = 0.0
                    events.append({
                        "year": mission_year,
                        "severity": "EMERGENCY",
                        "message": (
                            "Fission fuel EXHAUSTED — no spare cores remaining. "
                            "Reactor shutdown. Ship on RTG backup power only "
                            f"({s.rtg_power_kw:.1f} kW). Critical power shortage."
                        ),
                        "subsystem": "fission_reactor",
                    })

            # ── Scram events (rare safety shutdowns) ──
            scram_prob = (1.0 - s.control_rod_health) * 0.05
            if self._rng.random() < scram_prob:
                s.reactor_scrams_total += 1
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": (
                        f"Reactor SCRAM #{s.reactor_scrams_total} — automatic safety shutdown. "
                        f"Control rod health: {s.control_rod_health:.0%}. "
                        f"Restart in {self._rng.randint(1, 72)} hours."
                    ),
                    "subsystem": "fission_reactor",
                })

            # ── Fuel low warning ──
            if s.fuel_rod_count <= 2 and s.core_burnup_fraction > 0.5:
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"Fission fuel reserves critical: {s.fuel_rod_count} spare cores. "
                        f"Current core at {s.core_burnup_fraction:.0%} burnup. "
                        f"~{int(s.fuel_rod_count * 30 + 30 * (1 - s.core_burnup_fraction))} "
                        "years of fission power remaining."
                    ),
                    "subsystem": "fission_reactor",
                })

        # ── RTG decay (always running as backup) ──
        # Power = initial * (0.5)^(t / half_life)
        decay_factor = 0.5 ** (mission_year / s.rtg_half_life_years)
        s.rtg_power_kw = 2.0 * s.rtg_count * decay_factor  # 2 kW initial per RTG

        # ── Containment ──
        s.containment_integrity = max(0.8, s.containment_integrity - 0.0005)
        s.radiation_leakage_usv_hr = 0.5 / max(0.01, s.containment_integrity)

        # ── Radiator degradation (micrometeorite pitting, thermal cycling) ──
        s.radiator_health = max(0.4, s.radiator_health - 0.002)

        if s.radiator_health < 0.5:
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": (
                    f"Heat rejection radiators at {s.radiator_health:.0%}. "
                    "Reactor thermal efficiency degraded. "
                    "Deploy repair nanobots to radiator panels."
                ),
                "subsystem": "fission_reactor",
            })

        return events

    def get_power_report(self) -> dict[str, Any]:
        """Return current power generation status."""
        s = self.state
        return {
            "fission_kw": round(s.electrical_power_kw, 1),
            "rtg_kw": round(s.rtg_power_kw, 2),
            "total_kw": round(s.electrical_power_kw + s.rtg_power_kw, 1),
            "core_burnup": f"{s.core_burnup_fraction:.0%}",
            "core_age_years": s.core_age_years,
            "spare_cores": s.fuel_rod_count,
            "reactor_status": "CRITICAL" if s.is_critical else "SHUTDOWN",
            "containment": f"{s.containment_integrity:.0%}",
        }


# ════════════════════════════════════════════════════════════════
#  4. DEEP SPACE LASER COMMUNICATION
#     Reference: NASA DSOC (Psyche mission, 2023-2024)
# ════════════════════════════════════════════════════════════════

@dataclass
class LaserCommState:
    """Deep-space optical laser communication system.

    Based on NASA DSOC (Deep Space Optical Communications), demonstrated
    on the Psyche mission (2023-2024). DSOC achieved 267 Mbps at 33M km.

    For interstellar distances, data rate follows inverse-square law:
      P_received = P_transmitted * (D_receiver / (2 * distance * theta))^2

    At 1 light-year (~9.46e12 km):
      Rate drops to bits/second at best.
    At 10 light-years:
      Rate is effectively zero — store messages for posterity.

    One-way light delay = distance_ly * 1 year.

    Reference:
      - NASA DSOC: doi:10.2514/6.2023-4387
      - Biswas et al. (2024) "Flight demonstration of DSOC"
    """
    # Transmitter
    laser_power_w: float = 10.0           # ESTIMATE — 10 W flight laser (DSOC used 4 W TX; Biswas 2024 SPIE 12878)
    laser_wavelength_nm: float = 1550.0   # 1550 nm telecom C-band (DSOC flight wavelength; Biswas 2024)
    beam_divergence_urad: float = 3.0     # ESTIMATE — 3 µrad diffraction-limited beam (λ/D for 0.5 m TX; Biswas 2024)
    laser_health: float = 1.0
    laser_optics_health: float = 1.0      # Telescope/optics assembly

    # Receiver
    receiver_aperture_m: float = 1.0      # ESTIMATE — 1 m aperture telescope receiver (Hale: 5 m used for DSOC ground station; Biswas 2024)
    detector_sensitivity: float = 1.0     # Single-photon detector health

    receiver_health: float = 1.0

    # Communication state
    distance_ly: float = 0.0              # Current distance from Earth
    one_way_delay_years: float = 0.0      # Light travel time
    data_rate_bps: float = 0.0            # Current achievable data rate
    link_active: bool = True              # Is communication possible?
    last_message_received_year: float = 0.0
    last_message_sent_year: float = 0.0
    messages_sent_total: int = 0
    messages_received_total: int = 0

    # Store-and-forward buffer
    outbound_buffer_messages: int = 0     # Composed but unsendable messages
    inbound_buffer_messages: int = 0

    # Gravitational focusing relay (P3 fix)
    # The Sun's gravitational lens focuses EM radiation at its focal line
    # starting at ~550 AU (0.0087 ly). A relay probe at the focal line
    # amplifies signals by ~1e9. Ship benefits when Earth relay is deployed.
    # Reference: Turyshev & Toth (2017) "Direct Multipixel Imaging and
    # Spectroscopy of an Exoplanet with a Solar Gravity Lens Mission"
    focal_line_relay_deployed: bool = False
    focal_line_gain_factor: float = 1e9   # Amplification from gravitational lens (Turyshev & Toth 2017 Phys Rev D 96 024008)
    focal_line_relay_health: float = 1.0  # Relay probe health at 550 AU

    # Quantum key distribution (for secure comms within range)
    qkd_active: bool = True
    qkd_key_bits_exchanged: int = 0

    # Power
    power_consumption_kw: float = 5.0     # ESTIMATE — optical terminal + cooling overhead

    # Reference data rate at known distance (DSOC calibration)
    # DSOC: 267 Mbps at 33 million km = 3.5e-6 ly (Biswas et al. 2024 SPIE 12878)
    reference_rate_bps: float = 267e6     # Biswas 2024 SPIE 12878: DSOC peak 267 Mbps at 33 Mkm
    reference_distance_ly: float = 3.5e-6  # 33 million km in ly (DSOC Psyche flyby distance)


class LaserCommSimulator:
    """Simulates deep-space laser communication over interstellar distances.

    The fundamental constraint is the inverse-square law. Signal power
    drops as 1/r^2, and at interstellar distances this means data rates
    plummet to single-digit bits per second within a few light-years.

    Beyond ~5 ly, the link is effectively one-way: the ship transmits
    status updates that Earth might detect with large telescope arrays,
    but two-way communication is impractical.

    Store-and-forward: crew can compose messages even when no link
    exists. These are transmitted whenever conditions allow.
    """

    def __init__(self, velocity_c: float = 0.1, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._velocity_c = velocity_c
        self.state = LaserCommState()

    def _calculate_data_rate(self, distance_ly: float) -> float:
        """Calculate achievable data rate at given distance.

        Uses inverse-square scaling from DSOC reference point.
        DSOC achieved 267 Mbps at 33 million km (3.5e-6 ly).

        rate = reference_rate * (reference_distance / distance)^2

        If a gravitational focusing relay is deployed at the Sun's focal
        line (~550 AU), the gravitational lens amplification (~1e9) is
        applied, dramatically extending the communication range.
        """
        s = self.state
        if distance_ly <= 0:
            return s.reference_rate_bps

        rate = s.reference_rate_bps * (s.reference_distance_ly / distance_ly) ** 2
        # Apply hardware health
        rate *= s.laser_health * s.laser_optics_health * s.detector_sensitivity

        # Gravitational focusing relay amplification
        if s.focal_line_relay_deployed and s.focal_line_relay_health > 0.1:
            # Effective gain is sqrt(focal_line_gain_factor) because signal
            # is amplified on the receive side only (one-way benefit).
            effective_gain = math.sqrt(s.focal_line_gain_factor) * s.focal_line_relay_health
            rate *= effective_gain

        return max(0.0, rate)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # ── Update distance ──
        s.distance_ly = mission_year * self._velocity_c
        s.one_way_delay_years = s.distance_ly

        # ── Calculate data rate ──
        s.data_rate_bps = self._calculate_data_rate(s.distance_ly)

        # ── Link status thresholds ──
        # Below 1 bps: link is effectively dead
        if s.data_rate_bps < 1.0:
            if s.link_active:
                s.link_active = False
                events.append({
                    "year": mission_year,
                    "severity": "CRITICAL",
                    "message": (
                        f"Earth communication link LOST at {s.distance_ly:.2f} ly. "
                        f"Data rate {s.data_rate_bps:.2e} bps — below minimum threshold. "
                        f"One-way delay: {s.one_way_delay_years:.1f} years. "
                        "Switching to store-and-forward mode."
                    ),
                    "subsystem": "laser_comm",
                })
        elif s.data_rate_bps < 100.0:
            # Very low rate — text-only, high-priority messages
            if s.link_active:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": (
                        f"Comm link degraded: {s.data_rate_bps:.1f} bps at "
                        f"{s.distance_ly:.2f} ly. Text-only mode. "
                        f"Delay: {s.one_way_delay_years:.1f} years."
                    ),
                    "subsystem": "laser_comm",
                })

        # ── Messages ──
        if s.link_active and s.data_rate_bps >= 1.0:
            # Send queued messages
            if s.outbound_buffer_messages > 0:
                sent = min(s.outbound_buffer_messages, max(1, int(s.data_rate_bps / 1000)))
                s.outbound_buffer_messages -= sent
                s.messages_sent_total += sent
            else:
                # Regular status transmissions
                s.messages_sent_total += 1
        else:
            # Store messages for future (or posterity)
            s.outbound_buffer_messages += self._rng.randint(1, 5)

        # ── QKD availability ──
        # Quantum key distribution requires sufficient photon rate
        if s.data_rate_bps < 1000.0:
            s.qkd_active = False
        else:
            s.qkd_active = True
            s.qkd_key_bits_exchanged += int(s.data_rate_bps * 0.1)  # 10% of bandwidth

        # ── Focal line relay degradation ──
        if s.focal_line_relay_deployed:
            s.focal_line_relay_health = max(0.0, s.focal_line_relay_health - 0.003)
            if s.focal_line_relay_health < 0.2 and s.focal_line_relay_health > 0.0:
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": (
                        f"Gravitational lens relay probe degrading: "
                        f"{s.focal_line_relay_health:.0%} health. "
                        "Communication gain diminishing."
                    ),
                    "subsystem": "laser_comm",
                })

        # ── Hardware degradation ──
        s.laser_health = max(0.0, s.laser_health - 0.005)
        s.laser_optics_health = max(0.0, s.laser_optics_health - 0.003)
        s.detector_sensitivity = max(0.0, s.detector_sensitivity - 0.004)
        s.receiver_health = max(0.0, s.receiver_health - 0.003)

        # ── Laser replacement ──
        if s.laser_health < 0.2:
            s.laser_health = 0.90  # Replace from spares
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": "Laser transmitter replaced from spares.",
                "subsystem": "laser_comm",
            })

        # ── Optics cleaning/replacement ──
        if s.laser_optics_health < 0.3:
            s.laser_optics_health = 0.85
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": "Communication optics refurbished.",
                "subsystem": "laser_comm",
            })

        return events

    def get_comm_report(self) -> dict[str, Any]:
        """Return current communication status."""
        s = self.state
        if s.data_rate_bps >= 1e6:
            rate_str = f"{s.data_rate_bps / 1e6:.1f} Mbps"
        elif s.data_rate_bps >= 1e3:
            rate_str = f"{s.data_rate_bps / 1e3:.1f} kbps"
        elif s.data_rate_bps >= 1.0:
            rate_str = f"{s.data_rate_bps:.1f} bps"
        else:
            rate_str = "NO LINK"

        return {
            "distance_ly": round(s.distance_ly, 3),
            "data_rate": rate_str,
            "data_rate_bps": s.data_rate_bps,
            "one_way_delay_years": round(s.one_way_delay_years, 2),
            "link_active": s.link_active,
            "qkd_active": s.qkd_active,
            "messages_sent": s.messages_sent_total,
            "buffered_messages": s.outbound_buffer_messages,
            "laser_health": f"{s.laser_health:.0%}",
            "focal_relay_deployed": s.focal_line_relay_deployed,
            "focal_relay_health": f"{s.focal_line_relay_health:.0%}" if s.focal_line_relay_deployed else "N/A",
        }


# ════════════════════════════════════════════════════════════════
#  5. WASTE PROCESSING & CLOSED-LOOP RECYCLING
#     Reference: ISS ECLSS, NASA WRS, ESA MELiSSA
# ════════════════════════════════════════════════════════════════

@dataclass
class WasteProcessingState:
    """Closed-loop waste processing and recycling system.

    Modeled after ISS ECLSS (Environmental Control and Life Support System)
    scaled for long-duration autonomy.

    Subsystems:
      1. Pyrolysis reactor: organic waste -> syngas (CO + H2) at 500-900C
      2. Sabatier reactor: CO2 + 4H2 -> CH4 + 2H2O (water + methane)
      3. Electrolysis: 2H2O -> 2H2 + O2 (oxygen for breathing, H2 for Sabatier)
      4. Urine Processing Assembly (UPA): 93% water recovery
      5. Solid waste processor: incineration -> ash -> mineral extraction

    Target: 98%+ mass closure (only 2% lost per cycle).
    ISS achieves ~90% water recovery. MELiSSA targets 100%.

    Reference:
      - Wieland, P. (1998) "Living Together in Space: ISS ECLSS"
      - Lasseur et al. (2010) "MELiSSA: The European Approach"
    """
    # Pyrolysis
    pyrolysis_health: float = 1.0
    pyrolysis_temp_c: float = 700.0       # ESTIMATE — 600-900°C range for municipal solid waste (Arena 2012 Waste Manage 32 625)
    syngas_output_kg_day: float = 2.0     # ESTIMATE — ~2 kg/day syngas for 4-person crew (Arena 2012 scaling)

    # Sabatier reactor
    sabatier_health: float = 1.0
    sabatier_catalyst_life: float = 1.0   # Ruthenium catalyst degrades
    water_recovery_sabatier_kg_day: float = 1.5  # NASA BVAD (NASA/TP-2015-218570 §4.2): Sabatier water recovery

    # Electrolysis
    electrolyzer_health: float = 1.0
    electrolyzer_membrane_life: float = 1.0  # PEM membrane
    o2_output_kg_day: float = 3.5          # ESTIMATE — 4 crew × 0.84 kg/p/day + margin (NASA BVAD)
    h2_output_kg_day: float = 0.44         # ESTIMATE — stoichiometric H2 from OGA (NASA BVAD §4.2.2)

    # Urine processing
    upa_health: float = 1.0
    upa_water_recovery_pct: float = 93.0   # ISS UPA baseline: 93% (Carter 2009 ICES 2009-01-2352)
    upa_distillation_health: float = 1.0

    # Solid waste
    incinerator_health: float = 1.0
    mineral_extraction_efficiency: float = 0.80  # ESTIMATE — ~80% mineral recovery from incineration ash

    # Overall metrics
    mass_closure_pct: float = 98.0         # ESTIMATE — target 98%+ (ISS achieves ~90%; goal exceeds ISS)
    water_reserves_liters: float = 5000.0  # ESTIMATE — 30-day emergency buffer at crew demand
    o2_reserves_kg: float = 500.0          # ESTIMATE — ~150-day O2 reserve for 4-person crew
    waste_input_kg_day: float = 8.0        # NASA BVAD (NASA/TP-2015-218570 §4.1): ~2 kg/p/day solid waste

    # Trace contaminant control
    tcc_health: float = 1.0               # Activated charcoal + catalytic oxidizer
    co2_level_ppm: float = 400.0          # Normal: ~400 ppm; ISS limit 5000 ppm (NASA STD-3001 Vol 1)
    voc_level_ppb: float = 50.0           # ESTIMATE — below 100 ppb VOC target (NASA STD-3001 §6.6)

    # Power
    total_power_kw: float = 30.0          # ESTIMATE — combined ECLSS power (ISS ECLSS ~3 kW per person; scaled 4×)


class WasteProcessingSimulator:
    """Simulates closed-loop waste processing for a generation ship.

    The goal is to approach 100% mass closure — every atom of waste
    is recycled back into usable resources. In practice, some loss
    is inevitable (outgassing, imperfect separation, chemical side
    reactions). The 2% loss per cycle means you need initial reserves
    and periodic replenishment from any available source.

    ISS ECLSS is the closest real analog, but it only achieves ~90%
    water closure and requires regular resupply. A generation ship
    must do better — ESA's MELiSSA project targets full closure
    using biological + physicochemical loops.
    """

    def __init__(self, crew_size: int = 4, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew_size = crew_size
        self.state = WasteProcessingState()
        # Scale subsystems to crew. NASA BVAD per-person rates
        # (NASA/TP-2015-218570, Table 4.1.3 "ECLSS mass balance"):
        #   O2 demand        ~0.84 kg/p/day  →  electrolyzer 1.0 kg/p/day (20% margin)
        #   H2 for Sabatier  ~0.11 kg/p/day
        #   Water drink      ~2.5 L/p/day    →  Sabatier+UPA covers 4 L/p/day for all uses
        #   Solid waste      ~2.0 kg/p/day
        #   Sabatier H2O out ~0.82 L/p/day — stoichiometric: CO2 + 4H2 → CH4 + 2H2O
        #                    gives 2 mol H2O / mol CO2 = 36/44 kg H2O per kg CO2
        #                    × 1 kg CO2/crew/day (NASA BVAD respiratory output)
        #                    = 0.82 kg H2O/crew/day; rounded to 0.8 for loop losses
        # All rated outputs scale linearly with crew.
        self.state.waste_input_kg_day = crew_size * 2.0
        self.state.o2_output_kg_day = crew_size * 1.0
        self.state.h2_output_kg_day = crew_size * 0.11
        self.state.water_recovery_sabatier_kg_day = crew_size * 0.8
        # Emergency reserves sized to 30-day buffer at full crew demand.
        self.state.water_reserves_liters = max(
            5000.0, crew_size * 3.0 * 30.0
        )
        self.state.o2_reserves_kg = max(500.0, crew_size * 0.84 * 30.0)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # ── Pyrolysis degradation ──
        # High-temperature reactor: thermal cycling fatigue
        s.pyrolysis_health = max(0.3, s.pyrolysis_health - 0.004)
        s.syngas_output_kg_day = 2.0 * s.pyrolysis_health

        # ── Sabatier catalyst life ──
        # Ruthenium catalyst: poisoned by sulfur, sintering at high temps
        s.sabatier_catalyst_life = max(0.0, s.sabatier_catalyst_life - 0.01)
        s.sabatier_health = max(0.2, s.sabatier_health - 0.003)

        # Catalyst replacement every ~50 years
        if s.sabatier_catalyst_life < 0.1:
            s.sabatier_catalyst_life = 0.90  # Regenerate/replace catalyst
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": (
                    "Sabatier reactor catalyst regenerated. "
                    "Water recovery from CO2 restored."
                ),
                "subsystem": "waste_processing",
            })

        s.water_recovery_sabatier_kg_day = (
            self._crew_size * 0.8 * s.sabatier_health * s.sabatier_catalyst_life
        )

        # ── Electrolyzer membrane ──
        # PEM membrane degrades: crossover increases, efficiency drops
        s.electrolyzer_membrane_life = max(0.0, s.electrolyzer_membrane_life - 0.008)
        s.electrolyzer_health = max(0.3, s.electrolyzer_health - 0.003)

        # Membrane replacement every ~60 years
        if s.electrolyzer_membrane_life < 0.1:
            s.electrolyzer_membrane_life = 0.90
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": "Electrolyzer PEM membrane replaced. O2/H2 production restored.",
                "subsystem": "waste_processing",
            })

        s.o2_output_kg_day = (
            self._crew_size * 1.0 * s.electrolyzer_health * s.electrolyzer_membrane_life
        )
        s.h2_output_kg_day = (
            self._crew_size * 0.11 * s.electrolyzer_health * s.electrolyzer_membrane_life
        )

        # ── UPA (Urine Processing Assembly) ──
        s.upa_health = max(0.4, s.upa_health - 0.005)
        s.upa_distillation_health = max(0.3, s.upa_distillation_health - 0.004)
        s.upa_water_recovery_pct = 93.0 * s.upa_health * s.upa_distillation_health

        # ── Incinerator ──
        s.incinerator_health = max(0.4, s.incinerator_health - 0.003)

        # ── Trace contaminant control ──
        s.tcc_health = max(0.3, s.tcc_health - 0.005)
        # CO2 rises as TCC degrades
        s.co2_level_ppm = 400.0 + (1.0 - s.tcc_health) * 4600.0  # Up to 5000 ppm
        s.voc_level_ppb = 50.0 + (1.0 - s.tcc_health) * 450.0

        # ── Overall mass closure ──
        subsystem_efficiencies = [
            s.pyrolysis_health,
            s.sabatier_health * s.sabatier_catalyst_life,
            s.electrolyzer_health * s.electrolyzer_membrane_life,
            s.upa_health * s.upa_distillation_health,
            s.incinerator_health,
        ]
        avg_efficiency = sum(subsystem_efficiencies) / len(subsystem_efficiencies)
        s.mass_closure_pct = 98.0 * avg_efficiency

        # ── Water and O2 reserve tracking ──
        # Daily water balance per NASA BVAD NASA/TP-2015-218570 Table 4.1.3:
        #   drink+food:     2.5 L/p/day   → returned via urine (UPA) and feces
        #   hygiene:        0.5 L/p/day   → returned via humidity condensate
        #   total demand:   ~3.0 L/p/day
        # Recovery sources with closed-loop ECLSS:
        #   UPA from urine:          ~1.4 L/p/day (93% × 1.5 L urine)
        #   CHX condensate (sweat/resp): ~1.0 L/p/day (NASA/TP-2006-213694)
        #   Sabatier from CO₂+H₂:    ~0.5 L/p/day
        # Total recovery ≈ 2.9 L/p/day → ~0.1 L/p/day net loss (the 98%-
        # closure model). Earlier versions only counted UPA + Sabatier,
        # missing the CHX condensate loop and driving a false deficit.
        daily_water_need = self._crew_size * 3.0
        chx_condensate_recovery = self._crew_size * 1.0 * s.upa_health  # CHX drives with pump
        daily_water_recovered = (
            s.water_recovery_sabatier_kg_day +
            (s.upa_water_recovery_pct / 100.0) * self._crew_size * 1.5 +
            chx_condensate_recovery
        )
        daily_water_deficit = daily_water_need - daily_water_recovered
        annual_water_change = -daily_water_deficit * 365
        s.water_reserves_liters = max(0.0, s.water_reserves_liters + annual_water_change)

        # O2 balance: crew needs ~0.84 kg/person/day
        daily_o2_need = self._crew_size * 0.84
        daily_o2_deficit = daily_o2_need - s.o2_output_kg_day
        annual_o2_change = -daily_o2_deficit * 365
        s.o2_reserves_kg = max(0.0, s.o2_reserves_kg + annual_o2_change)

        # ── Events (latched: fire once on transition, re-arm on recovery) ──
        if s.mass_closure_pct < 90.0 and not getattr(self, "_closure_crit_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": (
                    f"Mass closure dropped to {s.mass_closure_pct:.1f}% "
                    f"(target: 98%+). Resource loss accelerating. "
                    f"Water reserves: {s.water_reserves_liters:.0f}L, "
                    f"O2 reserves: {s.o2_reserves_kg:.0f} kg."
                ),
                "subsystem": "waste_processing",
            })
            self._closure_crit_latched = True
        elif s.mass_closure_pct >= 92.0:
            self._closure_crit_latched = False
            if s.mass_closure_pct < 95.0 and not getattr(self, "_closure_warn_latched", False):
                events.append({
                    "year": mission_year,
                    "severity": "WARNING",
                    "message": (
                        f"Mass closure at {s.mass_closure_pct:.1f}%. "
                        "Maintenance required on recycling subsystems."
                    ),
                    "subsystem": "waste_processing",
                })
                self._closure_warn_latched = True
            elif s.mass_closure_pct >= 96.0:
                self._closure_warn_latched = False

        if s.water_reserves_liters < 1000.0 and not getattr(self, "_water_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL" if s.water_reserves_liters < 500 else "WARNING",
                "message": (
                    f"Water reserves low: {s.water_reserves_liters:.0f}L "
                    f"(crew needs {daily_water_need:.0f}L/day). "
                    f"Recovery rate: {daily_water_recovered:.1f}L/day."
                ),
                "subsystem": "waste_processing",
            })
            self._water_low_latched = True
        elif s.water_reserves_liters >= 1500.0:
            self._water_low_latched = False

        if s.o2_reserves_kg < 100.0 and not getattr(self, "_o2_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "EMERGENCY" if s.o2_reserves_kg < 50 else "CRITICAL",
                "message": (
                    f"Oxygen reserves critical: {s.o2_reserves_kg:.0f} kg. "
                    f"Production: {s.o2_output_kg_day:.2f} kg/day, "
                    f"need: {daily_o2_need:.2f} kg/day."
                ),
                "subsystem": "waste_processing",
            })
            self._o2_low_latched = True
        elif s.o2_reserves_kg >= 150.0:
            self._o2_low_latched = False

        if s.co2_level_ppm > 4000.0:
            events.append({
                "year": mission_year,
                "severity": "WARNING" if s.co2_level_ppm < 5000 else "CRITICAL",
                "message": (
                    f"CO2 level elevated: {s.co2_level_ppm:.0f} ppm "
                    f"(limit: 5000 ppm). TCC health: {s.tcc_health:.0%}."
                ),
                "subsystem": "waste_processing",
            })

        return events

    def get_recycling_report(self) -> dict[str, Any]:
        """Return current waste processing status."""
        s = self.state
        return {
            "mass_closure_pct": round(s.mass_closure_pct, 1),
            "water_reserves_liters": round(s.water_reserves_liters, 0),
            "o2_reserves_kg": round(s.o2_reserves_kg, 0),
            "co2_ppm": round(s.co2_level_ppm, 0),
            "pyrolysis_health": f"{s.pyrolysis_health:.0%}",
            "sabatier_health": f"{s.sabatier_health:.0%}",
            "electrolyzer_health": f"{s.electrolyzer_health:.0%}",
            "upa_recovery_pct": round(s.upa_water_recovery_pct, 1),
        }


# ════════════════════════════════════════════════════════════════
#  ORCHESTRATOR — Runs All 5 Systems Together
# ════════════════════════════════════════════════════════════════

class AdvancedSystemsOrchestrator:
    """Orchestrates all five advanced generation ship systems.

    Runs year-by-year simulation of:
      1. Radiation shielding (active + passive)
      2. Artificial gravity (O'Neill cylinder rotation)
      3. Nuclear fission reactor (Kilopower/MegaPower)
      4. Laser communication (DSOC-based)
      5. Waste processing (ECLSS-based closed-loop)

    Cross-system dependencies:
      - Fission reactor powers everything (radiation shield magnets,
        gravity bearings, laser comm, waste processing)
      - If reactor output drops, other systems degrade faster
      - Waste processing provides water for radiation shielding
      - Radiation dose affects crew health alongside gravity level
      - Communication loss is psychological (tracked but not fatal)

    Synergy model:
      - Reactor power budget: 500 kW total, allocated across systems
      - If total demand > supply, systems are throttled proportionally
    """

    def __init__(
        self,
        crew_size: int = 4,
        velocity_c: float = 0.1,
        seed: int | None = None,
    ) -> None:
        self._crew_size = crew_size
        self._velocity_c = velocity_c
        self._seed = seed

        self.radiation = RadiationShieldSimulator(seed=seed)
        self.gravity = ArtificialGravitySimulator(seed=seed)
        self.reactor = FissionReactorSimulator(seed=seed)
        self.comm = LaserCommSimulator(velocity_c=velocity_c, seed=seed)
        self.waste = WasteProcessingSimulator(crew_size=crew_size, seed=seed)

    def simulate_year(self, mission_year: float) -> dict[str, Any]:
        """Simulate one year across all five systems with cross-dependencies."""
        all_events: list[dict[str, Any]] = []

        # ── 1. Reactor first (determines power budget) ──
        reactor_events = self.reactor.simulate_year(mission_year)
        all_events.extend(reactor_events)

        available_power_kw = (
            self.reactor.state.electrical_power_kw +
            self.reactor.state.rtg_power_kw
        )

        # ── Power budget allocation ──
        # Radiation shielding: 70 kW (cryocooler 50 + electrostatic 20)
        # Gravity: 10-40 kW (bearing friction)
        # Comm: 5 kW
        # Waste processing: 30 kW
        # Total nominal: ~115-145 kW (well within 500 kW)
        power_demand_kw = (
            self.radiation.state.cryocooler_power_kw +
            self.radiation.state.electrostatic_power_kw +
            self.gravity.state.maintenance_power_kw +
            self.comm.state.power_consumption_kw +
            self.waste.state.total_power_kw
        )

        power_ratio = min(1.0, available_power_kw / max(1.0, power_demand_kw))

        if power_ratio < 1.0:
            cur_tier = 2 if power_ratio < 0.5 else 1
            prev_tier = getattr(self, "_pm_deficit_tier", 0)
            if cur_tier > prev_tier:
                self._pm_deficit_tier = cur_tier
                all_events.append({
                    "year": mission_year,
                    "severity": "CRITICAL" if cur_tier == 2 else "WARNING",
                    "message": (
                        f"Power deficit: {available_power_kw:.0f} kW available vs "
                        f"{power_demand_kw:.0f} kW demanded. "
                        f"Systems throttled to {power_ratio:.0%}."
                    ),
                    "subsystem": "power_management",
                })
        else:
            self._pm_deficit_tier = 0

        # ── 2. Radiation shielding (needs reactor power for cryocooler) ──
        # If power is limited, cryocooler suffers -> magnets warm -> quench risk
        if power_ratio < 0.8:
            self.radiation.state.cryocooler_health *= (0.9 + 0.1 * power_ratio)
        rad_events = self.radiation.simulate_year(mission_year)
        all_events.extend(rad_events)

        # ── 3. Artificial gravity ──
        grav_events = self.gravity.simulate_year(mission_year)
        all_events.extend(grav_events)

        # ── 4. Communication ──
        comm_events = self.comm.simulate_year(mission_year)
        all_events.extend(comm_events)

        # ── 5. Waste processing (needs power for electrolysis, pyrolysis) ──
        if power_ratio < 0.7:
            # Reduced power = reduced processing capacity
            self.waste.state.pyrolysis_health *= (0.95 + 0.05 * power_ratio)
            self.waste.state.electrolyzer_health *= (0.95 + 0.05 * power_ratio)
        waste_events = self.waste.simulate_year(mission_year)
        all_events.extend(waste_events)

        # ── Cross-system synergies ──

        # Waste processing water feeds radiation shield water tanks
        if self.waste.state.water_reserves_liters > 3000:
            replenish = min(50.0, self.waste.state.water_reserves_liters - 3000)
            self.radiation.state.water_shield_mass_kg = min(
                7000.0, self.radiation.state.water_shield_mass_kg + replenish
            )

        # Radiation dose compounds with low gravity (crew health interaction)
        annual_dose = (
            self.radiation.state.gcr_annual_unshielded_sv *
            (1.0 - self.radiation.state.total_dose_reduction)
        )
        if self.gravity.state.centripetal_g < 0.3 and annual_dose > 0.05:
            all_events.append({
                "year": mission_year,
                "severity": "EMERGENCY",
                "message": (
                    f"Compound health crisis: low gravity ({self.gravity.state.centripetal_g:.2f}g) "
                    f"+ elevated radiation ({annual_dose:.3f} Sv/yr). "
                    "Crew health deteriorating rapidly."
                ),
                "subsystem": "crew_health",
            })

        return {
            "year": mission_year,
            "events": all_events,
            "power": {
                "available_kw": round(available_power_kw, 1),
                "demand_kw": round(power_demand_kw, 1),
                "ratio": round(power_ratio, 3),
            },
            "radiation": {
                "dose_reduction": round(self.radiation.state.total_dose_reduction, 3),
                "cumulative_dose_sv": round(self.radiation.state.cumulative_crew_dose_sv, 4),
            },
            "gravity": {
                "g_level": round(self.gravity.state.centripetal_g, 3),
                "bearing_health": round(self.gravity.state.bearing_health, 3),
            },
            "reactor": {
                "power_kw": round(self.reactor.state.electrical_power_kw, 1),
                "burnup": round(self.reactor.state.core_burnup_fraction, 3),
                "spare_cores": self.reactor.state.fuel_rod_count,
            },
            "comm": {
                "distance_ly": round(self.comm.state.distance_ly, 3),
                "data_rate_bps": self.comm.state.data_rate_bps,
                "link_active": self.comm.state.link_active,
            },
            "waste": {
                "mass_closure_pct": round(self.waste.state.mass_closure_pct, 1),
                "water_liters": round(self.waste.state.water_reserves_liters, 0),
                "o2_kg": round(self.waste.state.o2_reserves_kg, 0),
            },
        }

    def run_mission(self, years: int = 100) -> list[dict[str, Any]]:
        """Run full mission simulation for given number of years."""
        results = []
        for y in range(1, years + 1):
            results.append(self.simulate_year(float(y)))
        return results

    def get_full_report(self) -> dict[str, Any]:
        """Return comprehensive status report across all systems."""
        return {
            "radiation_shield": {
                "dose_reduction": f"{self.radiation.state.total_dose_reduction:.0%}",
                "cumulative_dose_sv": round(self.radiation.state.cumulative_crew_dose_sv, 3),
                "operational_coils": sum(
                    1 for h in self.radiation.state.coil_health if h > 0.1
                ),
                "cryocooler_health": f"{self.radiation.state.cryocooler_health:.0%}",
                "quench_events": self.radiation.state.quench_events_total,
            },
            "artificial_gravity": self.gravity.get_gravity_report(),
            "fission_reactor": self.reactor.get_power_report(),
            "laser_comm": self.comm.get_comm_report(),
            "waste_processing": self.waste.get_recycling_report(),
        }
