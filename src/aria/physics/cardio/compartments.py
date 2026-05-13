"""Cardiovascular compartment ODEs (§4.1–§4.3 of K2 scope).

Closed-form analytic solutions so the ODEs can be evaluated at any
mission time without a numerical integrator. All parameters carry
inline citations.
"""

from __future__ import annotations

import math

# CGPM 1901 standard gravity.
G_ZERO_M_S2: float = 9.80665

# Hargens & Vico 2016 *Eur J Appl Physiol* 116 29 — HDT-to-0 g
# cephalic fluid shift asymptote.
FLUID_SHIFT_DELTA_V_MAX_L: float = 2.0
# Pavy-Le Traon et al. 2007 *EJAP* 101 143 HDT midpoint.
# Marked ESTIMATE in scope — cited estimate in lieu of individual data.
FLUID_SHIFT_TAU_HOURS: float = 6.0

# Convertino 1996 *J Appl Physiol* 81 7 Table 2 (biphasic PV fit).
CONVERTINO_A_FAST: float = 0.08
CONVERTINO_TAU_FAST_H: float = 24.0
CONVERTINO_A_SLOW: float = 0.05
CONVERTINO_TAU_SLOW_D: float = 14.0

# Perhonen et al. 2001 *J Appl Physiol* 91 645 — cardiac mass fit.
CARDIAC_MASS_ALPHA: float = 0.10  # 10 % mass loss at full 0 g asymptote
CARDIAC_MASS_TAU_DAYS: float = 21.0


def _gravity_deficit(local_g_m_s2: float) -> float:
    """(1 − g/g₀) clamped to [0, 1]. Negative deficit (centrifuge
    overshoot) is treated as zero since the compartment models were
    fit on 0 ≤ g ≤ 1 only."""
    if local_g_m_s2 < 0.0:
        raise ValueError("local_g_m_s2 must be non-negative")
    deficit = 1.0 - local_g_m_s2 / G_ZERO_M_S2
    if deficit < 0.0:
        return 0.0
    if deficit > 1.0:
        return 1.0
    return deficit


def cephalic_fluid_volume(
    time_s: float,
    local_g_m_s2: float,
    initial_volume_l: float = 0.0,
    delta_v_max_l: float = FLUID_SHIFT_DELTA_V_MAX_L,
    tau_hours: float = FLUID_SHIFT_TAU_HOURS,
) -> float:
    """Cephalic fluid shift volume relative to upright-1g baseline.

    Closed-form integration of
        dV/dt = (V_eq(g) − V) / τ
    with V_eq(g) = ΔV_max · (1 − g/g₀):

        V(t) = V_eq + (V₀ − V_eq) · exp(−t/τ)                [L]

    Canonical check: at t → ∞ with g = 0 → V = ΔV_max = 2 L
    (Hargens 2016).
    """
    if time_s < 0.0:
        raise ValueError("time_s must be non-negative")
    if tau_hours <= 0.0:
        raise ValueError("tau_hours must be positive")
    v_eq = delta_v_max_l * _gravity_deficit(local_g_m_s2)
    tau_s = tau_hours * 3600.0
    return v_eq + (initial_volume_l - v_eq) * math.exp(-time_s / tau_s)


def plasma_volume_fraction(
    time_hours: float,
    local_g_m_s2: float = 0.0,
    a_fast: float = CONVERTINO_A_FAST,
    tau_fast_h: float = CONVERTINO_TAU_FAST_H,
    a_slow: float = CONVERTINO_A_SLOW,
    tau_slow_d: float = CONVERTINO_TAU_SLOW_D,
) -> float:
    """Plasma volume as a fraction of upright-1g baseline.

    PV(t)/PV₀ = 1 − (1 − g/g₀) · [
        A_fast (1 − exp(−t/τ_fast)) + A_slow (1 − exp(−t/τ_slow))
    ]                                                        [–]

    (Convertino 1996 *J Appl Physiol* 81 7 Table 2, with linear
    partial-g scaling marked ESTIMATE in scope §4.2.) At t → ∞ and
    g = 0 the fraction asymptotes to 1 − (A_fast + A_slow) = 0.87,
    matching the Pavy-Le Traon 2007 bed-rest Fig 4 plateau of ≈ 87 %.
    """
    if time_hours < 0.0:
        raise ValueError("time_hours must be non-negative")
    if tau_fast_h <= 0.0 or tau_slow_d <= 0.0:
        raise ValueError("tau values must be positive")
    deficit = _gravity_deficit(local_g_m_s2)
    tau_slow_h = tau_slow_d * 24.0
    fast = a_fast * (1.0 - math.exp(-time_hours / tau_fast_h))
    slow = a_slow * (1.0 - math.exp(-time_hours / tau_slow_h))
    return 1.0 - deficit * (fast + slow)


def cardiac_mass_retention(
    time_days: float,
    local_g_m_s2: float,
    alpha: float = CARDIAC_MASS_ALPHA,
    tau_days: float = CARDIAC_MASS_TAU_DAYS,
) -> float:
    """M_heart(t) / M_0 with first-order atrophy (Perhonen 2001).

    M/M₀ = 1 − α · (1 − g/g₀) · (1 − exp(−t/τ_m))           [–]

    At 0 g, t → ∞: M → 1 − α = 0.90 (Perhonen 2001 6-week HDT ~8 %
    mean mass loss; α = 0.10 is the published asymptotic fit).
    """
    if time_days < 0.0:
        raise ValueError("time_days must be non-negative")
    if tau_days <= 0.0:
        raise ValueError("tau_days must be positive")
    deficit = _gravity_deficit(local_g_m_s2)
    return 1.0 - alpha * deficit * (1.0 - math.exp(-time_days / tau_days))
