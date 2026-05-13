"""Pod C3 — Rigid-body rotational dynamics library.

Implements audit items §2.3 (Euler force ω̇×r framework),
§2.15 (precession of angular momentum under torque),
§2.16 (nutation).

C3 is a **library pod** — it provides inertia tensors, Euler equations,
quaternions, and precession/nutation analytics that other pods (C1
ring kinematics, C4 CMG attitude) consume. It does not itself know
about habitat rings or attitude actuators.

See `docs/pods/C3_euler_tensor.md` for the scope note (derivations,
citations, verification test cases). Primary references:

- Goldstein, Poole, Safko *Classical Mechanics* 3rd ed (ISBN 978-0201657029)
  — Chapter 5 "The Rigid Body Equations of Motion"
- Landau-Lifshitz Vol. 1 *Mechanics* 3rd ed (ISBN 978-0750628969)
  — Chapter VI §§32–36
- Kuipers 1999 *Quaternions and Rotation Sequences* (ISBN 978-0691102986)
  — Chapter 6

Public API:
    inertia_from_point_masses       — I = Σ m(r²δ − r⊗r)
    parallel_axis_transform         — Steiner's theorem
    diagonalize_inertia             — principal axes + moments
    is_positive_definite            — PD check
    euler_equations_rhs             — τ = (dL/dt)_body + ω × L
    integrate_free_body_rk4         — torque-free spin integrator
    integrate_rigid_body_rk4        — with arbitrary torque
    torque_free_precession_rate     — Ω_p = ((I∥−I⊥)/I⊥) ω_3
    fast_spin_precession_rate       — Ω_prec = mgl / (I∥ ω_spin)
    cmg_reaction_torque             — τ = I∥ ω_spin × ω_gimbal
    quaternion_multiply             — q₁ ⊗ q₂
    quaternion_normalize            — enforce |q| = 1
    quaternion_kinematic_matrix     — Ω(ω) for q̇ = (1/2) Ω q
    quaternion_to_rotation_matrix   — attitude R₃₃
    quaternion_from_axis_angle      — (n̂, θ) → q
    rotation_matrix_313             — 3-1-3 Euler angles to R
"""

from .inertia import (
    diagonalize_inertia,
    inertia_from_point_masses,
    inertia_solid_sphere,
    inertia_thin_ring,
    is_positive_definite,
    parallel_axis_transform,
)
from .euler_equations import (
    euler_equations_rhs,
    integrate_free_body_rk4,
    integrate_rigid_body_rk4,
    kinetic_energy,
)
from .quaternion import (
    quaternion_conjugate,
    quaternion_from_axis_angle,
    quaternion_kinematic_matrix,
    quaternion_multiply,
    quaternion_normalize,
    quaternion_to_rotation_matrix,
)
from .euler_angles import (
    euler_angles_313_from_rotation_matrix,
    rotation_matrix_313,
)
from .precession import (
    cmg_reaction_torque,
    fast_spin_precession_rate,
    torque_free_precession_rate,
)

__all__ = [
    # Inertia
    "inertia_from_point_masses",
    "inertia_solid_sphere",
    "inertia_thin_ring",
    "parallel_axis_transform",
    "diagonalize_inertia",
    "is_positive_definite",
    # Euler eqs + integration
    "euler_equations_rhs",
    "integrate_free_body_rk4",
    "integrate_rigid_body_rk4",
    "kinetic_energy",
    # Quaternions
    "quaternion_multiply",
    "quaternion_normalize",
    "quaternion_conjugate",
    "quaternion_kinematic_matrix",
    "quaternion_to_rotation_matrix",
    "quaternion_from_axis_angle",
    # Euler angles
    "rotation_matrix_313",
    "euler_angles_313_from_rotation_matrix",
    # Precession
    "torque_free_precession_rate",
    "fast_spin_precession_rate",
    "cmg_reaction_torque",
]
