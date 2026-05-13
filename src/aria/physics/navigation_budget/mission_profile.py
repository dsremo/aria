"""Mission-profile dataclass for the navigation budget.

A :class:`MissionProfile` captures only the inputs the Phase 2/3
primitives need, so the budget layer has zero coupling to the
:class:`GenerationShipConfig` machinery. Consumers that want to
convert a ship config into a profile should use the helper
factories in this module or construct the profile directly.
"""

from __future__ import annotations

from dataclasses import dataclass

# CODATA 2018 / SI 2019
_C_M_S: float = 299792458.0
_LY_M: float = 9.4607304725808e15  # IAU 2012 light-year
_YEAR_S: float = 365.25 * 86400.0


@dataclass(frozen=True)
class MissionProfile:
    """Frozen inputs for the navigation uncertainty budget.

    Attributes:
        name: short identifier used in the report.
        ship_mass_kg: total ship mass (kg, positive).
        cross_section_m2: forward-facing area for ISM drag (m²,
            positive).
        cruise_velocity_m_s: |v| in the barycentric frame (m/s,
            non-negative).
        leg_distance_m: transit distance (m, positive).
        is_intergalactic: enables the cosmological Λ row.
    """

    name: str
    ship_mass_kg: float
    cross_section_m2: float
    cruise_velocity_m_s: float
    leg_distance_m: float
    is_intergalactic: bool = False

    def __post_init__(self) -> None:
        if self.ship_mass_kg <= 0.0:
            raise ValueError("ship_mass_kg must be positive")
        if self.cross_section_m2 <= 0.0:
            raise ValueError("cross_section_m2 must be positive")
        if self.cruise_velocity_m_s < 0.0:
            raise ValueError("cruise_velocity_m_s must be non-negative")
        if self.leg_distance_m <= 0.0:
            raise ValueError("leg_distance_m must be positive")

    @property
    def transit_time_s(self) -> float:
        """Δt = d / v                                          [s]."""
        if self.cruise_velocity_m_s == 0.0:
            return float("inf")
        return self.leg_distance_m / self.cruise_velocity_m_s


def mars_transit_profile(
    ship_mass_kg: float = 1.0e6,
    cross_section_m2: float = 100.0,
    cruise_velocity_km_s: float = 12.0,
) -> MissionProfile:
    """Canonical Earth → Mars transit profile.

    Mean Earth-Mars distance at the 2031 Hohmann window is about
    2.25×10¹¹ m (1.5 AU); at the NASA 2020 *Moon to Mars Transit
    Vehicle* reference cruise speed of 12 km/s the transit is
    ~6 months.
    """
    au_m = 1.495978707e11  # IAU 2012 astronomical unit
    return MissionProfile(
        name="Mars transit (Hohmann)",
        ship_mass_kg=ship_mass_kg,
        cross_section_m2=cross_section_m2,
        cruise_velocity_m_s=cruise_velocity_km_s * 1.0e3,
        leg_distance_m=1.5 * au_m,
        is_intergalactic=False,
    )


def proxima_cruise_profile(
    ship_mass_kg: float = 1.0e8,
    cross_section_m2: float = 500.0,
    velocity_c: float = 0.1,
) -> MissionProfile:
    """Canonical Proxima Centauri cruise profile (4.244 ly).

    Default cruise at 0.1 c matches the ARIA baseline
    GenerationShipConfig. At that velocity the cruise takes
    ~42 years.
    """
    return MissionProfile(
        name="Proxima Centauri cruise",
        ship_mass_kg=ship_mass_kg,
        cross_section_m2=cross_section_m2,
        cruise_velocity_m_s=velocity_c * _C_M_S,
        leg_distance_m=4.244 * _LY_M,
        is_intergalactic=False,
    )
