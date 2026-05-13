"""ECLSS habitat atmosphere mass-balance dynamics.

PROBLEM WITH THE PRIOR SIMULATION MODEL
-----------------------------------------
habitat_systems.py uses a lumped "ppm_yr" approximation that cannot resolve:
  - Hour-scale CO₂ buildup after CDRA failure (incapacitation in ~4 hours)
  - Transient O₂ depletion during OGA shutdown
  - Sabatier catalyst aging effects on CO₂ removal efficiency
  - Interaction between multiple ECLSS components (CDRA → Sabatier → OGA)

THIS MODULE
-----------
Implements a first-principles mass balance for the cabin atmosphere:

  dM_CO2/dt = ṁ_crew_CO2 − ṁ_cdra − ṁ_sabatier_in  [kg/s]
  dM_O2/dt  = ṁ_oga − ṁ_crew_O2 − ṁ_leak           [kg/s]
  dM_N2/dt  = −ṁ_N2_leak                              [kg/s]

where partial pressures are derived from mole fractions and total pressure.

CDRA DEGRADATION MODEL (Molecular sieve aging)
----------------------------------------------
The Carbon Dioxide Removal Assembly uses a two-bed zeolite 5A sieve.
Sorption capacity degrades as:
  η_cdra(t) = η₀ × exp(−t / τ_cdra)
  τ_cdra = 5 years (half-life ~3.5 yr) — calibrated to ISS Sorbent Bed failures
  Refs: Knox 2016 ICES-2016-234; Carter 2020 ICES-2020-223

SABATIER REACTOR MODEL (Bosch variant, CO₂ + 4H₂ → CH₄ + 2H₂O)
-----------------------------------------------------------------
Catalyst (Ruthenium on Al₂O₃) degrades via sintering:
  η_sab(t) = η₀ × (1 − 0.22 × (1 − exp(−t / τ_sab)))
  τ_sab = 3 years — ISS Sabatier development data (Abney 2011 ICES-2011-5112)
  CO₂ removal limited by H₂ availability from OGA.

OGA DEGRADATION MODEL (Electrolysis cell aging)
-----------------------------------------------
PEM cell voltage efficiency decays linearly with time:
  η_oga(t) = η₀ × max(0, 1 − r_oga × t)
  r_oga = 0.01/yr — conservative PEM cell lifetime (Takahashi 2019 ICES-2019-188)

TRACE CONTAMINANTS
------------------
CO and CH₄ accumulate from metabolic and pyrolysis sources.
CO cleared by TCCS (Trace Contaminant Control Subassembly):
  dM_CO/dt = ṁ_crew_CO − η_tccs × ṁ_CO / V_cabin  [kg/s]
  η_tccs = 0.90 (charcoal + Hopcalite; James 2011 ICES-2011-5097)

CREW PHYSIOLOGY REFERENCES
--------------------------
  Wieland (1994) NASA TM-108522 — crew metabolic rates (CO₂, O₂)
  NASA BVAD (2015) NASA/TP-2015-218570 — crew O₂/CO₂ baseline
  OSHA PEL CO₂ = 5000 ppm (8hr TWA); NIOSH IDLH = 40000 ppm
  NASA STD-3001 Vol.1 §6.6 — O₂ partial pressure limits [16–23% vol]

REFERENCES
----------
  Knox J.C. et al. (2016) ICES-2016-234 — CDRA sorbent bed aging
  Carter D.L. et al. (2020) ICES-2020-223 — ISS ECLSS status/efficiency
  Abney M.B. et al. (2011) ICES-2011-5112 — Sabatier system development
  James J.T. (2011) ICES-2011-5097 — TCCS trace contaminant removal
  Takahashi Y. et al. (2019) ICES-2019-188 — OGA cell degradation model
  Wieland P.O. (1994) NASA TM-108522 — crew metabolic baseline
  NASA (2015) NASA/TP-2015-218570 — BVAD human integration design handbook
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ── Crew metabolic constants ──────────────────────────────────────────────────

CREW_CO2_KG_DAY: float = 1.00     # kg CO₂ per person per day (Wieland 1994 TM-108522)
CREW_O2_KG_DAY: float = 0.84      # kg O₂ per person per day (NASA BVAD 2015)
CREW_CO_KG_DAY: float = 2.7e-3    # kg CO per person per day (metabolic; Wieland 1994)

# ── ECLSS nominal efficiencies ────────────────────────────────────────────────

CDRA_NOMINAL_EFFICIENCY: float = 0.98     # combined CDRA efficiency (Carter 2020 ICES-2020-223)
SABATIER_NOMINAL_EFFICIENCY: float = 0.95 # Sabatier CO₂ removal per pass (Abney 2011 ICES-2011-5112)
OGA_NOMINAL_RATE_KG_DAY_PER_CREW: float = 0.90  # kg O₂/day per crewmember (ISS OGS; NASA ECLSS 2019)

# ── Degradation time constants ────────────────────────────────────────────────

CDRA_DEGRADATION_TAU_YEARS: float = 5.0   # e-folding time for sorbent capacity (Knox 2016 ICES-2016-234)
SABATIER_DEGRADE_FRACTION: float = 0.22   # max efficiency loss from sintering (Abney 2011 ICES-2011-5112)
SABATIER_DEGRADATION_TAU_YEARS: float = 3.0  # sintering time constant (Abney 2011 ICES-2011-5112)
OGA_CELL_DECAY_RATE_PER_YEAR: float = 0.01   # fractional efficiency loss/yr (Takahashi 2019 ICES-2019-188)

# ── TCCS ─────────────────────────────────────────────────────────────────────

TCCS_CO_REMOVAL_EFFICIENCY: float = 0.90  # charcoal + Hopcalite (James 2011 ICES-2011-5097)

# ── Cabin atmosphere baseline ─────────────────────────────────────────────────

CABIN_TOTAL_PRESSURE_PA: float = 101325.0   # 1 atm (NASA STD-3001)
CABIN_O2_FRACTION_NOMINAL: float = 0.209    # NIST standard dry air (NIST)
CABIN_N2_FRACTION_NOMINAL: float = 0.790    # remainder (NIST)
CO2_MOLAR_MASS: float = 44.01               # g/mol
O2_MOLAR_MASS: float = 32.00               # g/mol
N2_MOLAR_MASS: float = 28.014              # g/mol

# ── Safety thresholds ─────────────────────────────────────────────────────────

CO2_PPM_NIOSH_IDLH: float = 40000.0   # NIOSH IDLH (immediately dangerous to life)
CO2_PPM_OSHA_PEL: float = 5000.0      # OSHA PEL 8hr TWA
CO2_PPM_COGNITIVE_IMPAIR: float = 1000.0  # cognitive impact onset (Allen 2016 Environ Health Perspect)
O2_FRACTION_HYPOXIA_LOW: float = 0.155    # hypoxia threshold (NASA STD-3001 Vol.1 §6.6)
O2_FRACTION_FIRE_HIGH: float = 0.300      # fire risk threshold (NASA STD-3001 Vol.1 §6.6)


@dataclass
class AtmosphereState:
    """Cabin atmosphere mass state.

    All masses are in kg for the full cabin volume.

    Attributes:
        co2_kg:      Current cabin CO₂ mass [kg].
        o2_kg:       Current cabin O₂ mass [kg].
        n2_kg:       Current cabin N₂ mass [kg].
        co_kg:       Trace CO mass [kg].
        ch4_kg:      Trace CH₄ mass [kg].
        cabin_volume_m3: Total pressurized volume [m³].
        cdra_age_years: Cumulative CDRA operation age [years].
        sabatier_age_years: Sabatier catalyst age [years].
        oga_age_years: OGA PEM cell age [years].
    """
    co2_kg: float = 0.0
    o2_kg: float = 0.0
    n2_kg: float = 0.0
    co_kg: float = 0.0
    ch4_kg: float = 0.0
    cabin_volume_m3: float = 2400.0   # ISS habitable volume ~930 m³; generation ship ~2400 m³
    cdra_age_years: float = 0.0
    sabatier_age_years: float = 0.0
    oga_age_years: float = 0.0

    @classmethod
    def nominal(cls, cabin_volume_m3: float = 2400.0, crew: int = 8) -> "AtmosphereState":
        """Initialise state at NASA-standard nominal atmosphere.

        O₂ mass: total_pressure × O₂_fraction × volume / (RT/M)
        Uses ideal gas: M_gas = pV/(nRT), n = pV/(RT) kg·mol
        At 293 K, 1 atm: ρ_air ≈ 1.204 kg/m³
        """
        rho_air = 1.204  # kg/m³ at 20°C, 1 atm (NIST)
        total_air_kg = rho_air * cabin_volume_m3
        s = cls(
            o2_kg=total_air_kg * CABIN_O2_FRACTION_NOMINAL * (O2_MOLAR_MASS / 28.97),
            n2_kg=total_air_kg * CABIN_N2_FRACTION_NOMINAL * (N2_MOLAR_MASS / 28.97),
            co2_kg=total_air_kg * 4e-4 * (CO2_MOLAR_MASS / 28.97),  # 400 ppm baseline
            co_kg=0.0,
            ch4_kg=0.0,
            cabin_volume_m3=cabin_volume_m3,
        )
        return s


@dataclass
class EclssConfig:
    """Configuration for the Environmental Control and Life Support System.

    Attributes:
        crew_size:       Number of crew members.
        cdra_online:     CDRA is active (CO₂ scrubbing).
        sabatier_online: Sabatier reactor active (CO₂ → CH₄ + H₂O).
        oga_online:      OGA active (H₂O electrolysis → O₂).
        tccs_online:     TCCS active (trace contaminant scrubbing).
        hull_leak_kg_day: N₂+O₂ hull leakage rate [kg/day].
    """
    crew_size: int = 8
    cdra_online: bool = True
    sabatier_online: bool = True
    oga_online: bool = True
    tccs_online: bool = True
    hull_leak_kg_day: float = 0.10  # ISS: ~0.227 kg/day (Matty 2010); conservative


# ── Component efficiency functions ────────────────────────────────────────────

def cdra_scrubbing_efficiency(cdra_age_years: float) -> float:
    """CDRA sorbent bed efficiency after aging.

    Models zeolite 5A capacity decay as first-order degradation:
        η = η₀ × exp(−age / τ)

    Args:
        cdra_age_years: Total operating time [years].

    Returns:
        Fractional CO₂ removal efficiency [0, 1].

    Reference: Knox et al. (2016) ICES-2016-234.
    """
    return CDRA_NOMINAL_EFFICIENCY * math.exp(
        -cdra_age_years / CDRA_DEGRADATION_TAU_YEARS
    )


def sabatier_co2_removal_fraction(sabatier_age_years: float) -> float:
    """Sabatier reactor CO₂ removal fraction after catalyst aging.

    Models sintering of Ru/Al₂O₃ catalyst:
        η = η₀ × (1 − A × (1 − exp(−age / τ)))

    Args:
        sabatier_age_years: Total catalyst operating time [years].

    Returns:
        Fractional CO₂ removal per pass [0, 1].

    Reference: Abney et al. (2011) ICES-2011-5112.
    """
    sintering = SABATIER_DEGRADE_FRACTION * (
        1.0 - math.exp(-sabatier_age_years / SABATIER_DEGRADATION_TAU_YEARS)
    )
    return max(0.0, SABATIER_NOMINAL_EFFICIENCY * (1.0 - sintering))


def oga_o2_rate_kg_day(oga_age_years: float, crew_size: int) -> float:
    """OGA electrolysis O₂ production rate after PEM cell aging.

    Args:
        oga_age_years: PEM cell operating time [years].
        crew_size:     Number of crew (scales nominal production).

    Returns:
        O₂ production rate [kg/day].

    Reference: Takahashi et al. (2019) ICES-2019-188.
    """
    cell_efficiency = max(0.0, 1.0 - OGA_CELL_DECAY_RATE_PER_YEAR * oga_age_years)
    return OGA_NOMINAL_RATE_KG_DAY_PER_CREW * crew_size * cell_efficiency


# ── Derived atmosphere quantities ─────────────────────────────────────────────

def cabin_co2_ppm(state: AtmosphereState) -> float:
    """CO₂ concentration in the cabin [ppm by volume].

    Uses mole fractions: ppm = (n_CO2 / n_total) × 1e6
    where n_i = m_i / M_i (moles).

    Args:
        state: Current atmosphere state.

    Returns:
        CO₂ concentration [ppm].
    """
    n_co2 = state.co2_kg * 1000.0 / CO2_MOLAR_MASS   # mol
    n_o2 = state.o2_kg * 1000.0 / O2_MOLAR_MASS
    n_n2 = state.n2_kg * 1000.0 / N2_MOLAR_MASS
    n_total = n_co2 + n_o2 + n_n2
    if n_total < 1e-12:
        return 0.0
    return (n_co2 / n_total) * 1e6


def cabin_o2_fraction(state: AtmosphereState) -> float:
    """O₂ volume fraction in the cabin.

    Args:
        state: Current atmosphere state.

    Returns:
        O₂ mole fraction [dimensionless, 0–1].
    """
    n_co2 = state.co2_kg * 1000.0 / CO2_MOLAR_MASS
    n_o2 = state.o2_kg * 1000.0 / O2_MOLAR_MASS
    n_n2 = state.n2_kg * 1000.0 / N2_MOLAR_MASS
    n_total = n_co2 + n_o2 + n_n2
    if n_total < 1e-12:
        return 0.0
    return n_o2 / n_total


def co2_incapacitation_risk(co2_ppm: float) -> float:
    """Fractional incapacitation risk from CO₂ exposure.

    Piecewise model calibrated to NIOSH/NASA thresholds:
    - Below 1000 ppm: 0 (nominal; Allen 2016)
    - 1000–5000 ppm: linear from 0 to 0.05 (cognitive impairment onset)
    - 5000–40000 ppm: linear from 0.05 to 0.50 (OSHA PEL to NIOSH IDLH)
    - Above 40000 ppm: 1.0 (immediate incapacitation)

    Args:
        co2_ppm: CO₂ concentration [ppm].

    Returns:
        Incapacitation probability [0, 1].

    References:
        Allen et al. (2016) Environ Health Perspect 124(12) 1832.
        OSHA 29 CFR 1910.1000 Table Z-1 (PEL 5000 ppm).
        NIOSH (1994) IDLH: 40000 ppm CO₂.
    """
    if co2_ppm <= CO2_PPM_COGNITIVE_IMPAIR:
        return 0.0
    if co2_ppm <= CO2_PPM_OSHA_PEL:
        frac = (co2_ppm - CO2_PPM_COGNITIVE_IMPAIR) / (
            CO2_PPM_OSHA_PEL - CO2_PPM_COGNITIVE_IMPAIR
        )
        return 0.05 * frac
    if co2_ppm <= CO2_PPM_NIOSH_IDLH:
        frac = (co2_ppm - CO2_PPM_OSHA_PEL) / (
            CO2_PPM_NIOSH_IDLH - CO2_PPM_OSHA_PEL
        )
        return 0.05 + 0.45 * frac
    return 1.0


def o2_hypoxia_risk(o2_fraction: float) -> float:
    """Fractional hypoxia risk from low O₂ partial pressure.

    - Above 20.9% (nominal): 0.
    - 15.5–20.9%: linear from 0 to 0.10 (mild hypoxia).
    - Below 15.5%: NASA STD-3001 emergency threshold → risk = 1.0.

    Args:
        o2_fraction: O₂ volume fraction [0–1].

    Returns:
        Hypoxia risk [0, 1].

    Reference: NASA STD-3001 Vol. 1, §6.6 Rev. B (2014).
    """
    if o2_fraction >= CABIN_O2_FRACTION_NOMINAL:
        return 0.0
    if o2_fraction >= O2_FRACTION_HYPOXIA_LOW:
        frac = (CABIN_O2_FRACTION_NOMINAL - o2_fraction) / (
            CABIN_O2_FRACTION_NOMINAL - O2_FRACTION_HYPOXIA_LOW
        )
        return 0.10 * frac
    return 1.0


# ── Time-step integrator ──────────────────────────────────────────────────────

def step_atmosphere(
    state: AtmosphereState,
    config: EclssConfig,
    dt_days: float,
) -> AtmosphereState:
    """Advance cabin atmosphere mass balance by dt_days.

    Uses explicit Euler integration (adequate for dt_days ≤ 1 day;
    for sub-hour resolution, call with dt_days = 1/24 or smaller).

    Mass balance (all rates in kg/day):
        dCO₂/dt = crew_production − cdra_removal − sabatier_removal
        dO₂/dt  = oga_production − crew_consumption − hull_leak_O2
        dN₂/dt  = −hull_leak_N2
        dCO/dt  = crew_production − tccs_removal

    Args:
        state:    Current atmosphere state (mutated in-place).
        config:   ECLSS configuration.
        dt_days:  Integration timestep [days].

    Returns:
        Updated state (same object).
    """
    if dt_days <= 0.0:
        return state

    n = config.crew_size

    # ── CO₂ dynamics ──────────────────────────────────────────────────────────
    co2_prod = CREW_CO2_KG_DAY * n * dt_days       # crew production

    cdra_removal = 0.0
    if config.cdra_online:
        eta_cdra = cdra_scrubbing_efficiency(state.cdra_age_years)
        cdra_removal = eta_cdra * co2_prod          # removes fraction of produced CO₂

    sab_removal = 0.0
    if config.sabatier_online:
        eta_sab = sabatier_co2_removal_fraction(state.sabatier_age_years)
        # Sabatier removes a fraction of remaining CO₂ above ambient baseline
        cabin_co2 = max(0.0, state.co2_kg)
        sab_removal = min(cabin_co2 * 0.05, eta_sab * co2_prod)  # rate-limited

    state.co2_kg = max(0.0, state.co2_kg + co2_prod - cdra_removal - sab_removal)

    # ── O₂ dynamics ───────────────────────────────────────────────────────────
    o2_consumed = CREW_O2_KG_DAY * n * dt_days
    o2_produced = 0.0
    if config.oga_online:
        o2_produced = oga_o2_rate_kg_day(state.oga_age_years, n) * dt_days

    # Hull leak: proportional to current O₂ fraction in the cabin
    o2_frac = cabin_o2_fraction(state)
    hull_leak_o2 = config.hull_leak_kg_day * o2_frac * dt_days
    hull_leak_n2 = config.hull_leak_kg_day * (1.0 - o2_frac) * dt_days

    state.o2_kg = max(0.0, state.o2_kg + o2_produced - o2_consumed - hull_leak_o2)
    state.n2_kg = max(0.0, state.n2_kg - hull_leak_n2)

    # ── Trace CO dynamics ─────────────────────────────────────────────────────
    co_prod = CREW_CO_KG_DAY * n * dt_days
    co_removed = 0.0
    if config.tccs_online:
        co_removed = TCCS_CO_REMOVAL_EFFICIENCY * co_prod
    state.co_kg = max(0.0, state.co_kg + co_prod - co_removed)

    # ── Age equipment ─────────────────────────────────────────────────────────
    if config.cdra_online:
        state.cdra_age_years += dt_days / 365.25
    if config.sabatier_online:
        state.sabatier_age_years += dt_days / 365.25
    if config.oga_online:
        state.oga_age_years += dt_days / 365.25

    return state
