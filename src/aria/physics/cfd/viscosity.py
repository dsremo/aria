"""Sutherland viscosity law (§4.10 of H1 scope).

Closed-form temperature dependence of dynamic viscosity for gases,

    μ(T) = μ_ref · (T / T_ref)^{3/2} · (T_ref + S) / (T + S)    [Pa·s]

derived by Sutherland 1893 from rigid-sphere kinetic theory with a
weak intermolecular attraction. White 2006 *Viscous Fluid Flow* 3rd
ed §1.4 Table 1-2 tabulates the canonical air coefficients used here.
Accurate to ~2 % over 100–1800 K.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SutherlandParameters:
    """Three-parameter Sutherland fit (μ_ref, T_ref, S).

    Attributes:
        mu_ref_pa_s: reference viscosity at T_ref (Pa·s).
        t_ref_k: reference temperature (K).
        s_k: Sutherland constant (K).
        source: citation.
    """

    mu_ref_pa_s: float
    t_ref_k: float
    s_k: float
    source: str


# Dry-air Sutherland coefficients from White 2006 Table 1-2 (also
# tabulated in Incropera 2011 Table A.4).
AIR_SUTHERLAND: SutherlandParameters = SutherlandParameters(
    mu_ref_pa_s=1.716e-5,  # White 2006 Table 1-2
    t_ref_k=273.15,  # White 2006 Table 1-2
    s_k=110.4,  # White 2006 Table 1-2
    source="White 2006 Viscous Fluid Flow 3rd ed Table 1-2",
)


def sutherland_viscosity(
    temperature_k: float, params: SutherlandParameters = AIR_SUTHERLAND
) -> float:
    """Dynamic viscosity μ(T) via the Sutherland law.

    Canonical check: μ_air(293.15 K) ≈ 1.82×10⁻⁵ Pa·s
    (NIST WebBook; Incropera 2011 Table A.4).
    """
    if temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive")
    t_ratio = temperature_k / params.t_ref_k
    return (
        params.mu_ref_pa_s
        * t_ratio**1.5
        * (params.t_ref_k + params.s_k)
        / (temperature_k + params.s_k)
    )
