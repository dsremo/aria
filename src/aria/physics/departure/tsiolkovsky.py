"""Tsiolkovsky rocket equation (§4.1 of docs/pods/A3_oberth_departure.md).

Starting from conservation of linear momentum in an inertial frame for a
variable-mass rocket ejecting propellant at exhaust speed `v_e`, neglecting
the second-order term `dm · dv`, and integrating from initial mass `m_0` to
final mass `m_f`:

    Δv = v_e · ln(m_0 / m_f)                    [m/s]

Reference derivation: Tsiolkovsky 1903 "Issledovanie mirovykh prostranstv
reaktivnymi priborami" (primary). Modern textbook derivation: Vallado 4th
ed §6.2 (ISBN 978-1881883180); Bate-Mueller-White §6 (ISBN 978-0486600611).

Specific impulse `I_sp` relates to exhaust speed by `v_e = I_sp · g_0`
where `g_0 = 9.80665 m/s²` is the *defined* standard gravity
(ISO 80000-3:2019). Note this is an exact, unit-conversion constant,
NOT the local gravitational acceleration anywhere.
"""

from __future__ import annotations

import math
from typing import Iterable

# ISO 80000-3:2019 defines standard gravity as exactly 9.80665 m/s².
# This is a unit-conversion constant only, not a physical measurement.
STANDARD_GRAVITY_M_S2: float = 9.80665  # ISO 80000-3:2019 (exact by definition)


def tsiolkovsky_delta_v(
    initial_mass_kg: float,
    final_mass_kg: float,
    exhaust_velocity_m_s: float,
) -> float:
    """Ideal Δv of a single-stage rocket burn (§4.1).

    Args:
        initial_mass_kg: wet mass at burn start (kg).
        final_mass_kg: dry mass at burn end, including empty tanks and
            payload (kg). Must be strictly positive and strictly less than
            ``initial_mass_kg``.
        exhaust_velocity_m_s: propellant exhaust velocity `v_e` in the
            rocket frame (m/s).

    Returns:
        Δv delivered by the burn, in m/s.

    Raises:
        ValueError: if masses or v_e are non-physical.
    """
    if initial_mass_kg <= 0.0:
        raise ValueError("initial_mass_kg must be positive")
    if final_mass_kg <= 0.0:
        raise ValueError("final_mass_kg must be positive")
    if final_mass_kg >= initial_mass_kg:
        raise ValueError(
            "final_mass_kg must be strictly less than initial_mass_kg "
            "(propellant must be expended)"
        )
    if exhaust_velocity_m_s <= 0.0:
        raise ValueError("exhaust_velocity_m_s must be positive")
    return exhaust_velocity_m_s * math.log(initial_mass_kg / final_mass_kg)


def exhaust_velocity_from_isp(specific_impulse_s: float) -> float:
    """Convert specific impulse (seconds) to exhaust velocity (m/s).

    `v_e = I_sp · g_0` with g_0 = 9.80665 m/s² (ISO 80000-3:2019 exact).
    """
    if specific_impulse_s <= 0.0:
        raise ValueError("specific_impulse_s must be positive")
    return specific_impulse_s * STANDARD_GRAVITY_M_S2


def stacked_delta_v(stages: Iterable[tuple[float, float, float]]) -> float:
    """Total Δv of a multi-stage rocket by Tsiolkovsky stacking (§4.6).

    For stages `i = 1 … N`, each defined by ``(m_0, m_f, v_e)``, the
    total Δv is the sum over stages of the per-stage Tsiolkovsky Δv.
    The stages are treated as independent; the caller is responsible
    for propagating mass hand-offs between stages (e.g., subtracting
    structural mass after stage drop).

    Args:
        stages: iterable of (initial_mass_kg, final_mass_kg,
            exhaust_velocity_m_s) tuples.

    Returns:
        Σ v_e,i · ln(m_0,i / m_f,i) in m/s.
    """
    total = 0.0
    for m0, mf, ve in stages:
        total += tsiolkovsky_delta_v(m0, mf, ve)
    return total
