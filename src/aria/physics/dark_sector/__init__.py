"""Dark-sector and speculative-physics uncertainty budget (Pods M1-M3).

Batched package covering:
  - M1 dark-matter drag upper bound + cosmological-constant term.
  - M2 weak-equivalence-principle (MICROSCOPE) differential-
    acceleration bound.
  - M3 time-drift bounds on α, μ, G from Webb 2011 / Ubachs 2016 /
    Hofmann & Müller 2018.
  - A shared :func:`propagate_uncertainty_row` consumer that turns
    per-effect perturbations into navigation / clock error-budget
    contributions via quadrature sums.

Every published bound has an inline citation in :mod:`bounds_db`.
These pods do **not** add forces to the simulator; they emit upper-
bound rows for the error budget so downstream consumers can prove
"this effect is below mission sensitivity".
"""

from __future__ import annotations

from .bounds_db import (
    ADMX_G_A_GAMMA_BOUND_GEV_INV,
    DARK_MATTER_DENSITY_READ_2014_KG_M3,
    DARK_MATTER_LOCAL_VELOCITY_M_S,
    HUBBLE_H0_KM_S_MPC,
    HUBBLE_OMEGA_LAMBDA,
    LAMBDA_COSMO_M2,
    MEGAPARSEC_M,
    MICROSCOPE_ETA_BOUND,
    PLANCK_2018_CMB_TEMPERATURE_K,
    VARYING_ALPHA_FRAC_PER_S,
    VARYING_G_FRAC_PER_S,
    VARYING_MU_FRAC_PER_S,
    XENONNT_SIGMA_SI_30GEV_M2,
    ClockSensitivity,
)
from .dark_matter import (
    cosmological_lambda_acceleration,
    dark_matter_drag_upper_bound,
    lambda_position_drift_over_transit,
)
from .equivalence_principle import (
    eotvos_parameter,
    microscope_differential_acceleration_bound,
)
from .uncertainty_budget import (
    UncertaintyBudgetRow,
    propagate_position_uncertainty_m,
    quadrature_sum_rows,
)
from .varying_constants import (
    alpha_drift_over_mission,
    clock_frequency_drift_from_alpha,
    g_drift_position_error_m,
    integrated_mu_drift,
)

__all__ = [
    "ADMX_G_A_GAMMA_BOUND_GEV_INV",
    "ClockSensitivity",
    "DARK_MATTER_DENSITY_READ_2014_KG_M3",
    "DARK_MATTER_LOCAL_VELOCITY_M_S",
    "HUBBLE_H0_KM_S_MPC",
    "HUBBLE_OMEGA_LAMBDA",
    "LAMBDA_COSMO_M2",
    "MEGAPARSEC_M",
    "MICROSCOPE_ETA_BOUND",
    "PLANCK_2018_CMB_TEMPERATURE_K",
    "UncertaintyBudgetRow",
    "VARYING_ALPHA_FRAC_PER_S",
    "VARYING_G_FRAC_PER_S",
    "VARYING_MU_FRAC_PER_S",
    "XENONNT_SIGMA_SI_30GEV_M2",
    "alpha_drift_over_mission",
    "clock_frequency_drift_from_alpha",
    "cosmological_lambda_acceleration",
    "dark_matter_drag_upper_bound",
    "eotvos_parameter",
    "g_drift_position_error_m",
    "integrated_mu_drift",
    "lambda_position_drift_over_transit",
    "microscope_differential_acceleration_bound",
    "propagate_position_uncertainty_m",
    "quadrature_sum_rows",
]
