"""Pod C1 — Rotating-frame kinematics for the habitat ring.

Implements audit items §2.1 (centrifugal a=ω²r), §2.2 (Coriolis),
§2.3 (Euler force ω̇×r — structural consequence), §2.4 (differential-g
across crew body), §2.7 (transient g during spin-up).

C1 is a pure-kinematics pod: it provides closed-form expressions for
the three rotating-frame pseudo-forces (centrifugal, Coriolis, Euler)
at any query point in a rigid ring spinning about a fixed axis, plus
the differential-g gradient across a crew body and a cosine-smoothed
spin-up profile.

See `docs/pods/C1_rotating_hab.md` for the scope note (derivations,
citations, verification test cases).

Public API:
    centrifugal_acceleration_scalar     — a_cf = ω² r
    centrifugal_acceleration_vector     — a_cf = -Ω × (Ω × r)
    coriolis_acceleration_scalar        — |a_cor| = 2 ω v (walking case)
    coriolis_acceleration_vector        — a_cor = -2 Ω × v
    euler_acceleration_scalar           — |a_E| = α r
    euler_acceleration_vector           — a_E = -(dΩ/dt) × r
    differential_g_head_to_foot         — Δg = ω² h
    cosine_spinup_profile               — (ω(t), α(t)) closed form
    cosine_spinup_peak_alpha            — α_peak for a given ramp
    coriolis_dropped_object_deflection  — Δx = (1/3) ω g t³ at deck
    fluid_paraboloid_height             — z(r) = z₀ + ω² r²/(2 g_local)
    RotatingRingConfig                  — common geometry + design values
"""

from .kinematics import (
    RotatingRingConfig,
    centrifugal_acceleration_scalar,
    centrifugal_acceleration_vector,
    coriolis_acceleration_scalar,
    coriolis_acceleration_vector,
    coriolis_dropped_object_deflection,
    differential_g_head_to_foot,
    euler_acceleration_scalar,
    euler_acceleration_vector,
    fluid_paraboloid_height,
)
from .spinup_profile import (
    cosine_spinup_peak_alpha,
    cosine_spinup_profile,
)

__all__ = [
    "RotatingRingConfig",
    "centrifugal_acceleration_scalar",
    "centrifugal_acceleration_vector",
    "coriolis_acceleration_scalar",
    "coriolis_acceleration_vector",
    "coriolis_dropped_object_deflection",
    "differential_g_head_to_foot",
    "euler_acceleration_scalar",
    "euler_acceleration_vector",
    "fluid_paraboloid_height",
    "cosine_spinup_peak_alpha",
    "cosine_spinup_profile",
]
