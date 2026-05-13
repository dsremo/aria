"""Habitat CFD primitives (Pods H1 + H3 — P1-5).

This package ships closed-form and correlation-level primitives that
cover the core compressible-flow, turbulence-closure, and natural-
convection benchmarks in the H1 and H3 scope notes. A full finite-
volume CFD solver is a downstream effort; what lives here is
sufficient for the ISS cabin-turnover benchmark, Sutherland viscosity
lookups, Reynolds/Prandtl/Mach dimensionless numbers, Blasius flat-
plate drag, the Launder-Spalding k-ε constants, log-law wall-function
evaluation, the analytic Sod shock tube reference state, and the
Churchill-Chu natural-convection Nusselt correlation used by pod H3.

References (full bibliography in the scope notes):
  - Landau & Lifshitz 1987 *Fluid Mechanics* 2nd ed.
  - Pope 2000 *Turbulent Flows* (ISBN 978-0521598866).
  - Kundu et al. 2016 *Fluid Mechanics* 6th ed (ISBN 978-0124059351).
  - White 2006 *Viscous Fluid Flow* 3rd ed (ISBN 978-0072402315).
  - Incropera et al. 2011 *Fundamentals of Heat and Mass Transfer*
    7th ed (ISBN 978-0470501979).
  - Schlichting & Gersten 2017 *Boundary-Layer Theory* 9th ed
    (ISBN 978-3662529171).
  - Launder & Spalding 1974 *Comput Methods Appl Mech Eng* 3 269.
  - Menter 1994 AIAA J 32 1598.
  - Toro 2009 *Riemann Solvers* 3rd ed (ISBN 978-3540498346).
  - Churchill & Chu 1975 *Int J Heat Mass Transfer* 18 1323.
"""

from __future__ import annotations

from .dimensionless import (
    grashof_number,
    mach_number,
    nusselt_churchill_chu_vertical_plate,
    prandtl_number,
    rayleigh_number,
    reynolds_number,
)
from .equation_of_state import (
    AIR_STANDARD,
    GasMixture,
    ideal_gas_density,
    ideal_gas_pressure,
    speed_of_sound,
    specific_gas_constant,
)
from .flow_regime import (
    FlowRegime,
    RegimeThresholds,
    classify_pipe_flow,
    classify_plate_flow,
)
from .sod_shock_tube import SodExactSolution, sod_exact_post_shock_state
from .turbulence_closure import (
    K_EPSILON_STANDARD,
    KEpsilonConstants,
    SmagorinskyConstants,
    turbulent_viscosity_k_epsilon,
)
from .viscosity import (
    AIR_SUTHERLAND,
    SutherlandParameters,
    sutherland_viscosity,
)
from .wall_functions import (
    CFL_EXPLICIT_LIMIT,
    blasius_skin_friction_coefficient,
    blasius_displacement_thickness_over_x,
    cfl_time_step_bound,
    friction_velocity,
    iss_cabin_turnover_time_s,
    law_of_the_wall_u_plus,
)
from .phase_transitions import (
    Phase,
    PhaseMargin,
    SUBSTANCE_DB,
    SubstanceThermo,
    determine_phase,
    latent_heat_j_kg,
    phase_safety_margin,
    vapor_pressure_pa,
)

__all__ = [
    "AIR_STANDARD",
    "AIR_SUTHERLAND",
    "CFL_EXPLICIT_LIMIT",
    "FlowRegime",
    "GasMixture",
    "K_EPSILON_STANDARD",
    "KEpsilonConstants",
    "RegimeThresholds",
    "SmagorinskyConstants",
    "SodExactSolution",
    "SutherlandParameters",
    "blasius_displacement_thickness_over_x",
    "blasius_skin_friction_coefficient",
    "cfl_time_step_bound",
    "classify_pipe_flow",
    "classify_plate_flow",
    "friction_velocity",
    "grashof_number",
    "ideal_gas_density",
    "ideal_gas_pressure",
    "iss_cabin_turnover_time_s",
    "law_of_the_wall_u_plus",
    "mach_number",
    "nusselt_churchill_chu_vertical_plate",
    "prandtl_number",
    "rayleigh_number",
    "reynolds_number",
    "sod_exact_post_shock_state",
    "specific_gas_constant",
    "speed_of_sound",
    "sutherland_viscosity",
    "turbulent_viscosity_k_epsilon",
    # Phase transitions
    "Phase",
    "PhaseMargin",
    "SUBSTANCE_DB",
    "SubstanceThermo",
    "determine_phase",
    "latent_heat_j_kg",
    "phase_safety_margin",
    "vapor_pressure_pa",
]
