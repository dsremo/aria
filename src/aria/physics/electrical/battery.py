"""Lithium-ion battery physics: C-rate limits, capacity fade, and thermal model.

PROBLEM WITH THE PRIOR SIMULATION MODEL
-----------------------------------------
ARIA's power subsystem treats battery storage as a simple energy bucket
(charge_kWh − discharge_kWh) with no physics:
  - No C-rate limit: the battery can theoretically deliver infinite power
  - No capacity fade with cycling: same capacity on day 1 and year 30
  - No thermal model: no heating from I²R inside the cell
  - No voltage model: cannot predict shutdown at low SoC

These omissions matter for a 30-year mission where:
  - Power surges (thruster burns, emergency) demand high C-rates
  - 10,000+ charge/discharge cycles cause measurable capacity loss
  - Cell self-heating can exceed safe operating temperature

THIS MODULE
-----------
Implements four interconnected models for Li-ion NMC/LFP cells:

1. C-RATE LIMIT
   Maximum discharge current: I_max = C_rate_max × capacity_Ah
   Ragone-limited power: P_max = η_discharge × V_nom × C_rate_max × capacity_Ah
   For spacecraft Li-ion NMC: C_rate_max ≈ 3C continuous (Jossen 2011)

2. CAPACITY FADE (cycle and calendar)
   Empirical Arrhenius-degradation model from Millner (2010):
     Q(N, T) = Q_0 × (1 − k_cycle × sqrt(N) − k_cal × t_yr × exp(−Ea_cal/(R×T)))
   where:
     k_cycle = 0.0013 (cycle fade, sqrt-N fit to NMC cycle data; Schmalstieg 2014)
     k_cal   = 0.015  (calendar fade coefficient; Millner 2010)
     Ea_cal  = 24600 J/mol (calendar aging activation energy; Millner 2010)
     R = 8.314 J/(mol·K), T in Kelvin

3. INTERNAL RESISTANCE AND JOULE HEATING
   V = V_OCV(SoC) − I × R_int(SoC, T)
   P_heat = I² × R_int     [W per cell]
   R_int(T) = R_int_ref × exp(−B × (T − T_ref))  (Arrhenius; Jossen 2011 §3.3)

4. OPEN-CIRCUIT VOLTAGE (SoC)
   Linear approximation for NMC cells:
     V_OCV = V_min + (V_max − V_min) × SoC
   Full polynomial requires cell-specific lookup tables (Plett 2015).

REFERENCES
----------
  Jossen A. & Weydanz W. (2006/2011) "Modern Batteries" — C-rate, R_int(T)
  Millner A. (2010) IECON 2010:1636 — Arrhenius capacity fade model
  Schmalstieg J. et al. (2014) J Power Sources 257:325 — sqrt(N) cycle fade
  Plett G.L. (2015) "Battery Management Systems Vol.1" Artech House — V_OCV
  NASA TN D-8706 (1977) — spacecraft battery qualification (C-rate limits)
  Bernardi D.M. et al. (1985) J Electrochem Soc 132:5 — thermal model
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Physical constants ────────────────────────────────────────────────────────

R_GAS: float = 8.314   # J/(mol·K) — universal gas constant (NIST CODATA 2018)

# ── NMC cell default parameters ───────────────────────────────────────────────

NMC_V_MIN: float = 3.0              # V — minimum cell voltage (Jossen 2011)
NMC_V_MAX: float = 4.2              # V — maximum cell voltage (Jossen 2011)
NMC_V_NOM: float = 3.6              # V — nominal cell voltage (Jossen 2011)
NMC_C_RATE_MAX_CONTINUOUS: float = 3.0   # C — max continuous discharge (Jossen 2011)
NMC_ETA_DISCHARGE: float = 0.97     # discharge efficiency (Jossen 2006 §4.2)
NMC_ETA_CHARGE: float = 0.97        # charge efficiency (Jossen 2006 §4.2)

# Capacity fade (Millner 2010 IECON; Schmalstieg 2014 J Power Sources 257:325)
# NMC LFP cycling: ~80% SoH after 500-2000 full cycles at 25°C
# k_cycle = 0.20 / sqrt(1000) = 0.0063  (1000 cycle life at 80% threshold; Schmalstieg 2014 Fig.3)
NMC_K_CYCLE: float = 0.0063         # cycle fade coefficient [per sqrt(N)] (Schmalstieg 2014)
NMC_K_CALENDAR: float = 0.040       # calendar fade coefficient [per sqrt(yr)] at T_ref (Millner 2010)
NMC_EA_CALENDAR: float = 24600.0    # calendar aging activation energy [J/mol] (Millner 2010)
NMC_T_REF_K: float = 298.0          # reference temperature [K] (25°C)

# Internal resistance (Jossen 2011 §3.3; Arrhenius temperature dependence)
NMC_R_INT_REF_OHM: float = 0.005   # Ω at SoC=0.5, T=298K (typical 50 Ah NMC pouch)
NMC_B_THERMAL: float = 0.035        # Arrhenius-like temperature coefficient [1/K] (Jossen 2011 §3.3)

# Safe operating limits
NMC_T_MIN_K: float = 253.0  # −20°C (NASA TN D-8706: cold start limit)
NMC_T_MAX_K: float = 333.0  # +60°C (NASA TN D-8706: thermal runaway threshold)
NMC_SOC_MIN: float = 0.10   # avoid deep discharge (Plett 2015 Vol.1)
NMC_SOC_MAX: float = 0.95   # avoid full charge for longevity (Plett 2015 Vol.1)


@dataclass
class BatteryCellConfig:
    """Configuration for one battery cell or module.

    Attributes:
        capacity_Ah:     Nominal cell capacity [Ah].
        n_series:        Cells in series (sets voltage).
        n_parallel:      Cells in parallel (sets capacity).
        v_min:           Minimum cell voltage [V].
        v_max:           Maximum cell voltage [V].
        v_nom:           Nominal cell voltage [V].
        c_rate_max:      Maximum continuous discharge C-rate.
        eta_discharge:   Round-trip discharge efficiency.
        eta_charge:      Round-trip charge efficiency.
        r_int_ref_ohm:   Internal resistance per cell at T_ref, SoC=0.5 [Ω].
        b_thermal:       Arrhenius temperature coefficient for R_int [1/K].
        k_cycle:         Cycle-fade coefficient [per √N].
        k_calendar:      Calendar-fade coefficient [/yr at T_ref].
        ea_calendar:     Calendar activation energy [J/mol].
        T_ref_K:         Reference temperature [K].
    """
    capacity_Ah: float = 50.0
    n_series: int = 8
    n_parallel: int = 1
    v_min: float = NMC_V_MIN
    v_max: float = NMC_V_MAX
    v_nom: float = NMC_V_NOM
    c_rate_max: float = NMC_C_RATE_MAX_CONTINUOUS
    eta_discharge: float = NMC_ETA_DISCHARGE
    eta_charge: float = NMC_ETA_CHARGE
    r_int_ref_ohm: float = NMC_R_INT_REF_OHM
    b_thermal: float = NMC_B_THERMAL
    k_cycle: float = NMC_K_CYCLE
    k_calendar: float = NMC_K_CALENDAR
    ea_calendar: float = NMC_EA_CALENDAR
    T_ref_K: float = NMC_T_REF_K

    @property
    def module_capacity_Ah(self) -> float:
        return self.capacity_Ah * self.n_parallel

    @property
    def module_voltage_V(self) -> float:
        return self.v_nom * self.n_series

    @property
    def module_energy_Wh(self) -> float:
        return self.module_capacity_Ah * self.module_voltage_V


# ── C-rate and power limits ───────────────────────────────────────────────────

def max_discharge_current_A(config: BatteryCellConfig, soh: float = 1.0) -> float:
    """Maximum discharge current from C-rate limit.

    I_max = C_rate_max × Q_module × SoH

    Args:
        config: Battery cell config.
        soh: State of Health [0–1].

    Returns:
        Maximum continuous discharge current [A].

    Reference: Jossen & Weydanz (2011) "Modern Batteries", C-rate definition.
    """
    return config.c_rate_max * config.module_capacity_Ah * max(0.0, soh)


def max_discharge_power_W(
    config: BatteryCellConfig,
    soh: float = 1.0,
    temperature_K: float = NMC_T_REF_K,
) -> float:
    """Maximum instantaneous discharge power [W].

    P_max = η × V_nom_module × I_max

    Args:
        config: Battery config.
        soh: State of Health [0–1].
        temperature_K: Cell temperature [K].

    Returns:
        Maximum power [W].

    Reference: Ragone (1968); Jossen 2011 §3.3.
    """
    I_max = max_discharge_current_A(config, soh)
    V_module = config.module_voltage_V
    # Voltage sag at max current: V = V_nom - I × R_int_total
    R_total = internal_resistance_ohm(config, temperature_K) * config.n_series / config.n_parallel
    V_effective = max(0.0, V_module - I_max * R_total)
    return config.eta_discharge * V_effective * I_max


# ── Internal resistance ───────────────────────────────────────────────────────

def internal_resistance_ohm(
    config: BatteryCellConfig,
    temperature_K: float,
    soc: float = 0.5,
) -> float:
    """Cell internal resistance as function of temperature.

    R_int(T) = R_ref × exp(−B × (T − T_ref))

    Simplified: ignores SoC dependence for now (SoC dependence is ±20%
    around SoC=0.5; Jossen 2011 Fig. 3.12).

    Args:
        config: Battery config.
        temperature_K: Cell temperature [K].
        soc: State of charge [0–1] (not used in current model — placeholder).

    Returns:
        Internal resistance [Ω].

    Reference: Jossen & Weydanz (2011) §3.3.
    """
    return config.r_int_ref_ohm * math.exp(
        -config.b_thermal * (temperature_K - config.T_ref_K)
    )


def cell_joule_heat_W(
    current_A: float,
    config: BatteryCellConfig,
    temperature_K: float = NMC_T_REF_K,
) -> float:
    """Heat generated in one cell by Ohmic resistance.

    P_heat = I² × R_int

    Args:
        current_A: Cell current [A] (charge or discharge).
        config: Battery config.
        temperature_K: Cell temperature [K].

    Returns:
        Heat generation rate [W].

    Reference: Bernardi et al. (1985) J Electrochem Soc 132:5.
    """
    R = internal_resistance_ohm(config, temperature_K)
    return current_A ** 2 * R


# ── Capacity fade ─────────────────────────────────────────────────────────────

def state_of_health(
    config: BatteryCellConfig,
    n_cycles: float,
    calendar_years: float,
    temperature_K: float = NMC_T_REF_K,
) -> float:
    """Remaining capacity as fraction of initial (State of Health).

    Q/Q₀ = 1 − k_cycle × √N − k_cal × t_yr × exp(−Ea/(R×T))

    Clamped to [0, 1].

    Args:
        config: Battery config.
        n_cycles: Total full-equivalent charge/discharge cycles.
        calendar_years: Total calendar age [years].
        temperature_K: Average storage/use temperature [K].

    Returns:
        State of Health [0, 1].

    References:
        Millner (2010) IECON 2010:1636 — calendar fade model.
        Schmalstieg et al. (2014) J Power Sources 257:325 — cycle fade model.
    """
    # Cycle fade: sqrt-N law (Schmalstieg 2014 J Power Sources 257:325)
    cycle_fade = config.k_cycle * math.sqrt(max(0.0, n_cycles))
    # Calendar fade: sqrt(t) model with Arrhenius temperature scaling (Millner 2010 IECON)
    # fade = k_cal × sqrt(t_yr) × exp(-Ea/RT) / exp(-Ea/RT_ref)
    arrhenius_ratio = math.exp(
        -config.ea_calendar / (R_GAS * temperature_K)
        + config.ea_calendar / (R_GAS * config.T_ref_K)
    )
    calendar_fade = config.k_calendar * math.sqrt(max(0.0, calendar_years)) * arrhenius_ratio
    soh = 1.0 - cycle_fade - calendar_fade
    return max(0.0, min(1.0, soh))


def cycles_to_eol(
    config: BatteryCellConfig,
    eol_threshold: float = 0.80,
    temperature_K: float = NMC_T_REF_K,
    calendar_years: float = 0.0,
) -> float:
    """Number of full cycles until State of Health drops to eol_threshold.

    Solves: 1 − k_cycle × √N − k_cal_term = eol_threshold
    for N (assuming calendar fade is fixed at given age).

    Args:
        config: Battery config.
        eol_threshold: SoH at end of life (default 80%).
        temperature_K: Operating temperature [K].
        calendar_years: Simultaneous calendar age [years].

    Returns:
        Number of full cycles to EOL.
    """
    arrhenius_ratio = math.exp(
        -config.ea_calendar / (R_GAS * temperature_K)
        + config.ea_calendar / (R_GAS * config.T_ref_K)
    )
    cal_term = config.k_calendar * math.sqrt(max(0.0, calendar_years)) * arrhenius_ratio
    available = (1.0 - eol_threshold) - cal_term
    if available <= 0.0:
        return 0.0
    return (available / config.k_cycle) ** 2


# ── Open-circuit voltage ──────────────────────────────────────────────────────

def open_circuit_voltage_V(config: BatteryCellConfig, soc: float) -> float:
    """Linear OCV model: V_OCV = V_min + (V_max − V_min) × SoC.

    A simplification — real NMC/LFP curves are nonlinear. Use lookup tables
    from manufacturer for precision. This model is sufficient for power budget
    simulations (Plett 2015 §3.2).

    Args:
        config: Battery config.
        soc: State of charge [0–1].

    Returns:
        Open-circuit voltage per cell [V].

    Reference: Plett G.L. (2015) "Battery Management Systems Vol.1" Artech.
    """
    soc_clamped = max(0.0, min(1.0, soc))
    return config.v_min + (config.v_max - config.v_min) * soc_clamped


def terminal_voltage_V(
    config: BatteryCellConfig,
    soc: float,
    current_A: float,
    temperature_K: float = NMC_T_REF_K,
) -> float:
    """Terminal voltage under load.

    V_terminal = V_OCV − I × R_int  (discharge convention: positive I = discharge)

    Args:
        config: Battery config.
        soc: State of charge [0–1].
        current_A: Load current (+ = discharge, − = charge) [A].
        temperature_K: Cell temperature [K].

    Returns:
        Terminal voltage [V]. Clamped to [V_min, V_max + 0.2].
    """
    V_oc = open_circuit_voltage_V(config, soc)
    R = internal_resistance_ohm(config, temperature_K)
    V = V_oc - current_A * R
    return max(config.v_min - 0.1, min(config.v_max + 0.2, V))


# ── Thermal safety ────────────────────────────────────────────────────────────

def is_thermal_safe(temperature_K: float) -> bool:
    """True if cell temperature is within safe operating range.

    Reference: NASA TN D-8706 — spacecraft battery qualification.
    """
    return NMC_T_MIN_K <= temperature_K <= NMC_T_MAX_K


def is_soc_safe(soc: float) -> bool:
    """True if SoC is within recommended operating range.

    Reference: Plett (2015) Vol.1 — protective SoC window.
    """
    return NMC_SOC_MIN <= soc <= NMC_SOC_MAX
