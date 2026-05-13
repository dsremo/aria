"""Non-Newtonian constitutive laws (§4.9 of H2 scope).

Carreau model (Bird, Stewart & Lightfoot 2007 *Transport Phenomena*
2nd ed §2.5 eq. 2.5-9):

    μ(γ̇) = μ_∞ + (μ_0 − μ_∞) [1 + (λ γ̇)²]^{(n−1)/2}        [Pa·s]

Power-law (Ostwald-de Waele, Bird 2007 §2.5 eq. 2.5-7):

    μ(γ̇) = K γ̇^{n−1}                                        [Pa·s]

Bingham plastic (Bird 2007 §2.5):

    τ = τ_0 + μ_p γ̇    (for τ > τ_0)                        [Pa]

Blood-specific Carreau parameters from Yeleswarapu 1998 PhD thesis
(Univ. Pittsburgh), Table 4.1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CarreauModel:
    """Five-parameter Carreau fit (μ_∞, μ_0, λ, n, source).

    Attributes:
        mu_inf_pa_s: μ_∞ infinite-shear viscosity (Pa·s).
        mu_0_pa_s: μ_0 zero-shear viscosity (Pa·s).
        lambda_s: λ time constant (s).
        n_exponent: n power-law index (dimensionless, usually < 1).
        source: citation.
    """

    mu_inf_pa_s: float
    mu_0_pa_s: float
    lambda_s: float
    n_exponent: float
    source: str


# Yeleswarapu 1998 PhD thesis Univ Pittsburgh Table 4.1 whole-blood
# Carreau fit (room-temperature, high-haematocrit donor).
BLOOD_CARREAU_YELESWARAPU: CarreauModel = CarreauModel(
    mu_inf_pa_s=3.45e-3,
    mu_0_pa_s=0.056,
    lambda_s=3.313,
    n_exponent=0.3568,
    source="Yeleswarapu 1998 PhD thesis Univ Pittsburgh Table 4.1",
)


def carreau_apparent_viscosity(
    shear_rate_1_s: float, model: CarreauModel = BLOOD_CARREAU_YELESWARAPU
) -> float:
    """Carreau apparent viscosity at a given shear rate.

    Bird 2007 eq. 2.5-9. At γ̇ → 0 returns μ_0; at γ̇ → ∞ returns
    μ_∞. For blood: 0.056 Pa·s at rest, 3.45e-3 Pa·s at high shear.
    """
    if shear_rate_1_s < 0.0:
        raise ValueError("shear_rate_1_s must be non-negative")
    if model.mu_inf_pa_s <= 0.0 or model.mu_0_pa_s <= 0.0:
        raise ValueError("Carreau viscosities must be positive")
    if model.lambda_s <= 0.0:
        raise ValueError("lambda_s must be positive")
    bracket = 1.0 + (model.lambda_s * shear_rate_1_s) ** 2
    return (
        model.mu_inf_pa_s
        + (model.mu_0_pa_s - model.mu_inf_pa_s)
        * bracket ** ((model.n_exponent - 1.0) / 2.0)
    )


def power_law_apparent_viscosity(
    shear_rate_1_s: float,
    consistency_index_pa_sn: float,
    power_law_exponent: float,
) -> float:
    """Ostwald-de Waele power-law viscosity μ = K γ̇^{n−1}.

    For n < 1 this is shear-thinning; n > 1 shear-thickening;
    n = 1 reduces to Newtonian with μ = K.
    """
    if shear_rate_1_s < 0.0:
        raise ValueError("shear_rate_1_s must be non-negative")
    if consistency_index_pa_sn <= 0.0:
        raise ValueError("consistency_index_pa_sn must be positive")
    if shear_rate_1_s == 0.0:
        # power-law singularity — return K (the n=1 Newtonian fallback).
        return consistency_index_pa_sn
    return consistency_index_pa_sn * shear_rate_1_s ** (power_law_exponent - 1.0)


def bingham_apparent_viscosity(
    shear_rate_1_s: float,
    yield_stress_pa: float,
    plastic_viscosity_pa_s: float,
) -> float:
    """Bingham-plastic apparent viscosity μ_app = τ / γ̇
    with τ = τ_0 + μ_p γ̇ (for τ > τ_0).

    Returns +∞ at γ̇ = 0 (unyielded). Caller is responsible for the
    yield check.
    """
    if shear_rate_1_s < 0.0:
        raise ValueError("shear_rate_1_s must be non-negative")
    if yield_stress_pa < 0.0:
        raise ValueError("yield_stress_pa must be non-negative")
    if plastic_viscosity_pa_s <= 0.0:
        raise ValueError("plastic_viscosity_pa_s must be positive")
    if shear_rate_1_s == 0.0:
        return float("inf")
    return yield_stress_pa / shear_rate_1_s + plastic_viscosity_pa_s
