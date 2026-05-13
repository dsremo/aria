"""Time-drift bounds on fundamental constants (§4.1–§4.3 of M3).

Webb 2011, Ubachs 2016, and LLR 2018 published upper bounds on the
fractional drift rates of α, μ, G. M3 does not assume any drift —
it propagates the *upper bounds* into a clock or navigation budget
so downstream gates can confirm the residual effect is sub-mission-
sensitivity.

Atomic-clock transitions depend on α through a sensitivity
coefficient K_α (Dzuba, Flambaum & Webb 1999 *PRL* 82 888):

    dν/ν = K_α · dα/α                                        [–]
"""

from __future__ import annotations

from .bounds_db import (
    CLOCK_SENSITIVITY_TABLE,
    ClockSensitivity,
    VARYING_ALPHA_FRAC_PER_S,
    VARYING_G_FRAC_PER_S,
    VARYING_MU_FRAC_PER_S,
)


def alpha_drift_over_mission(
    mission_duration_s: float,
    drift_rate_per_s: float = VARYING_ALPHA_FRAC_PER_S,
) -> float:
    """|Δα/α| over a mission of duration `T` under the bound.

    |Δα/α|_max = |α̇/α|_bound · T                             [–]
    """
    if mission_duration_s < 0.0:
        raise ValueError("mission_duration_s must be non-negative")
    if drift_rate_per_s < 0.0:
        raise ValueError("drift_rate_per_s must be non-negative")
    return drift_rate_per_s * mission_duration_s


def integrated_mu_drift(
    mission_duration_s: float,
    drift_rate_per_s: float = VARYING_MU_FRAC_PER_S,
) -> float:
    """|Δμ/μ| over a mission using the Ubachs 2016 QSO bound."""
    if mission_duration_s < 0.0:
        raise ValueError("mission_duration_s must be non-negative")
    if drift_rate_per_s < 0.0:
        raise ValueError("drift_rate_per_s must be non-negative")
    return drift_rate_per_s * mission_duration_s


def clock_frequency_drift_from_alpha(
    mission_duration_s: float,
    clock_name: str = "Cs-133-hfs",
    drift_rate_per_s: float = VARYING_ALPHA_FRAC_PER_S,
    sensitivity_table: dict[str, ClockSensitivity] = CLOCK_SENSITIVITY_TABLE,
) -> float:
    """|Δν/ν| upper bound for a specific clock transition.

    Δν/ν = K_α · Δα/α = K_α · (α̇/α)_bound · T               [–]
    """
    if clock_name not in sensitivity_table:
        raise KeyError(
            f"Unknown clock {clock_name!r}. Known: {sorted(sensitivity_table)}"
        )
    entry = sensitivity_table[clock_name]
    return abs(entry.k_alpha) * alpha_drift_over_mission(
        mission_duration_s, drift_rate_per_s
    )


def g_drift_position_error_m(
    local_gravity_m_s2: float,
    mission_duration_s: float,
    drift_rate_per_s: float = VARYING_G_FRAC_PER_S,
) -> float:
    """Position error from a linear drift in G over the mission.

    ΔG/G = Ġ/G · T; the acceleration shift is Δa = g · (ΔG/G), and
    the ballistic position error is (1/2) Δa · T² (scope note §4.3).
    """
    if local_gravity_m_s2 < 0.0:
        raise ValueError("local_gravity_m_s2 must be non-negative")
    if mission_duration_s < 0.0:
        raise ValueError("mission_duration_s must be non-negative")
    if drift_rate_per_s < 0.0:
        raise ValueError("drift_rate_per_s must be non-negative")
    delta_a = local_gravity_m_s2 * drift_rate_per_s * mission_duration_s
    return 0.5 * delta_a * mission_duration_s * mission_duration_s
