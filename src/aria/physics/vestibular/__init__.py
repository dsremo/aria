"""Pod C2 — Vestibular response to rotating-frame motion.

Implements audit items §2.10 (vestibular-Coriolis illusion), §2.11
(otolith vs semicircular-canal sensory conflict), §13.8 (vestibular
adaptation, motion sickness, spatial disorientation).

Translates the kinematic accelerations and angular velocities from
Pod C1 (centrifugal, Coriolis, Euler) into a biological response of
the human vestibular organ:

  - Cupula deflection in each semicircular canal (torsion-pendulum
    model, Steinhausen 1933 / Van Egmond 1949)
  - Otolith displacement under the gravito-inertial vector
    (Grant & Best 1987 first-order overdamped lag)
  - Cross-coupled Coriolis illusion when the crew tilts their head
    while the habitat ring is spinning (Guedry & Benson 1978)
  - Sensory-conflict-driven motion-sickness probability
    (Oman 1982/1990 dose model)
  - Cumulative-exposure adaptation envelope
    (Graybiel 1975, Young 2019)

See `docs/pods/C2_vestibular.md` for the scope note (derivations,
citations, verification test cases).

Public API:
    SemicircularCanalConstants
    canal_transfer_function_amplitude   — |H(jω)| at angular freq
    cupula_step_response                — analytic closed form
    cross_coupled_angular_acceleration  — Ω_ring × ω_head
    otolith_response                    — overdamped first-order
    OtolithConstants
    OmanMotionSicknessModel             — dP/dt ODE integrator
    adaptation_probability              — Young 2019 sigmoid
    motion_sickness_threshold_naive     — 5 rpm cross-coupling
    motion_sickness_threshold_adapted   — 10 rpm cross-coupling
"""

from .semicircular_canal import (
    HUMAN_CANAL_CONSTANTS,
    SemicircularCanalConstants,
    canal_transfer_function_amplitude,
    cupula_step_response,
)
from .cross_coupling import cross_coupled_angular_acceleration
from .otolith import (
    OTOLITH_DEFAULT_CONSTANTS,
    OtolithConstants,
    otolith_response_steady_state,
    otolith_step_response,
)
from .oman_dose import (
    OMAN_DEFAULT_K_DOWN,
    OMAN_DEFAULT_K_UP,
    OmanMotionSicknessModel,
    motion_sickness_threshold_adapted,
    motion_sickness_threshold_naive,
)
from .adaptation import (
    YOUNG_2019_E_HALF_S,
    adaptation_probability,
)

__all__ = [
    "HUMAN_CANAL_CONSTANTS",
    "SemicircularCanalConstants",
    "canal_transfer_function_amplitude",
    "cupula_step_response",
    "cross_coupled_angular_acceleration",
    "OTOLITH_DEFAULT_CONSTANTS",
    "OtolithConstants",
    "otolith_response_steady_state",
    "otolith_step_response",
    "OMAN_DEFAULT_K_UP",
    "OMAN_DEFAULT_K_DOWN",
    "OmanMotionSicknessModel",
    "motion_sickness_threshold_naive",
    "motion_sickness_threshold_adapted",
    "YOUNG_2019_E_HALF_S",
    "adaptation_probability",
]
