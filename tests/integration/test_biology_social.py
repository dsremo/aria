"""Integration tests for biology, ecology, and social systems.

Tests all six subsystems from the 100-Scientist Interrogation P1 gaps:
  - Biofilm & water quality
  - Fungal & pollinator ecosystem
  - Language & culture drift
  - Material degradation (Weibull)
  - Circadian & lighting
  - Noise & vibration
  - Orchestrator cross-system integration

35+ tests.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.biology_social import (
    BiofilmWaterSimulator,
    BiologySocialOrchestrator,
    CircadianLightingSimulator,
    FungalPollinatorSimulator,
    LanguageCultureSimulator,
    NoiseVibrationSimulator,
    WeibullComponent,
    WeibullDegradationSimulator,
)


# ── BIOFILM & WATER QUALITY ──

class TestBiofilmWater:

    def test_initial_state_clean(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        s = sim.state
        assert s.ph == 7.0
        assert s.biofilm_thickness_um == 0.0
        assert s.uv_lamp_health == 1.0
        assert s.pipe_corrosion_pct == 0.0

    def test_biofilm_grows_over_time(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        for y in range(1, 11):
            sim.simulate_year(float(y))
        assert sim.state.biofilm_thickness_um > 0

    def test_uv_lamp_degrades(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        for y in range(1, 21):
            sim.simulate_year(float(y))
        assert sim.state.uv_lamp_health < 0.5
        assert sim.state.uv_lamp_age_years == 20

    def test_chemical_flush_reduces_biofilm(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        for y in range(1, 5):
            sim.simulate_year(float(y))
        biofilm_at_4 = sim.state.biofilm_thickness_um
        assert biofilm_at_4 > 0
        events = sim.simulate_year(5.0)
        flush_events = [e for e in events if "flush" in e.get("message", "").lower()]
        assert len(flush_events) == 1
        assert sim.state.biofilm_thickness_um < biofilm_at_4

    def test_water_quality_index_range(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        sim.simulate_year(1.0)
        assert 0 <= sim.state.water_quality_index <= 100

    def test_pipe_corrosion_accumulates(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.pipe_corrosion_pct > 2.0

    def test_heavy_metals_increase_with_corrosion(self) -> None:
        sim = BiofilmWaterSimulator(seed=42)
        initial = sim.state.heavy_metals_ppb
        for y in range(1, 30):
            sim.simulate_year(float(y))
        assert sim.state.heavy_metals_ppb > initial


# ── FUNGAL & POLLINATOR ECOSYSTEM ──

class TestFungalPollinator:

    def test_initial_healthy_ecosystem(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        assert sim.soil.mycorrhizal_coverage == 0.95
        assert sim.pollinators.hive_count == 10
        assert sim.pollinators.total_bees == 500_000

    def test_soil_diversity_declines(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.soil.microbiome_index < 0.8

    def test_mycorrhizal_tracks_fungal_diversity(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        limit = sim.soil.soil_fungi_diversity * 0.95 + 0.01
        assert sim.soil.mycorrhizal_coverage <= limit

    def test_varroa_spreads(self) -> None:
        sim = FungalPollinatorSimulator(seed=10)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.pollinators.varroa_prevalence > 0

    def test_pollinator_collapse_reduces_yield(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        for i in range(10):
            sim.pollinators.hive_health[i] = 0.1
        sim.pollinators.varroa_prevalence = 0.9
        sim.simulate_year(50.0)
        assert sim.pollinators.crop_yield_modifier < 0.8

    def test_fungal_disease_grows(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.soil.powdery_mildew_severity > 0
        assert sim.soil.black_spot_severity > 0

    def test_phosphorus_depends_on_mycorrhizae(self) -> None:
        sim = FungalPollinatorSimulator(seed=42)
        sim.soil.soil_fungi_diversity = 0.3
        sim.simulate_year(1.0)
        assert sim.soil.phosphorus_uptake_efficiency < 0.5


# ── LANGUAGE & CULTURE DRIFT ──

class TestLanguageCulture:

    def test_initial_no_divergence(self) -> None:
        sim = LanguageCultureSimulator(seed=42)
        assert sim.state.vocab_divergence_pct == 0.0
        assert sim.state.dialect_count == 1

    def test_swadesh_drift_per_generation(self) -> None:
        """Swadesh (1952): ~0.4% core vocab change per 25-year generation."""
        sim = LanguageCultureSimulator(seed=42)
        for y in range(1, 26):
            sim.simulate_year(float(y))
        assert 0.1 < sim.state.vocab_divergence_pct < 1.0

    def test_8pct_at_500_years(self) -> None:
        """500 years ≈ 20 generations → ~8% divergence (Swadesh rate)."""
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(500.0)
        assert 5 < sim.state.vocab_divergence_pct < 12

    def test_technical_drifts_slower(self) -> None:
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(250.0)
        assert sim.state.technical_divergence_pct < sim.state.casual_divergence_pct

    def test_aria_accuracy_degrades(self) -> None:
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(500.0)
        assert sim.state.aria_translation_accuracy < 1.0
        assert sim.state.aria_translation_accuracy >= 0.5

    def test_manuals_need_updating(self) -> None:
        """At Swadesh rate, technical divergence crosses 5% threshold ~1040 yr."""
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(1200.0)
        assert sim.state.manuals_needing_update > 0

    def test_dialect_formation(self) -> None:
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(500.0)
        assert sim.state.dialect_count >= 5

    def test_cultural_loss_asymptotic(self) -> None:
        sim = LanguageCultureSimulator(seed=42)
        sim.simulate_year(1000.0)
        assert sim.state.cultural_fragments_lost > 0.9
        assert sim.state.cultural_fragments_lost <= 1.0


# ── WEIBULL MATERIAL DEGRADATION ──

class TestWeibullDegradation:

    def test_weibull_cdf_at_eta(self) -> None:
        comp = WeibullComponent(
            name="test", category="mechanical",
            beta=2.5, eta_years=25,
        )
        comp.age_years = 25
        sim = WeibullDegradationSimulator(seed=42)
        cdf = sim._failure_cdf(comp)
        assert abs(cdf - 0.6321) < 0.01

    def test_mtbf_formula(self) -> None:
        comp = WeibullComponent(
            name="test", category="electronics",
            beta=0.8, eta_years=15,
        )
        expected = 15 * math.gamma(1 + 1 / 0.8)
        assert abs(comp.mtbf_years - expected) < 0.1

    def test_electronics_infant_mortality(self) -> None:
        comp = WeibullComponent(
            name="test", category="electronics",
            beta=0.8, eta_years=15,
        )
        assert comp.beta < 1.0

    def test_structural_wearout(self) -> None:
        comp = WeibullComponent(
            name="test", category="structural",
            beta=3.5, eta_years=80,
        )
        assert comp.beta > 1.0

    def test_preventive_maintenance_occurs(self) -> None:
        sim = WeibullDegradationSimulator(seed=42)
        target = next(
            c for c in sim.components if c.category == "electronics"
        )
        threshold = target.next_maintenance_year
        for y in range(1, int(threshold) + 5):
            sim.simulate_year(float(y))
        assert target.times_replaced >= 1 or target.failed

    def test_maintenance_schedule_complete(self) -> None:
        sim = WeibullDegradationSimulator(seed=42)
        schedule = sim.get_maintenance_schedule()
        assert len(schedule) == 15
        for entry in schedule:
            assert "mtbf_years" in entry
            assert "maintenance_interval_years" in entry
            assert entry["mtbf_years"] > 0

    def test_bathtub_curve_hazard(self) -> None:
        sim = WeibullDegradationSimulator(seed=42)
        elec = WeibullComponent(
            name="e", category="electronics",
            beta=0.8, eta_years=15,
        )
        mech = WeibullComponent(
            name="m", category="mechanical",
            beta=2.5, eta_years=25,
        )
        elec.age_years = 1
        h1 = sim._hazard_rate(elec)
        elec.age_years = 10
        h10 = sim._hazard_rate(elec)
        assert h10 < h1

        mech.age_years = 1
        h1m = sim._hazard_rate(mech)
        mech.age_years = 20
        h20m = sim._hazard_rate(mech)
        assert h20m > h1m


# ── CIRCADIAN & LIGHTING ──

class TestCircadianLighting:

    def test_initial_healthy(self) -> None:
        sim = CircadianLightingSimulator(seed=42)
        s = sim.state
        assert s.habitat_led_health == 1.0
        assert s.grow_led_health == 1.0
        assert s.spectrum_cct_k == 5000.0

    def test_led_degrades(self) -> None:
        sim = CircadianLightingSimulator(seed=42)
        for y in range(1, 26):
            sim.simulate_year(float(y))
        # Grow LEDs degrade faster (more hours, more heat)
        assert sim.state.grow_led_health < sim.state.habitat_led_health

    def test_color_shift(self) -> None:
        sim = CircadianLightingSimulator(seed=42)
        for y in range(1, 31):
            sim.simulate_year(float(y))
        assert sim.state.color_shift_nm > 5
        assert sim.state.spectrum_cct_k < 5000

    def test_sad_rises(self) -> None:
        sim = CircadianLightingSimulator(seed=42)
        for y in range(1, 61):
            sim.simulate_year(float(y))
        assert sim.state.sad_prevalence_pct > 2.0

    def test_grow_lights_separate(self) -> None:
        sim = CircadianLightingSimulator(seed=42)
        assert sim.state.grow_light_hours == 18.0
        assert sim.state.day_hours == 12.0


# ── NOISE & VIBRATION ──

class TestNoiseVibration:

    def test_initial_within_limits(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.living_quarter_db < 65

    def test_db_combination(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        result = sim._combine_db([60.0, 60.0])
        assert abs(result - 63.01) < 0.1

    def test_dampers_degrade(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        for y in range(1, 51):
            sim.simulate_year(float(y))
        assert sim.state.damper_health < 0.8

    def test_hearing_loss_accumulates(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        for y in range(1, 101):
            sim.simulate_year(float(y))
        assert sim.state.crew_avg_hearing_loss_db > 0

    def test_quiet_zone_quieter(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.quiet_zone_db < sim.state.living_quarter_db

    def test_work_area_louder(self) -> None:
        sim = NoiseVibrationSimulator(seed=42)
        sim.simulate_year(1.0)
        assert sim.state.work_area_db > sim.state.living_quarter_db


# ── ORCHESTRATOR ──

class TestOrchestrator:

    def test_runs_all(self) -> None:
        orch = BiologySocialOrchestrator(seed=42)
        events = orch.simulate_year(1.0)
        assert isinstance(events, list)

    def test_50_year_run(self) -> None:
        orch = BiologySocialOrchestrator(seed=42)
        all_events = []
        for y in range(1, 51):
            all_events.extend(orch.simulate_year(float(y)))
        assert len(all_events) > 0
        subsystems = {e.get("subsystem") for e in all_events}
        assert len(subsystems) >= 2

    def test_crop_yield_degrades(self) -> None:
        orch = BiologySocialOrchestrator(seed=42)
        initial = orch.get_crop_yield_modifier()
        for y in range(1, 51):
            orch.simulate_year(float(y))
        assert orch.get_crop_yield_modifier() <= initial

    def test_1000_year_smoke(self) -> None:
        orch = BiologySocialOrchestrator(seed=42)
        for y in range(1, 1001):
            events = orch.simulate_year(float(y))
            for e in events:
                assert "year" in e
                assert "severity" in e
                assert "message" in e
                assert "subsystem" in e
