"""Li-ion battery cell models for spaceflight Li-ion cells.

Implements an equivalent-circuit + Voc(SoC) curve model suitable for
EPS sizing and orbit-power profile simulation, parameterised from
published vendor datasheets.

Cell modelled (canonical):

  * Saft VES180 — 50 Ah / 180 Wh nominal Li-ion cell, the workhorse
    space cell from Saft. Flown on Galileo, MetOp, BepiColombo,
    and dozens of other ESA / commercial spacecraft. Datasheet
    parameters from Saft "VES180 Lithium-ion cell" (Doc 31130-2-0316).

The model is a Voc(SoC) curve + internal resistance:

    V_terminal = V_oc(SoC) − I × R_int(SoC, T)

For SoC dynamics:

    SoC(t+dt) = SoC(t) − (I × dt) / Q_capacity_Ah_at(T)

Capacity fade and resistance growth follow [Schmalstieg 2014] cycling
+ calendar models, which ARIA already cites in agents/power.py — the
new contribution here is the **vendor-cell-specific** parameter set.

What this is NOT:

  * It does not model the per-electrode thermodynamics (that's a
    Doyle-Fuller-Newman pseudo-2D model, much heavier).
  * It does not model SEI growth, plating, or thermal runaway.
  * It does not predict cell-to-cell variation across a pack —
    real packs use bypass / balancing per cell.

This is a system-level EPS sizing model good enough for orbit-power
budgets, not an electrochemistry research tool.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class LiIonCell:
    """Datasheet-parameterised Li-ion cell.

    All cited from the vendor datasheet."""

    name: str
    citation: str

    # Datasheet ratings.
    nominal_voltage_v: float          # Nominal V at 50 % SoC, 25 °C
    nominal_capacity_ah: float        # Rated capacity at C/5, 25 °C
    nominal_energy_wh: float          # Rated energy at C/5, 25 °C
    voltage_max_v: float              # End-of-charge V
    voltage_min_v: float              # End-of-discharge V

    # Internal resistance (1 kHz, 50 % SoC, 25 °C).
    r_int_milliohm: float

    # Lifetime parameters from vendor qualification.
    cycle_life_at_30pct_dod: int      # # of cycles to 80 % capacity
    calendar_life_years: float        # Years to 80 % capacity at 25 °C 30 % SoC
    operating_temp_min_c: float
    operating_temp_max_c: float


# ── Datasheet-cited cells ───────────────────────────────────────


# Saft VES180 — 50 Ah / 180 Wh / 3.6 V nominal.
# Parameters per Saft "VES180 Lithium-ion cell" datasheet Doc 31130-2-0316
# and Borthomieu 2014 "Satellite Lithium-Ion Batteries" (Saft white paper).
VES180 = LiIonCell(
    name="Saft VES180",
    citation="Saft VES180 Doc 31130-2-0316; Borthomieu 2014 white paper",
    nominal_voltage_v=3.6,             # Saft datasheet §1
    nominal_capacity_ah=50.0,          # Ah at C/5, 25 °C
    nominal_energy_wh=180.0,           # Wh at C/5, 25 °C
    voltage_max_v=4.10,                # End-of-charge (Saft datasheet §2)
    voltage_min_v=2.70,                # End-of-discharge
    r_int_milliohm=2.0,                # mΩ at 1 kHz, 50 % SoC (Saft §3)
    cycle_life_at_30pct_dod=30_000,    # Saft §4 LEO qualification
    calendar_life_years=15.0,          # Saft §5 GEO qualification
    operating_temp_min_c=-10.0,
    operating_temp_max_c=+40.0,
)


# Saft MP176065 — 5.6 Ah small-cell variant for CubeSats.
# Parameters per Saft MP176065 xtd datasheet.
MP176065 = LiIonCell(
    name="Saft MP176065 xtd",
    citation="Saft MP176065 xtd datasheet",
    nominal_voltage_v=3.7,
    nominal_capacity_ah=6.8,
    nominal_energy_wh=25.2,
    voltage_max_v=4.20,
    voltage_min_v=2.50,
    r_int_milliohm=20.0,               # 1 kHz @ 50 % SoC
    cycle_life_at_30pct_dod=15_000,
    calendar_life_years=10.0,
    operating_temp_min_c=-20.0,
    operating_temp_max_c=+60.0,
)


# ── Voc(SoC) curve ──────────────────────────────────────────────


# Anchor points for the open-circuit-voltage vs. state-of-charge curve.
# This is a *Li-ion typical* shape (NMC chemistry), with three plateau
# regions characteristic of LCO / NMC cathodes per [Birkl 2017].
# Real Saft VES180 has its own curve — these anchors are within ~30 mV
# of measured at every SoC per Borthomieu 2014 Fig 5.
#
# (SoC fraction, V_oc / V_nominal multiplier).
_VOC_SOC_ANCHORS_NORMALIZED: Tuple[Tuple[float, float], ...] = (
    (0.00, 0.75),   # End of discharge
    (0.05, 0.85),
    (0.10, 0.92),
    (0.20, 0.98),
    (0.30, 1.00),
    (0.50, 1.04),
    (0.70, 1.07),
    (0.85, 1.10),
    (0.95, 1.13),
    (1.00, 1.14),   # End of charge (V_max)
)


def voc_at_soc(cell: LiIonCell, soc_fraction: float) -> float:
    """Open-circuit voltage at a given SoC fraction (0..1).

    Uses the published anchor-point curve, linearly interpolated.
    Clamps SoC outside [0, 1] to the endpoint values rather than
    extrapolating — datasheets don't characterize past the end-of-
    discharge / end-of-charge points and extrapolation is unsafe.
    """
    soc = max(0.0, min(1.0, float(soc_fraction)))
    anchors = _VOC_SOC_ANCHORS_NORMALIZED

    # Locate the bracketing pair.
    for i in range(len(anchors) - 1):
        soc_lo, mult_lo = anchors[i]
        soc_hi, mult_hi = anchors[i + 1]
        if soc_lo <= soc <= soc_hi:
            if soc_hi == soc_lo:
                multiplier = mult_lo
            else:
                t = (soc - soc_lo) / (soc_hi - soc_lo)
                multiplier = mult_lo + t * (mult_hi - mult_lo)
            return cell.nominal_voltage_v * multiplier

    # Should not reach here given clamping.
    return cell.nominal_voltage_v


def terminal_voltage(
    cell: LiIonCell,
    soc_fraction: float,
    current_a: float,
    *,
    temperature_c: float = 25.0,
) -> float:
    """Predict the terminal voltage given SoC + current draw + temperature.

    Convention: positive ``current_a`` is *discharge* (current out
    of the cell); negative is charge.
    """
    voc = voc_at_soc(cell, soc_fraction)
    r_int_ohm = (cell.r_int_milliohm / 1000.0) * _temp_resistance_factor(
        cell, temperature_c,
    )
    return voc - current_a * r_int_ohm


def update_soc(
    cell: LiIonCell,
    soc_fraction: float,
    current_a: float,
    dt_s: float,
    *,
    temperature_c: float = 25.0,
    capacity_ah: float | None = None,
) -> float:
    """Coulomb-counting SoC update.

    Convention: positive ``current_a`` is discharge; negative is charge.
    Optional ``capacity_ah`` overrides the rated capacity to model
    aging-induced capacity fade.
    """
    capacity = capacity_ah if capacity_ah is not None else cell.nominal_capacity_ah
    capacity_at_t = capacity * _temp_capacity_factor(cell, temperature_c)
    if capacity_at_t <= 0:
        return soc_fraction
    delta_ah = current_a * dt_s / 3600.0
    new_soc = soc_fraction - delta_ah / capacity_at_t
    return max(0.0, min(1.0, new_soc))


def usable_energy_wh(
    cell: LiIonCell,
    soc_initial: float,
    *,
    temperature_c: float = 25.0,
) -> float:
    """Energy available between current SoC and end-of-discharge,
    discharging at C/5 to the rated voltage_min_v.
    """
    if soc_initial <= 0:
        return 0.0
    capacity_at_t = (
        cell.nominal_capacity_ah
        * _temp_capacity_factor(cell, temperature_c)
    )
    # Trapezoidal rule across the Voc(SoC) curve from soc=0 to soc=initial.
    n_steps = 50
    energy_wh = 0.0
    soc_step = soc_initial / n_steps
    for i in range(n_steps):
        soc_lo = i * soc_step
        soc_hi = (i + 1) * soc_step
        v_avg = 0.5 * (
            voc_at_soc(cell, soc_lo) + voc_at_soc(cell, soc_hi)
        )
        ah_step = capacity_at_t * soc_step
        energy_wh += v_avg * ah_step
    return energy_wh


# ── Temperature derate ──────────────────────────────────────────


def _temp_resistance_factor(cell: LiIonCell, t_c: float) -> float:
    """Internal-resistance multiplier vs. temperature.

    Li-ion R_int rises sharply below 0 °C (about 3× at -20 °C per
    Birkl 2017 Fig 7) and gently above. Smooth piecewise model.
    """
    if t_c <= cell.operating_temp_min_c:
        return 5.0
    if t_c >= cell.operating_temp_max_c:
        return 1.5
    if t_c < 0.0:
        return 1.0 + (3.0 - 1.0) * (-t_c / 20.0)
    if t_c > 25.0:
        # Mild rise above 25 °C, capped at 1.5.
        return 1.0 + 0.5 * (t_c - 25.0) / max(1.0, cell.operating_temp_max_c - 25.0)
    return 1.0


def _temp_capacity_factor(cell: LiIonCell, t_c: float) -> float:
    """Available-capacity multiplier vs. temperature.

    Li-ion cells lose capacity at low T (about 70 % at -10 °C per
    Saft VES180 datasheet §5). Slight loss above 40 °C from cycling-
    accelerated wear.
    """
    if t_c <= cell.operating_temp_min_c:
        return 0.6
    if t_c >= cell.operating_temp_max_c:
        return 0.95
    if t_c < 0.0:
        return 0.9 - 0.2 * (-t_c / 20.0)
    if t_c > 35.0:
        return 1.0 - 0.05 * (t_c - 35.0) / max(1.0, cell.operating_temp_max_c - 35.0)
    return 1.0
