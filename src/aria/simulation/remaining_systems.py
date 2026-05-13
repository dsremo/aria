"""Remaining P1 Systems — 100-Scientist Interrogation Gap Closure.

Six subsystems that were previously unmodeled:

1. STELLAR PROPER MOTION (P1)
   Target star moves due to proper motion (~0.1-10 arcsec/year).
   Over 1000 years: Alpha Centauri moves ~3800 arcsec = ~1 degree.
   Navigation must account for this. Mid-course corrections needed
   every 50-100 years. If not corrected: miss target by ~0.07 ly
   at 100 ly distance.

   Physics:
     - Proper motion: tangential velocity / distance = angular drift
     - Alpha Cen: 3.7 arcsec/yr (fastest bright star)
     - Barnard's Star: 10.3 arcsec/yr (highest known)
     - Correction burn delta-V: ~10 m/s per degree of course change
     - Accumulated error = integral of uncorrected drift over time

   Reference: Hipparcos/Gaia catalog proper motions, van de Kamp (1977).

2. OORT CLOUD PASSAGE (P1)
   At departure: pass through Sol's Oort Cloud (10,000-100,000 AU).
   At arrival: pass through target star's Oort Cloud.
   Debris density: ~100x interstellar medium baseline.
   Duration: ~10-50 years per cloud transit at 0.1c.
   Enhanced collision risk: shield stress test period.
   May encounter comets — potential water/ice mining opportunity.

   Physics:
     - Sol Oort Cloud: ~10,000-100,000 AU, ~10^11 comets >1km
     - Number density: ~10^-25 /m^3 for >1mm particles
     - At 0.1c: 50,000 AU crossed in ~2.5 years (inner to outer)
     - Collision cross-section: ship ~500 m^2 forward area
     - Expected impacts: Poisson process with lambda from density

   Reference: Weissman (1996) Oort Cloud, Stern (2003), Hills (1981).

3. COMPUTING REGRESSION (P1)
   Cannot fabricate modern CPUs on ship (7nm lithography impossible).
   Best the ship can make: ~1990s era chips (~500nm process).
   Computing power degrades as chips fail and replacements are cruder.
   ARIA must optimize for declining compute.
   Glass archive stores chip designs but fab can't execute them.
   Mitigation: redundancy, FPGA reprogramming, neuromorphic alternatives.

   Physics:
     - MTBF for space-rated CPU: ~50,000 hours (~5.7 years)
     - With radiation: MTBF drops to ~20,000 hours (~2.3 years)
     - Replacement chips: ~1/1000th the performance of originals
     - Total compute fleet: 100 original CPUs + fabrication line
     - Moore's Law in reverse: each replacement generation is cruder

   Reference: NASA RAD750 heritage, ESA LEON processors, FPGA SEU rates.

4. SEAL & GASKET LIFECYCLE (P1)
   Every pressure seal on the ship has finite life.
   Elastomer seals: 10-30 year replacement cycle.
   O-rings: ~15 years in radiation environment.
   Total seals on ship: ~10,000. Replacement rate: ~500/year.
   If seal production stops: atmosphere leaks accelerate.
   Manufacturing can produce polymer seals but not fluoroelastomer.

   Physics:
     - EPDM rubber: compression set 50% at 10 years
     - Viton (FKM): better radiation resistance but harder to fabricate
     - Seal failure mode: compression set → crack → leak
     - Leak rate ∝ (age / rated_life)^2 for aging seals
     - Atmosphere loss: ~0.01%/year per failed seal

   Reference: Parker O-Ring Handbook, NASA TP-2009-01, rubber aging (Gillen 2005).

5. CATALYST LIFECYCLE (Sabatier, electrolysis) (P1)
   Sabatier catalyst (Ru/Al2O3): poisons from sulfur, loses activity 2%/yr.
   Electrolysis electrodes: platinum degrades, iridium alternative.
   Catalyst mass: 50 kg total, cannot be synthesized — only regenerated.
   Regeneration: heat treatment at 500°C recovers ~80% activity.
   Without catalysts: water recycling and CO2 conversion fail.

   Physics:
     - Sabatier: CO2 + 4H2 → CH4 + 2H2O (exothermic, 165°C)
     - Catalyst deactivation: sintering + sulfur poisoning + coking
     - Activity decay: A(t) = A0 * exp(-k*t), k ~0.02/yr
     - Regeneration cycle: 500°C for 4h, recovers 80% of lost activity
     - Electrolysis: 2H2O → 2H2 + O2, Pt/Ir electrodes degrade 1%/yr

   Reference: Junaedi (2012) Sabatier for ISS, Carmo (2013) PEM electrolysis.

6. GRAVITY-DEPENDENT FERTILITY (P1)
   0.56g reproduction never tested in any mammal.
   Potential issues: embryo implantation, fetal development, bone formation.
   Best case: fertility ~80% of 1g. Worst case: fertility ~30%.
   Centrifuge births: medical centrifuge at 1g for delivery.
   Model: fertility_rate = base_rate × gravity_factor(g).

   Physics:
     - Earth fertility rate: ~0.06 per woman per year (developed world)
     - Gravity factor: logistic curve centered at 0.5g
     - Below 0.3g: implantation failure rate >70% (estimated)
     - Centrifuge at 1g: eliminates gravity penalty for delivery only
     - Generational population model: Leslie matrix with fertility input

   Reference: Ronca (2003) rat reproduction in simulated µg,
   Tou (2002) embryo development, Oyama (1975) centrifuge studies.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

from aria.simulation.mil_hdbk_217f import get_failure_rate, get_mtbf_years

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════
#  1. STELLAR PROPER MOTION
# ════════════════════════════════════════════════════════════════

@dataclass
class StellarProperMotionState:
    """Tracks target star drift and navigation correction."""
    # Target star parameters
    target_distance_ly: float = 100.0
    # α Cen A proper motion: 3.679 arcsec/yr (van Leeuwen 2007 A&A 474 653 Hipparcos)
    proper_motion_arcsec_yr: float = 3.7   # van Leeuwen 2007 A&A 474 653 Hipparcos catalog
    # α Cen radial velocity -21.4 km/s (Kervella 2017 A&A 598 L7)
    radial_velocity_km_s: float = -21.0    # Kervella 2017 A&A 598 L7

    # Accumulated navigation error
    uncorrected_drift_arcsec: float = 0.0
    total_drift_arcsec: float = 0.0         # Total drift since departure
    corrections_applied: int = 0
    correction_interval_years: int = 75     # ESTIMATE — mid-course correction cadence (~75 yr intervals)
    last_correction_year: float = 0.0

    # Delta-V budget for corrections
    # 10 m/s per degree: Cassini trajectory correction maneuver budget (JPL IOM 312.F-04)
    correction_dv_m_s_per_deg: float = 10.0  # ESTIMATE — JPL IOM 312.F-04 TCM budget
    total_correction_dv_spent: float = 0.0   # m/s cumulative
    # Total nav budget 500 m/s: Dachwald (2004) IAA-04-IAA.4.8.7 interstellar nav budget
    max_correction_dv: float = 500.0         # ESTIMATE — Dachwald 2004 IAA-04 interstellar nav

    # Miss distance
    projected_miss_ly: float = 0.0

    # Observation accuracy
    # HST Fine Guidance Sensors: ~0.001 arcsec; GAIA: ~25 μas; shipboard tracker 0.1 arcsec ESTIMATE
    star_tracker_accuracy_arcsec: float = 0.1  # ESTIMATE — 0.1 arcsec shipboard optical tracker


class StellarProperMotionSimulator:
    """Navigation correction for target star proper motion.

    A star at 100 ly moving at 3.7 arcsec/yr accumulates 3700 arcsec
    over 1000 years — about 1 degree. Without mid-course corrections
    the ship misses by ~0.07 ly, far outside any star system.
    """

    def __init__(self, target_distance_ly: float = 100.0,
                 proper_motion: float = 3.7, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = StellarProperMotionState(
            target_distance_ly=target_distance_ly,
            proper_motion_arcsec_yr=proper_motion,
        )

    def _compute_miss_distance(self) -> float:
        """Convert uncorrected angular drift to physical miss at target."""
        s = self.state
        drift_deg = s.uncorrected_drift_arcsec / 3600.0
        drift_rad = math.radians(drift_deg)
        # At target_distance_ly, tangential miss = distance * tan(drift)
        miss_ly = s.target_distance_ly * math.tan(drift_rad)
        return abs(miss_ly)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Accumulate proper motion drift ---
        annual_drift = s.proper_motion_arcsec_yr
        # Add small random component for parallax/measurement uncertainty
        annual_drift += self._rng.gauss(0, 0.01)
        s.total_drift_arcsec += annual_drift
        s.uncorrected_drift_arcsec += annual_drift

        # --- Mid-course correction ---
        years_since_correction = mission_year - s.last_correction_year
        if years_since_correction >= s.correction_interval_years:
            if s.total_correction_dv_spent < s.max_correction_dv:
                correction_deg = s.uncorrected_drift_arcsec / 3600.0
                dv_needed = correction_deg * s.correction_dv_m_s_per_deg
                dv_available = s.max_correction_dv - s.total_correction_dv_spent

                if dv_needed <= dv_available:
                    # Full correction
                    residual = self._rng.gauss(0, s.star_tracker_accuracy_arcsec)
                    s.uncorrected_drift_arcsec = residual
                    s.total_correction_dv_spent += dv_needed
                else:
                    # Partial correction with remaining budget
                    fraction = dv_available / dv_needed
                    s.uncorrected_drift_arcsec *= (1.0 - fraction)
                    s.total_correction_dv_spent += dv_available

                s.corrections_applied += 1
                s.last_correction_year = mission_year
                events.append({
                    "year": mission_year, "severity": "INFO",
                    "message": (
                        f"Mid-course correction #{s.corrections_applied}: "
                        f"residual drift {s.uncorrected_drift_arcsec:.2f} arcsec, "
                        f"dV budget used {s.total_correction_dv_spent:.1f}/{s.max_correction_dv:.0f} m/s"
                    ),
                    "subsystem": "stellar_proper_motion",
                })
            else:
                if not getattr(self, "_dv_exhausted_latched", False):
                    events.append({
                        "year": mission_year, "severity": "CRITICAL",
                        "message": (
                            f"Navigation dV budget exhausted. "
                            f"Uncorrected drift: {s.uncorrected_drift_arcsec:.1f} arcsec"
                        ),
                        "subsystem": "stellar_proper_motion",
                    })
                    self._dv_exhausted_latched = True

        # --- Update miss distance ---
        s.projected_miss_ly = self._compute_miss_distance()

        # Latched miss-distance tiers: fire once when crossing threshold.
        if not hasattr(self, "_miss_tier"):
            self._miss_tier = 0
        if s.projected_miss_ly > 0.05 and self._miss_tier < 2:
            self._miss_tier = 2
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"MISSION FAILURE RISK: miss distance {s.projected_miss_ly:.4f} ly "
                    f"exceeds 0.05 ly threshold. Target star system unreachable."
                ),
                "subsystem": "stellar_proper_motion",
            })
        elif s.projected_miss_ly > 0.01 and self._miss_tier < 1:
            self._miss_tier = 1
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"Projected target miss: {s.projected_miss_ly:.4f} ly "
                    f"({s.uncorrected_drift_arcsec:.1f} arcsec uncorrected)"
                ),
                "subsystem": "stellar_proper_motion",
            })
        elif s.projected_miss_ly <= 0.005:
            self._miss_tier = 0  # Re-arm on recovery

        return events


# ════════════════════════════════════════════════════════════════
#  2. OORT CLOUD PASSAGE
# ════════════════════════════════════════════════════════════════

@dataclass
class OortCloudState:
    """State for Oort Cloud transit phases."""
    # Cloud parameters — Hills (1981) AJ 86 1730: inner Oort 10 000 AU, outer 100 000 AU
    inner_boundary_au: float = 10_000.0   # Hills 1981 AJ 86 1730 inner Oort boundary
    outer_boundary_au: float = 100_000.0  # Hills 1981 AJ 86 1730 outer Oort boundary
    # ISM dust grain density ~1e-27 m⁻³ (Grün 1985 A&A 145 220); Oort 100× denser
    base_debris_density_m3: float = 1e-25  # ESTIMATE — Grün 1985 ISM × 100 Oort multiplier
    density_multiplier: float = 100.0      # ESTIMATE — Oort vs ISM density ratio (Weissman 1996)

    # Ship parameters
    ship_velocity_c: float = 0.1
    # Ship cross section 500 m²: ESTIMATE — O'Neill (1977) colony hull projected area
    ship_cross_section_m2: float = 500.0  # ESTIMATE — O'Neill 1977 High Frontier hull area

    # Transit tracking
    in_sol_oort: bool = False
    in_target_oort: bool = False
    sol_oort_entry_year: float = 0.0
    sol_oort_exit_year: float = 0.0
    target_oort_entry_year: float = 0.0
    target_oort_exit_year: float = 0.0

    # Cumulative impact statistics
    total_impacts: int = 0
    shield_stress_factor: float = 1.0  # 1.0 = normal, >1 = elevated
    comets_detected: int = 0
    water_ice_harvested_kg: float = 0.0

    # Mission parameters (filled at init)
    mission_duration_years: float = 1000.0
    distance_ly: float = 100.0


class OortCloudSimulator:
    """Models passage through Oort Clouds at departure and arrival.

    At 0.1c the Sol Oort Cloud (10k-100k AU) is traversed in ~1.4 years
    (inner edge reached quickly after departure). The target star's cloud
    is encountered ~50 years before arrival.
    """

    # 1 AU in meters
    AU_M = 1.496e11
    # Speed of light m/s
    C_M_S = 2.998e8
    # 1 ly in AU
    LY_AU = 63_241.0

    def __init__(self, mission_duration: float = 1000.0,
                 distance_ly: float = 100.0, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = OortCloudState(
            mission_duration_years=mission_duration,
            distance_ly=distance_ly,
        )
        # Compute transit windows
        v_au_yr = self.state.ship_velocity_c * self.C_M_S / self.AU_M * 3.156e7
        # Sol Oort Cloud: entered at inner_boundary / velocity
        self.state.sol_oort_entry_year = (
            self.state.inner_boundary_au / v_au_yr
        )
        self.state.sol_oort_exit_year = (
            self.state.outer_boundary_au / v_au_yr
        )
        # Target Oort Cloud: approached from outer boundary
        total_dist_au = distance_ly * self.LY_AU
        target_outer_from_start = total_dist_au - self.state.outer_boundary_au
        target_inner_from_start = total_dist_au - self.state.inner_boundary_au
        self.state.target_oort_entry_year = target_outer_from_start / v_au_yr
        self.state.target_oort_exit_year = target_inner_from_start / v_au_yr

    def _in_oort_cloud(self, mission_year: float) -> tuple[bool, bool]:
        """Return (in_sol_oort, in_target_oort) for given year."""
        s = self.state
        in_sol = s.sol_oort_entry_year <= mission_year <= s.sol_oort_exit_year
        in_target = s.target_oort_entry_year <= mission_year <= s.target_oort_exit_year
        return in_sol, in_target

    def _impact_rate(self) -> float:
        """Expected impacts per year while inside an Oort Cloud."""
        s = self.state
        v_m_s = s.ship_velocity_c * self.C_M_S
        # Volume swept per second
        volume_per_sec = s.ship_cross_section_m2 * v_m_s
        # Seconds per year
        sec_per_yr = 3.156e7
        volume_per_yr = volume_per_sec * sec_per_yr
        density = s.base_debris_density_m3 * s.density_multiplier
        return volume_per_yr * density

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        in_sol, in_target = self._in_oort_cloud(mission_year)
        was_in_sol = s.in_sol_oort
        was_in_target = s.in_target_oort
        s.in_sol_oort = in_sol
        s.in_target_oort = in_target

        # --- Transition events ---
        if in_sol and not was_in_sol:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": "Entering Sol's Oort Cloud. Elevated debris density.",
                "subsystem": "oort_cloud",
            })
        if not in_sol and was_in_sol:
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": "Exited Sol's Oort Cloud. Returning to ISM baseline.",
                "subsystem": "oort_cloud",
            })
        if in_target and not was_in_target:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": "Entering target star's Oort Cloud. Shield stress elevated.",
                "subsystem": "oort_cloud",
            })
        if not in_target and was_in_target:
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": "Exited target star's Oort Cloud. Approaching inner system.",
                "subsystem": "oort_cloud",
            })

        # --- Impact calculations while in cloud ---
        if in_sol or in_target:
            s.shield_stress_factor = 1.0 + s.density_multiplier * 0.01
            expected_impacts = self._impact_rate()
            # Poisson draw
            actual_impacts = self._rng.poisson(expected_impacts) if hasattr(
                self._rng, 'poisson'
            ) else self._poisson_draw(expected_impacts)
            s.total_impacts += actual_impacts

            if actual_impacts > 0:
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": (
                        f"Oort Cloud transit: {actual_impacts} micro-impacts detected. "
                        f"Cumulative: {s.total_impacts}. Shield stress: {s.shield_stress_factor:.2f}x"
                    ),
                    "subsystem": "oort_cloud",
                })

            # --- Comet detection opportunity ---
            # Weissman 1996 Earth Moon Planets 72 19: ~10¹² Oort comets → ~0.5%/yr intercept
            comet_prob = 0.005  # Weissman 1996 Earth Moon Planets 72 19 (ship cross-section)
            if self._rng.random() < comet_prob:
                s.comets_detected += 1
                # Mining opportunity
                if self._rng.random() < 0.3:  # ESTIMATE: 30% chance it's accessible for mining
                    harvested = self._rng.uniform(100, 5000)  # ESTIMATE: 100-5000 kg H2O ice
                    s.water_ice_harvested_kg += harvested
                    events.append({
                        "year": mission_year, "severity": "INFO",
                        "message": (
                            f"Comet mining opportunity: harvested {harvested:.0f} kg "
                            f"water ice. Total: {s.water_ice_harvested_kg:.0f} kg"
                        ),
                        "subsystem": "oort_cloud",
                    })
                else:
                    events.append({
                        "year": mission_year, "severity": "INFO",
                        "message": (
                            f"Comet #{s.comets_detected} detected but trajectory "
                            f"too divergent for mining."
                        ),
                        "subsystem": "oort_cloud",
                    })
        else:
            s.shield_stress_factor = 1.0

        return events

    def _poisson_draw(self, lam: float) -> int:
        """Manual Poisson draw using inverse CDF (Knuth algorithm)."""
        if lam <= 0:
            return 0
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= self._rng.random()
            if p <= L:
                return k - 1


# ════════════════════════════════════════════════════════════════
#  3. COMPUTING REGRESSION
# ════════════════════════════════════════════════════════════════

@dataclass
class ComputingRegressionState:
    """Tracks computing capability degradation over the mission."""
    # Original computing fleet
    original_cpu_count: int = 100          # ESTIMATE — fleet count at departure
    original_cpu_alive: int = 100
    # 2026-era high-perf CPU ~100 GFLOPS = ~10⁵ MIPS (SPEC CPU2017 benchmark scale)
    original_cpu_mips: float = 100_000.0   # ESTIMATE — 2026-era CPU ≈ 10⁵ MIPS

    # Replacement (fabricated) CPUs
    replacement_cpu_count: int = 0
    # 500nm foundry ≈ 1990s Pentium ≈ ~100 MIPS (Intel Pentium 1993 spec sheet)
    replacement_cpu_mips: float = 100.0    # ESTIMATE — 500nm process ≈ Pentium ~100 MIPS
    replacement_fab_rate_per_year: int = 5  # ESTIMATE — ship foundry fabrication rate

    # Overall compute
    total_mips: float = 0.0
    peak_mips: float = 0.0
    compute_ratio: float = 1.0  # Current / peak

    # Failure model
    # Modern CPU in deep-space GCR field: ~1/MTBF per year; estimated from
    # Heidel 2009 IEEE TNS SEU cross-section scaled to die area and GCR flux
    original_mtbf_years: float = 2.3       # ESTIMATE — CPU MTBF under GCR (Heidel 2009 scaling)
    replacement_mtbf_years: float = 5.0    # ESTIMATE — cruder but rad-hardened design

    # ARIA adaptation
    aria_optimization_level: float = 1.0   # 1.0 = full, 0.0 = minimal
    critical_compute_threshold: float = 0.1  # ESTIMATE — below this ARIA degrades critically
    fpga_pool_count: int = 20              # ESTIMATE — reprogrammable FPGA count
    fpga_alive: int = 20
    # Xilinx Virtex-7 ≈ 10 000 MIPS equivalent (Xilinx DS180, 2013)
    fpga_mips: float = 10_000.0            # ESTIMATE — Xilinx Virtex-class FPGA ≈ 10⁴ MIPS

    # Neuromorphic backup
    neuromorphic_chips: int = 10           # ESTIMATE — backup neuromorphic count
    neuromorphic_alive: int = 10
    # Intel Loihi 2: ~10⁻² J/inference → 5000 MIPS equivalent for sparse tasks
    neuromorphic_mips_equiv: float = 5_000.0  # ESTIMATE — Intel Loihi 2 class (~5000 MIPS equiv)


class ComputingRegressionSimulator:
    """Models the inevitable decline in computing power aboard ship.

    Modern 7nm chips cannot be fabricated — the ship's foundry can produce
    ~500nm process chips (early 1990s equivalent). As original CPUs fail from
    radiation damage and aging, replacements are 1/1000th the performance.
    ARIA must progressively shed capabilities to survive on declining compute.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = ComputingRegressionState()
        # Set peak before computing ratio
        self.state.peak_mips = (
            self.state.original_cpu_alive * self.state.original_cpu_mips
            + self.state.fpga_alive * self.state.fpga_mips
            + self.state.neuromorphic_alive * self.state.neuromorphic_mips_equiv
        )
        self._update_total_mips()

    def _update_total_mips(self) -> None:
        s = self.state
        s.total_mips = (
            s.original_cpu_alive * s.original_cpu_mips
            + s.replacement_cpu_count * s.replacement_cpu_mips
            + s.fpga_alive * s.fpga_mips
            + s.neuromorphic_alive * s.neuromorphic_mips_equiv
        )
        if s.peak_mips > 0:
            s.compute_ratio = s.total_mips / s.peak_mips
        else:
            s.compute_ratio = 0.0

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Original CPU failures ---
        failed_originals = 0
        for _ in range(s.original_cpu_alive):
            if self._rng.random() < (1.0 / s.original_mtbf_years):
                failed_originals += 1
        s.original_cpu_alive = max(0, s.original_cpu_alive - failed_originals)

        if failed_originals > 0:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"{failed_originals} original CPU(s) failed. "
                    f"Remaining: {s.original_cpu_alive}/{s.original_cpu_count}"
                ),
                "subsystem": "computing_regression",
            })

        # --- FPGA failures (radiation-hardened MOS ICs) ---
        # MIL-HDBK-217F Sec 5.1: MOS digital gate array, 1k-3k gates
        # FPGA MTBF in space: lambda_b * pi_E(S_F) -> ~54 yr per chip
        _fpga_mtbf_yr = get_mtbf_years("fpga", "space_flight")
        _fpga_annual_p = 1.0 / max(1.0, _fpga_mtbf_yr)
        for _ in range(s.fpga_alive):
            if self._rng.random() < _fpga_annual_p:
                s.fpga_alive -= 1
        s.fpga_alive = max(0, s.fpga_alive)

        # --- Neuromorphic chip failures (analog IC, very robust) ---
        # MIL-HDBK-217F Sec 5.1: analog/linear IC, lower gate count
        # Neuromorphic chips are simpler analog circuits; use ic_digital
        # with 0.5x derating for lower complexity -> ~108 yr MTBF
        _neuro_mtbf_yr = get_mtbf_years("ic_digital", "space_flight") * 2.0
        _neuro_annual_p = 1.0 / max(1.0, _neuro_mtbf_yr)
        for _ in range(s.neuromorphic_alive):
            if self._rng.random() < _neuro_annual_p:
                s.neuromorphic_alive -= 1
        s.neuromorphic_alive = max(0, s.neuromorphic_alive)

        # --- Fabricate replacement CPUs ---
        if s.original_cpu_alive < s.original_cpu_count:
            new_cpus = min(s.replacement_fab_rate_per_year, failed_originals + 2)
            s.replacement_cpu_count += new_cpus
            if new_cpus > 0:
                events.append({
                    "year": mission_year, "severity": "INFO",
                    "message": (
                        f"Fabricated {new_cpus} replacement CPU(s) "
                        f"(500nm process, {s.replacement_cpu_mips} MIPS each). "
                        f"Total replacements: {s.replacement_cpu_count}"
                    ),
                    "subsystem": "computing_regression",
                })

        # --- Replacement CPU failures too ---
        failed_replacements = 0
        for _ in range(s.replacement_cpu_count):
            if self._rng.random() < (1.0 / s.replacement_mtbf_years):
                failed_replacements += 1
        s.replacement_cpu_count = max(0, s.replacement_cpu_count - failed_replacements)

        # --- Update totals ---
        self._update_total_mips()

        # --- ARIA optimization level ---
        if s.compute_ratio > 0.5:
            s.aria_optimization_level = 1.0
        elif s.compute_ratio > 0.1:
            s.aria_optimization_level = 0.3 + 0.7 * (
                (s.compute_ratio - 0.1) / 0.4
            )
        else:
            s.aria_optimization_level = max(0.05, s.compute_ratio * 3.0)

        # --- Severity events (latched tiers) ---
        if s.compute_ratio < s.critical_compute_threshold:
            if not getattr(self, "_compute_crit_latched", False):
                events.append({
                    "year": mission_year, "severity": "CRITICAL",
                    "message": (
                        f"Computing below critical threshold: "
                        f"{s.compute_ratio:.1%} of peak. "
                        f"ARIA degraded to {s.aria_optimization_level:.1%} capability."
                    ),
                    "subsystem": "computing_regression",
                })
                self._compute_crit_latched = True
                self._compute_warn_latched = False
        elif s.compute_ratio < 0.5:
            self._compute_crit_latched = False
            if not getattr(self, "_compute_warn_latched", False):
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": (
                        f"Computing at {s.compute_ratio:.1%} of peak. "
                        f"ARIA operating at {s.aria_optimization_level:.1%}."
                    ),
                    "subsystem": "computing_regression",
                })
                self._compute_warn_latched = True
        else:
            self._compute_crit_latched = False
            self._compute_warn_latched = False

        return events


