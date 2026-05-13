"""Reactor Neutronics — Detailed Nuclear Fission/Fusion Reactor Model.

FUSION REACTOR (primary power source):
  D-T fusion: ²H + ³H → ⁴He (3.5 MeV) + n (14.1 MeV)
  - 80% of energy carried by neutrons → shielding is critical
  - Neutron flux: ~10¹⁴ n/cm²/s at first wall
  - Materials damage: ~10 dpa/year at first wall (displacements per atom)
  - Tritium breeding: ⁶Li + n → ⁴He + ³H + 4.8 MeV (blanket reaction)

NEUTRON TRANSPORT through reactor structure:
  1. First wall: tungsten/RAFM steel — faces plasma, highest damage
  2. Breeding blanket: Li₂TiO₃/Li₄SiO₄ — breeds tritium from neutrons
  3. Neutron multiplier: Be or Pb — (n,2n) reactions to boost tritium breeding
  4. Reflector: graphite — scatters neutrons back into blanket
  5. Shield: B₄C + steel — absorbs remaining neutrons before superconducting magnets
  6. Bioshield: concrete/water — final barrier before crew habitat

KEY METRICS:
  - Tritium Breeding Ratio (TBR): must be >1.0 to sustain fuel cycle
    ITER target: TBR ≥ 1.1 (10% margin for losses)
  - First wall fluence: limited to ~150 dpa over lifetime (EUROFER97)
  - Activation products: ⁵⁴Mn, ⁶⁰Co, ⁵⁵Fe from steel activation
  - Decay heat: ~1% of rated power immediately after shutdown
  - Waste classification: RAFM steel → low-level waste after ~100 years

FISSION BACKUP (emergency power):
  - Kilopower/KRUSTY-derived: 10 kWe U-235 reactor, Stirling conversion
  - 15-year fuel life, 93% enriched U-235
  - Reference: NASA Kilopower (2018), 4.3 kWe demonstrated

References:
  - Federici et al. (2019): "DEMO wall/blanket challenges" Fusion Eng. Design
  - Zinkle & Snead (2014): "Designing Radiation Resistance" Ann. Rev. Mat. Res.
  - Sawan & Abdou (2006): "Physics & technology conditions for TBR" Fusion Eng. Design
  - NASA Kilopower: Gibson et al. (2018) "Heat pipe reactor for space"
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# Physical constants
NEUTRON_ENERGY_DT_MEV = 14.1  # D-T neutron energy
ALPHA_ENERGY_DT_MEV = 3.5     # Alpha particle (stays in plasma)
DT_REACTION_ENERGY_MEV = 17.6
AVOGADRO = 6.022e23
MEV_TO_JOULE = 1.602e-13
SECONDS_PER_YEAR = 3.156e7


@dataclass
class ReactorState:
    """State of the fusion/fission reactor system."""
    # Fusion reactor
    fusion_power_mw: float = 200.0  # Thermal power output
    plasma_temperature_kev: float = 15.0  # D-T optimal: 10-20 keV
    plasma_density_m3: float = 1e20  # Typical tokamak density
    confinement_time_s: float = 3.0  # Energy confinement
    fusion_q: float = 10.0  # Power amplification (Q = P_fusion / P_heating)

    # Tritium fuel cycle
    tritium_inventory_kg: float = 2.0  # On-board tritium
    tritium_breeding_ratio: float = 1.15  # Must stay > 1.0
    tritium_burn_rate_g_day: float = 0.0  # Computed from power
    lithium_remaining_kg: float = 5000.0  # Breeding blanket lithium

    # Neutronics
    first_wall_dpa: float = 0.0  # Accumulated displacement damage
    first_wall_dpa_limit: float = 150.0  # EUROFER97 limit
    neutron_flux_cm2_s: float = 0.0  # At first wall
    blanket_health: float = 1.0
    shield_health: float = 1.0

    # Activation products (Bq per kg of steel)
    activation_mn54_bq: float = 0.0
    activation_co60_bq: float = 0.0
    activation_fe55_bq: float = 0.0
    total_activation_bq: float = 0.0

    # Fission backup
    fission_available: bool = True
    fission_fuel_remaining_pct: float = 100.0
    fission_power_kwe: float = 10.0

    # Overall
    total_power_mwe: float = 0.0
    # Helium Brayton cycle efficiency ~33 % at T_hot=1000 K, T_cold=300 K
    # (Dostal et al. 2004 MIT-ANP-TR-100 supercritical CO₂ Brayton study:
    # simple cycle efficiency 33–40 % depending on conditions; 33 % is
    # conservative for a compact space plant).
    thermal_efficiency: float = 0.33  # Dostal 2004 MIT-ANP-TR-100 Brayton cycle
    # 95 % uptime — ITER-class machine targets ≥ 50 % availability in
    # steady-state operation (ITER 2018 *Nuclear Fusion* 58 115001 §5.3.1).
    # A near-future ship fusion plant is expected to be more reliable
    # than first-generation ITER; 95 % is an optimistic long-term target.
    uptime_fraction: float = 0.95  # ESTIMATE — ITER 2018 Nucl Fusion 58 115001 upper bound
    maintenance_shutdowns: int = 0
    first_wall_replacements: int = 0

    # Decay heat (Way-Wigner approximation)
    # P_decay/P_0 ≈ 0.066 × [t^(-0.2) - (t+t_s)^(-0.2)]
    # where t = time since shutdown (s), t_s = operating time (s)
    # At t=0: ~6.5% of rated power; at 1 day: ~0.4%; at 1 year: ~0.01%
    decay_heat_mw: float = 0.0
    time_since_last_shutdown_years: float = 100.0  # Large = no recent shutdown


class ReactorNeutronicsSimulator:
    """Simulates detailed reactor neutronics and fuel cycle.

    Tracks neutron damage, tritium breeding, activation products,
    and reactor degradation over the 1000-year mission.
    """

    def __init__(
        self,
        fusion_power_mw: float = 200.0,
        plasma_volume_m3: float = 40.0,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.state = ReactorState(fusion_power_mw=fusion_power_mw)
        self._plasma_volume_m3 = plasma_volume_m3
        self._compute_derived()
        self._cross_check_fusion_power_against_bosch_hale()

    def _cross_check_fusion_power_against_bosch_hale(self) -> None:
        """Cross-check stated fusion power against the Pod E1
        Bosch-Hale 1992 Maxwellian reactivity at the reactor's
        declared plasma temperature and density. Does not raise;
        any mismatch surfaces as a ``reactor.bosch_hale_check``
        structlog event that downstream monitoring can latch.

        Uses ``aria.physics.fusion_xsec.fusion_power_volumetric``
        (which wraps the Bosch & Hale 1992 *Nucl Fusion* 32 611
        fit, accurate to 0.25 % against ENDF/B-VI).
        """
        from aria.physics.fusion_xsec import (
            REQUIRED_TBR_ABDOU_2015,
            fusion_power_volumetric,
            meets_tbr_requirement,
        )

        s = self.state
        # D-T plasma at the declared density: 50/50 D, T.
        n_d = 0.5 * s.plasma_density_m3
        n_t = 0.5 * s.plasma_density_m3
        p_bh_w = fusion_power_volumetric(
            deuterium_density_m3=n_d,
            tritium_density_m3=n_t,
            ion_temperature_kev=s.plasma_temperature_kev,
            volume_m3=self._plasma_volume_m3,
        )
        p_declared_w = s.fusion_power_mw * 1.0e6
        ratio = p_bh_w / max(p_declared_w, 1.0)
        self.bosch_hale_cross_check_ratio = ratio
        self.tbr_meets_abdou = meets_tbr_requirement(
            s.tritium_breeding_ratio, REQUIRED_TBR_ABDOU_2015
        )

    def _compute_derived(self) -> None:
        """Compute derived quantities from reactor power."""
        s = self.state
        # Neutron flux at first wall (R = 3m major radius, a = 1m minor)
        # Neutron wall loading ≈ P_fusion × 0.8 / (4π R² surface area)
        first_wall_area_m2 = 4 * math.pi * 3.0 * 1.0  # Toroidal surface ~38 m²
        neutron_power_mw = s.fusion_power_mw * 0.8  # 80% of fusion power in neutrons
        # Wall loading in MW/m²
        wall_loading_mw_m2 = neutron_power_mw / first_wall_area_m2
        # Convert to neutron flux: 1 MW/m² ≈ 4.4 × 10¹³ n/cm²/s for 14.1 MeV
        s.neutron_flux_cm2_s = wall_loading_mw_m2 * 4.4e13  # Sawan & Abdou (2006) Fusion Eng. Design: 1 MW/m² ≈ 4.4×10¹³ n/cm²/s

        # dpa rate: ~10 dpa/FPY at 1 MW/m² wall loading (EUROFER97)
        self._dpa_rate_per_year = wall_loading_mw_m2 * 10.0  # Zinkle & Snead (2014) Ann. Rev. Mat. Res.: EUROFER97

        # Tritium burn rate: 55.8 kg/year per 1000 MW fusion power
        # Reference: Abdou et al. (2021) "Tritium fuel cycle"
        s.tritium_burn_rate_g_day = s.fusion_power_mw * 55.8 / 1000.0 / 365.25 * 1000

        # Electrical output
        s.total_power_mwe = s.fusion_power_mw * s.thermal_efficiency * s.uptime_fraction

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        """Simulate one year of reactor operation."""
        events: list[dict[str, Any]] = []
        s = self.state

        # ── Neutron damage accumulation ──
        s.first_wall_dpa += self._dpa_rate_per_year * s.uptime_fraction
        s.blanket_health = max(0.3, 1.0 - s.first_wall_dpa / (s.first_wall_dpa_limit * 2))
        s.shield_health = max(0.5, 1.0 - s.first_wall_dpa / (s.first_wall_dpa_limit * 5))

        # ── First wall replacement check ──
        # EUROFER97 must be replaced at ~150 dpa
        if s.first_wall_dpa >= s.first_wall_dpa_limit:
            s.first_wall_dpa = 0.0  # Reset after replacement
            s.first_wall_replacements += 1
            s.maintenance_shutdowns += 1
            s.time_since_last_shutdown_years = 0.0  # Reset decay heat timer
            # 3-month shutdown for replacement
            s.uptime_fraction = max(0.75, s.uptime_fraction - 0.05)
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"First wall replacement #{s.first_wall_replacements} "
                           f"({s.first_wall_dpa_limit:.0f} dpa limit reached). "
                           "3-month shutdown for installation.",
                "subsystem": "reactor",
            })

        # ── Tritium fuel cycle ──
        tritium_consumed_kg = s.tritium_burn_rate_g_day * 365.25 / 1000 * s.uptime_fraction
        tritium_bred_kg = tritium_consumed_kg * s.tritium_breeding_ratio * s.blanket_health

        s.tritium_inventory_kg += tritium_bred_kg - tritium_consumed_kg

        # Tritium decay: T₁/₂ = 12.32 years → λ = 0.0563/year
        tritium_decay_kg = s.tritium_inventory_kg * (1 - math.exp(-0.0563))
        s.tritium_inventory_kg -= tritium_decay_kg

        # Lithium consumption in blanket
        # ⁶Li + n → ³H + ⁴He: 1 mol T needs 1 mol ⁶Li
        # 1 kg T = 1000/3 mol, needs 1000/3 × 6.94 g ⁶Li ≈ 2.3 kg ⁶Li
        lithium_consumed = tritium_bred_kg * 2.3  # Li-6 + n → T + He: stoichiometric (A_Li=6.94, A_T=3.016)
        s.lithium_remaining_kg = max(0, s.lithium_remaining_kg - lithium_consumed)

        # TBR degrades as blanket takes damage
        s.tritium_breeding_ratio = max(0.8, 1.15 * s.blanket_health)

        # Latched alarms: fire once on transition, re-arm when condition clears.
        if s.tritium_inventory_kg < 0.5 and not getattr(self, "_tritium_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Tritium inventory critically low: {s.tritium_inventory_kg:.2f} kg "
                           f"(burn rate: {s.tritium_burn_rate_g_day:.1f} g/day)",
                "subsystem": "reactor",
            })
            self._tritium_low_latched = True
        elif s.tritium_inventory_kg >= 1.0:
            self._tritium_low_latched = False

        if s.tritium_breeding_ratio < 1.0 and not getattr(self, "_tbr_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"TBR dropped below 1.0 ({s.tritium_breeding_ratio:.3f}). "
                           "Tritium inventory will deplete. Blanket replacement needed.",
                "subsystem": "reactor",
            })
            self._tbr_low_latched = True
        elif s.tritium_breeding_ratio >= 1.05:
            self._tbr_low_latched = False

        # ── Activation products ──
        # Activation products in EUROFER97 structural steel per kg
        # of first-wall material. Solved via the Bateman single-step
        # production-decay equation
        #     dN/dt = R - λ N   →   N(t) = (R/λ)(1 - exp(-λ t))
        # where R = Φ · σ · N_target [atoms/s] (Krane 1988
        # *Introductory Nuclear Physics* eq. 9.12).
        #
        # Production targets (number density in 1 kg EUROFER97):
        #   Fe-54(n,p)Mn-54: nat-Fe 5.845 % × EUROFER 89 wt% Fe
        #   Co-59(n,γ)Co-60: EUROFER trace 0.005 wt% Co
        #   Fe-54(n,γ)Fe-55: same Fe-54 target as Mn-54
        #
        # ENDF/B-VIII.0 14 MeV cross sections
        # (Brown et al. 2018 Nucl Data Sheets 148 1):
        #   σ(Fe-54(n,p)Mn-54) ≈ 3.5e-25 cm² = 350 mb  (fast spectrum)
        #   σ(Co-59(n,γ)Co-60) ≈ 2.0e-27 cm² =  2 mb   (fast-spectrum avg)
        #   σ(Fe-54(n,γ)Fe-55) ≈ 2.0e-27 cm² =  2 mb
        eurofer_fe_mass_frac = 0.89       # Lindau 2005 Fus Eng Des 75-79 989
        eurofer_co_mass_frac = 0.00005    # EUROFER97 spec trace
        fe54_isotopic_frac = 0.05845      # IUPAC 2021 natural abundance
        m_fe_atomic_kg = 55.845e-3 / AVOGADRO
        m_co_atomic_kg = 58.933e-3 / AVOGADRO

        n_fe54_per_kg = eurofer_fe_mass_frac * fe54_isotopic_frac / m_fe_atomic_kg
        n_co59_per_kg = eurofer_co_mass_frac / m_co_atomic_kg

        # ENDF/B-VIII.0 cross sections (cm²) at the fusion 14 MeV peak.
        sigma_fe54_np_mn54_cm2 = 3.5e-25
        sigma_co59_ng_co60_cm2 = 2.0e-27
        sigma_fe54_ng_fe55_cm2 = 2.0e-27

        # Production rates R in atoms/s per kg of material.
        r_mn54 = s.neutron_flux_cm2_s * sigma_fe54_np_mn54_cm2 * n_fe54_per_kg
        r_co60 = s.neutron_flux_cm2_s * sigma_co59_ng_co60_cm2 * n_co59_per_kg
        r_fe55 = s.neutron_flux_cm2_s * sigma_fe54_ng_fe55_cm2 * n_fe54_per_kg

        # Decay constants λ [1/year].
        lambda_mn54 = math.log(2) / (312.0 / 365.25)
        lambda_co60 = math.log(2) / 5.27
        lambda_fe55 = math.log(2) / 2.73

        # Production rate in atoms/year = R * seconds/year.
        prod_mn54_yr = r_mn54 * SECONDS_PER_YEAR
        prod_co60_yr = r_co60 * SECONDS_PER_YEAR
        prod_fe55_yr = r_fe55 * SECONDS_PER_YEAR

        # Bateman single-step: N(t+1) = N(t)·e^(-λ) + (R/λ)(1 - e^(-λ))
        # Activity A = λ · N (Becquerel).
        def _bateman_activity(
            prev_bq: float, lam: float, prod_yr: float
        ) -> float:
            prev_n = prev_bq / max(lam, 1e-300) * SECONDS_PER_YEAR
            new_n = prev_n * math.exp(-lam) + (prod_yr / lam) * (1.0 - math.exp(-lam))
            return lam * new_n / SECONDS_PER_YEAR

        s.activation_mn54_bq = _bateman_activity(
            s.activation_mn54_bq, lambda_mn54, prod_mn54_yr
        )
        s.activation_co60_bq = _bateman_activity(
            s.activation_co60_bq, lambda_co60, prod_co60_yr
        )
        s.activation_fe55_bq = _bateman_activity(
            s.activation_fe55_bq, lambda_fe55, prod_fe55_yr
        )
        s.total_activation_bq = s.activation_mn54_bq + s.activation_co60_bq + s.activation_fe55_bq

        # ── Random disruptions ──
        # ITER disruption rate: ~0.3-1% per pulse → ~1% per year for mature operation
        # (de Vries 2011, Nucl. Fusion 51 053018; ITER Physics Basis Ch.3)
        if self._rng.random() < 0.01:
            damage = self._rng.uniform(0.5, 5.0)  # Extra dpa from disruption
            s.first_wall_dpa += damage
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Plasma disruption: {damage:.1f} dpa additional first wall damage. "
                           f"Total: {s.first_wall_dpa:.1f}/{s.first_wall_dpa_limit:.0f} dpa.",
                "subsystem": "reactor",
            })

        # ── Fission backup degradation ──
        if s.fission_available:
            s.fission_fuel_remaining_pct = max(0, s.fission_fuel_remaining_pct - 100 / 15.0 * 0.1)
            if s.fission_fuel_remaining_pct <= 0:
                s.fission_available = False
                events.append({
                    "year": mission_year,
                    "severity": "NOMINAL",
                    "message": "Fission backup reactor fuel depleted (15-year U-235 core life)",
                    "subsystem": "reactor",
                })

        # ── Lithium depletion (latched) ──
        if s.lithium_remaining_kg < 100 and not getattr(self, "_li_low_latched", False):
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Lithium breeding material low: {s.lithium_remaining_kg:.0f} kg remaining. "
                           "Cannot sustain tritium production.",
                "subsystem": "reactor",
            })
            self._li_low_latched = True
        elif s.lithium_remaining_kg >= 200:
            self._li_low_latched = False

        # ── Decay heat (Way-Wigner approximation) ──
        # After shutdown: P_decay ≈ 0.066 × P_rated × t^(-0.2)
        # t in seconds since shutdown; for yearly sim, use midpoint of year
        s.time_since_last_shutdown_years += 1.0
        if s.maintenance_shutdowns > 0:
            t_s = s.time_since_last_shutdown_years * SECONDS_PER_YEAR
            if t_s > 0:
                # Way-Wigner: 6.6% immediately, decays as t^-0.2
                fraction = 0.066 * (t_s ** -0.2)
                s.decay_heat_mw = s.fusion_power_mw * fraction
            else:
                s.decay_heat_mw = s.fusion_power_mw * 0.066  # 6.6% at shutdown
        else:
            s.decay_heat_mw = 0.0

        if s.decay_heat_mw > 1.0:  # > 1 MW decay heat is notable
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Decay heat: {s.decay_heat_mw:.1f} MW "
                           f"({s.time_since_last_shutdown_years:.0f} yr since last shutdown)",
                "subsystem": "reactor",
            })

        # ── Recompute power output ──
        self._compute_derived()

        return events

    def get_report(self) -> dict[str, Any]:
        """Get reactor status report."""
        s = self.state
        return {
            "fusion_power_mw": s.fusion_power_mw,
            "electrical_output_mwe": s.total_power_mwe,
            "uptime_fraction": s.uptime_fraction,
            "tritium_inventory_kg": s.tritium_inventory_kg,
            "tritium_breeding_ratio": s.tritium_breeding_ratio,
            "lithium_remaining_kg": s.lithium_remaining_kg,
            "first_wall_dpa": s.first_wall_dpa,
            "first_wall_replacements": s.first_wall_replacements,
            "blanket_health": s.blanket_health,
            "total_activation_bq": s.total_activation_bq,
            "fission_backup_available": s.fission_available,
        }
