"""
Fuel cost estimation from ΔV via the Tsiolkovsky rocket equation.

Tsiolkovsky: Δv = Isp × g₀ × ln(m_initial / m_final)

Rearranging for fuel mass:
  m_fuel = m_dry × (exp(Δv / (Isp × g₀)) - 1)

Common propulsion Isp values:
  Cold gas (N₂):        60-80 s
  Monopropellant (N₂H₄): 200-230 s
  Bipropellant (MMH/NTO): 300-330 s
  Ion (Xe):              1000-3000 s
  Hall thruster:         1500-2500 s
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Standard gravity (m/s²) — used in Isp calculation
G0 = 9.80665  # ISO 80000-3:2019 / BIPM: g_n = 9.80665 m/s² (exact, by definition)


@dataclass
class PropulsionType:
    """Propulsion system characteristics."""

    name: str
    isp_s: float  # specific impulse in seconds
    typical_thrust_n: float  # typical thrust in Newtons


# Common propulsion types — Isp from Sutton & Biblarz "Rocket Propulsion Elements" 9th ed. 2016
COLD_GAS = PropulsionType("Cold Gas (N2)", 70.0, 0.5)      # Sutton 2016 Table 2-1: N2 cold-gas Isp ~60-80 s; ESTIMATE 0.5 N thrust (typical 1U CubeSat)
MONOPROPELLANT = PropulsionType("Monopropellant (N2H4)", 220.0, 4.0)  # Sutton 2016 §7.3: N2H4 Isp 220-230 s; ESTIMATE 4 N typical small thruster
BIPROPELLANT = PropulsionType("Bipropellant (MMH/NTO)", 310.0, 400.0)  # Sutton 2016 §6.5: MMH/NTO Isp 300-315 s; ESTIMATE 400 N (AOCS thruster class)
ION_THRUSTER = PropulsionType("Ion Thruster (Xe)", 2000.0, 0.1)  # Sutton 2016 §19.4: Xe ion Isp 1000-3000 s; ESTIMATE 0.1 N (Busek BIT-3 class)
HALL_THRUSTER = PropulsionType("Hall Thruster", 1800.0, 0.5)  # Sutton 2016 §19.6: Hall Isp 1500-2500 s; ESTIMATE 0.5 N (Fakel SPT-50 class)


def fuel_mass_required(
    delta_v_m_s: float,
    dry_mass_kg: float,
    isp_s: float = 220.0,
) -> float:
    """Compute fuel mass required for a given ΔV.

    Tsiolkovsky: m_fuel = m_dry × (exp(Δv / (Isp × g₀)) - 1)

    Args:
        delta_v_m_s: Required ΔV in m/s
        dry_mass_kg: Spacecraft dry mass in kg
        isp_s: Specific impulse in seconds

    Returns:
        Required fuel mass in kg
    """
    if delta_v_m_s <= 0:
        return 0.0

    exhaust_velocity = isp_s * G0  # m/s
    mass_ratio = math.exp(delta_v_m_s / exhaust_velocity)
    return dry_mass_kg * (mass_ratio - 1.0)


def burn_duration_seconds(
    delta_v_m_s: float,
    dry_mass_kg: float,
    thrust_n: float,
    isp_s: float = 220.0,
) -> float:
    """Estimate burn duration for a maneuver.

    For constant-thrust:
      t_burn = m_fuel × Isp × g₀ / thrust

    Args:
        delta_v_m_s: Required ΔV in m/s
        dry_mass_kg: Spacecraft dry mass in kg
        thrust_n: Engine thrust in Newtons
        isp_s: Specific impulse in seconds

    Returns:
        Burn duration in seconds
    """
    if thrust_n <= 0:
        return float("inf")

    m_fuel = fuel_mass_required(delta_v_m_s, dry_mass_kg, isp_s)
    # Fuel flow rate: ṁ = F / (Isp × g₀)
    mdot = thrust_n / (isp_s * G0)
    if mdot <= 0:
        return float("inf")

    return m_fuel / mdot


def delta_v_budget_report(
    delta_v_m_s: float,
    dry_mass_kg: float,
) -> dict[str, dict[str, float]]:
    """Generate fuel cost report for all propulsion types.

    Args:
        delta_v_m_s: Required ΔV in m/s
        dry_mass_kg: Spacecraft dry mass in kg

    Returns:
        Dict mapping propulsion type name → {fuel_kg, burn_duration_s}
    """
    report = {}
    for prop in [COLD_GAS, MONOPROPELLANT, BIPROPELLANT, ION_THRUSTER, HALL_THRUSTER]:
        fuel_kg = fuel_mass_required(delta_v_m_s, dry_mass_kg, prop.isp_s)
        burn_s = burn_duration_seconds(delta_v_m_s, dry_mass_kg, prop.typical_thrust_n, prop.isp_s)
        report[prop.name] = {
            "fuel_mass_kg": fuel_kg,
            "burn_duration_s": burn_s,
            "isp_s": prop.isp_s,
        }
    return report
