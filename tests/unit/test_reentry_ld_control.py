from __future__ import annotations
import pytest
from aria.simulation.reentry_ld_control import (
    EntryVehicle, simulate_reentry_ld, earth_density,
)


def test_orion_nominal_entry_decelerates():
    """60° bank rolls lift enough to prevent skip-out; vehicle decelerates
    below supersonic by end of the simulation."""
    r = simulate_reentry_ld(EntryVehicle(),
                             bank_schedule=lambda t, h: 60.0)
    # Must bleed off the 11 km/s entry speed significantly
    assert r.final_speed_mps < 200    # chute-deploy-worthy speed
    # Peak-g reached
    assert r.peak_g > 3


def test_peak_g_apollo_class():
    """Apollo return entry peak g ~6-7; Orion expected similar."""
    r = simulate_reentry_ld(EntryVehicle())
    assert 3 < r.peak_g < 15


def test_density_monotonic_with_altitude():
    assert earth_density(0) > earth_density(5000) > earth_density(20_000)


def test_bank_schedule_affects_crossrange():
    # Constant full-up bank (lift up) vs rolled bank
    r_up = simulate_reentry_ld(EntryVehicle(), bank_schedule=lambda t, h: 0.0)
    r_side = simulate_reentry_ld(EntryVehicle(), bank_schedule=lambda t, h: 45.0)
    # Different bank profiles should produce different crossrange outcomes
    assert r_up.crossrange_km != r_side.crossrange_km


def test_ballistic_heat_rate_nonzero():
    r = simulate_reentry_ld(EntryVehicle())
    assert r.peak_heat_rate_w_cm2 > 0
