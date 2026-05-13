"""Cabin fire model tests."""
from __future__ import annotations
import pytest
from aria.simulation.cabin_fire import (
    CabinAtmosphere, simulate_fire, ignition_probability,
)


def test_high_o2_atmosphere_ignites_more_easily():
    normal = CabinAtmosphere(o2_fraction=0.21)
    apollo1 = CabinAtmosphere(o2_fraction=1.00, total_pressure_kpa=115)
    p_n = ignition_probability(normal, heat_source_w=50)
    p_apollo = ignition_probability(apollo1, heat_source_w=50)
    assert p_apollo > p_n


def test_fire_consumes_oxygen():
    r = simulate_fire(CabinAtmosphere(), fuel_kg=0.5, suppression_after_s=300)
    # Oxygen should have dropped from 0.21
    assert r.final_o2_fraction < 0.21


def test_suppression_extinguishes_fire():
    r = simulate_fire(CabinAtmosphere(), fuel_kg=2.0, suppression_after_s=5,
                       suppression_type="co2_flood")
    assert r.extinguished


def test_co_rises_during_burn():
    r = simulate_fire(CabinAtmosphere(), fuel_kg=2.0, suppression_after_s=60)
    assert r.peak_co_ppm > 0


def test_temperature_rises_during_fire():
    r = simulate_fire(CabinAtmosphere(), fuel_kg=1.0, suppression_after_s=300)
    assert r.peak_temp_k > 295.0
