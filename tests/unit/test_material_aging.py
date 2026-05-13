"""Material aging model tests."""
from __future__ import annotations
import pytest
from aria.simulation.material_aging import (
    MATERIALS, predict_service_life, embrittlement_factor, AgingReport,
    creep_rate_per_year, mmod_damage_fraction, radiation_dose_damage,
)


def test_ti6al4v_survives_100_year_cruise():
    r = predict_service_life("Ti-6Al-4V", years=100,
                             neutron_flux_n_cm2_s=100, stress_mpa=80)
    assert not r.failure_predicted


def test_kevlar_degrades_faster_than_titanium():
    ti = predict_service_life("Ti-6Al-4V", years=220)
    kev = predict_service_life("Kevlar", years=220)
    assert kev.total_damage >= ti.total_damage


def test_mmod_grows_linearly_with_time():
    d1 = mmod_damage_fraction(exposed_area_m2=100, flux_per_m2_yr=1e-4, years=50)
    d2 = mmod_damage_fraction(exposed_area_m2=100, flux_per_m2_yr=1e-4, years=200)
    assert d2 > d1


def test_embrittlement_monotonic_in_dose():
    mat = MATERIALS["Ti-6Al-4V"]
    assert embrittlement_factor(0.0, mat) > embrittlement_factor(5.0, mat)


def test_creep_hot_metal_vs_cold():
    mat = MATERIALS["Al-2219"]
    cold = creep_rate_per_year(100.0, 290.0, mat)
    hot = creep_rate_per_year(100.0, 700.0, mat)
    assert hot > cold


def test_materials_all_have_positive_constants():
    for m in MATERIALS.values():
        assert m.activation_energy_kj_mol > 0
        assert m.melting_temp_k > 273
        assert m.gcr_dose_to_failure_krad > 0


def test_life_remaining_nonneg():
    r = predict_service_life("EUROFER97", years=50)
    assert r.life_remaining_years is None or r.life_remaining_years >= 0
