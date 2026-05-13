"""Ram-pressure drag on a cruise-phase ship.

When a ship sweeps through an ambient medium at relative velocity
`v`, the medium ram pressure against the forward-facing cross
section is

    P_ram = ρ · v²                                           [Pa]

(Landau-Lifshitz 1987 *Fluid Mechanics* 2nd ed §9), which for a
blunt body with drag coefficient `C_D ≈ 2` gives the drag force

    F_drag = C_D · (1/2) ρ v² · A                            [N]

and the deceleration

    a_drag = C_D · (1/2) ρ v² · A / M                        [m/s²]

The factor of 2 in `C_D` is the hypersonic / free-molecular-flow
limit for a flat plate (Schaaf & Chambré 1961 *Flow of Rarefied
Gases* ISBN 978-0691625102); for an aerodynamic shape `C_D` can
drop by an order of magnitude but blunt interstellar probes are
conservative at the free-molecular value.

The stopping length — distance over which the ship slows by a
factor of e — is

    L_stop = M / (C_D · ρ · A)                               [m]

independent of velocity for the linear momentum sink.
"""

from __future__ import annotations


def ram_pressure_pa(
    mass_density_kg_m3: float, relative_velocity_m_s: float
) -> float:
    """Ram pressure `P = ρ v²` [Pa]."""
    if mass_density_kg_m3 <= 0.0:
        raise ValueError("mass_density_kg_m3 must be positive")
    return (
        mass_density_kg_m3
        * relative_velocity_m_s
        * relative_velocity_m_s
    )


def ram_pressure_drag_acceleration(
    mass_density_kg_m3: float,
    relative_velocity_m_s: float,
    cross_section_m2: float,
    ship_mass_kg: float,
    drag_coefficient: float = 2.0,
) -> float:
    """Deceleration from ambient ram pressure on the forward face.

    a = C_D · (1/2) ρ v² · A / M                             [m/s²]

    Defaults to the free-molecular flat-plate `C_D = 2`
    (Schaaf & Chambré 1961), which is the appropriate high-Knudsen
    regime for interstellar cruise (Kn ≫ 1 at ISM densities).
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if cross_section_m2 < 0.0:
        raise ValueError("cross_section_m2 must be non-negative")
    if drag_coefficient <= 0.0:
        raise ValueError("drag_coefficient must be positive")
    p_ram = ram_pressure_pa(mass_density_kg_m3, relative_velocity_m_s)
    return drag_coefficient * 0.5 * p_ram * cross_section_m2 / ship_mass_kg


def stopping_length_m(
    mass_density_kg_m3: float,
    cross_section_m2: float,
    ship_mass_kg: float,
    drag_coefficient: float = 2.0,
) -> float:
    """e-folding velocity-decay length in a uniform medium.

    L_stop = M / (C_D · ρ · A)                               [m]

    For a 10⁶ kg blunt ship (A = 300 m²) in the Local Interstellar
    Cloud (ρ ≈ 5.2×10⁻²² kg/m³) this is ~10²⁰ m ≈ 10 kpc — vastly
    longer than any realistic mission leg, which confirms that ISM
    ram drag does not stop the ship. For mm-level trajectory
    accuracy, though, the residual deceleration still needs to
    enter the navigation budget.
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if mass_density_kg_m3 <= 0.0:
        raise ValueError("mass_density_kg_m3 must be positive")
    if cross_section_m2 <= 0.0:
        raise ValueError("cross_section_m2 must be positive")
    if drag_coefficient <= 0.0:
        raise ValueError("drag_coefficient must be positive")
    return ship_mass_kg / (drag_coefficient * mass_density_kg_m3 * cross_section_m2)