# ════════════════════════════════════════════════════════════════
#  4. SEAL & GASKET LIFECYCLE
# ════════════════════════════════════════════════════════════════

@dataclass
class SealGasketState:
    """Tracks the ship's pressure seal inventory and leak rate."""
    # Inventory
    # EPDM and Viton O-ring rated life in radiation: 10–20 yr depending on
    # total ionizing dose and temperature (ECSS-Q-70-71C §5.3; Sheridan 1998
    # *J Spacecraft Rockets* 35 826 radiation-aged silicone data). 15 yr
    # is conservative mid-estimate.
    total_seals: int = 10_000
    seal_rated_life_years: float = 15.0   # ECSS-Q-70-71C §5.3 mid-range
    elastomer_rated_life_years: float = 20.0  # EPDM — ECSS-Q-70-71C §5.3 upper bound

    # Age tracking (simplified: cohorts by installation decade)
    seal_age_distribution: list[float] = field(default_factory=lambda: [0.0] * 10_000)

    # Manufacturing
    polymer_seals_per_year: int = 600     # ESTIMATE — ARIA manufacturing capacity
    fluoroelastomer_available: bool = False  # Cannot make Viton on ship
    seal_inventory_spare: int = 5_000      # ESTIMATE — initial spare inventory

    # Failure and leak tracking
    failed_seals: int = 0
    replaced_seals: int = 0
    active_leaks: int = 0
    atmosphere_loss_pct_yr: float = 0.0
    cumulative_atmo_loss_pct: float = 0.0

    # Polymer replacement seals (no PTFE binders, lower compression-set
    # resistance) rated at ~70 % of Viton life; conservative per
    # Sheridan 1998 *J Spacecraft Rockets* 35 826 comparative data.
    polymer_seal_life_factor: float = 0.7  # Sheridan 1998 J Spacecraft Rockets 35 826


