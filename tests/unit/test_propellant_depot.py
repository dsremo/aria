from __future__ import annotations
import pytest
from aria.simulation.propellant_depot import (
    CryoTank, boil_off_per_day, zbo_cryocooler_power_kw,
    simulate_storage, transfer_propellant,
)


def test_lh2_boils_faster_than_lox():
    t_lh2 = CryoTank("lh2", "LH2", 100_000, 5000)
    t_lox = CryoTank("lox", "LOX", 100_000, 5000)
    assert boil_off_per_day(t_lh2) > boil_off_per_day(t_lox)


def test_zbo_reduces_boiloff():
    passive = CryoTank("p", "LH2", 100_000, 5000, zbo_enabled=False)
    active = CryoTank("a", "LH2", 100_000, 5000, zbo_enabled=True)
    assert boil_off_per_day(active) < boil_off_per_day(passive)


def test_storage_depletes_monotonically():
    t = CryoTank("t", "LH2", 50_000, 3000, zbo_enabled=False)
    traj = simulate_storage(t, days=30)
    masses = [m for _, m in traj]
    assert all(m2 <= m1 for m1, m2 in zip(masses, masses[1:]))


def test_transfer_cannot_exceed_source():
    t = CryoTank("t", "LOX", 100, 10)
    r = transfer_propellant(t, dest_empty_mass_kg=0, desired_transfer_kg=500)
    assert r.mass_transferred_kg <= 100


def test_transfer_rate_positive():
    t = CryoTank("t", "LOX", 10_000, 500)
    r = transfer_propellant(t, dest_empty_mass_kg=0, desired_transfer_kg=5000)
    assert r.avg_flow_rate_kg_s > 0


def test_cryocooler_power_nonneg():
    t = CryoTank("t", "LH2", 100_000, 5000, zbo_enabled=True)
    assert zbo_cryocooler_power_kw(t) >= 0
