from __future__ import annotations
import math
import numpy as np
import pytest
from aria.simulation.rcs_attitude import (
    RigidBody, Thruster, apollo_csm_rcs, rcs_torque, simulate_attitude,
    quat_normalize, quat_derivative, rotate_vector_by_quat,
)


def test_zero_torque_no_rate_change():
    body = apollo_csm_rcs()
    schedule = [[0.0] * len(body.thrusters) for _ in range(20)]
    q0 = np.array([1.0, 0, 0, 0])
    w0 = np.array([0.01, 0, 0])
    qf, wf, _ = simulate_attitude(body, q0, w0, schedule, dt_s=0.1)
    # Angular velocity preserved (body had no external torque)
    assert np.allclose(wf, w0, atol=1e-5)


def test_positive_torque_increases_rate():
    body = apollo_csm_rcs()
    # Fire first thruster (should produce torque)
    cmds = [0.0] * len(body.thrusters)
    cmds[0] = 1.0
    schedule = [cmds for _ in range(50)]
    q0 = np.array([1.0, 0, 0, 0])
    w0 = np.zeros(3)
    _, wf, _ = simulate_attitude(body, q0, w0, schedule, dt_s=0.1)
    assert np.linalg.norm(wf) > 0


def test_quaternion_stays_unit():
    body = apollo_csm_rcs()
    cmds = [1.0, 0, 0, 0, 0, 1.0] + [0.0] * (len(body.thrusters) - 6)
    schedule = [cmds] * 100
    q0 = np.array([1.0, 0, 0, 0])
    w0 = np.zeros(3)
    qf, _, _ = simulate_attitude(body, q0, w0, schedule, dt_s=0.05)
    assert abs(np.linalg.norm(qf) - 1.0) < 1e-3


def test_rcs_torque_nonzero_with_offset_thruster():
    body = apollo_csm_rcs()
    cmds = [0.0] * len(body.thrusters)
    cmds[0] = 1.0
    tau = rcs_torque(body, cmds)
    assert np.linalg.norm(tau) > 0


def test_quaternion_normalize_unit():
    q = quat_normalize(np.array([2.0, 0, 0, 0]))
    assert abs(np.linalg.norm(q) - 1.0) < 1e-10


def test_rotate_vector_identity_quat():
    v = np.array([1.0, 0, 0])
    q = np.array([1.0, 0, 0, 0])   # identity
    rv = rotate_vector_by_quat(q, v)
    assert np.allclose(rv, v)