class SealGasketSimulator:
    """Models the lifecycle of ~10,000 pressure seals throughout the ship.

    Seals degrade from compression set, radiation embrittlement, and thermal
    cycling. The ship can manufacture polymer replacements but not
    fluoroelastomer (Viton), so replacement seals are lower quality.
    Failed seals cause atmosphere leaks that compound over time.
    """

    def __init__(self, total_seals: int = 10_000,
                 seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = SealGasketState(
            total_seals=total_seals,
            seal_age_distribution=[0.0] * total_seals,
        )

    def _seal_failure_prob(self, age: float, is_replacement: bool = False) -> float:
        """Probability a seal fails this year given its age."""
        s = self.state
        rated_life = s.seal_rated_life_years
        if is_replacement:
            rated_life *= s.polymer_seal_life_factor

        # Failure probability ramps up as (age/rated_life)^2
        ratio = age / rated_life
        if ratio < 0.5:
            return 0.001  # Very low during useful life
        elif ratio < 1.0:
            return 0.01 * ratio ** 2
        else:
            # Past rated life: rapidly increasing failure
            return min(0.5, 0.05 * ratio ** 2)

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Age all seals ---
        new_failures = 0
        for i in range(len(s.seal_age_distribution)):
            s.seal_age_distribution[i] += 1.0
            age = s.seal_age_distribution[i]
            is_replacement = age < mission_year * 0.5  # Rough heuristic
            if self._rng.random() < self._seal_failure_prob(age, is_replacement):
                new_failures += 1
                s.seal_age_distribution[i] = -1  # Mark as failed

        # --- Remove failed seals and replace ---
        failed_indices = [
            i for i, a in enumerate(s.seal_age_distribution) if a < 0
        ]
        replacements_available = min(
            len(failed_indices),
            s.polymer_seals_per_year,
            s.seal_inventory_spare + s.polymer_seals_per_year,
        )

        replaced_this_year = 0
        for idx in failed_indices[:replacements_available]:
            s.seal_age_distribution[idx] = 0.0  # Fresh seal
            replaced_this_year += 1
            if s.seal_inventory_spare > 0:
                s.seal_inventory_spare -= 1

        unreplaced = len(failed_indices) - replaced_this_year
        # Unreplaced seals stay marked but we set them to a high age
        for idx in failed_indices[replacements_available:]:
            s.seal_age_distribution[idx] = 999.0  # Permanently failed

        s.failed_seals += new_failures
        s.replaced_seals += replaced_this_year
        s.active_leaks = max(0, s.active_leaks + unreplaced - replaced_this_year)
        s.active_leaks = max(s.active_leaks, 0)

        # --- Atmosphere loss ---
        # ESTIMATE: 0.01%/yr per active leak seal — no published spacecraft data for
        # multi-seal leak accumulation; scaled from ISS O2 make-up rate ~0.003 kg/day
        leak_rate_per_seal = 0.0001  # ESTIMATE — 0.01% atmosphere loss per active failed seal/yr
        s.atmosphere_loss_pct_yr = s.active_leaks * leak_rate_per_seal
        s.cumulative_atmo_loss_pct += s.atmosphere_loss_pct_yr

        # --- Events ---
        # Seal failures are routine wear. Yearly telemetry stays INFO unless
        # the ship can't keep up with them (leaks growing faster than repairs).
        if new_failures > 0:
            keeping_up = replaced_this_year >= new_failures * 0.9
            severity = "INFO" if keeping_up else "WARNING"
            if s.active_leaks > 500 and not keeping_up:
                severity = "CRITICAL"
            events.append({
                "year": mission_year, "severity": severity,
                "message": (
                    f"Seal failures: {new_failures} this year, "
                    f"{replaced_this_year} replaced. "
                    f"Active leaks: {s.active_leaks}. "
                    f"Atmo loss: {s.atmosphere_loss_pct_yr:.4f}%/yr "
                    f"(cumulative: {s.cumulative_atmo_loss_pct:.3f}%)"
                ),
                "subsystem": "seal_gasket",
            })

        # Latched: cumulative atmo loss only grows, so fire once per tier.
        if not hasattr(self, "_atmo_tier"):
            self._atmo_tier = 0
        if s.cumulative_atmo_loss_pct > 5.0 and self._atmo_tier < 1:
            self._atmo_tier = 1
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"Cumulative atmosphere loss {s.cumulative_atmo_loss_pct:.2f}% "
                    f"exceeds 5% threshold. Pressure integrity compromised."
                ),
                "subsystem": "seal_gasket",
            })

        if s.seal_inventory_spare <= 0 and replaced_this_year < new_failures:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    "Seal spare inventory exhausted. "
                    "Relying entirely on polymer fabrication."
                ),
                "subsystem": "seal_gasket",
            })

        return events


