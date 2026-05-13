"""Open-loop sublimator — Apollo PLSS / Shuttle FES emergency thermal flash.

A water sublimator throws away heat by flashing water to vapour at
low pressure; the latent heat carries the load straight to vacuum.
This is the lifeboat path used by Apollo 13 (LM water sublimator
served as primary cooling for the CM during return), and it remains
on every modern EVA suit + Orion ECLSS as the ECLSS-failure backup.

Equations
---------

Latent heat rejection:

    Q_dot = m_dot · L_v(T)

where L_v(T) is the latent heat of sublimation of water (≈2.838 MJ/kg
at 0 °C, varying weakly with T per Murphy & Koop 2005, QJRMS 131,
1539–1565).  We use 2.834e6 J/kg as a standard reference value
matching NASA-TM-2018-219859 §4.2.

Mass-flow controller:

The plate temperature is held at the sublimation set-point by
modulating the water feed.  Operationally, the operator sets a
thermal load Q_target; the sublimator computes m_dot = Q_target / L_v,
then the vent dynamics delivers a small thrust + torque (the plumes
from PLSS sublimators are tens of mN — non-zero but rarely dominant).

Apollo PLSS reference: rejected ~290 W per 1 kg/h of water (Larson &
Pranke §17.7 Tab 17-1).  Verify 290 W · 3600 s = 1.044 MJ ≠ 2.834
MJ/kg — the difference is the *useful* thermal-cooling fraction:
NASA's PLSS-Section-7 spec rates the device at 81 W/kg for sustained
operation, with the rest of the latent heat lost to vent-line
condensation and parasitic losses.  We expose ``efficiency`` so the
caller picks the regime they want; 0.40 is the Apollo PLSS field
value, 1.00 is the thermodynamic ideal.

Reference:
    Larson-Pranke §17.7 (Apollo PLSS); NASA-TM-2018-219859 §4.2;
    Murphy & Koop 2005.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from aria.physics.venting.vent_dynamics import (
    GasState, VentGeometry, VentResult, vent_thrust_and_torque,
)

# Latent heat of sublimation of ice at 273 K — NASA-TM-2018-219859 §4.2.
# Murphy & Koop 2005 Eq 7 gives L_s = 2834.1 kJ/kg at 273 K.
L_SUBLIMATION_J_KG = 2.834e6

# Apollo PLSS sustained rejection rating (Larson-Pranke Tab 17-1).
APOLLO_PLSS_EFFICIENCY = 0.40


@dataclass
class SublimatorConfig:
    """Where the sublimator vents from + how it operates."""
    geometry: VentGeometry
    feed_water_temperature_k: float = 273.15
    feed_water_pressure_pa: float = 600.0   # ~triple-point of water
    efficiency: float = APOLLO_PLSS_EFFICIENCY
    max_water_flow_kg_s: float = 1e-3        # ~3.6 kg/h ceiling


@dataclass(frozen=True)
class SublimatorResult:
    water_flow_kg_s: float
    heat_rejected_w: float
    vent_result: VentResult


def simulate_sublimator(
    cfg: SublimatorConfig,
    target_heat_load_w: float,
) -> SublimatorResult:
    """Compute steady-state water flow + thrust/torque from a vapour vent.

    Operator picks the heat load they want rejected; the sublimator
    figures out the water flow + the vent plume.  Saturates at
    ``cfg.max_water_flow_kg_s``.
    """
    if target_heat_load_w <= 0.0 or cfg.efficiency <= 0.0:
        zero = VentResult(0.0, 0.0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                          False, "no load")
        return SublimatorResult(0.0, 0.0, zero)
    needed_water = target_heat_load_w / (cfg.efficiency * L_SUBLIMATION_J_KG)
    water_flow = min(needed_water, cfg.max_water_flow_kg_s)
    actual_q = water_flow * cfg.efficiency * L_SUBLIMATION_J_KG

    # Plume thrust: water vapour at the feed conditions.
    gas = GasState(
        pressure_pa=cfg.feed_water_pressure_pa,
        temperature_k=cfg.feed_water_temperature_k,
        gas="h2o_vap",
    )
    vr = vent_thrust_and_torque(gas, cfg.geometry, 0.0, converging_only=True)
    return SublimatorResult(
        water_flow_kg_s=float(water_flow),
        heat_rejected_w=float(actual_q),
        vent_result=vr,
    )
