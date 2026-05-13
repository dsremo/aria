"""TPS ablation — Goldstein 1965 charring/pyrolysis recession model.

The R37 aerocapture module computes peak heat flux + total heat load
but stops short of *recession* — how much TPS material is consumed.
For Galileo-class entries (Jupiter atmospheric probe, q̇_peak ≈ 30 kW/cm²)
recession is the dominant TPS sizing constraint; for Mars/Earth entry
it sets the heat-shield mass budget.

Model
-----

A charring TPS responds to incident heat flux by:
  1. Surface heating raises temperature.
  2. At ``T_pyrolysis`` the virgin material decomposes into char + gas.
  3. Pyrolysis gases pass through the char layer, blocking some
     convective heat (transpiration cooling) before exiting.
  4. The char surface itself oxidises / sublimates above
     ``T_ablation``; the recession rate balances mass loss against
     incident enthalpy.

The simplest closed-form per Goldstein 1965 J Aerospace Sci 32(4):

    ṁ_a = (q̇_in − q̇_blockage) / Δh_eff

with mass-injection blockage (Tauber-Sutton AIAA-91-0287 Eq 19):

    q̇_blockage = q̇_in · (1 − exp(−η · ṁ_a / ṁ_∞))

where η ≈ 0.6 for laminar boundary layers (Park 1990 §6.5).  We
solve the implicit equation by Newton iteration; convergence is
usually 3–5 steps.

Recession rate:

    ṡ = ṁ_a / ρ_TPS

Reference:
    Goldstein 1965 AIAA J 3(3) 391-393 "An exact integral relation
    for charring ablation"; Tauber & Sutton 1991 AIAA-91-0287;
    Park 1990 *Nonequilibrium Hypersonic Aerothermodynamics* §6.5;
    NASA-TM-2014-218145 (PICA), NASA TR-R-376 (Sutton-Graves baseline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# Heat of effective ablation Δh_eff (J/kg) per material.  Calibrated
# against published recession data; the table tracks NASA-TM-2014-218145
# §3 Table 3-1 + Park 1990 Tab 6.4 (RCC).
TPS_MATERIALS: Dict[str, Dict[str, float]] = {
    "PICA": {
        "density_kg_m3": 270.0,        # NASA-TM-2014-218145 Tab 3-1
        "delta_h_eff_j_kg": 4.5e6,     # Tran 1996 NASA-TM-110362
        "T_pyrolysis_k": 700.0,
        "T_ablation_k": 1900.0,
        "char_emissivity": 0.85,
    },
    "AVCOAT": {
        "density_kg_m3": 320.0,        # Apollo + MSL Aeroshell (Wright 2014)
        "delta_h_eff_j_kg": 7.8e6,
        "T_pyrolysis_k": 700.0,
        "T_ablation_k": 2100.0,
        "char_emissivity": 0.85,
    },
    "RCC": {
        "density_kg_m3": 1620.0,       # Reinforced carbon-carbon (NASA TM-X-71)
        "delta_h_eff_j_kg": 3.0e7,     # nearly non-ablating; mostly oxidation
        "T_pyrolysis_k": 1750.0,
        "T_ablation_k": 2700.0,
        "char_emissivity": 0.82,
    },
    "LI-900": {
        "density_kg_m3": 144.0,        # Shuttle silica tile (NASA SP-2010-571)
        "delta_h_eff_j_kg": 6.0e7,     # nearly non-ablating (reusable)
        "T_pyrolysis_k": 1600.0,
        "T_ablation_k": 1900.0,
        "char_emissivity": 0.90,
    },
    "Carbon_phenolic": {
        "density_kg_m3": 1450.0,        # Galileo / DragonFly (Park 1990 Tab 6.4)
        "delta_h_eff_j_kg": 1.8e7,
        "T_pyrolysis_k": 800.0,
        "T_ablation_k": 3100.0,         # high — sublimation regime
        "char_emissivity": 0.85,
    },
}


# ── Dataclasses ─────────────────────────────────────────────────


@dataclass(frozen=True)
class AblationConfig:
    """Inputs for one ablation calculation."""
    material: str
    heat_flux_w_m2: float          # incident convective heat flux
    boundary_mass_flux_kg_m2_s: float = 0.1   # ṁ_∞ — freestream mass flux
    blockage_eta: float = 0.6      # Park 1990 §6.5 — laminar BL constant
    radiative_emission: bool = True


@dataclass(frozen=True)
class AblationResult:
    mass_flux_kg_m2_s: float       # ṁ_a (recession mass flux)
    recession_rate_m_s: float      # ṡ (linear recession)
    blockage_w_m2: float           # heat blocked by mass injection
    effective_heat_flux_w_m2: float
    surface_temperature_k: float   # equilibrium re-radiation temperature
    char_thickness_m: float = 0.0
    notes: str = ""


# ── Core ────────────────────────────────────────────────────────


def _re_radiation_T(q_w_m2: float, emissivity: float) -> float:
    """Equilibrium re-radiation temperature: q = ε σ T⁴.  Stefan-
    Boltzmann constant (CODATA 2018)."""
    SIGMA = 5.670_374_419e-8
    if q_w_m2 <= 0.0 or emissivity <= 0.0:
        return 0.0
    return (q_w_m2 / (emissivity * SIGMA)) ** 0.25


def _ablation_mass_flux_implicit(
    q_in: float, delta_h: float, eta: float, m_inf: float,
) -> float:
    """Solve  ṁ_a = (q_in · exp(-η·ṁ_a/ṁ_∞)) / Δh_eff  by Newton iter.

    Initial guess: q_in / Δh_eff (no blockage); blockage shrinks it.
    """
    if q_in <= 0.0 or delta_h <= 0.0 or m_inf <= 0.0:
        return 0.0
    m = q_in / delta_h
    for _ in range(50):
        b = math.exp(-eta * m / m_inf)
        f = m * delta_h - q_in * b
        df = delta_h + q_in * (eta / m_inf) * b
        if df == 0.0:
            break
        step = f / df
        m_new = m - step
        if m_new < 0.0:
            m_new = 0.5 * m
        if abs(m_new - m) < 1e-9 * max(m, 1.0):
            return float(m_new)
        m = m_new
    return float(m)


def recession_rate_m_s(cfg: AblationConfig) -> float:
    """Convenience wrapper returning ṡ alone."""
    return simulate_ablation(cfg).recession_rate_m_s


def simulate_ablation(cfg: AblationConfig) -> AblationResult:
    if cfg.material not in TPS_MATERIALS:
        raise ValueError(
            f"unknown TPS material '{cfg.material}'; pick from "
            + ", ".join(sorted(TPS_MATERIALS))
        )
    p = TPS_MATERIALS[cfg.material]
    q_in = max(cfg.heat_flux_w_m2, 0.0)
    rho = p["density_kg_m3"]
    delta_h = p["delta_h_eff_j_kg"]
    eta = float(cfg.blockage_eta)
    m_inf = float(cfg.boundary_mass_flux_kg_m2_s)

    m_a = _ablation_mass_flux_implicit(q_in, delta_h, eta, m_inf)
    blockage = q_in * (1.0 - math.exp(-eta * m_a / m_inf if m_inf > 0 else 0))
    q_eff = q_in - blockage

    if cfg.radiative_emission:
        # Surface temperature equilibrates with ablation product gas
        # at q_eff = ε σ T⁴ (after blockage).
        T_surf = _re_radiation_T(q_eff, p["char_emissivity"])
    else:
        T_surf = 0.0

    s_dot = m_a / rho if rho > 0 else 0.0
    return AblationResult(
        mass_flux_kg_m2_s=float(m_a),
        recession_rate_m_s=float(s_dot),
        blockage_w_m2=float(blockage),
        effective_heat_flux_w_m2=float(q_eff),
        surface_temperature_k=float(T_surf),
        char_thickness_m=0.0,
        notes=(
            f"material={cfg.material} ρ={rho:.0f} kg/m³ "
            f"Δh_eff={delta_h:.2e} J/kg η={eta:.2f}"
        ),
    )
