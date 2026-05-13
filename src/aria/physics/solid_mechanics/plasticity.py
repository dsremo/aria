"""J2 plasticity — yield criterion closed forms (§4.4 of F1 scope).

The von Mises yield function (Hill 1950 eq. 2.32, ISBN 978-0198503675):

    f(σ, α, R) = σ̄_VM(σ − α) − (σ_y0 + R)                [Pa]

with α_ij back-stress (kinematic hardening) and R the isotropic
hardening variable. A stress state is elastic if f < 0, at yield if
f = 0, and forbidden if f > 0. The plastic loading case f = 0 with
ḟ > 0 is resolved by the associated flow rule and the Kuhn-Tucker-
Karush consistency conditions (Simo & Hughes 1998 *Computational
Inelasticity* §3, ISBN 978-0387975207).

For a **uniaxial** stress state σ_11 = σ, σ_22 = σ_33 = 0, the von
Mises equivalent reduces to σ̄ = |σ|, so the yield check is simply
|σ| ≥ σ_y. For a general triaxial state the test is
σ̄_VM(σ) ≥ σ_y0 + R.

The effective plastic strain increment (Simo & Hughes 1998 eq. 3.20):

    Δp̄ = √(2/3 · Δε^p_ij Δε^p_ij)                        [-]

This module exposes the closed-form yield check and the effective
plastic strain increment; the full return-mapping integrator for
rate-independent J2 plasticity is deferred to a follow-up commit
(it is an iterative algorithm that needs a consistent-tangent
Jacobian and test cases against commercial FE).
"""

from __future__ import annotations

import math

import numpy as np

from .stress_tensor import von_mises_equivalent_stress


def von_mises_yield_check(
    stress_pa: np.ndarray,
    yield_strength_pa: float,
    isotropic_hardening_r_pa: float = 0.0,
) -> tuple[bool, float]:
    """Check whether a stress state lies inside, on, or outside the
    von Mises yield surface.

    Args:
        stress_pa: (3, 3) Cauchy stress tensor (Pa).
        yield_strength_pa: initial yield stress σ_y0 (Pa).
        isotropic_hardening_r_pa: current isotropic hardening offset
            R (Pa). Defaults to 0 (no hardening history).

    Returns:
        ``(has_yielded, yield_value_f)``:
          - ``has_yielded``: True if `σ̄_VM ≥ σ_y0 + R` to numerical
            tolerance.
          - ``yield_value_f``: the value of the yield function
            `f = σ̄_VM − (σ_y0 + R)`. Negative → elastic, zero →
            at yield, positive → forbidden (return-mapping needed).
    """
    if yield_strength_pa <= 0.0:
        raise ValueError("yield_strength_pa must be positive")
    if isotropic_hardening_r_pa < 0.0:
        raise ValueError("isotropic_hardening_r_pa must be non-negative")
    sigma_vm = von_mises_equivalent_stress(stress_pa)
    f = sigma_vm - (yield_strength_pa + isotropic_hardening_r_pa)
    return bool(f >= -1e-9), f


def effective_plastic_strain_increment(
    plastic_strain_increment: np.ndarray,
) -> float:
    """Effective plastic strain increment `Δp̄ = √(2/3 · Δε^p_ij Δε^p_ij)`.

    Args:
        plastic_strain_increment: (3, 3) symmetric plastic strain
            increment tensor Δε^p_ij (dimensionless).

    Returns:
        Scalar Δp̄ (dimensionless, non-negative).
    """
    dep = np.asarray(plastic_strain_increment, dtype=float).reshape(3, 3)
    dep = 0.5 * (dep + dep.T)  # symmetrize defensively
    return math.sqrt((2.0 / 3.0) * float(np.sum(dep * dep)))


# ════════════════════════════════════════════════════════════════════
#  Return-mapping integrator — Simo & Hughes (1998) Box 3.1
# ════════════════════════════════════════════════════════════════════

def _deviator(stress: np.ndarray) -> np.ndarray:
    """Deviatoric part s_ij = σ_ij − (tr σ / 3) δ_ij."""
    tr = np.trace(stress)
    s = stress.copy()
    s[0, 0] -= tr / 3
    s[1, 1] -= tr / 3
    s[2, 2] -= tr / 3
    return s


