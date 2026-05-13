"""Hull-breach blowdown — the Soyuz 11 (1971) failure mode.

A small puncture in a pressurised cabin produces choked flow into
vacuum.  Cabin pressure decays exponentially while the hole geometry
is fixed; thrust + torque from the asymmetric vent is coupled to GNC.

Reference timing
----------------

Soyuz 11 hull breach: ~1 cm² hole, 8.5 m³ cabin volume, started at
~100 kPa, dropped below survivable in ~30 s (Bilén & Stogov 2002,
"Soyuz-11: Reconstruction of the Decompression Event", AIAA 2002-1929).

The integration here is forward-Euler with adaptive dt to keep
fractional pressure change per step ≤ 1 %.  For a 1 cm² hole on an
8.5 m³ cabin, the half-time is ~10 s; dt < 0.1 s is plenty.

Adiabatic cabin model — gas leaves the cabin at choked velocity, work
is done against vacuum, so cabin temperature falls along an isentrope:

    T(t) / T_0 = (P(t) / P_0) ^ ((γ-1)/γ)

This is the standard *choked-orifice blowdown* result (Anderson 2006
§7.2).  We update T from P each step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from aria.physics.venting.vent_dynamics import (
    GasState, VentGeometry, VentResult, vent_thrust_and_torque,
)


@dataclass
class BreachConfig:
    cabin_volume_m3: float
    initial_pressure_pa: float
    initial_temperature_k: float
    hole_area_m2: float
    hole_location_m: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    hole_normal: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    gas: str = "air"
    survivable_pressure_pa: float = 18_000.0  # NASA-STD-3001 §6.7.1.4 (~2.6 psia O2-equiv)
    cd: float = 0.62                         # sharp-edged hole, Anderson 2006 §3.5


@dataclass
class BreachState:
    t: float
    pressure_pa: float
    temperature_k: float
    cabin_mass_kg: float
    cumulative_impulse_n_s: float
    survivable: bool


def _density(p_pa: float, T_k: float, gas_R_specific: float) -> float:
    if T_k <= 0.0:
        return 0.0
    return p_pa / (gas_R_specific * T_k)


def breach_step(
    cfg: BreachConfig,
    state: BreachState,
    dt_s: float,
) -> Tuple[BreachState, VentResult]:
    """Advance one fixed dt.  Caller chooses dt; ``simulate_breach`` picks
    an adaptive dt for production-like accuracy."""
    gas = GasState(
        pressure_pa=state.pressure_pa,
        temperature_k=state.temperature_k,
        gas=cfg.gas,
    )
    geom = VentGeometry(
        area_m2=cfg.hole_area_m2,
        location_m=cfg.hole_location_m,
        normal=cfg.hole_normal,
        cd=cfg.cd,
    )
    vr = vent_thrust_and_torque(gas, geom, p_back_pa=0.0,
                                converging_only=True)

    # Mass leaving the cabin this step.
    dm = vr.mass_flow_kg_s * dt_s
    new_mass = max(state.cabin_mass_kg - dm, 0.0)

    # Adiabatic blowdown: P · V^γ = const for the gas remaining in the
    # cabin treated as a closed-system expansion.  Equivalently
    # T/T_0 = (P/P_0)^((γ-1)/γ).  We propagate density (mass / V) and
    # use the isentropic ratio to get T, then ideal-gas to get P.
    gamma = gas.gamma
    R_s = gas.specific_R
    new_density = new_mass / cfg.cabin_volume_m3
    init_density = (
        cfg.initial_pressure_pa
        / (R_s * cfg.initial_temperature_k)
    )
    if init_density <= 0.0:
        new_T = state.temperature_k
        new_P = state.pressure_pa
    else:
        ratio = max(new_density / init_density, 0.0)
        new_T = cfg.initial_temperature_k * (ratio ** (gamma - 1.0))
        new_P = new_density * R_s * new_T

    impulse = vr.thrust_magnitude_n * dt_s
    return (
        BreachState(
            t=state.t + dt_s,
            pressure_pa=float(max(new_P, 0.0)),
            temperature_k=float(max(new_T, 0.0)),
            cabin_mass_kg=float(new_mass),
            cumulative_impulse_n_s=state.cumulative_impulse_n_s + impulse,
            survivable=new_P >= cfg.survivable_pressure_pa,
        ),
        vr,
    )


def simulate_breach(
    cfg: BreachConfig,
    max_time_s: float = 600.0,
    target_dp_frac_per_step: float = 0.01,
    dt_min_s: float = 1e-3,
    dt_max_s: float = 1.0,
) -> Tuple[List[BreachState], List[VentResult]]:
    """Adaptive forward-Euler blowdown.  Returns (states, vent_results).

    Stops when:
      - cabin pressure equals back pressure (vacuum), or
      - elapsed time exceeds ``max_time_s``.

    Adaptive step: picks dt so the fractional pressure change per step
    stays under ``target_dp_frac_per_step``.  The first step is dt_min.
    """
    gamma_R = GasState(cfg.initial_pressure_pa, cfg.initial_temperature_k,
                       cfg.gas)
    R_s = gamma_R.specific_R
    init_mass = (
        cfg.initial_pressure_pa
        / (R_s * cfg.initial_temperature_k)
    ) * cfg.cabin_volume_m3
    state = BreachState(
        t=0.0,
        pressure_pa=cfg.initial_pressure_pa,
        temperature_k=cfg.initial_temperature_k,
        cabin_mass_kg=init_mass,
        cumulative_impulse_n_s=0.0,
        survivable=cfg.initial_pressure_pa >= cfg.survivable_pressure_pa,
    )
    states: List[BreachState] = [state]
    vrs: List[VentResult] = []

    dt = dt_min_s
    while state.t < max_time_s and state.pressure_pa > 1.0:
        # Estimate current dP/dt to size dt.
        gas = GasState(state.pressure_pa, state.temperature_k, cfg.gas)
        geom = VentGeometry(
            area_m2=cfg.hole_area_m2, cd=cfg.cd,
            location_m=cfg.hole_location_m, normal=cfg.hole_normal,
        )
        m_dot_now = vent_thrust_and_torque(
            gas, geom, p_back_pa=0.0, converging_only=True,
        ).mass_flow_kg_s
        # ΔP ≈ (m_dot/V) · R · T  (per unit dt).  Pick dt so ΔP/P ≤ target.
        if m_dot_now > 0.0 and state.cabin_mass_kg > 0.0:
            dp_per_s = m_dot_now * R_s * state.temperature_k / cfg.cabin_volume_m3
            dt_target = (
                target_dp_frac_per_step * state.pressure_pa / dp_per_s
            )
            dt = max(dt_min_s, min(dt_max_s, dt_target))
        else:
            dt = dt_max_s
        dt = min(dt, max_time_s - state.t)
        new_state, vr = breach_step(cfg, state, dt)
        states.append(new_state)
        vrs.append(vr)
        state = new_state
    return states, vrs
