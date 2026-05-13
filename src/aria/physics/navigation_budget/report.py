"""Navigation budget report generator.

Given a :class:`MissionProfile`, pull per-effect upper bounds from
the Phase 2/3 primitives and return a :class:`NavigationBudget`
that lists every row and the quadrature total.

This module does **not** claim any detection of dark-sector or
exotic effects — it propagates published experimental *upper
bounds* so the downstream consumer can confirm residual effects
are below mission sensitivity (NASA-STD-7009A §5.5 convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..cruise_drag import (
    LOCAL_INTERSTELLAR_CLOUD,
    chandrasekhar_dynamical_friction_acceleration,
    ram_pressure_drag_acceleration,
    stopping_length_m,
)
from ..dark_sector import (
    UncertaintyBudgetRow,
    cosmological_lambda_acceleration,
    dark_matter_drag_upper_bound,
    propagate_position_uncertainty_m,
    quadrature_sum_rows,
)
from .mission_profile import MissionProfile


# Local interstellar sound speed — used as Chandrasekhar velocity
# dispersion surrogate for a neutral cloud. Redfield & Linsky 2008
# give T_e ≈ 7500 K → v̄ ≈ √(k T/m_H) ~ 10 km/s.
_LIC_SOUND_SPEED_M_S: float = 1.0e4


@dataclass(frozen=True)
class NavigationBudget:
    """Per-effect rows plus the quadrature total.

    Attributes:
        profile: the mission profile that generated the report.
        rows: tuple of :class:`UncertaintyBudgetRow` entries; each
            carries a position-error contribution in metres.
        total_position_error_m: √(Σ row_m²) of the metre-unit rows.
        stopping_length_m: ISM drag e-folding length (for the
            "cruise is drag-limited?" gate).
    """

    profile: MissionProfile
    rows: tuple[UncertaintyBudgetRow, ...]
    total_position_error_m: float
    stopping_length_m: float

    @property
    def is_drag_limited(self) -> bool:
        """True iff the transit distance exceeds the e-folding stop
        length (i.e. the ship coasts past the 1/e velocity-decay
        point during the mission leg)."""
        return self.profile.leg_distance_m > self.stopping_length_m


def build_navigation_budget(profile: MissionProfile) -> NavigationBudget:
    """Propagate every bounded physical effect into a single budget.

    Rows included:
      - ISM ram-drag position drift (cruise_drag.ram_pressure)
      - Chandrasekhar dynamical-friction drift (cruise_drag)
      - XENONnT-consistent DM drag upper bound (dark_sector.M1)
      - Λ cosmological drift over the leg (dark_sector.M1, only if
        the profile is flagged `is_intergalactic`)

    Each row stores the accumulated position error over the transit
    time `Δt = d / v`. Rows are combined in quadrature
    (propagate_position_uncertainty_m · quadrature_sum_rows) — the
    standard NASA-STD-7009A §5.5 treatment for independent bounded
    error sources.
    """
    dt_s = profile.transit_time_s

    # ── ISM ram-drag ──────────────────────────────────────────────
    rho_ism = LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3
    a_ram = ram_pressure_drag_acceleration(
        mass_density_kg_m3=rho_ism,
        relative_velocity_m_s=profile.cruise_velocity_m_s,
        cross_section_m2=profile.cross_section_m2,
        ship_mass_kg=profile.ship_mass_kg,
    )
    dx_ram = propagate_position_uncertainty_m(a_ram, dt_s)

    # ── Chandrasekhar dynamical friction (on LIC gas) ─────────────
    a_df = chandrasekhar_dynamical_friction_acceleration(
        ship_mass_kg=profile.ship_mass_kg,
        velocity_m_s=profile.cruise_velocity_m_s,
        background_density_kg_m3=rho_ism,
        velocity_dispersion_m_s=_LIC_SOUND_SPEED_M_S,
    )
    dx_df = propagate_position_uncertainty_m(a_df, dt_s)

    # ── XENONnT-consistent DM drag upper bound ────────────────────
    a_dm = dark_matter_drag_upper_bound(
        ship_mass_kg=profile.ship_mass_kg,
        ship_velocity_through_halo_m_s=profile.cruise_velocity_m_s,
    )
    dx_dm = propagate_position_uncertainty_m(a_dm, dt_s)

    rows: List[UncertaintyBudgetRow] = [
        UncertaintyBudgetRow(
            name="ISM_ram_LIC",
            effect_category="cruise_drag",
            perturbation_value=dx_ram,
            units="m",
            source="Ferriere 2001 + Redfield & Linsky 2008",
        ),
        UncertaintyBudgetRow(
            name="Chandrasekhar_DF",
            effect_category="cruise_drag",
            perturbation_value=dx_df,
            units="m",
            source="Chandrasekhar 1943; Binney & Tremaine 2008",
        ),
        UncertaintyBudgetRow(
            name="DM_drag_XENONnT_30GeV",
            effect_category="dark_sector_M1",
            perturbation_value=dx_dm,
            units="m",
            source="Aprile et al. 2023 PRL 131 041003",
        ),
    ]

    # ── Cosmological Λ drift (intergalactic only) ─────────────────
    if profile.is_intergalactic:
        a_lambda = cosmological_lambda_acceleration(profile.leg_distance_m)
        dx_lambda = propagate_position_uncertainty_m(a_lambda, dt_s)
        rows.append(
            UncertaintyBudgetRow(
                name="Lambda_cosmological",
                effect_category="dark_sector_M1",
                perturbation_value=dx_lambda,
                units="m",
                source="Planck Collaboration 2020 A&A 641 A6",
            )
        )

    total = quadrature_sum_rows(rows, unit_filter="m")

    l_stop = stopping_length_m(
        mass_density_kg_m3=rho_ism,
        cross_section_m2=profile.cross_section_m2,
        ship_mass_kg=profile.ship_mass_kg,
    )

    return NavigationBudget(
        profile=profile,
        rows=tuple(rows),
        total_position_error_m=total,
        stopping_length_m=l_stop,
    )
