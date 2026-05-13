"""Stuck-open vent valve — failure mode that depletes a tank past
the operator's intended endpoint.

The valve was opened on command (e.g. ``vent_tank``) but failed to
close.  Tank pressure decays exponentially while the valve passes
choked flow into vacuum; thrust + torque accumulate the same way as
a hull breach, but with a much larger reservoir behind it.

This is a thin operational wrapper over :func:`vent_thrust_and_torque`
plus an exponential pressure model for a tank with constant volume
and adiabatic blowdown:

    P(t) / P_0 = exp(−t / τ)

where τ ≈ V / (C_d · A · √(γ R T_0) · k(γ)), with k(γ) the same
critical-flow factor that appears in :func:`choked_mass_flow`.

For NTO/MMH propellant tanks (Apollo CSM ~660 lb dump, Sutton-Biblarz
Tab 7-2) τ ≈ 30–60 s; for high-pressure He pressurant τ ≈ 10–20 s.

Reference:
    Sutton-Biblarz §3.3 + §10.5; Larson-Pranke §17.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from aria.physics.venting.vent_dynamics import (
    GAS_PROPERTIES, GasState, VentGeometry, VentResult,
    vent_thrust_and_torque, R_UNIVERSAL,
)


@dataclass
class StuckValveConfig:
    tank_volume_m3: float
    initial_pressure_pa: float
    initial_temperature_k: float
    gas: str
    geometry: VentGeometry
    detected_at_s: float = float("inf")     # when crew/AI notices it


def _blowdown_tau_s(cfg: StuckValveConfig) -> float:
    """Characteristic blowdown time for an adiabatic choked vent."""
    g, M = GAS_PROPERTIES[cfg.gas]
    R_s = R_UNIVERSAL / M
    k = math.sqrt(g) * (
        (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
    )
    a0 = math.sqrt(R_s * cfg.initial_temperature_k)  # √(R T)
    denom = (
        cfg.geometry.cd * cfg.geometry.area_m2
        * k * a0
        / cfg.tank_volume_m3
    )
    if denom <= 0.0:
        return float("inf")
    return 1.0 / denom


def simulate_stuck_valve(
    cfg: StuckValveConfig,
    max_time_s: float = 300.0,
    dt_s: float = 0.5,
) -> Tuple[List[float], List[float], List[VentResult]]:
    """Forward-Euler blowdown.  Returns (times, pressures_pa, vent_results).

    Detection time at ``cfg.detected_at_s`` is *not* enforced here —
    the simulator just runs until pressure ≈ vacuum or max_time.  The
    detection field is for downstream scoring (Δp lost between command
    and detection).  See `tests/unit/test_stuck_valve.py` for usage.
    """
    g, M = GAS_PROPERTIES[cfg.gas]
    R_s = R_UNIVERSAL / M
    times: List[float] = [0.0]
    pressures: List[float] = [cfg.initial_pressure_pa]
    vrs: List[VentResult] = []

    P = cfg.initial_pressure_pa
    T = cfg.initial_temperature_k
    rho = P / (R_s * T)
    init_rho = rho
    init_T = T
    t = 0.0
    while t < max_time_s and P > 1.0:
        gas = GasState(P, T, cfg.gas)
        vr = vent_thrust_and_torque(gas, cfg.geometry, 0.0, True)
        # Mass leaving the tank.
        dm = vr.mass_flow_kg_s * dt_s
        new_mass = max(rho * cfg.tank_volume_m3 - dm, 0.0)
        rho = new_mass / cfg.tank_volume_m3
        # Isentropic temperature update from density.
        ratio = max(rho / init_rho, 0.0)
        T = init_T * (ratio ** (g - 1.0)) if init_rho > 0 else T
        P = rho * R_s * T
        t += dt_s
        times.append(t)
        pressures.append(float(P))
        vrs.append(vr)
    return times, pressures, vrs
