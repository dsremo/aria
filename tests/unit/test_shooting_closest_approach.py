from __future__ import annotations
import numpy as np
import pytest
from aria.simulation.shooting_closest_approach import (
    shoot_closest_approach, demo_propagator_factory,
)


def test_converges_for_linear_propagator():
    prop = demo_propagator_factory(base_ca_km=4000, sensitivity_km_per_mps=100)
    r = shoot_closest_approach(
        initial_dv=np.zeros(3),
        propagator=prop,
        target_ca_km=130.0,
        max_iter=5,
    )
    assert r.converged
    assert abs(r.final_ca_km - 130.0) < 5.0


def test_no_change_if_already_at_target():
    prop = demo_propagator_factory(base_ca_km=130)
    r = shoot_closest_approach(
        initial_dv=np.zeros(3), propagator=prop,
        target_ca_km=130.0, max_iter=5,
    )
    assert r.converged
    assert r.iterations == 0


def test_records_corrections():
    prop = demo_propagator_factory(base_ca_km=5000, sensitivity_km_per_mps=50)
    r = shoot_closest_approach(
        initial_dv=np.zeros(3), propagator=prop,
        target_ca_km=130.0, max_iter=20,
    )
    assert len(r.corrections) > 0


def test_non_converging_reports_false():
    # Zero-sensitivity propagator: Jacobian is zero → never converges
    prop = lambda dv: 5000.0
    r = shoot_closest_approach(
        initial_dv=np.zeros(3), propagator=prop,
        target_ca_km=130.0, max_iter=3,
    )
    assert not r.converged
