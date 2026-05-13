from __future__ import annotations
import numpy as np
import pytest
from aria.simulation.range_only_observability import (
    RangeMeasurement, assess_observability, range_jacobian_row,
)


def test_range_jacobian_direction_along_los():
    sat = np.array([1000.0, 0, 0, 0, 0, 0])
    obs = np.array([0.0, 0, 0])
    H = range_jacobian_row(sat, obs)
    # Position gradient is unit vector from obs to sat
    assert np.allclose(H[:3], [1, 0, 0])
    # No velocity dependence in instantaneous range
    assert np.allclose(H[3:], [0, 0, 0])


def test_range_only_is_underdetermined():
    """Range-only measurements can't observe the full 6-DOF state."""
    state0 = np.array([7_000_000.0, 0, 0, 0, 7500.0, 0])
    obs_positions = [np.array([np.cos(k)*6.4e6, np.sin(k)*6.4e6, 0])
                     for k in np.linspace(0, 6.28, 8)]
    meas = [RangeMeasurement(t_s=k*60, observer_pos=p, range_m=1e6)
            for k, p in enumerate(obs_positions)]
    r = assess_observability(state0, meas)
    assert not r.observable       # range-only cannot recover velocity
    assert r.missing_dof >= 3


def test_few_measurements_flagged():
    r = assess_observability(np.zeros(6), [])
    assert not r.observable
    assert r.rank == 0


def test_position_partially_observable():
    """Position DOF should be observable with ≥3 geometric diversity."""
    state0 = np.array([7_000_000.0, 0, 0, 0, 7500.0, 0])
    # Widely separated observers
    positions = [np.array([6.4e6, 0, 0]), np.array([0, 6.4e6, 0]),
                 np.array([0, 0, 6.4e6]), np.array([-6.4e6, 0, 0]),
                 np.array([0, -6.4e6, 0]), np.array([0, 0, -6.4e6])]
    meas = [RangeMeasurement(k, p, 1e6) for k, p in enumerate(positions)]
    r = assess_observability(state0, meas)
    # At least 3 position DOF should be observable (H has 3-D row space)
    assert r.rank >= 3
