"""Hull fatigue assessment — combine pressure, thermal, Goodman,
Basquin, and Miner into one report.

The typical generation-ship hull sees three distinct cyclic loads:

  1. **Pressure cycles** — cabin internal pressure depressurisation
     events (emergency dumps, docking airlock operations). The
     hoop stress `σ_h = p R / t` is the dominant stress component
     for a thin-wall cylindrical hull.
  2. **Thermal cycles** — diurnal or orbital-period temperature
     swings around the habitat. Constrained thermal stress is
     `σ_th = −E α ΔT` (compressive when the bar heats).
  3. **Combined block** — pressure + thermal together, where both
     contribute to the alternating amplitude and the mean stress.

For each block the bridge computes:

  - The Goodman-corrected equivalent zero-mean amplitude
    (Suresh 1998 §7.4).
  - The Basquin S-N life `N_f` at that amplitude.
  - A damage fraction `n/N_f` per Miner's rule (§7.5).

The sum over all blocks is the total accumulated damage; failure
is predicted at D = 1.0. The report also returns a ballpark
"mission-end damage" assuming a given number of cycles per year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..solid_mechanics import (
    basquin_life,
    get_structural_material,
    goodman_equivalent_amplitude,
    miner_cumulative_damage,
    thin_wall_hoop_stress,
)
from ..thermal_stress import (
    get_material_properties as get_thermal_material,
    uniaxial_constrained_stress,
)


@dataclass(frozen=True)
class HullGeometry:
    """Thin-wall cylinder geometry.

    Attributes:
        radius_m: inner radius (m).
        wall_thickness_m: wall thickness (m).
        material_name: key used for both structural and thermal
            property lookups (must exist in both tables).
    """

    radius_m: float
    wall_thickness_m: float
    material_name: str = "Ti-6Al-4V"

    def __post_init__(self) -> None:
        if self.radius_m <= 0.0:
            raise ValueError("radius_m must be positive")
        if self.wall_thickness_m <= 0.0:
            raise ValueError("wall_thickness_m must be positive")
        if self.radius_m / self.wall_thickness_m < 10.0:
            raise ValueError(
                "thin-wall hoop formula requires R/t ≥ 10; use a thick-wall "
                "formula for your configuration"
            )


@dataclass(frozen=True)
class CycleBlock:
    """One pressure-cycle block.

    Attributes:
        delta_pressure_pa: peak-to-peak pressure range (Pa). The
            mean stress is taken as σ_h(p_max) / 2 under the usual
            assumption that the hull cycles between 0 and p_max.
        cycles_per_year: number of cycles of this block per year.
        name: optional tag for the report row.
    """

    delta_pressure_pa: float
    cycles_per_year: float
    name: str = "pressure"

    def __post_init__(self) -> None:
        if self.delta_pressure_pa <= 0.0:
            raise ValueError("delta_pressure_pa must be positive")
        if self.cycles_per_year <= 0.0:
            raise ValueError("cycles_per_year must be positive")


@dataclass(frozen=True)
class ThermalCycleBlock:
    """One thermal-cycle block.

    Attributes:
        delta_t_k: peak-to-peak temperature swing (K).
        cycles_per_year: number of thermal cycles per year (e.g.
            365.25 for a diurnal cycle, 5844 for an LEO orbit).
        name: optional tag for the report row.
    """

    delta_t_k: float
    cycles_per_year: float
    name: str = "thermal"

    def __post_init__(self) -> None:
        if self.delta_t_k <= 0.0:
            raise ValueError("delta_t_k must be positive")
        if self.cycles_per_year <= 0.0:
            raise ValueError("cycles_per_year must be positive")


@dataclass(frozen=True)
class HullFatigueReport:
    """Combined Basquin/Miner life estimate.

    Attributes:
        cumulative_damage_per_year: Σ (cycles_per_year / N_f_i).
        cycles_per_year_by_block: dict of {block name: n_per_yr}.
        basquin_life_by_block: dict of {block name: N_f}.
        goodman_amplitude_by_block: dict of {block name:
            Goodman-corrected equivalent zero-mean amplitude (Pa)}.
        years_to_failure: 1.0 / cumulative_damage_per_year.
            Returns ``inf`` if damage is 0.
    """

    cumulative_damage_per_year: float
    cycles_per_year_by_block: dict[str, float]
    basquin_life_by_block: dict[str, float]
    goodman_amplitude_by_block: dict[str, float]
    years_to_failure: float


def build_hull_fatigue_report(
    geometry: HullGeometry,
    pressure_blocks: Sequence[CycleBlock] = (),
    thermal_blocks: Sequence[ThermalCycleBlock] = (),
) -> HullFatigueReport:
    """Assemble a combined pressure + thermal fatigue report.

    For each block the bridge:
      1. Computes the stress amplitude Δσ/2 (half of the peak-to-
         peak value).
      2. Computes a mean stress equal to Δσ/2 (i.e. the block
         cycles from 0 to Δσ, not fully reversed — the common
         cabin-pressure assumption).
      3. Applies the Goodman correction.
      4. Evaluates Basquin life at the equivalent zero-mean
         amplitude.
      5. Adds its (cycles_per_year / N_f) contribution to the
         cumulative damage.

    Args:
        geometry: hull geometry and material key.
        pressure_blocks: one or more :class:`CycleBlock` entries.
        thermal_blocks: one or more :class:`ThermalCycleBlock`
            entries.

    Returns:
        :class:`HullFatigueReport`.

    Raises:
        ValueError: if neither block list has any entries.
    """
    if not pressure_blocks and not thermal_blocks:
        raise ValueError(
            "build_hull_fatigue_report needs at least one pressure or "
            "thermal block"
        )

    struct = get_structural_material(geometry.material_name)
    thermal = get_thermal_material(geometry.material_name)

    cycles_per_year_by_block: dict[str, float] = {}
    basquin_life_by_block: dict[str, float] = {}
    goodman_amp_by_block: dict[str, float] = {}

    # ── Pressure blocks ──────────────────────────────────────────
    for block in pressure_blocks:
        sigma_max = thin_wall_hoop_stress(
            pressure_pa=block.delta_pressure_pa,
            radius_m=geometry.radius_m,
            wall_thickness_m=geometry.wall_thickness_m,
        )
        sigma_amplitude = 0.5 * sigma_max
        sigma_mean = 0.5 * sigma_max  # cycles 0 → σ_max
        sigma_eq = goodman_equivalent_amplitude(
            stress_amplitude_pa=sigma_amplitude,
            mean_stress_pa=sigma_mean,
            ultimate_strength_pa=struct.ultimate_strength_pa,
        )
        n_f = basquin_life(
            stress_amplitude_pa=sigma_eq,
            sigma_f_prime_pa=struct.basquin_sigma_f_prime_pa,
            basquin_b_exponent=struct.basquin_b_exponent,
        )
        cycles_per_year_by_block[block.name] = block.cycles_per_year
        basquin_life_by_block[block.name] = n_f
        goodman_amp_by_block[block.name] = sigma_eq

    # ── Thermal blocks ───────────────────────────────────────────
    for block in thermal_blocks:
        sigma_thermal = abs(
            uniaxial_constrained_stress(
                youngs_modulus_pa=thermal.youngs_modulus_pa,
                cte_k_inv=thermal.cte_k_inv,
                delta_t_k=block.delta_t_k,
            )
        )
        # A temperature swing from T_0 - ΔT/2 to T_0 + ΔT/2 is fully
        # reversed, so σ_mean = 0 and the Goodman correction is an
        # identity.
        sigma_eq = sigma_thermal / 2.0  # half-peak amplitude
        n_f = basquin_life(
            stress_amplitude_pa=sigma_eq,
            sigma_f_prime_pa=struct.basquin_sigma_f_prime_pa,
            basquin_b_exponent=struct.basquin_b_exponent,
        )
        cycles_per_year_by_block[block.name] = block.cycles_per_year
        basquin_life_by_block[block.name] = n_f
        goodman_amp_by_block[block.name] = sigma_eq

    # ── Miner accumulation ──────────────────────────────────────
    cumulative_damage_per_year = miner_cumulative_damage(
        cycles_per_block=list(cycles_per_year_by_block.values()),
        cycles_to_failure_per_block=list(basquin_life_by_block.values()),
    )
    years_to_failure = (
        float("inf")
        if cumulative_damage_per_year <= 0.0
        else 1.0 / cumulative_damage_per_year
    )

    return HullFatigueReport(
        cumulative_damage_per_year=cumulative_damage_per_year,
        cycles_per_year_by_block=dict(cycles_per_year_by_block),
        basquin_life_by_block=dict(basquin_life_by_block),
        goodman_amplitude_by_block=dict(goodman_amp_by_block),
        years_to_failure=years_to_failure,
    )