# ════════════════════════════════════════════════════════════════
#  5. CATALYST LIFECYCLE (Sabatier, Electrolysis)
# ════════════════════════════════════════════════════════════════

@dataclass
class CatalystLifecycleState:
    """Tracks catalyst activity for ECLSS chemical processes."""
    # Sabatier catalyst (Ru/Al2O3)
    # Methanation Ru/Al2O3 activity decay ~2 %/yr under continuous CO₂+H₂
    # feed at 250–350 °C (Stangeland et al. 2017 *Energy Conv Manag*
    # 152 204, Table 2 long-term TOS stability data).
    sabatier_activity: float = 1.0         # 0-1, fraction of peak
    sabatier_decay_rate: float = 0.02      # Stangeland 2017 Table 2 TOS rate
    sabatier_mass_kg: float = 30.0         # ESTIMATE — ARIA ECLSS sizing
    sabatier_sulfur_poisoning: float = 0.0  # Accumulated poison fraction
    sabatier_coke_buildup: float = 0.0      # Carbon deposition

    # Electrolysis electrodes (Pt/Ir)
    # PEM water electrolysis Pt/C anode activity loss ~0.5–2 %/yr per
    # Babic et al. 2017 *J Electrochem Soc* 164 F387 (§3.4 degradation
    # rate review). 1 %/yr is conservative mid-range.
    electrolysis_activity: float = 1.0
    electrolysis_decay_rate: float = 0.01   # Babic 2017 J Electrochem Soc 164 F387
    electrolysis_electrode_mass_kg: float = 20.0  # ESTIMATE — ARIA ECLSS sizing
    platinum_remaining_pct: float = 100.0
    iridium_alternative_active: bool = False

    # Regeneration
    # Sabatier coke removal by H₂ treatment at 500 °C recovers ~80 % of
    # lost activity (Stangeland 2017 Table 3 regeneration data).
    regeneration_count: int = 0
    regeneration_recovery: float = 0.80     # Stangeland 2017 Table 3
    regeneration_interval_years: int = 10   # ESTIMATE — conservative ARIA cycle
    last_regeneration_year: float = 0.0
    max_regenerations: int = 50             # ESTIMATE — no long-run data beyond ~30 cycles

    # ECLSS impact
    co2_conversion_efficiency: float = 1.0
    water_recycling_efficiency: float = 1.0
    o2_production_efficiency: float = 1.0


