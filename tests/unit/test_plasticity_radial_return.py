"""Radial-return J2 plasticity tests."""
from __future__ import annotations
import math
import numpy as np
import pytest
from aria.physics.solid_mechanics.plasticity import (
    radial_return_j2, consistent_tangent_modulus, von_mises_yield_check,
)


# Ti-6Al-4V: E = 113 GPa, ν = 0.34, σ_y = 880 MPa, H = 1.5 GPa
_E = 113e9
_NU = 0.34
_SIGMA_Y = 880e6
_H = 1.5e9


def test_pure_elastic_stays_inside_yield_surface():
    """A small strain increment must remain inside the von Mises surface."""
    stress_n = np.zeros((3, 3))
    d_eps = np.zeros((3, 3))
    d_eps[0, 0] = 0.5 * _SIGMA_Y / _E     # half the uniaxial-stress elastic limit
    stress_new, p_new, dgamma, plastic = radial_return_j2(
        stress_n, d_eps, 0.0, _E, _NU, _SIGMA_Y, _H,
    )
    assert not plastic
    assert dgamma == 0.0
    assert p_new == 0.0
    # Check σ̄ < σ_y (step stayed elastic)
    sigma_vm = math.sqrt(1.5 * np.sum(
        (stress_new - np.trace(stress_new) / 3 * np.eye(3)) ** 2
    ))
    assert sigma_vm < _SIGMA_Y


def test_yielding_large_strain_triggers_plastic():
    """Applying 2 × elastic limit must trigger plastic flow."""
    stress_n = np.zeros((3, 3))
    eps_limit = _SIGMA_Y / _E
    d_eps = np.zeros((3, 3))
    d_eps[0, 0] = 2.0 * eps_limit
    stress_new, p_new, dgamma, plastic = radial_return_j2(
        stress_n, d_eps, 0.0, _E, _NU, _SIGMA_Y, _H,
    )
    assert plastic
    assert dgamma > 0
    assert p_new > 0
    # Stress must satisfy yield condition after mapping (to tolerance)
    sigma_vm = math.sqrt(1.5 * np.sum(
        (stress_new - np.trace(stress_new) / 3 * np.eye(3)) ** 2
    ))
    radius = _SIGMA_Y + _H * p_new
    assert abs(sigma_vm - radius) / radius < 0.01


def test_perfect_plasticity_cap_at_yield_stress():
    """With H=0, stress must plateau at σ_y under continued straining."""
    stress_n = np.zeros((3, 3))
    d_eps = np.zeros((3, 3))
    d_eps[0, 0] = 0.05   # large plastic strain
    stress_new, p_new, _, plastic = radial_return_j2(
        stress_n, d_eps, 0.0, _E, _NU, _SIGMA_Y, hardening_modulus_pa=0.0,
    )
    assert plastic
    sigma_vm = math.sqrt(1.5 * np.sum(
        (stress_new - np.trace(stress_new) / 3 * np.eye(3)) ** 2
    ))
    # For perfect plasticity σ̄ must be exactly σ_y (to tol.)
    assert abs(sigma_vm - _SIGMA_Y) / _SIGMA_Y < 0.01


def test_plastic_strain_monotonic_over_load_steps():
    """Cumulative plastic strain must never decrease."""
    stress = np.zeros((3, 3))
    p = 0.0
    d_eps = np.zeros((3, 3))
    d_eps[0, 0] = 0.003
    prev_p = 0.0
    for _ in range(5):
        stress, p, _, _ = radial_return_j2(stress, d_eps, p, _E, _NU, _SIGMA_Y, _H)
        assert p >= prev_p - 1e-12
        prev_p = p


def test_hardening_raises_flow_stress():
    """With H>0, flow stress after yielding exceeds initial σ_y."""
    stress_n = np.zeros((3, 3))
    d_eps = np.zeros((3, 3))
    d_eps[0, 0] = 0.02
    stress_new, p_new, _, _ = radial_return_j2(
        stress_n, d_eps, 0.0, _E, _NU, _SIGMA_Y, hardening_modulus_pa=_H,
    )
    sigma_vm = math.sqrt(1.5 * np.sum(
        (stress_new - np.trace(stress_new) / 3 * np.eye(3)) ** 2
    ))
    assert sigma_vm > _SIGMA_Y   # hardening lifted the yield surface


def test_consistent_tangent_is_6x6():
    stress_trial = np.eye(3) * 100e6
    stress_trial[0, 0] = 500e6
    C = consistent_tangent_modulus(stress_trial, delta_gamma=0.001,
                                    youngs_modulus_pa=_E, poisson_ratio=_NU,
                                    hardening_modulus_pa=_H)
    assert C.shape == (6, 6)
    # Bulk modulus should still drive hydrostatic entries
    K = _E / (3.0 * (1.0 - 2.0 * _NU))
    # K = (C[0,0] + 2*C[0,1]) / 3 for isotropic elasticity — loose check
    assert C[0, 0] > 0
    assert C[0, 1] > 0


def test_poisson_ratio_bounds():
    with pytest.raises(ValueError):
        radial_return_j2(np.zeros((3, 3)), np.zeros((3, 3)), 0.0,
                         _E, 0.5, _SIGMA_Y, _H)  # ν=0.5 forbidden
    with pytest.raises(ValueError):
        radial_return_j2(np.zeros((3, 3)), np.zeros((3, 3)), 0.0,
                         _E, -0.1, _SIGMA_Y, _H)
