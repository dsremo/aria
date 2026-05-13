"""ECLSS ↔ Digital Twin Bridge — connects life support mass balance to geometry.

The ECLSS simulation (crew_ecosystem.py) tracks element-level mass flows
(C, H, O, N, P, S, etc.) with recycling efficiencies. The digital twin
has physical compartment geometry (volumes, surface areas). This bridge
connects them so that:

1. Agriculture zone volume → maximum crop production capacity
2. Habitat zone volume → air volume for O2/CO2 concentration
3. Physical pipe/tank constraints → achievable recycling efficiency
4. Water system volume → water buffer capacity before depletion

References
----------
  NASA/TP-2015-218570 (BVAD) — Baseline Values and Assumptions Document
  NASA-STD-3001 Vol 1 — crew habitability standards
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ECLSSPhysicalConstraints:
    """Physical constraints on ECLSS derived from digital twin geometry."""
    # Compartment volumes
    habitat_volume_m3: float          # Pressurized habitat volume (m³)
    agriculture_volume_m3: float      # Agriculture zone volume (m³)
    total_pressurized_m3: float       # All pressurized zones combined

    # Derived air system parameters
    air_mass_kg: float                # Total air mass (kg) at 1 atm
    o2_mass_kg: float                 # O2 mass (21% of air)
    co2_buffer_hours: float           # Hours before CO2 hits 1% if scrubber fails

    # Derived water system parameters
    water_tank_capacity_kg: float     # Water storage capacity (kg)
    daily_water_demand_kg: float      # Water demand per day (kg)
    water_reserve_days: float         # Days of water reserve

    # Derived agriculture parameters
    crop_area_m2: float               # Available growing area (m²)
    max_food_production_kg_day: float # Maximum food output (kg/day)
    crew_food_demand_kg_day: float    # Crew food demand (kg/day)
    food_self_sufficiency_pct: float  # % of food needs met by agriculture


def compute_eclss_constraints(
    hull_inner_radius_m: float,
    hull_length_m: float,
    crew_size: int = 100,
    habitat_ring_radius_m: float = 0.0,
    habitat_tube_radius_m: float = 0.0,
    ring_agri_fraction: float = 0.40,
    vertical_levels: int = 3,
    packing_efficiency: float = 0.80,
    yield_kg_m2_yr: float = 5.0,
    cold_storage_months: float = 0.0,
) -> ECLSSPhysicalConstraints:
    """Compute ECLSS physical constraints from hull geometry.

    Uses the ARIA zone layout (compartments.py) fractions:
      B (Habitat):     10%–35% of hull length = 25%
      C (Agriculture): 35%–55% of hull length = 20%

    Args:
        hull_inner_radius_m: Inner radius of pressurized hull (m).
        hull_length_m:       Total hull length (m).
        crew_size:           Number of crew for demand calculations.

    Returns:
        ECLSSPhysicalConstraints with all derived values.

    References:
        NASA/TP-2015-218570 (BVAD) — crew consumables per person per day.
        NASA-STD-3001 Vol 1 Rev C §4.2 — cabin atmosphere.
    """
    # Input validation — prevent silently-wrong results from negative or
    # unphysical inputs (e.g. r² flipping sign invisibly). Each caller gets
    # a clear error naming the offending parameter.
    if hull_inner_radius_m <= 0:
        raise ValueError(f"hull_inner_radius_m must be > 0, got {hull_inner_radius_m}")
    if hull_length_m <= 0:
        raise ValueError(f"hull_length_m must be > 0, got {hull_length_m}")
    if crew_size < 0:
        raise ValueError(f"crew_size must be >= 0, got {crew_size}")
    if habitat_ring_radius_m < 0 or habitat_tube_radius_m < 0:
        raise ValueError(
            f"habitat_ring dimensions must be >= 0; got "
            f"ring={habitat_ring_radius_m}, tube={habitat_tube_radius_m}"
        )
    if not (1 <= vertical_levels <= 20):
        raise ValueError(f"vertical_levels must be 1..20, got {vertical_levels}")
    if not (0.0 < packing_efficiency <= 1.0):
        raise ValueError(f"packing_efficiency must be in (0, 1], got {packing_efficiency}")
    if not (0.0 <= ring_agri_fraction <= 1.0):
        raise ValueError(f"ring_agri_fraction must be in [0, 1], got {ring_agri_fraction}")
    if yield_kg_m2_yr < 0:
        raise ValueError(f"yield_kg_m2_yr must be >= 0, got {yield_kg_m2_yr}")
    if cold_storage_months < 0:
        raise ValueError(f"cold_storage_months must be >= 0, got {cold_storage_months}")

    cross_section = math.pi * hull_inner_radius_m ** 2

    # Zone volumes (from compartments.py zone fractions)
    habitat_length = hull_length_m * 0.25   # Zone B: 10%–35%
    agri_length = hull_length_m * 0.20      # Zone C: 35%–55%
    # Other pressurized zones: Command (10%), Manufacturing (15%), Storage (12%)
    other_length = hull_length_m * 0.37

    habitat_vol = cross_section * habitat_length
    agri_vol = cross_section * agri_length
    other_vol = cross_section * other_length
    total_pressurized = habitat_vol + agri_vol + other_vol

    # Air system: 1 atm = 101325 Pa, air density ≈ 1.225 kg/m³ at 20°C
    air_density = 1.225  # kg/m³ at 1 atm, 20°C — US Standard Atmosphere 1976
    air_mass = total_pressurized * air_density
    o2_mass = air_mass * 0.21  # 21% O2 by mass (approx)

    # CO2 buffer: crew produces ~1.0 kg CO2/person/day (NASA BVAD TP-2015-218570 §4.1)
    # At 1% CO2 (10,000 ppm), the atmosphere holds ~1% × air_mass in CO2
    co2_limit_kg = air_mass * 0.01
    co2_production_rate_kg_hr = crew_size * 1.0 / 24.0  # kg/hr
    co2_buffer_hours = co2_limit_kg / co2_production_rate_kg_hr if co2_production_rate_kg_hr > 0 else float('inf')

    # Water system: 2% of habitat volume for water tanks (ESTIMATE)
    # Water demand: 25 kg/person/day (drinking + hygiene + food prep — NASA BVAD §4.2)
    water_capacity = habitat_vol * 0.02 * 1000  # 2% vol × 1000 kg/m³
    daily_water = crew_size * 25.0  # kg/day; NASA BVAD §4.2 Table 4-1
    water_reserve = water_capacity / daily_water if daily_water > 0 else float('inf')

    # Agriculture — "Zone C" inside the main hull.
    # Vertical farming: N levels × packing efficiency across the agri-zone cross-section.
    hull_crop_area = cross_section * vertical_levels * packing_efficiency

    # Habitat ring agriculture.
    #
    # We model ONE gravitational-floor deck running around the ring at
    # the outermost equator (where centripetal acceleration is highest),
    # with floor width = tube diameter (2·r_tube). That gives a pre-
    # packing floor area of:
    #
    #     ring_floor_area = 2π · R_major · (2 · r_tube)
    #
    # This is a deliberate SIMPLIFICATION (ESTIMATE): a real torus can
    # host multiple stacked decks above and below the equator (Stanford
    # Torus had ~6 usable decks per O'Neill 1977 NASA-SP-413), so the
    # true floor area scales roughly with cross-section area × circum-
    # ference / deck-spacing. Our `vertical_levels` factor is intended
    # for hydroponic *rack* stacking within a single deck, not multiple
    # gravitational decks. Upgrade to a proper torus-packing model when
    # deck count becomes a real design variable.
    if habitat_ring_radius_m > 0 and habitat_tube_radius_m > 0:
        ring_floor_area = 2.0 * math.pi * habitat_ring_radius_m * (2.0 * habitat_tube_radius_m)
        ring_crop_area = (ring_floor_area * ring_agri_fraction
                          * vertical_levels * packing_efficiency)
    else:
        ring_crop_area = 0.0

    crop_area = hull_crop_area + ring_crop_area

    # Mixed-crop yield: ~5 kg/m²/yr (Zabel 2020 "EDEN ISS" Life Sci Space Res).
    # Caller may inject leafy-green / aquaponic yields by raising `yield_kg_m2_yr`.
    food_production = crop_area * yield_kg_m2_yr / 365.25  # kg/day
    food_demand = crew_size * 1.8  # kg/person/day dry mass; NASA BVAD §4.2 Table 4-1

    # Cold-storage buffering: freeze-dried reserves let you close the gap
    # when instantaneous production < demand. Effectively reduces demand
    # by the cached-production-over-months window, spread across the
    # whole mission horizon. Caller passes 0.0 to disable.
    if cold_storage_months > 0:
        buffer_kg_day = (food_production * cold_storage_months * 30.0) / 365.25
        food_production += buffer_kg_day

    # Zero-demand case: vacuously self-sufficient (no one to feed). Previously
    # returned 0, which misleadingly reads as "failed to meet demand".
    food_self_sufficiency = (
        min(100.0, food_production / food_demand * 100)
        if food_demand > 0 else 100.0
    )

    return ECLSSPhysicalConstraints(
        habitat_volume_m3=habitat_vol,
        agriculture_volume_m3=agri_vol,
        total_pressurized_m3=total_pressurized,
        air_mass_kg=air_mass,
        o2_mass_kg=o2_mass,
        co2_buffer_hours=co2_buffer_hours,
        water_tank_capacity_kg=water_capacity,
        daily_water_demand_kg=daily_water,
        water_reserve_days=water_reserve,
        crop_area_m2=crop_area,
        max_food_production_kg_day=food_production,
        crew_food_demand_kg_day=food_demand,
        food_self_sufficiency_pct=food_self_sufficiency,
    )


if __name__ == "__main__":
    # Default ARIA generation ship parameters
    # Hull inner radius ≈ 12.1 m (from parameters.py, derived from cross_section_m2)
    # Hull length ≈ 712 m (from parameters.py)
    c = compute_eclss_constraints(12.1, 712.0, crew_size=100)
    print(f"\n── ECLSS Physical Constraints (100 crew, 712m hull) ──")
    print(f"  Habitat volume:     {c.habitat_volume_m3:>10.0f} m³")
    print(f"  Agriculture volume: {c.agriculture_volume_m3:>10.0f} m³")
    print(f"  Total pressurized:  {c.total_pressurized_m3:>10.0f} m³")
    print(f"  Air mass:           {c.air_mass_kg:>10.0f} kg")
    print(f"  O2 mass:            {c.o2_mass_kg:>10.0f} kg")
    print(f"  CO2 buffer:         {c.co2_buffer_hours:>10.1f} hours")
    print(f"  Water capacity:     {c.water_tank_capacity_kg:>10.0f} kg")
    print(f"  Water reserve:      {c.water_reserve_days:>10.1f} days")
    print(f"  Crop area:          {c.crop_area_m2:>10.0f} m²")
    print(f"  Food production:    {c.max_food_production_kg_day:>10.1f} kg/day")
    print(f"  Food demand:        {c.crew_food_demand_kg_day:>10.1f} kg/day")
    print(f"  Self-sufficiency:   {c.food_self_sufficiency_pct:>10.1f}%")
