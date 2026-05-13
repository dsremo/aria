"""Ship-level attitude dynamics and CMG actuators (Pod C4 — P1-7).

Gyroscopic stiffness of a spinning habitat ring, dual-spin angular-
momentum bookkeeping, 4-CMG pyramid steering (Wie 1998 §7.4), and the
Margulies-Aubrun singularity metric.

References (full list in the C4 scope note):
  - Wertz (ed.) 1978 *Spacecraft Attitude Determination and Control*
    Ch. 15-16 (ISBN 978-9027709592).
  - Wie 1998 *Space Vehicle Dynamics and Control* §7 AIAA (ISBN
    978-1563472619).
  - Sidi 1997 *Spacecraft Dynamics and Control* §6 Cambridge (ISBN
    978-0521787802).
  - Bedrossian et al. 2009 *J Guidance* 32(2) 553.
  - Oh & Vadali 1991 *J Guidance* 14(1) 69.
  - Margulies & Aubrun 1978 *J Astronaut Sci* 26(2) 159.
"""

from __future__ import annotations

from .cmg_pyramid import (
    ISS_CMG_PYRAMID_SKEW_DEG,
    ISS_CMG_ROTOR_MOMENTUM_N_M_S,
    PyramidCMGCluster,
    cmg_pyramid_jacobian,
    cmg_pyramid_total_momentum,
)
from .cmg_steering import (
    cmg_pseudoinverse_steering,
    singularity_margin,
)
from .dual_spin import (
    dual_spin_total_angular_momentum,
    gyroscopic_reaction_torque,
    wertz_nutation_frequency,
)
from .momentum_management import (
    CMG_DESAT_TRIGGER_FRACTION,
    is_cmg_saturation_imminent,
    rcs_desat_impulse_required,
)
from .mrp_control import (
    AttitudeReference,
    AttitudeState,
    ControlTorque,
    MRPFeedbackController,
    mrp_error,
    mrp_kinematics,
    mrp_to_dcm,
    propagate_attitude,
    tune_gains,
)

__all__ = [
    "CMG_DESAT_TRIGGER_FRACTION",
    "ISS_CMG_PYRAMID_SKEW_DEG",
    "ISS_CMG_ROTOR_MOMENTUM_N_M_S",
    "PyramidCMGCluster",
    "cmg_pseudoinverse_steering",
    "cmg_pyramid_jacobian",
    "cmg_pyramid_total_momentum",
    "dual_spin_total_angular_momentum",
    "gyroscopic_reaction_torque",
    "is_cmg_saturation_imminent",
    "rcs_desat_impulse_required",
    "singularity_margin",
    "wertz_nutation_frequency",
    # MRP feedback controller
    "AttitudeReference",
    "AttitudeState",
    "ControlTorque",
    "MRPFeedbackController",
    "mrp_error",
    "mrp_kinematics",
    "mrp_to_dcm",
    "propagate_attitude",
    "tune_gains",
]
