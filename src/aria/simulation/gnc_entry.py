"""Simplified GNC (Guidance, Navigation & Control) for Entry Corridor Analysis.

The entry angle at EI is not a knob you turn — it's a result of navigation
accuracy, mid-course corrections, and atmospheric uncertainty. This module
models the full chain from navigation error to entry corridor success probability.

WHY THIS MATTERS
================
Apollo's entry corridor was ±1° around −6.5° (−5.5° to −7.5°). The 3σ
navigation error for Apollo was ~0.3° — tight, but achievable with DSN tracking.

If navigation error exceeds the corridor width, the capsule either:
  - Skips out of atmosphere (too shallow) → misses Earth → crew loss
  - Burns up / exceeds G-limit (too steep) → structural failure → crew loss

This module computes the probability that navigation + atmospheric errors
cause the entry angle to fall outside the safe corridor.

NAVIGATION ERROR MODEL
======================
Entry angle uncertainty comes from three sources:

1. State knowledge error (DSN tracking):
   - Apollo: σ_position ≈ 1 km, σ_velocity ≈ 0.1 m/s at last TCM
   - Artemis/Orion: σ_position ≈ 0.3 km, σ_velocity ≈ 0.03 m/s (GPS + DSN)
   - Maps to σ_γ ≈ 0.05–0.15° at EI (geometry-dependent)

2. Mid-course correction (TCM) execution error:
   - Engine pointing: ±0.1° (Apollo); ±0.03° (modern inertial nav)
   - Thrust magnitude: ±0.3% (Apollo SPS); ±0.1% (modern hydrazine)
   - Maps to σ_γ ≈ 0.02–0.05° at EI

3. Atmospheric density uncertainty:
   - Entry day density can be ±30% from prediction (solar activity, diurnal)
   - Effect on γ_effective: ≈ ±0.1° (the atmosphere "pulls" the trajectory)
   - Maps to σ_γ ≈ 0.05–0.1°

Combined: σ_γ_total = sqrt(σ_nav² + σ_tcm² + σ_atmo²) ≈ 0.1–0.2° (3σ ≈ 0.3–0.6°)

References
----------
  NASA SP-287 (1971) "What Made Apollo a Success?" §6 — reentry guidance
  NASA SP-350 (1975) §7.5 — entry corridor and navigation accuracy
  NASA/TM-2011-217144 §4 — Orion GN&C entry guidance requirements
  Battin R.H. (1999) "An Introduction to the Mathematics and Methods of
    Astrodynamics" §11 — navigation and guidance
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# Entry corridor bounds (NASA SP-350 §7.5; NASA SP-4009 §6.4)
CORRIDOR_NOMINAL_DEG = -6.5   # Nominal entry angle (deg) — Apollo/Artemis
CORRIDOR_SHALLOW_DEG = -5.5   # Shallow limit (deg) — skip-out risk
CORRIDOR_STEEP_DEG   = -7.5   # Steep limit (deg) — overheat/structural risk
CORRIDOR_WIDTH_DEG   = abs(CORRIDOR_SHALLOW_DEG - CORRIDOR_STEEP_DEG)  # 2.0°

# Apollo navigation accuracy (NASA SP-287 §6; Battin 1999 §11.4)
APOLLO_NAV_SIGMA_DEG    = 0.10  # 1σ entry angle from DSN tracking — NASA SP-287 §6.3
APOLLO_TCM_SIGMA_DEG    = 0.03  # 1σ from TCM execution error — NASA SP-287 §6.5
APOLLO_ATMO_SIGMA_DEG   = 0.07  # 1σ from atmospheric uncertainty — NASA SP-287 §6.6

# Modern (Artemis/Orion) navigation accuracy (NASA/TM-2011-217144 §4.2)
MODERN_NAV_SIGMA_DEG    = 0.05  # 1σ from GPS + DSN — NASA/TM-2011-217144 §4.2
MODERN_TCM_SIGMA_DEG    = 0.02  # 1σ from modern RCS — NASA/TM-2011-217144 §4.3
MODERN_ATMO_SIGMA_DEG   = 0.06  # 1σ from atmospheric model error — ESTIMATE


# ═══════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class NavigationErrorBudget:
    """Navigation error budget for entry angle prediction."""
    nav_sigma_deg: float       # 1σ state knowledge error mapped to γ at EI
    tcm_sigma_deg: float       # 1σ TCM execution error mapped to γ at EI
    atmo_sigma_deg: float      # 1σ atmospheric density prediction error
    total_sigma_deg: float     # RSS combined 1σ
    three_sigma_deg: float     # 3σ total (99.7% bounds)


@dataclass
class CorridorAnalysis:
    """Entry corridor probability analysis."""
    nominal_angle_deg: float           # Target entry angle (deg)
    corridor_shallow_deg: float        # Shallow bound (deg)
    corridor_steep_deg: float          # Steep bound (deg)
    corridor_width_deg: float          # Total corridor width (deg)
    sigma_total_deg: float             # 1σ entry angle uncertainty (deg)
    probability_in_corridor: float     # P(γ within corridor) — the money number
    probability_skip_out: float        # P(γ > shallow limit) — crew loss scenario
    probability_overheat: float        # P(γ < steep limit) — crew loss scenario
    margin_shallow_sigma: float        # (nominal − shallow) / σ — margin in σ units
    margin_steep_sigma: float          # (steep − nominal) / σ — margin in σ units
    min_margin_sigma: float            # min of both margins — limiting margin


@dataclass
class MonteCarloResult:
    """Monte Carlo entry corridor simulation result."""
    n_samples: int
    nominal_angle_deg: float
    sigma_deg: float
    angles_deg: np.ndarray             # Sampled entry angles (N,)
    in_corridor: np.ndarray            # Boolean array (N,)
    skip_out: np.ndarray               # Boolean array (N,)
    overheat: np.ndarray               # Boolean array (N,)
    fraction_in_corridor: float
    fraction_skip_out: float
    fraction_overheat: float
    peak_decel_g: np.ndarray           # Peak decel for each sample (N,)
    peak_heat_w_cm2: np.ndarray        # Peak heat rate for each sample (N,)


# ═══════════════════════════════════════════════════════════════════
#  NAVIGATION ERROR BUDGET
# ═══════════════════════════════════════════════════════════════════

def navigation_error_budget(
    nav_sigma_deg: float = MODERN_NAV_SIGMA_DEG,
    tcm_sigma_deg: float = MODERN_TCM_SIGMA_DEG,
    atmo_sigma_deg: float = MODERN_ATMO_SIGMA_DEG,
) -> NavigationErrorBudget:
    """Compute the combined navigation error budget for entry angle.

    The three error sources are statistically independent (Gaussian), so
    they combine as root-sum-square (RSS):
      σ_total = sqrt(σ_nav² + σ_tcm² + σ_atmo²)

    Args:
        nav_sigma_deg:  1σ state knowledge error at EI (deg).
        tcm_sigma_deg:  1σ TCM execution error at EI (deg).
        atmo_sigma_deg: 1σ atmospheric model error (deg).

    Returns:
        NavigationErrorBudget with combined sigma.

    References:
        NASA SP-287 §6 — Apollo navigation error budget.
        Battin (1999) §11.4 — RSS error combination.
    """
    sigma_total = math.sqrt(nav_sigma_deg**2 + tcm_sigma_deg**2 + atmo_sigma_deg**2)
    return NavigationErrorBudget(
        nav_sigma_deg=nav_sigma_deg,
        tcm_sigma_deg=tcm_sigma_deg,
        atmo_sigma_deg=atmo_sigma_deg,
        total_sigma_deg=sigma_total,
        three_sigma_deg=3.0 * sigma_total,
    )


# ═══════════════════════════════════════════════════════════════════
#  CORRIDOR PROBABILITY (ANALYTICAL)
# ═══════════════════════════════════════════════════════════════════

def corridor_probability(
    nominal_angle_deg: float = CORRIDOR_NOMINAL_DEG,
    sigma_deg: float = 0.1,
    corridor_shallow_deg: float = CORRIDOR_SHALLOW_DEG,
    corridor_steep_deg: float = CORRIDOR_STEEP_DEG,
) -> CorridorAnalysis:
    """Compute probability that the entry angle falls within the safe corridor.

    Models entry angle as Gaussian: γ ~ N(γ_nominal, σ²)
    P(in corridor) = Φ((γ_shallow − γ_nom)/σ) − Φ((γ_steep − γ_nom)/σ)

    where Φ is the standard normal CDF.

    Args:
        nominal_angle_deg:     Target entry angle (deg, negative).
        sigma_deg:             1σ entry angle uncertainty (deg).
        corridor_shallow_deg:  Shallow corridor bound (deg, negative, less negative).
        corridor_steep_deg:    Steep corridor bound (deg, negative, more negative).

    Returns:
        CorridorAnalysis with probabilities and margins.

    References:
        NASA SP-350 §7.5 — Apollo entry corridor ±1°.
    """
    from scipy.stats import norm

    # Margins in sigma units
    margin_shallow = (nominal_angle_deg - corridor_shallow_deg) / sigma_deg
    margin_steep = (corridor_steep_deg - nominal_angle_deg) / sigma_deg

    # CDF-based probabilities
    # P(γ > shallow) = skip out (γ is negative, "shallow" is less negative)
    z_shallow = (corridor_shallow_deg - nominal_angle_deg) / sigma_deg
    z_steep = (corridor_steep_deg - nominal_angle_deg) / sigma_deg

    p_skip = 1.0 - norm.cdf(z_shallow)   # P(γ > shallow limit)
    p_overheat = norm.cdf(z_steep)        # P(γ < steep limit)
    p_in_corridor = 1.0 - p_skip - p_overheat

    return CorridorAnalysis(
        nominal_angle_deg=nominal_angle_deg,
        corridor_shallow_deg=corridor_shallow_deg,
        corridor_steep_deg=corridor_steep_deg,
        corridor_width_deg=abs(corridor_shallow_deg - corridor_steep_deg),
        sigma_total_deg=sigma_deg,
        probability_in_corridor=p_in_corridor,
        probability_skip_out=p_skip,
        probability_overheat=p_overheat,
        margin_shallow_sigma=abs(margin_shallow),
        margin_steep_sigma=abs(margin_steep),
        min_margin_sigma=min(abs(margin_shallow), abs(margin_steep)),
    )


# ═══════════════════════════════════════════════════════════════════
#  MONTE CARLO ENTRY CORRIDOR
# ═══════════════════════════════════════════════════════════════════

def monte_carlo_entry(
    nominal_angle_deg: float = CORRIDOR_NOMINAL_DEG,
    sigma_deg: float = 0.1,
    v_entry_ms: float = 11_000.0,
    ballistic_coeff: float = 335.0,
    lift_to_drag: float = 0.3,
    n_samples: int = 10_000,
    seed: int = 42,
    corridor_shallow_deg: float = CORRIDOR_SHALLOW_DEG,
    corridor_steep_deg: float = CORRIDOR_STEEP_DEG,
) -> MonteCarloResult:
    """Monte Carlo simulation of entry corridor success probability.

    Samples N entry angles from N(nominal, σ²) and computes peak deceleration
    and peak heat rate for each using the calibrated Apollo/Orion formulas
    from lunar_return.py.

    This is the standard approach for mission safety certification — NASA
    requires P(safe corridor) > 0.999 (3σ margin) for crewed missions.

    Args:
        nominal_angle_deg: Target entry angle (deg, negative).
        sigma_deg:         1σ angle uncertainty (deg).
        v_entry_ms:        Entry speed at EI (m/s).
        ballistic_coeff:   β (kg/m²).
        lift_to_drag:      L/D of entry vehicle.
        n_samples:         Number of Monte Carlo samples.
        seed:              Random seed for reproducibility.
        corridor_shallow_deg: Shallow bound (deg).
        corridor_steep_deg:   Steep bound (deg).

    Returns:
        MonteCarloResult with sampled angles, decel/heat arrays, and statistics.

    References:
        NASA SP-287 §6 — Monte Carlo entry analysis approach.
        NASA-STD-8729.1A — probabilistic risk assessment.
    """
    from aria.simulation.lunar_return import compute_reentry

    rng = np.random.default_rng(seed)
    angles = rng.normal(nominal_angle_deg, sigma_deg, n_samples)

    in_corridor = np.zeros(n_samples, dtype=bool)
    skip_out = np.zeros(n_samples, dtype=bool)
    overheat = np.zeros(n_samples, dtype=bool)
    peak_g = np.zeros(n_samples)
    peak_q = np.zeros(n_samples)

    for i, gamma in enumerate(angles):
        in_corridor[i] = corridor_steep_deg <= gamma <= corridor_shallow_deg
        skip_out[i] = gamma > corridor_shallow_deg
        overheat[i] = gamma < corridor_steep_deg

        # Compute reentry parameters for this angle
        re = compute_reentry(
            v_entry_ms,
            entry_angle_deg=gamma,
            ballistic_coeff=ballistic_coeff,
            lift_to_drag=lift_to_drag,
        )
        peak_g[i] = re.peak_decel_g
        peak_q[i] = re.peak_heat_rate_w_cm2

    return MonteCarloResult(
        n_samples=n_samples,
        nominal_angle_deg=nominal_angle_deg,
        sigma_deg=sigma_deg,
        angles_deg=angles,
        in_corridor=in_corridor,
        skip_out=skip_out,
        overheat=overheat,
        fraction_in_corridor=float(np.mean(in_corridor)),
        fraction_skip_out=float(np.mean(skip_out)),
        fraction_overheat=float(np.mean(overheat)),
        peak_decel_g=peak_g,
        peak_heat_w_cm2=peak_q,
    )


# ═══════════════════════════════════════════════════════════════════
#  MISSION-SPECIFIC PROFILES
# ═══════════════════════════════════════════════════════════════════

def apollo_gnc_analysis() -> CorridorAnalysis:
    """Apollo-era GNC corridor analysis.

    Apollo navigation accuracy: 3σ ≈ 0.36° (NASA SP-287 §6).
    Corridor: −5.5° to −7.5° (±1° around −6.5°).
    Margin: 1.0° / 0.12° ≈ 8.3σ → P(safe) > 0.999999.

    Reference: NASA SP-287 (1971) §6; NASA SP-350 (1975) §7.5.
    """
    budget = navigation_error_budget(
        APOLLO_NAV_SIGMA_DEG, APOLLO_TCM_SIGMA_DEG, APOLLO_ATMO_SIGMA_DEG,
    )
    return corridor_probability(
        CORRIDOR_NOMINAL_DEG, budget.total_sigma_deg,
    )


def artemis_gnc_analysis() -> CorridorAnalysis:
    """Artemis/Orion GNC corridor analysis.

    Modern navigation: GPS + DSN gives better state knowledge.
    But Artemis 2 used a shallower entry angle (−3.7°), which shifts
    the corridor. Using standard Apollo corridor for comparison.

    Reference: NASA/TM-2011-217144 §4.2.
    """
    budget = navigation_error_budget(
        MODERN_NAV_SIGMA_DEG, MODERN_TCM_SIGMA_DEG, MODERN_ATMO_SIGMA_DEG,
    )
    return corridor_probability(
        CORRIDOR_NOMINAL_DEG, budget.total_sigma_deg,
    )


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n── GNC Entry Corridor Analysis ──────────────────────────────")

    print("\n1. Apollo-era navigation error budget:")
    ab = navigation_error_budget(APOLLO_NAV_SIGMA_DEG, APOLLO_TCM_SIGMA_DEG, APOLLO_ATMO_SIGMA_DEG)
    print(f"   σ_nav:    {ab.nav_sigma_deg:.3f}°")
    print(f"   σ_tcm:    {ab.tcm_sigma_deg:.3f}°")
    print(f"   σ_atmo:   {ab.atmo_sigma_deg:.3f}°")
    print(f"   σ_total:  {ab.total_sigma_deg:.3f}° (3σ = {ab.three_sigma_deg:.3f}°)")

    print("\n2. Apollo corridor probability:")
    ac = apollo_gnc_analysis()
    print(f"   Corridor:     [{ac.corridor_steep_deg}°, {ac.corridor_shallow_deg}°] "
          f"(width {ac.corridor_width_deg:.1f}°)")
    print(f"   Nominal:      {ac.nominal_angle_deg}°")
    print(f"   P(safe):      {ac.probability_in_corridor:.8f}")
    print(f"   P(skip-out):  {ac.probability_skip_out:.2e}")
    print(f"   P(overheat):  {ac.probability_overheat:.2e}")
    print(f"   Margin:       {ac.min_margin_sigma:.1f}σ")

    print("\n3. Modern (Artemis) corridor probability:")
    mc = artemis_gnc_analysis()
    print(f"   σ_total:      {mc.sigma_total_deg:.3f}°")
    print(f"   P(safe):      {mc.probability_in_corridor:.10f}")
    print(f"   Margin:       {mc.min_margin_sigma:.1f}σ")

    print("\n4. Monte Carlo (10,000 samples, Orion at −6.5°, σ=0.08°):")
    mc_result = monte_carlo_entry(sigma_deg=0.08, n_samples=10_000)
    print(f"   In corridor:  {mc_result.fraction_in_corridor*100:.2f}%")
    print(f"   Skip-out:     {mc_result.fraction_skip_out*100:.4f}%")
    print(f"   Overheat:     {mc_result.fraction_overheat*100:.4f}%")
    print(f"   Peak-g range: {mc_result.peak_decel_g.min():.1f}–{mc_result.peak_decel_g.max():.1f} g")
    print(f"   Mean peak-g:  {mc_result.peak_decel_g.mean():.1f} ± {mc_result.peak_decel_g.std():.2f} g")
