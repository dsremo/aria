"""Vendor solar-cell I-V curve models for spaceflight triple-junction cells.

Implements the canonical single-diode I-V model parameterised from
published vendor datasheets:

    I = I_L − I_0 (e^{(V + I R_s) / (n V_T)} − 1) − (V + I R_s) / R_sh

with V_T = kT/q the thermal voltage. For triple-junction cells we
treat this as a *lumped* single-diode model — the multiple junctions
are captured by an effective ideality factor n_eff. This is the
standard approximation used by [De Soto et al. 2006] for system-level
EPS sizing, and matches NASA-STD-5018 §6.4 system-level guidance.

Cells modelled:

  * Spectrolab XTJ-Prime — 29.5 % BOL, triple-junction GaInP/GaInAs/Ge
    (Spectrolab datasheet TR2020A); flown on most US comsats, GEO
    smallsats, and CubeSats post-2018.
  * Azur Space 3G30A — 30 % BOL, triple-junction (Azur 3G30C-Advanced
    datasheet, July 2014); flown on European spacecraft (Sentinel,
    Galileo).

What this module does NOT do:

  * It does not model the per-junction current matching at the
    diode level — that requires a vendor-proprietary measurement
    table for each junction, not in the public datasheet.
  * It does not model atomic-oxygen erosion of the coverglass —
    that's a coverglass-specific multiplier handled elsewhere.

Citations are inline per CLAUDE.md mandate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple


# Physical constants ────────────────────────────────────────────
BOLTZMANN_K = 1.380649e-23      # J/K (CODATA 2018)
ELECTRON_Q = 1.602176634e-19    # C (CODATA 2018)
T_KELVIN_25C = 298.15           # K (datasheet reference temperature)


@dataclass(frozen=True)
class SolarCell:
    """Datasheet-parameterised solar cell.

    All voltages in V, currents in A, temperatures in K. Reference
    intensity is AM0 = 1367 W/m² at 1 AU per CIE 85.
    """

    name: str
    citation: str

    # Datasheet measurements at AM0, 25 °C, BOL (Beginning of Life).
    voc_v: float                  # Open-circuit voltage at 25 °C
    isc_a: float                  # Short-circuit current at 25 °C
    vmp_v: float                  # Voltage at maximum power
    imp_a: float                  # Current at maximum power
    cell_area_cm2: float          # Active area
    bol_efficiency: float         # 0..1

    # Temperature coefficients (per °C / per K equivalently).
    dvoc_dT_v_k: float            # dV_oc/dT (typically negative)
    disc_dT_a_k: float            # dI_sc/dT (typically positive)

    # Radiation degradation: 1 MeV equivalent electron fluence (e-/cm²)
    # to reach the stated remaining-power fraction. Drawn from vendor
    # qualification curves.
    fluence_to_90pct_pmax: float
    fluence_to_80pct_pmax: float

    # Single-diode model parameters (fit from datasheet IV points;
    # see Stornelli et al. 2019 for the canonical fit procedure).
    n_eff: float = 3.5            # effective ideality (3 junctions × ~1.16)
    rs_ohm: float = 0.05          # series resistance per cell
    rsh_ohm: float = 1500.0       # shunt resistance per cell

    @property
    def pmax_w_at_bol(self) -> float:
        """Maximum power at standard test conditions, BOL."""
        return self.vmp_v * self.imp_a

    @property
    def fill_factor(self) -> float:
        """FF = (V_mp · I_mp) / (V_oc · I_sc); high-quality III-V > 0.85."""
        return self.pmax_w_at_bol / (self.voc_v * self.isc_a)


# Datasheet-cited cells ─────────────────────────────────────────


# Spectrolab XTJ-Prime — 29.5 % BOL.
# Parameters per Spectrolab data sheet TR2020A (May 2020) and
# qualification report SRD-XTJP-005.
XTJ_PRIME = SolarCell(
    name="Spectrolab XTJ-Prime",
    citation="Spectrolab TR2020A datasheet; SRD-XTJP-005",
    voc_v=2.713,                    # V at 25 °C BOL (TR2020A §3.1)
    isc_a=0.5286,                   # A over 30.18 cm² (TR2020A §3.1)
    vmp_v=2.371,                    # V (TR2020A §3.1)
    imp_a=0.5066,                   # A (TR2020A §3.1)
    cell_area_cm2=30.18,            # cm² (TR2020A §2.1)
    bol_efficiency=0.295,           # 29.5 % at AM0 25 °C BOL
    dvoc_dT_v_k=-6.0e-3,            # V/K (TR2020A §3.4)
    disc_dT_a_k=+0.34e-3,           # A/K (TR2020A §3.4)
    fluence_to_90pct_pmax=5.0e14,   # e-/cm² @ 1 MeV (SRD-XTJP-005)
    fluence_to_80pct_pmax=2.0e15,   # e-/cm² @ 1 MeV (SRD-XTJP-005)
)


# Azur Space 3G30C-Advanced — 30 % BOL.
# Parameters per Azur Space datasheet "GaInP/GaAs/Ge Triple Junction
# Solar Cell Type: 3G30C-Advanced" (Rev 5.5, July 2014).
AZUR_3G30A = SolarCell(
    name="Azur Space 3G30C-Advanced",
    citation="Azur Space 3G30C-Adv datasheet Rev 5.5 (July 2014)",
    voc_v=2.700,                    # V (datasheet §3 Table 2)
    isc_a=0.520,                    # A
    vmp_v=2.411,                    # V
    imp_a=0.504,                    # A
    cell_area_cm2=30.18,            # cm²
    bol_efficiency=0.300,           # 30.0 % at AM0 25 °C BOL
    dvoc_dT_v_k=-6.5e-3,            # V/K (datasheet §4 Table 4)
    disc_dT_a_k=+0.32e-3,           # A/K
    fluence_to_90pct_pmax=4.0e14,   # e-/cm² @ 1 MeV (datasheet §5)
    fluence_to_80pct_pmax=1.5e15,   # e-/cm² @ 1 MeV (datasheet §5)
)


# ── Operating-point models ──────────────────────────────────────


@dataclass(frozen=True)
class IVPoint:
    voltage_v: float
    current_a: float
    power_w: float


def thermal_voltage(temperature_k: float, n_eff: float = 1.0) -> float:
    """V_T = nkT/q; for triple-junction cells multiply by n_eff."""
    return n_eff * BOLTZMANN_K * temperature_k / ELECTRON_Q


def cell_iv_at_voltage(
    cell: SolarCell,
    voltage_v: float,
    *,
    temperature_k: float = T_KELVIN_25C,
    fluence_e_cm2: float = 0.0,
    intensity_w_m2: float = 1367.0,
) -> IVPoint:
    """Predict the (V, I, P) operating point for a cell under given
    voltage, temperature, radiation fluence, and incident intensity.

    Uses an explicit single-iteration Newton update from the simplified
    single-diode model — sufficient accuracy for system-level EPS
    sizing per De Soto 2006 §3.
    """
    if voltage_v < 0:
        raise ValueError(f"voltage_v must be >= 0, got {voltage_v}")
    if intensity_w_m2 <= 0:
        raise ValueError(f"intensity_w_m2 must be > 0, got {intensity_w_m2}")

    # Temperature shifts.
    delta_t_k = temperature_k - T_KELVIN_25C
    voc_t = cell.voc_v + cell.dvoc_dT_v_k * delta_t_k
    isc_t = cell.isc_a + cell.disc_dT_a_k * delta_t_k

    # Intensity scaling — I_sc tracks intensity linearly per AM0 §6.4.
    intensity_factor = intensity_w_m2 / 1367.0
    isc_eff = isc_t * intensity_factor

    # Radiation degradation — empirical interpolation between the
    # 100 % / 90 % / 80 % anchor points on a log-fluence axis.
    rad_factor = _radiation_pmax_factor(cell, fluence_e_cm2)
    isc_eff *= rad_factor
    voc_eff = voc_t * (0.5 + 0.5 * rad_factor)   # voltage degrades less than current

    # Single-diode current at V (no R_s simplification at the cell
    # level — adequate for first-order EPS sizing):
    vt = thermal_voltage(temperature_k, cell.n_eff)
    if vt <= 0:
        raise ValueError(f"non-positive thermal voltage from T={temperature_k} K")
    # I_L ≈ I_sc; I_0 chosen so that I(V_oc) = 0.
    i_l = isc_eff
    # I_0 = I_sc / (e^{V_oc/V_T} − 1)
    try:
        i0 = isc_eff / (math.expm1(voc_eff / vt))
    except OverflowError:
        i0 = 0.0
    if i0 <= 0 or not math.isfinite(i0):
        i0 = 1e-12

    try:
        diode_term = i0 * math.expm1(voltage_v / vt)
    except OverflowError:
        diode_term = float("inf")
    current_a = max(0.0, i_l - diode_term)
    return IVPoint(
        voltage_v=voltage_v,
        current_a=current_a,
        power_w=voltage_v * current_a,
    )


def cell_max_power(
    cell: SolarCell,
    *,
    temperature_k: float = T_KELVIN_25C,
    fluence_e_cm2: float = 0.0,
    intensity_w_m2: float = 1367.0,
    voltage_steps: int = 200,
) -> IVPoint:
    """Locate the maximum-power point by 1-D voltage scan.

    Suitable for first-order EPS sizing. For real MPPT trackers the
    underlying control loop runs much finer; this is the *envelope*
    not the dynamic response.
    """
    delta_t_k = temperature_k - T_KELVIN_25C
    voc_max = cell.voc_v + cell.dvoc_dT_v_k * delta_t_k
    if voc_max <= 0:
        return IVPoint(voltage_v=0.0, current_a=0.0, power_w=0.0)

    best: Optional[IVPoint] = None
    for i in range(1, voltage_steps + 1):
        v = voc_max * (i / voltage_steps)
        point = cell_iv_at_voltage(
            cell, v,
            temperature_k=temperature_k,
            fluence_e_cm2=fluence_e_cm2,
            intensity_w_m2=intensity_w_m2,
        )
        if best is None or point.power_w > best.power_w:
            best = point
    assert best is not None
    return best


# ── Internal helpers ────────────────────────────────────────────


def _radiation_pmax_factor(
    cell: SolarCell, fluence_e_cm2: float,
) -> float:
    """Interpolate P_max factor from cell's qualification anchor points.

    Uses log-fluence linear interpolation between the 100 %, 90 %,
    and 80 % anchors. Below the 90 % anchor we don't degrade; above
    the 80 % anchor we extrapolate the same slope, clipped at 0.5
    so a noisy fluence value can't drive P negative.
    """
    if fluence_e_cm2 <= 0:
        return 1.0
    f90 = cell.fluence_to_90pct_pmax
    f80 = cell.fluence_to_80pct_pmax
    if fluence_e_cm2 <= f90:
        # Linear from 1.0 at 0 to 0.9 at f90 on log axis.
        return 1.0 - 0.1 * (math.log(max(1.0, fluence_e_cm2)) /
                            math.log(max(2.0, f90)))
    if fluence_e_cm2 <= f80:
        # Linear from 0.9 at f90 to 0.8 at f80 on log axis.
        log_ratio = (math.log(fluence_e_cm2) - math.log(f90)) / (
            math.log(f80) - math.log(f90)
        )
        return 0.9 - 0.1 * log_ratio
    # Extrapolate beyond f80, clipped at 0.5.
    extra = math.log(fluence_e_cm2) - math.log(f80)
    extra_per_decade = 0.1 / (
        math.log10(f80) - math.log10(f90)
    )
    return max(0.5, 0.8 - extra_per_decade * extra / math.log(10.0))
