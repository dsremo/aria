"""EVA radiation dose tests (SPE + GCR)."""
from __future__ import annotations
import pytest
from aria.simulation.eva_radiation import (
    SolarEvent, AUGUST_1972_SPE, spe_flux_profile,
    simulate_eva_dose, shielding_attenuation, habitat_safe_haven_dose,
)


def test_quiet_6h_eva_well_under_limit():
    r = simulate_eva_dose(eva_duration_h=6.0, event=None, dose_limit_msv=50.0)
    assert not r.abort_recommended
    assert r.total_dose_msv < 1.0   # GCR alone gives < 1 mSv in 6 h


def test_august_1972_unshielded_eva_aborts():
    """An astronaut EVAing during the August 1972 SPE peak would exceed 50 mSv."""
    r = simulate_eva_dose(eva_duration_h=4.0,
                          event=AUGUST_1972_SPE,
                          start_offset_h=0,   # starts at peak
                          shield_g_cm2=0.3,
                          dose_limit_msv=50.0)
    assert r.abort_recommended
    assert r.total_dose_msv > 50


def test_shielding_reduces_dose():
    """Heavier shielding → lower dose."""
    r_light = simulate_eva_dose(eva_duration_h=4.0, event=AUGUST_1972_SPE,
                                shield_g_cm2=0.3)
    r_heavy = simulate_eva_dose(eva_duration_h=4.0, event=AUGUST_1972_SPE,
                                shield_g_cm2=10.0)
    assert r_heavy.total_dose_msv < r_light.total_dose_msv


def test_safe_haven_1m_regolith():
    """1 m regolith shelter keeps an August 1972-class SPE dose acceptable."""
    dose = habitat_safe_haven_dose(AUGUST_1972_SPE, shelter_g_cm2=150.0)
    assert dose < 100     # < 100 mSv even for the largest historical event


def test_spe_profile_peaks_and_decays():
    flux_peak = spe_flux_profile(AUGUST_1972_SPE,
                                  AUGUST_1972_SPE.rise_time_hours)
    flux_before = spe_flux_profile(AUGUST_1972_SPE, 0)
    flux_after = spe_flux_profile(AUGUST_1972_SPE,
                                   AUGUST_1972_SPE.rise_time_hours + 48)
    assert flux_before < flux_peak
    assert flux_after < flux_peak


def test_attenuation_monotone_in_shield():
    att1 = shielding_attenuation(1.0)
    att10 = shielding_attenuation(10.0)
    att100 = shielding_attenuation(100.0)
    assert 1 > att1 > att10 > att100 > 0


def test_zero_duration_zero_dose():
    r = simulate_eva_dose(eva_duration_h=0.0)
    assert r.total_dose_msv == 0