def radial_return_j2(
    stress_n: np.ndarray,
    strain_increment: np.ndarray,
    plastic_strain_n: float,
    youngs_modulus_pa: float,
    poisson_ratio: float,
    yield_strength_pa: float,
    hardening_modulus_pa: float = 0.0,
) -> tuple[np.ndarray, float, float, bool]:
    """Rate-independent J2 plasticity return mapping with linear isotropic
    hardening. Computes one load step from `stress_n` given a strain increment.

    Algorithm (Simo & Hughes 1998 §3.3, Box 3.1):

        σ^trial = σ^n + C : Δε                      # elastic predictor
        s^trial = dev(σ^trial)
        f^trial = ||s^trial|| − √(2/3) (σ_y + H p^n)
        if f^trial ≤ 0: σ = σ^trial          # stays elastic
        else:
            Δγ = f^trial / (2μ + (2/3) H)
            n̂ = s^trial / ||s^trial||
            σ = σ^trial − 2μ Δγ n̂
            p = p^n + √(2/3) Δγ

    Args:
        stress_n: (3,3) Cauchy stress at step n (Pa).
        strain_increment: (3,3) symmetric total strain increment Δε.
        plastic_strain_n: accumulated effective plastic strain p^n.
        youngs_modulus_pa: E (Pa).
        poisson_ratio: ν (dimensionless, 0 ≤ ν < 0.5).
        yield_strength_pa: σ_y (Pa).
        hardening_modulus_pa: H (Pa). Linear isotropic hardening; H=0 for
            perfect plasticity, H>0 for work-hardening.

    Returns:
        ``(stress_new, plastic_strain_new, delta_gamma, plastic)``
            stress_new: (3,3) updated Cauchy stress
            plastic_strain_new: updated accumulated effective plastic strain
            delta_gamma: plastic multiplier Δγ (0 for elastic step)
            plastic: True if the step was plastic
    """
    if yield_strength_pa <= 0.0:
        raise ValueError("yield_strength_pa must be positive")
    if not (0.0 <= poisson_ratio < 0.5):
        raise ValueError("poisson_ratio must be in [0, 0.5)")
    if hardening_modulus_pa < 0.0:
        raise ValueError("hardening_modulus_pa must be non-negative")

    E = youngs_modulus_pa
    nu = poisson_ratio
    H = hardening_modulus_pa
    mu = E / (2.0 * (1.0 + nu))          # shear modulus
    K = E / (3.0 * (1.0 - 2.0 * nu))     # bulk modulus

    # Symmetrize inputs
    s_n = 0.5 * (stress_n + stress_n.T)
    d_eps = 0.5 * (strain_increment + strain_increment.T)

    # Elastic predictor (isotropic elasticity): σ = σ^n + λ tr(Δε) I + 2μ Δε
    tr_de = np.trace(d_eps)
    lam = K - (2.0 / 3.0) * mu           # Lamé's first parameter
    I3 = np.eye(3)
    stress_trial = s_n + lam * tr_de * I3 + 2.0 * mu * d_eps

    # Deviatoric trial stress
    s_trial = _deviator(stress_trial)
    s_trial_norm = math.sqrt(np.sum(s_trial * s_trial))

    # Yield-surface radius in stress space
    yield_radius = math.sqrt(2.0 / 3.0) * (yield_strength_pa
                                            + H * plastic_strain_n)

    f_trial = s_trial_norm - yield_radius
    if f_trial <= 0.0 or s_trial_norm < 1e-12:
        # Elastic step — trial stress is admissible
        return stress_trial, plastic_strain_n, 0.0, False

    # Plastic correction (radial return). Closed form for linear H:
    #   Δγ = f^trial / (2μ + (2/3) H)
    delta_gamma = f_trial / (2.0 * mu + (2.0 / 3.0) * H)
    n_hat = s_trial / s_trial_norm
    stress_new = stress_trial - 2.0 * mu * delta_gamma * n_hat
    plastic_strain_new = plastic_strain_n + math.sqrt(2.0 / 3.0) * delta_gamma
    return stress_new, plastic_strain_new, float(delta_gamma), True


def consistent_tangent_modulus(
    stress_trial: np.ndarray,
    delta_gamma: float,
    youngs_modulus_pa: float,
    poisson_ratio: float,
    hardening_modulus_pa: float = 0.0,
) -> np.ndarray:
    """Algorithmic (consistent) tangent for linear isotropic-hardening J2
    plasticity — Simo & Hughes (1998) eq. 3.45.

    Returns the 6x6 Voigt-form operator C^ep.

    This is the object Newton-Raphson iterators (e.g. an FEA nonlinear
    loop) need to achieve quadratic convergence. It differs from the
    continuum tangent above the yield surface.
    """
    E = youngs_modulus_pa
    nu = poisson_ratio
    mu = E / (2.0 * (1.0 + nu))
    K = E / (3.0 * (1.0 - 2.0 * nu))
    H = hardening_modulus_pa

    s_trial = _deviator(stress_trial)
    s_norm = math.sqrt(np.sum(s_trial * s_trial))
    if s_norm < 1e-12:
        theta = 1.0
        theta_bar = 0.0
        n = np.zeros((3, 3))
    else:
        # θ and θ̄ from Simo & Hughes
        # θ = 1 − 2μΔγ / ||s^trial||
        theta = 1.0 - 2.0 * mu * delta_gamma / s_norm
        theta_bar = 1.0 / (1.0 + H / (3.0 * mu)) - (1.0 - theta)
        n = s_trial / s_norm

    # Build the 6x6 Voigt tangent
    # C^ep = K·(1⊗1) + 2μθ·P_dev − 2μ θ̄·(n ⊗ n)
    # Where P_dev is the deviatoric projector.
    one = np.array([1, 1, 1, 0, 0, 0], dtype=float)
    I4 = np.eye(6)
    # Voigt deviatoric projector
    P_dev = I4 - (1.0 / 3.0) * np.outer(one, one)
    # Shear entries need the factor 2
    P_dev[3, 3] = 0.5
    P_dev[4, 4] = 0.5
    P_dev[5, 5] = 0.5

    n_voigt = np.array([n[0, 0], n[1, 1], n[2, 2], n[0, 1], n[1, 2], n[0, 2]], dtype=float)

    Cep = K * np.outer(one, one) + 2.0 * mu * theta * P_dev \
          - 2.0 * mu * theta_bar * np.outer(n_voigt, n_voigt)
    return Cep
