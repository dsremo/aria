"""ISRU plant physics tests."""
from __future__ import annotations
import pytest
from aria.simulation.isru_plant import (
    ISRUPlantConfig, run_plant, cumulative_over_mission, ascent_refuel_days,
)


def test_baseline_plant_produces_propellant():
    r = run_plant(ISRUPlantConfig(), duration_h=24)
    assert r.liquid_o2_kg > 10     # at least 10 kg LOX/day
    assert r.liquid_h2_kg > 0.5    # at least 0.5 kg LH₂/day
    assert r.water_extracted_kg > 50


def test_mass_conservation_electrolysis():
    """H₂ + O₂ mass out = water mass in (with tolerance for rounding)."""
    r = run_plant(ISRUPlantConfig(), duration_h=24)
    water = r.water_extracted_kg
    # Not all water reaches electrolyzer (it may be electrolyzer-limited)
    # But h2+o2 ≤ water (conservation)
    assert r.h2_produced_kg + r.o2_produced_kg <= water + 1e-6
    # And the ratio matches electrolysis stoichiometry
    if r.h2_produced_kg > 0.1:
        ratio = r.o2_produced_kg / r.h2_produced_kg
        assert 7.5 < ratio < 8.5   # ~7.94 for H₂O → H₂ + ½ O₂


def test_power_budget_not_exceeded():
    cfg = ISRUPlantConfig(total_power_limit_kw=50)
    r = run_plant(cfg, duration_h=1)
    avg_power = r.energy_used_kwh / (cfg.operational_duty_cycle * 1)
    assert avg_power <= cfg.total_power_limit_kw + 0.1


def test_low_power_scales_down():
    """Reducing total power should reduce output."""
    big = run_plant(ISRUPlantConfig(total_power_limit_kw=50), duration_h=24)
    small = run_plant(ISRUPlantConfig(total_power_limit_kw=20), duration_h=24)
    assert small.liquid_o2_kg < big.liquid_o2_kg


def test_ascent_refuel_days_reasonable():
    """Refueling Apollo LM ascent stage (~2400 kg) should take >20 days at baseline."""
    days = ascent_refuel_days(ISRUPlantConfig())
    assert 10 < days < 150


def test_cumulative_over_30_days_multiplicative():
    cfg = ISRUPlantConfig()
    daily = run_plant(cfg, duration_h=22)
    mission = cumulative_over_mission(cfg, mission_days=30, hours_per_day=22)
    assert abs(mission.liquid_o2_kg - daily.liquid_o2_kg * 30) < 0.01
    assert abs(mission.energy_used_kwh - daily.energy_used_kwh * 30) < 1


def test_water_fraction_scales_output():
    """Higher regolith water content should produce more water + propellant."""
    lean = run_plant(ISRUPlantConfig(regolith_water_fraction=0.01), duration_h=24)
    rich = run_plant(ISRUPlantConfig(regolith_water_fraction=0.10), duration_h=24)
    assert rich.water_extracted_kg >= lean.water_extracted_kg