class CatalystLifecycleSimulator:
    """Models degradation and regeneration of ECLSS catalysts.

    Sabatier reaction (CO2 + 4H2 -> CH4 + 2H2O) uses Ru/Al2O3 catalyst
    that poisons from trace sulfur and loses activity ~2%/year. Heat
    regeneration at 500C recovers ~80% but with diminishing returns.
    Electrolysis electrodes (Pt) degrade ~1%/year.

    Without catalysts: CO2 scrubbing, water recycling, and O2 production
    all fail — a life support emergency.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = CatalystLifecycleState()

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # --- Sabatier catalyst degradation ---
        # Sulfur poisoning: small random increments from trace atmosphere contaminants
        sulfur_increment = self._rng.gauss(0.003, 0.001)
        s.sabatier_sulfur_poisoning = min(
            1.0, s.sabatier_sulfur_poisoning + max(0, sulfur_increment)
        )

        # Coke buildup from incomplete conversion
        coke_increment = 0.001 * (1.0 + (1.0 - s.sabatier_activity))
        s.sabatier_coke_buildup = min(1.0, s.sabatier_coke_buildup + coke_increment)

        # Combined activity decay
        poison_factor = 1.0 - 0.5 * s.sabatier_sulfur_poisoning
        coke_factor = 1.0 - 0.3 * s.sabatier_coke_buildup
        base_decay = math.exp(-s.sabatier_decay_rate)
        s.sabatier_activity *= base_decay * poison_factor * coke_factor
        s.sabatier_activity = max(0.0, min(1.0, s.sabatier_activity))

        # --- Electrolysis electrode degradation ---
        s.electrolysis_activity *= math.exp(-s.electrolysis_decay_rate)
        s.platinum_remaining_pct *= (1.0 - s.electrolysis_decay_rate)

        # Switch to iridium when platinum gets low
        if s.platinum_remaining_pct < 30.0 and not s.iridium_alternative_active:
            s.iridium_alternative_active = True
            s.electrolysis_activity = min(1.0, s.electrolysis_activity + 0.3)
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": (
                    "Switched to iridium electrolysis electrodes. "
                    f"Platinum at {s.platinum_remaining_pct:.1f}%."
                ),
                "subsystem": "catalyst_lifecycle",
            })

        # --- Regeneration cycle ---
        years_since_regen = mission_year - s.last_regeneration_year
        if years_since_regen >= s.regeneration_interval_years:
            if s.regeneration_count < s.max_regenerations:
                # Recovery with diminishing returns
                diminishing = max(0.3, s.regeneration_recovery * (
                    1.0 - 0.005 * s.regeneration_count
                ))
                lost_activity = 1.0 - s.sabatier_activity
                recovered = lost_activity * diminishing
                s.sabatier_activity = min(1.0, s.sabatier_activity + recovered)

                # Regeneration partially clears coke and sulfur
                s.sabatier_coke_buildup *= 0.3  # Clears 70% of coke
                s.sabatier_sulfur_poisoning *= 0.5  # Clears 50% of sulfur

                s.regeneration_count += 1
                s.last_regeneration_year = mission_year
                events.append({
                    "year": mission_year, "severity": "INFO",
                    "message": (
                        f"Catalyst regeneration #{s.regeneration_count}: "
                        f"Sabatier activity recovered to {s.sabatier_activity:.1%}. "
                        f"Recovery factor: {diminishing:.1%}"
                    ),
                    "subsystem": "catalyst_lifecycle",
                })
            else:
                events.append({
                    "year": mission_year, "severity": "CRITICAL",
                    "message": (
                        "Maximum regeneration cycles exhausted. "
                        "Catalyst cannot be further recovered."
                    ),
                    "subsystem": "catalyst_lifecycle",
                })

        # --- ECLSS efficiency impact ---
        s.co2_conversion_efficiency = s.sabatier_activity
        s.water_recycling_efficiency = (
            0.5 * s.sabatier_activity + 0.5 * s.electrolysis_activity
        )
        s.o2_production_efficiency = s.electrolysis_activity

        # --- Severity events (latched tiers) ---
        if s.sabatier_activity < 0.3:
            if not getattr(self, "_sab_crit_latched", False):
                events.append({
                    "year": mission_year, "severity": "CRITICAL",
                    "message": (
                        f"Sabatier catalyst critically degraded: "
                        f"{s.sabatier_activity:.1%} activity. "
                        f"CO2 conversion failing."
                    ),
                    "subsystem": "catalyst_lifecycle",
                })
                self._sab_crit_latched = True
                self._sab_warn_latched = False
        elif s.sabatier_activity < 0.6:
            self._sab_crit_latched = False
            if not getattr(self, "_sab_warn_latched", False):
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": (
                        f"Sabatier catalyst degraded: {s.sabatier_activity:.1%}. "
                        f"Sulfur: {s.sabatier_sulfur_poisoning:.1%}, "
                        f"Coke: {s.sabatier_coke_buildup:.1%}"
                    ),
                    "subsystem": "catalyst_lifecycle",
                })
                self._sab_warn_latched = True
        else:
            self._sab_crit_latched = False
            self._sab_warn_latched = False

        if s.electrolysis_activity < 0.3 and not getattr(self, "_elec_low_latched", False):
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"Electrolysis critically degraded: "
                    f"{s.electrolysis_activity:.1%}. "
                    f"O2 production compromised."
                ),
                "subsystem": "catalyst_lifecycle",
            })
            self._elec_low_latched = True
        elif s.electrolysis_activity >= 0.35:
            self._elec_low_latched = False

        return events


# ════════════════════════════════════════════════════════════════
#  6. GRAVITY-DEPENDENT FERTILITY
# ════════════════════════════════════════════════════════════════

@dataclass
class GravityFertilityState:
    """Tracks population dynamics under reduced gravity fertility effects."""
    # Habitat gravity
    habitat_gravity_g: float = 0.56  # Ship's centrifugal gravity

    # Population
    population: int = 50
    women_of_childbearing_age: int = 12  # ~25% of population
    children_under_15: int = 5
    elderly_over_60: int = 5

    # Fertility parameters
    # General fertility rate ~0.06/woman/yr assumes a TFR ≈ 2.1 over
    # ~35 childbearing years → rate per year ≈ 2.1/35 = 0.06.
    # (United Nations World Fertility Patterns 2015, replacement TFR
    # high-income nations.)
    base_fertility_rate: float = 0.06  # UN World Fertility Patterns 2015
    gravity_fertility_factor: float = 1.0  # Computed from gravity
    effective_fertility_rate: float = 0.06

    # Centrifuge
    centrifuge_available: bool = True
    centrifuge_g: float = 1.0
    centrifuge_births: int = 0
    natural_births: int = 0
    # 30 % complication reduction from 1g centrifuge delivery is an
    # ESTIMATE — rodent microgravity obstetrics show elevated complications,
    # but no human data exists for reduced-gravity birth outcomes
    # (Ronca & Alberts 2000 *Am J Physiol Regul Integr Comp Physiol* 279).
    centrifuge_benefit: float = 0.3  # ESTIMATE — Ronca & Alberts 2000 (rodent analogue)

    # Outcomes
    total_births: int = 0
    total_deaths: int = 0
    birth_complications: int = 0
    implantation_failures: int = 0
    fetal_bone_defects: int = 0

    # Population trajectory
    growth_rate: float = 0.0
    # Minimum viable population: Frankham 1995 Annu Rev Genet 29 305: genetic MVP ~50;
    # functional/social MVP for mission ops ESTIMATE ≈ 20 (half genetic MVP, skill constraints)
    minimum_viable_population: int = 20   # ESTIMATE — functional MVP for ship operations
    population_collapse_risk: float = 0.0

    # Scenario
    gravity_scenario: str = "moderate"  # "best", "moderate", "worst"


class GravityFertilitySimulator:
    """Models reproduction under reduced gravity with population dynamics.

    0.56g fertility is completely untested. Three scenarios:
    - Best case: 80% of 1g fertility
    - Moderate case: 55% of 1g fertility (default)
    - Worst case: 30% of 1g fertility (population collapse likely)

    A medical centrifuge provides 1g for delivery, reducing
    birth complications but not addressing implantation/gestation.
    """

    # Mortality rates by age cohort (WHO 2019 life tables, high-income nations)
    # Source: WHO Life Tables 2019 (https://www.who.int/data/gho/data/themes/mortality-and-global-health)
    CHILD_MORTALITY = 0.001    # WHO 2019 Life Tables: <15 high-income: ~1/1000/yr
    ADULT_MORTALITY = 0.003    # WHO 2019 Life Tables: 15-60 high-income: ~3/1000/yr
    ELDERLY_MORTALITY = 0.045  # WHO 2019 Life Tables: 65+ high-income: ~45/1000/yr

    def __init__(self, population: int = 50,
                 gravity_g: float = 0.56,
                 scenario: str = "moderate",
                 seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        women = max(1, int(population * 0.25))
        children = max(0, int(population * 0.10))
        elderly = max(0, int(population * 0.10))
        self.state = GravityFertilityState(
            population=population,
            women_of_childbearing_age=women,
            children_under_15=children,
            elderly_over_60=elderly,
            habitat_gravity_g=gravity_g,
            gravity_scenario=scenario,
        )
        self._update_gravity_factor()

    def _gravity_fertility_factor(self, g: float) -> float:
        """Logistic model for gravity's effect on fertility.

        Returns fraction of 1g fertility achievable at given gravity.
        Centered at 0.5g with steepness depending on scenario.
        """
        scenario = self.state.gravity_scenario
        # All logistic parameters are ESTIMATE — no human data for fertility at 0.56g.
        # Rodent data (Ronca & Alberts 2000) shows reduced implantation in ~0.3g.
        if scenario == "best":
            # Optimistic: gentle decline — ESTIMATE
            k = 4.0       # ESTIMATE: shallow sigmoid steepness
            midpoint = 0.25  # ESTIMATE: fertility halved at 0.25g
        elif scenario == "worst":
            # Pessimistic: steep decline — ESTIMATE
            k = 8.0       # ESTIMATE: steep sigmoid steepness
            midpoint = 0.6   # ESTIMATE: fertility halved at 0.6g
        else:
            # Moderate: middle ground — ESTIMATE
            k = 6.0       # ESTIMATE: moderate sigmoid steepness
            midpoint = 0.4   # ESTIMATE: fertility halved at 0.4g

        factor = 1.0 / (1.0 + math.exp(-k * (g - midpoint)))
        return max(0.05, min(1.0, factor))

    def _update_gravity_factor(self) -> None:
        s = self.state
        s.gravity_fertility_factor = self._gravity_fertility_factor(
            s.habitat_gravity_g
        )
        s.effective_fertility_rate = (
            s.base_fertility_rate * s.gravity_fertility_factor
        )

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        if s.population <= 0:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": "Population extinct.",
                "subsystem": "gravity_fertility",
            })
            return events

        self._update_gravity_factor()

        # --- Births ---
        births = 0
        complications = 0
        implant_fails = 0
        bone_defects = 0

        for _ in range(s.women_of_childbearing_age):
            # Attempt conception
            if self._rng.random() < s.effective_fertility_rate:
                # Implantation check (gravity-dependent)
                implant_prob = 0.7 + 0.3 * s.gravity_fertility_factor
                if self._rng.random() < implant_prob:
                    # Fetal development check
                    bone_ok = self._rng.random() < (
                        0.8 + 0.2 * s.habitat_gravity_g
                    )
                    if not bone_ok:
                        bone_defects += 1

                    # Delivery
                    if s.centrifuge_available:
                        complication_prob = 0.05  # Low with 1g centrifuge
                        s.centrifuge_births += 1
                    else:
                        complication_prob = 0.15 * (
                            1.0 + (1.0 - s.habitat_gravity_g)
                        )
                        s.natural_births += 1

                    if self._rng.random() < complication_prob:
                        complications += 1

                    births += 1
                else:
                    implant_fails += 1

        s.total_births += births
        s.birth_complications += complications
        s.implantation_failures += implant_fails
        s.fetal_bone_defects += bone_defects
        s.children_under_15 += births

        # --- Deaths ---
        child_deaths = sum(
            1 for _ in range(s.children_under_15)
            if self._rng.random() < self.CHILD_MORTALITY
        )
        adult_count = max(0, (
            s.population - s.children_under_15 - s.elderly_over_60
        ))
        adult_deaths = sum(
            1 for _ in range(adult_count)
            if self._rng.random() < self.ADULT_MORTALITY
        )
        elderly_deaths = sum(
            1 for _ in range(s.elderly_over_60)
            if self._rng.random() < self.ELDERLY_MORTALITY
        )
        total_deaths = child_deaths + adult_deaths + elderly_deaths
        s.total_deaths += total_deaths

        # --- Update population ---
        s.population = s.population + births - total_deaths
        s.population = max(0, s.population)

        # Cohort rebalancing (simplified)
        s.children_under_15 = max(0, s.children_under_15 - child_deaths)
        s.elderly_over_60 = max(0, s.elderly_over_60 - elderly_deaths)
        # Age transitions every 15 years for children → adult
        if mission_year % 15 < 1 and s.children_under_15 > 0:
            graduating = max(1, s.children_under_15 // 3)
            s.children_under_15 -= graduating
            # Half become women of childbearing age
            new_women = graduating // 2
            s.women_of_childbearing_age += new_women
        # Age transitions: adults → elderly every 30 years
        if mission_year % 30 < 1 and s.women_of_childbearing_age > 2:
            aging = max(1, s.women_of_childbearing_age // 4)
            s.women_of_childbearing_age -= aging
            s.elderly_over_60 += aging

        # Ensure cohorts don't exceed population
        total_cohort = (
            s.children_under_15 + s.women_of_childbearing_age + s.elderly_over_60
        )
        if total_cohort > s.population and s.population > 0:
            scale = s.population / total_cohort
            s.children_under_15 = int(s.children_under_15 * scale)
            s.elderly_over_60 = int(s.elderly_over_60 * scale)
            s.women_of_childbearing_age = max(
                0, s.population - s.children_under_15 - s.elderly_over_60
            )

        # --- Growth rate ---
        if s.population > 0:
            s.growth_rate = (births - total_deaths) / s.population
        else:
            s.growth_rate = 0.0

        # --- Population collapse risk ---
        if s.population < s.minimum_viable_population:
            s.population_collapse_risk = 1.0 - (
                s.population / s.minimum_viable_population
            )
        else:
            s.population_collapse_risk = 0.0

        # --- Events ---
        if births > 0:
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": (
                    f"{births} birth(s) (fertility factor: "
                    f"{s.gravity_fertility_factor:.1%} of 1g). "
                    f"Complications: {complications}. "
                    f"Population: {s.population}"
                ),
                "subsystem": "gravity_fertility",
            })

        if implant_fails > 0:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"{implant_fails} implantation failure(s) — "
                    f"gravity-dependent effect at {s.habitat_gravity_g}g."
                ),
                "subsystem": "gravity_fertility",
            })

        if s.population < s.minimum_viable_population:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"Population {s.population} below minimum viable "
                    f"({s.minimum_viable_population}). "
                    f"Collapse risk: {s.population_collapse_risk:.0%}"
                ),
                "subsystem": "gravity_fertility",
            })

        if bone_defects > 0:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"{bone_defects} fetal bone formation defect(s) — "
                    f"reduced gravity effect."
                ),
                "subsystem": "gravity_fertility",
            })

        return events
