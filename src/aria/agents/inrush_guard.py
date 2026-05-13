"""Pulsed-load inrush guard (power & thermal audit P-17).

Spacecraft pulsed loads — high-gain antenna keying, ion-thruster
arc-jet ignition, scientific-instrument flash heating — draw transient
inrush currents 2–5× their steady-state.  When the bus is already
stressed (low SoC, partial solar), the inrush spike depresses the bus
voltage below the undervoltage cutoff and triggers a downstream
brown-out.

This module is the deterministic gate the agent hits before commanding
a pulsed load: it reads the latest ``power.prediction`` from the
shared scratchpad and refuses the burst if the predicted post-inrush
state would dip the bus below the safe threshold.

Reference defaults:
  * Patterson 2007 §3 — NEXT ion thruster arc-jet ignition transient
    profile (3× steady-state, 10 ms exponential decay).
  * NASA-STD-4002 §6.5 — bus undervoltage interlock guidance:
    re-flight only after a margin of ≥ 5 V above cutoff is established.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


# Patterson 2007 §3 — typical inrush is 3× steady-state for 10 ms
# (exponential decay; we model the *peak*, not the integral, because
# the bus undervoltage interlock fires on instantaneous voltage).
DEFAULT_INRUSH_MULTIPLIER = 3.0      # × steady-state — Patterson 2007 §3
DEFAULT_INRUSH_DURATION_S = 0.010    # s — Patterson 2007 §3

# Bus undervoltage cutoff with 5-V margin per NASA-STD-4002 §6.5.
DEFAULT_BUS_NOMINAL_V = 28.0         # V — typical small-sat bus
DEFAULT_BUS_CUTOFF_V = 24.0          # V — bus undervoltage cutoff
# Software-gating margin above cutoff.  Smaller than the NASA-STD-4002
# §6.5 5-V re-flight margin because at a 28-V nominal bus there are
# only 4 V of headroom; we want SW to refuse bursts whose predicted
# dip would land within 1 V of cutoff (= ≥ 25 V post-burst).
DEFAULT_BUS_SAFE_MARGIN_V = 1.0      # V — SW gate; HW interlock at cutoff

# SoC floor below which we refuse pulsed loads outright.  Slightly above
# the proactive load-shed threshold (20 %) so the budget guard sits
# *upstream* of the load-shed ladder.
DEFAULT_MIN_SOC_FOR_BURST = 30.0     # % — TT&C / power audit defence-in-depth


@dataclass(frozen=True)
class InrushVerdict:
    allowed: bool
    reason: str = ""
    predicted_dip_v: float = 0.0
    predicted_post_v: float = 0.0


def check_burst_allowed(
    *,
    burst_steady_state_w: float,
    bus_voltage_v: float,
    power_prediction: Optional[Mapping[str, Any]] = None,
    bus_resistance_ohm: float = 0.05,
    bus_nominal_v: float = DEFAULT_BUS_NOMINAL_V,
    bus_cutoff_v: float = DEFAULT_BUS_CUTOFF_V,
    bus_safe_margin_v: float = DEFAULT_BUS_SAFE_MARGIN_V,
    inrush_multiplier: float = DEFAULT_INRUSH_MULTIPLIER,
    min_soc_for_burst_pct: float = DEFAULT_MIN_SOC_FOR_BURST,
) -> InrushVerdict:
    """Refuse a pulsed-load burst that would drop the bus below
    ``cutoff + margin`` after a ``inrush_multiplier × steady-state``
    transient, OR when SoC is below ``min_soc_for_burst_pct``.

    The bus dip is approximated as ``I_inrush × R_bus`` where
    ``I_inrush = inrush_multiplier × burst_w / bus_voltage_v``.  This
    is the standard CCSDS-style first-order budget — if the operator
    has a more accurate transient model, pass it in via
    ``power_prediction['predicted_dip_v']``.
    """
    # SoC floor.
    if power_prediction is not None:
        soc = float(power_prediction.get("battery_soc", 100.0))
        if soc < min_soc_for_burst_pct:
            return InrushVerdict(
                allowed=False,
                reason=f"soc_below_burst_floor: soc={soc:.1f} < {min_soc_for_burst_pct}",
            )

    # Compute predicted instantaneous dip.
    if bus_voltage_v <= 0:
        return InrushVerdict(allowed=False, reason="invalid_bus_voltage")
    explicit_dip = (
        float(power_prediction.get("predicted_dip_v", 0.0))
        if power_prediction is not None else 0.0
    )
    if explicit_dip > 0:
        dip_v = explicit_dip
    else:
        i_inrush = inrush_multiplier * burst_steady_state_w / bus_voltage_v
        dip_v = i_inrush * bus_resistance_ohm

    post_v = bus_voltage_v - dip_v
    if post_v < bus_cutoff_v + bus_safe_margin_v:
        return InrushVerdict(
            allowed=False,
            reason=(f"inrush_undervoltage_risk: post_v={post_v:.2f} < "
                    f"cutoff+margin={bus_cutoff_v + bus_safe_margin_v:.2f}"),
            predicted_dip_v=dip_v,
            predicted_post_v=post_v,
        )

    return InrushVerdict(
        allowed=True,
        reason="ok",
        predicted_dip_v=dip_v,
        predicted_post_v=post_v,
    )
