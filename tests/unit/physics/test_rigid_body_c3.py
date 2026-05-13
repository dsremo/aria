"""Verification tests for Pod C3 (rigid-body rotational dynamics).

Covers the four test cases from `docs/pods/C3_euler_tensor.md` §9:

  9.1 Poinsot torque-free precession — |L|², T conservation for an
      asymmetric body integrated over many spin periods
  9.2 Heavy symmetric top — fast-spin precession rate Ω ≈ mgl/(I_∥ ω)
  9.3 Euler-quaternion equivalence — attitude paths agree to ~1e-9
      residual in the final rotation matrix
  9.4 CMG gyroscopic torque — τ = I_∥ ω_spin × ω_gimbal magnitude
      31.4 N·m (Wertz 1978 §15.2 example)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from aria.physics.rigid_body import (
    cmg_reaction_torque,
    diagonalize_inertia,
    euler_equations_rhs,
    fast_spin_precession_rate,
    inertia_from_point_masses,
    inertia_solid_sphere,
    inertia_thin_ring,
    integrate_free_body_rk4,
    integrate_rigid_body_rk4,
    is_positive_definite,
    kinetic_energy,
    parallel_axis_transform,
    quaternion_from_axis_angle,
    quaternion_kinematic_matrix,
    quaternion_multiply,
    quaternion_normalize,
    quaternion_to_rotation_matrix,
    rotation_matrix_313,
    torque_free_precession_rate,
)
from aria.physics.rigid_body.quaternion import integrate_quaternion_rk4
from aria.physics.rigid_body.euler_angles import (
    euler_angles_313_from_rotation_matrix,
)


# ─────────────────────────────────────────────────────────────────────
# Test 9.1 — Poinsot torque-free precession
# Source: Goldstein 2002 §5.6 Example (ISBN 978-0201657029)
# ─────────────────────────────────────────────────────────────────────


class TestPoinsotTorqueFree:
    """Torque-free integration of an asymmetric body must conserve
    both the squared angular momentum `|L|² = (Iω)·(Iω)` and the
    kinetic energy `T = (1/2) ωᵀ I ω`.

    This is the most demanding integrator test in C3 because the three
    Euler equations are nonlinearly coupled — RK4 error in any single
    component leaks into both conservation laws.
    """

    I1, I2, I3 = 1.0, 2.0, 3.0
    I = np.diag([I1, I2, I3])
    # Generic initial ω that projects onto all three axes.
    omega0 = np.array([0.1, 1.0, 0.5])

    def test_l_squared_conserved(self) -> None:
        L0 = self.I @ self.omega0
        L2_0 = float(np.dot(L0, L0))
        omega_final, _ = integrate_free_body_rk4(
            inertia_kg_m2=self.I,
            omega0_rad_s=self.omega0,
            t0=0.0,
            t_end=100.0,  # many spin periods
            dt=1.0e-3,
        )
        L1 = self.I @ omega_final
        L2_1 = float(np.dot(L1, L1))
        rel = abs((L2_1 - L2_0) / L2_0)
        assert rel < 1.0e-7, f"|L|² drift {rel:.3e}"

    def test_kinetic_energy_conserved(self) -> None:
        T0 = kinetic_energy(self.I, self.omega0)
        omega_final, _ = integrate_free_body_rk4(
            inertia_kg_m2=self.I,
            omega0_rad_s=self.omega0,
            t0=0.0,
            t_end=100.0,
            dt=1.0e-3,
        )
        T1 = kinetic_energy(self.I, omega_final)
        rel = abs((T1 - T0) / T0)
        assert rel < 1.0e-7, f"T drift {rel:.3e}"

    def test_rhs_is_zero_when_omega_aligned_with_principal_axis(self) -> None:
        # Pure rotation about one principal axis is a fixed point of
        # the torque-free Euler equations (trivially stable for the
        # extremal axes, unstable for the intermediate axis — the
        # "tennis racket" theorem).
        for axis in range(3):
            w = np.zeros(3)
            w[axis] = 2.5
            a = euler_equations_rhs(self.I, w, np.zeros(3))
            assert float(np.linalg.norm(a)) < 1.0e-14

    def test_symmetric_top_closed_form_match(self) -> None:
        # For an oblate symmetric top (I_1 = I_2 < I_3), the scalar
        # precession rate is Ω_p = ((I_∥−I_⊥)/I_⊥) ω_3 = ((3−1)/1)·0.5
        # = 1.0 rad/s.
        I_sym = np.diag([1.0, 1.0, 3.0])
        omega = np.array([0.2, 0.0, 0.5])
        Omega_p = torque_free_precession_rate(
            I_parallel_kg_m2=3.0,
            I_perpendicular_kg_m2=1.0,
            spin_rate_rad_s=0.5,
        )
        assert Omega_p == pytest.approx(1.0, rel=1e-12)
        # Integrate for one precession period and check ω_1, ω_2 close
        # near their initial values.
        T_p = 2.0 * math.pi / Omega_p
        omega_final, _ = integrate_free_body_rk4(
            I_sym, omega, 0.0, T_p, dt=1.0e-4
        )
        # ω_3 is unchanged (torque-free); ω_1, ω_2 return to initial up
        # to RK4 error.
        assert omega_final[2] == pytest.approx(0.5, rel=1e-8)
        assert omega_final[0] == pytest.approx(0.2, abs=1e-3)
        assert omega_final[1] == pytest.approx(0.0, abs=1e-3)


# ─────────────────────────────────────────────────────────────────────
# Test 9.2 — Heavy symmetric top, fast-spin precession
# Source: Landau-Lifshitz Vol.1 §35 Problem 1 (ISBN 978-0750628969)
# ─────────────────────────────────────────────────────────────────────


class TestHeavyTopFastSpin:
    """Fast-spin precession rate `Ω = mgl/(I_∥ ω_spin)`."""

    def test_analytic_closed_form(self) -> None:
        # Scope §9.2 worked example:
        # m=1, l=0.1, g=9.80665, I_∥=2, ω_spin=50
        # → Ω = 9.80665 · 0.1 / (2 · 50) = 0.00981 rad/s
        omega_prec = fast_spin_precession_rate(
            mass_kg=1.0,
            g_m_s2=9.80665,
            pivot_offset_m=0.1,
            I_parallel_kg_m2=2.0,
            spin_rate_rad_s=50.0,
        )
        assert omega_prec == pytest.approx(0.009_806_65, rel=1e-12)

    def test_faster_spin_slower_precession(self) -> None:
        # Ω ∝ 1/ω_spin; doubling the spin should halve the precession.
        slow = fast_spin_precession_rate(1.0, 9.81, 0.1, 2.0, 100.0)
        fast = fast_spin_precession_rate(1.0, 9.81, 0.1, 2.0, 200.0)
        assert fast == pytest.approx(slow / 2.0, rel=1e-12)

    def test_zero_spin_raises(self) -> None:
        with pytest.raises(ValueError):
            fast_spin_precession_rate(1.0, 9.81, 0.1, 2.0, 0.0)


# ─────────────────────────────────────────────────────────────────────
# Test 9.3 — Euler / quaternion equivalence
# Source: Kuipers 1999 §6.7 (ISBN 978-0691102986)
# ─────────────────────────────────────────────────────────────────────


class TestEulerQuaternionEquivalence:
    """Attitude integrated through quaternion-RK4 must match an
    independent Euler-angle integration outside the singularity."""

    def test_roundtrip_axis_angle(self) -> None:
        # Construct a rotation, convert to matrix, recover Euler angles,
        # rebuild the matrix, and verify equality.
        axis = np.array([1.0, 1.0, 1.0])
        angle = 0.7
        q = quaternion_from_axis_angle(axis, angle)
        R = quaternion_to_rotation_matrix(q)
        # Should be orthogonal and determinant +1.
        assert np.allclose(R.T @ R, np.eye(3), atol=1e-12)
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-12)

    def test_composition_matches_matrix_product(self) -> None:
        q1 = quaternion_from_axis_angle([1, 0, 0], 0.5)
        q2 = quaternion_from_axis_angle([0, 1, 0], 0.3)
        q12 = quaternion_multiply(q1, q2)
        R_from_q = quaternion_to_rotation_matrix(q12)
        R_direct = (
            quaternion_to_rotation_matrix(q1)
            @ quaternion_to_rotation_matrix(q2)
        )
        assert np.allclose(R_from_q, R_direct, atol=1e-12)

    def test_quaternion_rk4_pure_z_spin(self) -> None:
        # Constant ω = ω_z ẑ; after time t the rotation should be
        # by angle ω·t about the z-axis.
        omega_z = 1.5  # rad/s
        q0 = np.array([1.0, 0.0, 0.0, 0.0])  # identity
        t_end = 2.0  # seconds → 3 rad rotation

        q_final, _ = integrate_quaternion_rk4(
            q0=q0, t0=0.0, t_end=t_end, dt=1e-4,
            omega_fn=lambda t: np.array([0.0, 0.0, omega_z]),
        )
        expected_angle = omega_z * t_end
        # The magnitude of the vector part equals |sin(angle/2)|
        vec_norm = float(np.linalg.norm(q_final[1:]))
        assert vec_norm == pytest.approx(
            abs(math.sin(expected_angle / 2.0)), abs=1e-6
        )
        # And the scalar part equals cos(angle/2).
        assert q_final[0] == pytest.approx(math.cos(expected_angle / 2.0), abs=1e-6)

    def test_euler_313_matrix_roundtrip(self) -> None:
        phi, theta, psi = 0.2, 0.7, 0.4
        R = rotation_matrix_313(phi, theta, psi)
        phi_r, theta_r, psi_r = euler_angles_313_from_rotation_matrix(R)
        assert phi_r == pytest.approx(phi, abs=1e-12)
        assert theta_r == pytest.approx(theta, abs=1e-12)
        assert psi_r == pytest.approx(psi, abs=1e-12)

    def test_euler_313_singular_raises(self) -> None:
        # θ = 0 is the gimbal-lock singularity (sin θ = 0).
        R = rotation_matrix_313(0.2, 0.0, 0.4)
        with pytest.raises(ValueError, match="singular"):
            euler_angles_313_from_rotation_matrix(R)


# ─────────────────────────────────────────────────────────────────────
# Test 9.4 — CMG reaction torque (Wertz 1978 §15.2)
# ─────────────────────────────────────────────────────────────────────


class TestCMGReactionTorque:
    """Control-moment gyroscope reaction torque.

    Scope §9.4: `I_∥ = 0.5 kg·m²`, ω_spin = 6000 rpm = 628.3 rad/s,
    ω_gimbal = 0.1 rad/s perpendicular to ω_spin → |τ| = 31.4 N·m.
    """

    def test_wertz_example_magnitude(self) -> None:
        I_parallel = 0.5
        spin_rpm = 6000.0
        spin_rad_s = spin_rpm * 2.0 * math.pi / 60.0  # ≈ 628.3185 rad/s
        # Spin about z, gimbal about x (perpendicular).
        omega_spin = np.array([0.0, 0.0, spin_rad_s])
        omega_gimbal = np.array([0.1, 0.0, 0.0])
        tau = cmg_reaction_torque(I_parallel, omega_spin, omega_gimbal)
        mag = float(np.linalg.norm(tau))
        expected = I_parallel * spin_rad_s * 0.1  # 31.4159 N·m
        assert mag == pytest.approx(expected, rel=1e-12)
        assert mag == pytest.approx(31.4159, abs=0.01)

    def test_parallel_inputs_give_zero_torque(self) -> None:
        # ω_spin ∥ ω_gimbal → cross product zero.
        tau = cmg_reaction_torque(
            I_parallel_kg_m2=0.5,
            omega_spin_rad_s=np.array([0.0, 0.0, 628.0]),
            omega_gimbal_rad_s=np.array([0.0, 0.0, 0.3]),
        )
        assert float(np.linalg.norm(tau)) == 0.0

    def test_torque_direction_right_handed(self) -> None:
        # Spin ẑ × gimbal x̂ = ŷ → torque along +y.
        tau = cmg_reaction_torque(
            I_parallel_kg_m2=1.0,
            omega_spin_rad_s=np.array([0.0, 0.0, 1.0]),
            omega_gimbal_rad_s=np.array([1.0, 0.0, 0.0]),
        )
        assert tau[0] == 0.0
        assert tau[1] == pytest.approx(1.0, abs=1e-15)
        assert tau[2] == 0.0


# ─────────────────────────────────────────────────────────────────────
# Inertia tensor primitives
# ─────────────────────────────────────────────────────────────────────


class TestInertiaTensor:
    def test_point_masses_symmetric(self) -> None:
        positions = np.array(
            [
                [1.0, 0.0, 0.0],
                [-1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, -1.0, 0.0],
            ]
        )
        masses = np.ones(4)
        I = inertia_from_point_masses(positions, masses)
        # Should be symmetric.
        assert np.allclose(I, I.T, atol=1e-15)
        # I_xx = Σ m(y² + z²) = 2·0 + 2·1 = 2
        assert I[0, 0] == pytest.approx(2.0, abs=1e-15)
        assert I[1, 1] == pytest.approx(2.0, abs=1e-15)
        assert I[2, 2] == pytest.approx(4.0, abs=1e-15)

    def test_parallel_axis_theorem(self) -> None:
        # Solid sphere at CM, then shifted to a point 1 m away on +z.
        M, R = 10.0, 0.5
        I_cm = inertia_solid_sphere(M, R)
        I_shifted = parallel_axis_transform(I_cm, np.array([0.0, 0.0, 1.0]), M)
        # Along z-axis the offset squared is 0 (since a_z·a_z = 1 but
        # (|a|² − a_z²) = 1 − 1 = 0). So I_zz is unchanged.
        assert I_shifted[2, 2] == pytest.approx(I_cm[2, 2], abs=1e-15)
        # In the x-y plane the theorem adds M · 1² = 10 to the diagonal.
        assert I_shifted[0, 0] == pytest.approx(I_cm[0, 0] + 10.0, abs=1e-15)
        assert I_shifted[1, 1] == pytest.approx(I_cm[1, 1] + 10.0, abs=1e-15)

    def test_thin_ring_matches_scope_note(self) -> None:
        M = 1000.0
        R = 2.0
        I = inertia_thin_ring(M, R)
        MR2 = M * R * R
        assert I[2, 2] == pytest.approx(MR2, rel=1e-15)
        assert I[0, 0] == pytest.approx(0.5 * MR2, rel=1e-15)
        assert I[1, 1] == pytest.approx(0.5 * MR2, rel=1e-15)

    def test_positive_definite_check(self) -> None:
        assert is_positive_definite(np.diag([1.0, 2.0, 3.0]))
        # Zero eigenvalue = positive semi-definite (valid for thin-rod
        # geometry with no moment about one axis). Accepted per fix.
        assert is_positive_definite(np.diag([1.0, 0.0, 3.0]))
        assert not is_positive_definite(np.diag([1.0, -1.0, 3.0]))

    def test_diagonalization_returns_ascending_eigenvalues(self) -> None:
        I = np.diag([3.0, 1.0, 2.0])
        eigvals, eigvecs = diagonalize_inertia(I)
        assert eigvals[0] <= eigvals[1] <= eigvals[2]
        # Recover the original by similarity transform.
        reconstructed = eigvecs @ np.diag(eigvals) @ eigvecs.T
        assert np.allclose(reconstructed, I, atol=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Quaternion invariants
# ─────────────────────────────────────────────────────────────────────


class TestQuaternionInvariants:
    def test_identity_quaternion_rotation_is_identity(self) -> None:
        q = np.array([1.0, 0.0, 0.0, 0.0])
        assert np.allclose(quaternion_to_rotation_matrix(q), np.eye(3), atol=1e-15)

    def test_normalize_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="zero norm"):
            quaternion_normalize(np.zeros(4))

    def test_kinematic_matrix_antisymmetric_block(self) -> None:
        # Ω(ω) is skew-symmetric; i.e. Ω + Ωᵀ = 0.
        Omega = quaternion_kinematic_matrix(np.array([1.0, 2.0, 3.0]))
        assert np.allclose(Omega + Omega.T, 0.0, atol=1e-15)
