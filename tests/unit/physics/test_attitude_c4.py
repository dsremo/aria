"""Unit tests for Pod C4 — gyroscopic attitude (P1-7).

Benchmarks:
  - Wertz 1978 *Spacecraft Attitude Determination and Control* §16
    (dual-spin example, ISBN 978-9027709592).
  - Wie 1998 *Space Vehicle Dynamics and Control* §7 AIAA (ISBN
    978-1563472619).
  - Bedrossian et al. 2009 *J Guidance* 32(2) 553 (ISS CMG specs).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.attitude import (
    CMG_DESAT_TRIGGER_FRACTION,
    ISS_CMG_PYRAMID_SKEW_DEG,
    ISS_CMG_ROTOR_MOMENTUM_N_M_S,
    cmg_pseudoinverse_steering,
    cmg_pyramid_jacobian,
    cmg_pyramid_total_momentum,
    dual_spin_total_angular_momentum,
    gyroscopic_reaction_torque,
    is_cmg_saturation_imminent,
    rcs_desat_impulse_required,
    singularity_margin,
    wertz_nutation_frequency,
)


# ──────────────────────────────────────────────────────────────────────
#  Dual-spin
# ──────────────────────────────────────────────────────────────────────


def test_dual_spin_total_angular_momentum_wertz_example():
    """Wertz 1978 §16.3 example: symmetric bus (I_1=I_2=1, I_3=2),
    rotor along +z with I_rot = 0.3, ω_rot = 100.
    Bus spins at Ω = (0, 0, 5). L = (0, 0, 10) + (0, 0, 30) = 40."""
    i_bus = np.diag([1.0, 1.0, 2.0])
    omega = np.array([0.0, 0.0, 5.0])
    l = dual_spin_total_angular_momentum(
        bus_inertia_tensor_kg_m2=i_bus,
        bus_angular_velocity_rad_s=omega,
        ring_inertia_parallel_kg_m2=0.3,
        ring_spin_rate_rad_s=100.0,
        ring_spin_axis_bus_frame=np.array([0.0, 0.0, 1.0]),
    )
    assert l[2] == pytest.approx(40.0, rel=1.0e-12)
    assert l[0] == 0.0 and l[1] == 0.0


def test_dual_spin_accepts_cmg_momentum_contribution():
    i_bus = np.eye(3)
    l = dual_spin_total_angular_momentum(
        bus_inertia_tensor_kg_m2=i_bus,
        bus_angular_velocity_rad_s=np.zeros(3),
        ring_inertia_parallel_kg_m2=0.0,
        ring_spin_rate_rad_s=0.0,
        ring_spin_axis_bus_frame=np.array([1.0, 0.0, 0.0]),
        cmg_momentum_bus_frame=np.array([0.0, 0.0, 7.5]),
    )
    assert l[2] == pytest.approx(7.5)


def test_gyroscopic_reaction_torque_aria_baseline():
    """ARIA baseline ring check (Wie 1998 §7.3):
    I_∥ = 2.35e9, ω_rel = 0.4189, Ω_bus = 1e-3 perpendicular.
    |τ| = 1e-3 · 2.35e9 · 0.4189 ≈ 9.84e5 N·m."""
    i_parallel = 2.35e9
    omega_rel = 0.4189
    l_ring = i_parallel * omega_rel * np.array([0.0, 0.0, 1.0])
    omega_bus = np.array([1.0e-3, 0.0, 0.0])  # perpendicular slew
    tau = gyroscopic_reaction_torque(omega_bus, l_ring)
    mag = float(np.linalg.norm(tau))
    assert 9.8e5 < mag < 9.9e5, f"|τ| = {mag:.3e}"
    # orthogonal to both input axes
    assert tau @ omega_bus == pytest.approx(0.0, abs=1.0e-9)
    assert tau @ l_ring == pytest.approx(0.0, abs=1.0e-9)


def test_wertz_nutation_frequency_oblate_prolate():
    """For I_s = 2, I_t = 1, ω_3 = 5 rad/s → ω_nut = 5 rad/s."""
    w = wertz_nutation_frequency(
        transverse_moment_kg_m2=1.0, spin_moment_kg_m2=2.0, spin_rate_rad_s=5.0
    )
    assert w == pytest.approx(5.0, rel=1.0e-12)


def test_wertz_nutation_symmetric_body_zero():
    """For I_s = I_t the body is a spherical top → no nutation."""
    w = wertz_nutation_frequency(1.0, 1.0, 3.0)
    assert w == 0.0


# ──────────────────────────────────────────────────────────────────────
#  CMG pyramid
# ──────────────────────────────────────────────────────────────────────


def test_iss_cmg_pyramid_skew_is_magic_angle():
    """Wie 1998 §7.4: β = arctan(√2) ≈ 54.7356° makes the envelope
    spherical and is the ISS choice."""
    assert ISS_CMG_PYRAMID_SKEW_DEG == pytest.approx(
        math.degrees(math.atan(math.sqrt(2.0))), rel=1.0e-4
    )


def test_iss_rotor_momentum_bedrossian():
    """Bedrossian 2009 Table 2: |h_i| = 4760 N·m·s."""
    assert ISS_CMG_ROTOR_MOMENTUM_N_M_S == 4760.0


def test_pyramid_total_momentum_zero_when_all_gimbals_cancel():
    """At δ = 0 the four zero-rotor axes cancel pairwise (±y, ±x)."""
    h_stack = cmg_pyramid_total_momentum(np.zeros(4))
    assert np.allclose(h_stack, 0.0, atol=1.0e-9)


def test_pyramid_jacobian_rank_3_nominal():
    """H(δ=0) should be rank 3 (full bus torque authority)."""
    h = cmg_pyramid_jacobian(np.zeros(4))
    rank = int(np.linalg.matrix_rank(h, tol=1.0e-6))
    assert rank == 3


def test_pyramid_jacobian_shape():
    h = cmg_pyramid_jacobian(np.array([0.1, 0.2, 0.3, 0.4]))
    assert h.shape == (3, 4)


def test_pyramid_jacobian_rejects_wrong_shape():
    with pytest.raises(ValueError):
        cmg_pyramid_jacobian(np.array([0.0, 0.0, 0.0]))


# ──────────────────────────────────────────────────────────────────────
#  Singularity metric and steering law
# ──────────────────────────────────────────────────────────────────────


def test_singularity_margin_nominal_is_positive():
    h = cmg_pyramid_jacobian(np.zeros(4))
    m = singularity_margin(h)
    assert m > 0.0


def test_steering_produces_commanded_torque_at_nominal():
    """At δ=0 the pseudoinverse should give δ̇ such that
    −H δ̇ ≈ τ_cmd."""
    h = cmg_pyramid_jacobian(np.zeros(4))
    tau_cmd = np.array([100.0, -50.0, 200.0])
    delta_dot = cmg_pseudoinverse_steering(h, tau_cmd)
    tau_actual = -h @ delta_dot
    assert np.allclose(tau_actual, tau_cmd, atol=1.0e-6)


def test_steering_damped_at_singular_config():
    """Collapse H to a rank-1 matrix and check that the damped
    pseudoinverse clips the blow-up instead of returning ∞."""
    h_singular = np.zeros((3, 4))
    h_singular[0, :] = 1.0  # rank-1 — all torques along x only
    tau_off_axis = np.array([0.0, 1.0, 0.0])  # unreachable
    delta_dot = cmg_pseudoinverse_steering(
        h_singular, tau_off_axis, min_singular_value=1.0e-3
    )
    assert np.all(np.isfinite(delta_dot))
    # The on-axis component should still be handled (rank-1 allows x).
    tau_x = np.array([1.0, 0.0, 0.0])
    dd_x = cmg_pseudoinverse_steering(h_singular, tau_x)
    assert np.allclose(-h_singular @ dd_x, tau_x, atol=1.0e-6)


# ──────────────────────────────────────────────────────────────────────
#  Momentum management
# ──────────────────────────────────────────────────────────────────────


def test_cmg_desat_trigger_at_80_percent():
    """Wie 1998 §7.4.4 ISS rule: trigger at 80 % h_max."""
    assert CMG_DESAT_TRIGGER_FRACTION == 0.80
    assert is_cmg_saturation_imminent(
        np.array([0.0, 0.0, 80.0]), h_max_n_m_s=100.0
    )
    assert not is_cmg_saturation_imminent(
        np.array([0.0, 0.0, 79.0]), h_max_n_m_s=100.0
    )


def test_rcs_desat_impulse_formula():
    """|h| / arm = required |FΔt|."""
    impulse = rcs_desat_impulse_required(
        np.array([0.0, 0.0, 1.0e5]), moment_arm_m=50.0
    )
    assert impulse == pytest.approx(2.0e3, rel=1.0e-12)
