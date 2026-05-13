"""Lunar surface thermal cycling tests."""
from __future__ import annotations
import pytest
from aria.simulation.lunar_surface_thermal import (
    LunarThermalSite, surface_temperature, diurnal_cycle,
    EquipmentThermalConfig, simulate_equipment,
    thermal_cycle_fatigue_cycles, SYNODIC_MONTH_D,
)


def test_equatorial_cycle_matches_apollo_envelope():
    """Apollo 17 recorded ~100 K night to ~380 K day at Taurus-Littrow."""
    cycle = diurnal_cycle(LunarThermalSite(), n_samples=60)
    tmin = min(s.surface_temp_k for s in cycle)
    tmax = max(s.surface_temp_k for s in cycle)
    assert 90 < tmin < 200        # night floor (physical bound)
    assert 300 < tmax < 395       # day peak
    # Swing should be a substantial fraction of the Apollo 279 K range
    assert tmax - tmin > 150


def test_polar_site_much_flatter():
    """Polar latitudes see more stable temperature (permanent shadow / grazing sun)."""
    eq_cycle = diurnal_cycle(LunarThermalSite(latitude_deg=0), n_samples=30)
    polar_cycle = diurnal_cycle(LunarThermalSite(latitude_deg=85), n_samples=30)
    eq_swing = max(s.surface_temp_k for s in eq_cycle) - min(s.surface_temp_k for s in eq_cycle)
    polar_swing = max(s.surface_temp_k for s in polar_cycle) - min(s.surface_temp_k for s in polar_cycle)
    assert polar_swing < eq_swing


def test_equipment_temp_bounded():
    cfg = EquipmentThermalConfig()
    history = simulate_equipment(cfg, LunarThermalSite(), n_cycles=1, dt_s=1800)
    temps = [s.equipment_temp_k for s in history]
    assert all(100 < t < 500 for t in temps)


def test_fatigue_damage_positive_for_real_delta_t():
    damage = thermal_cycle_fatigue_cycles(delta_t_k=250, n_cycles=120)
    assert damage > 0
    # Very large ΔT + many cycles should eventually exceed damage=1
    damage_big = thermal_cycle_fatigue_cycles(delta_t_k=400, n_cycles=100_000)
    assert damage_big > damage


def test_zero_delta_t_no_damage():
    assert thermal_cycle_fatigue_cycles(delta_t_k=0, n_cycles=1000) == 0


def test_sun_elevation_periodic():
    """Solar elevation must repeat on a synodic-month period."""
    site = LunarThermalSite()
    s1 = surface_temperature(0.0, site)
    s2 = surface_temperature(SYNODIC_MONTH_D * 24, site)
    assert abs(s1.sun_elevation_deg - s2.sun_elevation_deg) < 1.0
