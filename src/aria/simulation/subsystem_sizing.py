"""Subsystem sizing calculators for preliminary spacecraft design.

Provides first-order sizing for:
- **Thermal radiators**: area needed to reject waste heat at given T
- **Solar arrays**: area for required power with given efficiency + degradation
- **Batteries**: capacity for eclipse duration + depth of discharge
- **RCS propellant**: mass for mission lifetime (attitude + station-keeping)
- **Data storage**: on-board memory for mission data rate × downlink gap

These are back-of-envelope sizing formulas used in conceptual design
(phase A/B studies). For detailed design use SINDA-G (thermal),
Systems Toolkit, etc.

References:
    Wertz & Larson (1999) "Space Mission Analysis and Design" (SMAD)
    Larson & Wertz (2005) "Space Mission Engineering: The New SMAD"
    Gilmore (2002) "Spacecraft Thermal Control Handbook" vol. 1
    Brown (2002) "Elements of Spacecraft Design"
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Physical constants
_SIGMA_SB = 5.670374419e-8   # Stefan-Boltzmann [W/m²/K⁴]
_SOLAR_CONST = 1361.0         # Solar constant at 1 AU [W/m²]


# ══════════════════════════════════════════════════════════════════
#  Thermal radiator sizing
# ══════════════════════════════════════════════════════════════════

@dataclass
class RadiatorSizing:
    """Radiator size estimate."""
    area_m2: float
    waste_heat_w: float
    operating_temp_k: float
    emissivity: float
    environment_temp_k: float
    mass_kg: float              # Gilmore 2002: ~5 kg/m² for deployable radiators


def size_radiator(
    waste_heat_w: float,
    operating_temp_k: float = 300.0,
    emissivity: float = 0.85,
    environment_temp_k: float = 250.0,
    view_factor: float = 0.5,   # fraction of sky visible (0.5 = single-sided)
    areal_density_kg_m2: float = 5.0,
) -> RadiatorSizing:
    """Compute required radiator area.

    Q_rad = ε σ A F (T_rad^4 - T_env^4)
    → A = Q / [ε σ F (T_rad^4 - T_env^4)]

    Args:
        waste_heat_w: heat to reject [W]
        operating_temp_k: radiator surface temperature
        emissivity: surface emissivity (high-emissivity paint ~0.85)
        environment_temp_k: effective sink temperature (250K typical cold)
        view_factor: fraction of sky visible to radiator
        areal_density_kg_m2: mass per unit area (deployable ~5, body ~15)

    Returns:
        RadiatorSizing with area and mass estimate.

    Reference: Gilmore 2002 §7.
    """
    t_eff_4 = operating_temp_k ** 4 - environment_temp_k ** 4
    if t_eff_4 <= 0 or view_factor <= 0:
        return RadiatorSizing(
            area_m2=float("inf"),
            waste_heat_w=waste_heat_w,
            operating_temp_k=operating_temp_k,
            emissivity=emissivity,
            environment_temp_k=environment_temp_k,
            mass_kg=float("inf"),
        )

    area = waste_heat_w / (emissivity * _SIGMA_SB * view_factor * t_eff_4)
    mass = area * areal_density_kg_m2

    return RadiatorSizing(
        area_m2=area,
        waste_heat_w=waste_heat_w,
        operating_temp_k=operating_temp_k,
        emissivity=emissivity,
        environment_temp_k=environment_temp_k,
        mass_kg=mass,
    )


# ══════════════════════════════════════════════════════════════════
#  Solar array sizing
# ══════════════════════════════════════════════════════════════════

@dataclass
class SolarArraySizing:
    """Solar array area + mass estimate."""
    area_m2: float
    power_bol_w: float          # beginning-of-life
    power_eol_w: float          # end-of-life
    mass_kg: float              # typically 2.5 kg/m² for rigid arrays
    solar_distance_au: float


def size_solar_array(
    required_power_w: float,
    solar_distance_au: float = 1.0,
    cell_efficiency: float = 0.30,    # GaAs triple-junction
    packing_factor: float = 0.80,      # cell area / total panel area
    degradation_per_year: float = 0.02,  # radiation damage
    mission_duration_yr: float = 10.0,
    inherent_loss: float = 0.10,       # cosine losses, wiring, temperature
    areal_density_kg_m2: float = 2.5,  # rigid panel typical
) -> SolarArraySizing:
    """Compute required solar array area for EOL power requirement.

    P_bol = S × η × F_pack × (1 - L) × A  (@ 1 AU)
    At distance d (AU): scale by 1/d²
    P_eol = P_bol × (1 - deg_per_yr)^mission_years

    Rearrange: A = P_required / (S × η × F × (1-L) × (1-deg)^t / d²)

    Args:
        required_power_w: required power at end of mission life
        solar_distance_au: heliocentric distance
        cell_efficiency: solar cell efficiency (GaAs ~30%, silicon ~18%)
        packing_factor: cell area fraction of panel
        degradation_per_year: annual power loss (radiation + UV)
        mission_duration_yr: mission lifetime
        inherent_loss: cosine + wiring + temperature losses
        areal_density_kg_m2: panel mass per area

    Returns:
        SolarArraySizing

    Reference: SMAD §11.4.
    """
    flux = _SOLAR_CONST / (solar_distance_au ** 2)
    eol_factor = (1.0 - degradation_per_year) ** mission_duration_yr

    # Required BOL power to deliver required EOL power
    required_bol = required_power_w / eol_factor

    # Area to deliver BOL power
    effective_eff = cell_efficiency * packing_factor * (1.0 - inherent_loss)
    if effective_eff <= 0:
        return SolarArraySizing(
            area_m2=float("inf"),
            power_bol_w=required_bol,
            power_eol_w=required_power_w,
            mass_kg=float("inf"),
            solar_distance_au=solar_distance_au,
        )

    area = required_bol / (flux * effective_eff)
    mass = area * areal_density_kg_m2

    return SolarArraySizing(
        area_m2=area,
        power_bol_w=required_bol,
        power_eol_w=required_power_w,
        mass_kg=mass,
        solar_distance_au=solar_distance_au,
    )


# ══════════════════════════════════════════════════════════════════
#  Battery sizing
# ══════════════════════════════════════════════════════════════════

@dataclass
class BatterySizing:
    """Battery capacity + mass estimate."""
    capacity_wh: float
    capacity_ah: float
    max_depth_of_discharge: float
    eclipse_duration_min: float
    load_w: float
    mass_kg: float              # Li-ion typical 150 Wh/kg


def size_battery(
    load_w: float,
    eclipse_duration_s: float,
    max_dod: float = 0.4,           # Li-ion safe for ~2000 cycles at 40% DoD
    bus_voltage: float = 28.0,
    specific_energy_wh_kg: float = 150.0,  # Li-ion typical
    efficiency: float = 0.90,        # round-trip charge/discharge
) -> BatterySizing:
    """Compute battery capacity for eclipse load.

    E_required = P_load × T_eclipse / η_discharge
    C_bat = E_required / DoD

    Args:
        load_w: constant load during eclipse [W]
        eclipse_duration_s: maximum eclipse time [s]
        max_dod: maximum depth of discharge (Li-ion: 0.3-0.5)
        bus_voltage: spacecraft bus voltage
        specific_energy_wh_kg: battery chemistry energy density
        efficiency: discharge efficiency

    Returns:
        BatterySizing

    Reference: SMAD §11.5.
    """
    energy_required_wh = load_w * eclipse_duration_s / 3600.0 / efficiency
    capacity_wh = energy_required_wh / max_dod
    capacity_ah = capacity_wh / bus_voltage
    mass = capacity_wh / specific_energy_wh_kg

    return BatterySizing(
        capacity_wh=capacity_wh,
        capacity_ah=capacity_ah,
        max_depth_of_discharge=max_dod,
        eclipse_duration_min=eclipse_duration_s / 60.0,
        load_w=load_w,
        mass_kg=mass,
    )


# ══════════════════════════════════════════════════════════════════
#  RCS propellant sizing
# ══════════════════════════════════════════════════════════════════

@dataclass
class RCSPropellantSizing:
    """RCS/ADCS propellant budget."""
    total_impulse_ns: float
    total_dv_ms: float
    propellant_mass_kg: float
    vehicle_mass_kg: float
    isp_s: float


def size_rcs_propellant(
    vehicle_mass_kg: float,
    mission_duration_yr: float = 5.0,
    attitude_dv_per_year_ms: float = 20.0,   # attitude control leak + slews
    stationkeeping_dv_per_year_ms: float = 50.0,  # LEO drag makeup
    momentum_management_dv_per_year_ms: float = 5.0,
    margin: float = 0.3,             # 30% margin for unknowns
    isp_s: float = 220.0,            # typical cold gas or monoprop
) -> RCSPropellantSizing:
    """Budget propellant for attitude + station-keeping over mission.

    Uses Tsiolkovsky to convert Δv requirements to propellant mass.
    SMAD §11.3 propellant budgeting.
    """
    total_dv = (attitude_dv_per_year_ms
                + stationkeeping_dv_per_year_ms
                + momentum_management_dv_per_year_ms) * mission_duration_yr
    total_dv_with_margin = total_dv * (1.0 + margin)

    # Tsiolkovsky: m_prop = m_vehicle * (exp(Δv / (Isp*g0)) - 1) / exp(...)
    g0 = 9.80665
    exhaust_v = isp_s * g0
    mass_ratio = math.exp(total_dv_with_margin / exhaust_v)
    propellant_mass = vehicle_mass_kg * (1.0 - 1.0 / mass_ratio)

    # Total impulse
    impulse = propellant_mass * exhaust_v

    return RCSPropellantSizing(
        total_impulse_ns=impulse,
        total_dv_ms=total_dv_with_margin,
        propellant_mass_kg=propellant_mass,
        vehicle_mass_kg=vehicle_mass_kg,
        isp_s=isp_s,
    )


# ══════════════════════════════════════════════════════════════════
#  Data storage sizing
# ══════════════════════════════════════════════════════════════════

@dataclass
class DataStorageSizing:
    """On-board data storage requirement."""
    storage_gb: float
    data_rate_mbps: float
    downlink_gap_hours: float
    duty_cycle: float           # fraction of time generating data
    margin: float


def size_data_storage(
    data_rate_mbps: float,
    downlink_gap_hours: float,
    duty_cycle: float = 0.5,
    margin: float = 0.5,
) -> DataStorageSizing:
    """Size on-board data storage.

    Storage >= data_rate × gap × duty_cycle × (1 + margin)

    Args:
        data_rate_mbps: instrument data rate [Mbps]
        downlink_gap_hours: worst-case gap between downlinks
        duty_cycle: fraction of time collecting data
        margin: safety margin (50% is typical for science missions)
    """
    data_bits = data_rate_mbps * 1e6 * downlink_gap_hours * 3600 * duty_cycle
    data_gb = data_bits / (8 * 1e9) * (1.0 + margin)

    return DataStorageSizing(
        storage_gb=data_gb,
        data_rate_mbps=data_rate_mbps,
        downlink_gap_hours=downlink_gap_hours,
        duty_cycle=duty_cycle,
        margin=margin,
    )
