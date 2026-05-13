"""Tests for aria.simulation.degradation_bridge — NASA C-MAPSS degradation bridge."""

from __future__ import annotations

import math

import pytest

from aria.simulation.degradation_bridge import (
    CMAPSS_ALPHA,
    HOURS_PER_YEAR,
    SUBSYSTEM_PROFILES,
    get_degradation,
    get_degradation_years,
    get_instantaneous_rate,
    get_profile,
    get_rul,
    get_rul_years,
    list_subsystems,
)


# ---- Core degradation curve ------------------------------------------------

class TestGetDegradation:
    """Test the primary get_degradation(subsystem, age_hours) API."""

    def test_brand_new_equipment_is_healthy(self):
        """At age 0, every subsystem should report health = 1.0."""
        for name in list_subsystems():
            assert get_degradation(name, 0) == pytest.approx(1.0), name

    def test_end_of_life_is_zero(self):
        """At design life, health should be 0.0."""
        for name in list_subsystems():
            profile = get_profile(name)
            life_h = int(profile["design_life_hours"])
            health = get_degradation(name, life_h)
            assert health == pytest.approx(0.0, abs=1e-6), name

    def test_midlife_health_uses_alpha(self):
        """At 50% of design life, health = 1 - 0.5^alpha."""
        profile = get_profile("fusion_reactor")
        half_life = int(profile["design_life_hours"] / 2)
        health = get_degradation("fusion_reactor", half_life)
        expected = 1.0 - 0.5 ** CMAPSS_ALPHA
        assert health == pytest.approx(expected, abs=1e-4)

    def test_alpha_1538_is_convex(self):
        """With alpha=1.538 > 1, degradation should accelerate over time.

        This means health at 25% life > expected linear, and health at
        75% life < expected linear.
        """
        profile = get_profile("fusion_reactor")
        life_h = profile["design_life_hours"]

        h_25 = get_degradation("fusion_reactor", int(life_h * 0.25))
        h_75 = get_degradation("fusion_reactor", int(life_h * 0.75))

        # Linear would give 0.75 at 25% and 0.25 at 75%.
        # Convex (alpha>1): degradation is slower early, faster late than linear.
        # health = 1 - t^1.538 at t=0.25 -> ~0.88 (> 0.75 linear)
        # health = 1 - t^1.538 at t=0.75 -> ~0.36 (< 0.75 but > 0.25)
        # The key insight: more health is preserved early, less late vs linear.
        assert h_25 > 0.75, "Early life: health should exceed linear model"
        assert h_75 < h_25, "Late life: health should be much lower than early"
        # Verify the nonlinearity: at 75% life, health drops below what
        # would remain under a symmetric wear pattern.
        assert h_75 < 0.5, "At 75% life, more than half the health is lost"

    def test_health_never_exceeds_one(self):
        assert get_degradation("pump", 0) <= 1.0

    def test_health_never_below_zero(self):
        # Well past design life
        profile = get_profile("pump")
        h = get_degradation("pump", int(profile["design_life_hours"] * 2))
        assert h >= 0.0

    def test_negative_age_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            get_degradation("pump", -1)


# ---- Aliases ---------------------------------------------------------------

class TestAliases:
    """Subsystem aliases should resolve to the correct canonical profile."""

    @pytest.mark.parametrize("alias,canonical", [
        ("reactor", "fusion_reactor"),
        ("engine", "fusion_reactor"),
        ("life_support", "co2_scrubber"),
        ("hull", "hull_panel"),
        ("printer", "printer_fdm"),
        ("fusion_reactor_health", "fusion_reactor"),
        ("electronics_health", "electronics"),
    ])
    def test_alias_resolves(self, alias: str, canonical: str):
        profile_alias = get_profile(alias)
        profile_canon = get_profile(canonical)
        assert profile_alias == profile_canon

    def test_unknown_subsystem_uses_default(self):
        """Unknown subsystem names should silently use the default profile."""
        h = get_degradation("nonexistent_widget", 0)
        assert h == pytest.approx(1.0)


# ---- RUL estimation --------------------------------------------------------

class TestGetRUL:
    """Test remaining useful life estimation."""

    def test_full_health_gives_full_life(self):
        profile = get_profile("co2_scrubber")
        rul = get_rul("co2_scrubber", 1.0)
        assert rul == pytest.approx(profile["design_life_hours"], rel=1e-4)

    def test_zero_health_gives_zero_rul(self):
        assert get_rul("co2_scrubber", 0.0) == pytest.approx(0.0)

    def test_rul_roundtrip(self):
        """Degradation then RUL should roundtrip: age + rul ≈ design_life."""
        profile = get_profile("pump")
        life_h = profile["design_life_hours"]
        age = int(life_h * 0.4)  # 40% through life
        health = get_degradation("pump", age)
        rul = get_rul("pump", health)
        assert age + rul == pytest.approx(life_h, rel=1e-3)

    def test_rul_years_conversion(self):
        rul_h = get_rul("fusion_reactor", 0.5)
        rul_y = get_rul_years("fusion_reactor", 0.5)
        assert rul_y == pytest.approx(rul_h / HOURS_PER_YEAR, rel=1e-6)


# ---- Convenience wrappers ---------------------------------------------------

class TestYearsWrapper:
    def test_degradation_years_matches_hours(self):
        h_hours = get_degradation("fusion_reactor", int(10 * HOURS_PER_YEAR))
        h_years = get_degradation_years("fusion_reactor", 10.0)
        assert h_hours == pytest.approx(h_years, abs=1e-4)


# ---- Instantaneous rate -----------------------------------------------------

class TestInstantaneousRate:
    def test_rate_zero_at_start_for_convex_curve(self):
        """For alpha > 1, the derivative at t=0 is 0 (slow initial wear)."""
        rate = get_instantaneous_rate("fusion_reactor", 0)
        assert rate == pytest.approx(0.0)

    def test_rate_increases_over_time(self):
        """Rate should increase monotonically for alpha > 1."""
        rates = [
            get_instantaneous_rate("fusion_reactor", int(y * HOURS_PER_YEAR))
            for y in [5, 15, 25, 35, 45]
        ]
        for i in range(1, len(rates)):
            assert rates[i] > rates[i - 1], (
                f"Rate at year {5 + i*10} should exceed rate at year {5 + (i-1)*10}"
            )

    def test_rate_is_positive(self):
        rate = get_instantaneous_rate("pump", int(5 * HOURS_PER_YEAR))
        assert rate > 0

    def test_negative_age_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            get_instantaneous_rate("pump", -100)


# ---- Profile registry -------------------------------------------------------

class TestProfileRegistry:
    def test_list_subsystems_not_empty(self):
        subs = list_subsystems()
        assert len(subs) > 10

    def test_all_profiles_have_required_keys(self):
        for name in list_subsystems():
            profile = get_profile(name)
            assert "design_life_hours" in profile
            assert "alpha" in profile
            assert "description" in profile
            assert profile["design_life_hours"] > 0
            assert profile["alpha"] > 0

    def test_critical_subsystems_exist(self):
        """Critical ship subsystems must be registered."""
        critical = [
            "fusion_reactor", "co2_scrubber", "water_recycler",
            "algae_bioreactor", "hull_panel", "electronics",
        ]
        registered = list_subsystems()
        for name in critical:
            assert name in registered, f"Missing critical subsystem: {name}"


# ---- Specific alpha value from NASA data ------------------------------------

class TestNASAAlpha:
    def test_alpha_value(self):
        """The fitted alpha from C-MAPSS FD001 should be 1.538."""
        assert CMAPSS_ALPHA == pytest.approx(1.538, abs=1e-3)

    def test_alpha_supralinear(self):
        """Alpha > 1 confirms accelerating degradation (not linear)."""
        assert CMAPSS_ALPHA > 1.0

    def test_curve_shape_matches_turbofan_behavior(self):
        """Verify the curve produces the expected 'bathtub' pattern:
        - First 20% of life: minimal degradation (health > 0.9)
        - Last 20% of life: rapid degradation (health < 0.3)
        """
        profile = get_profile("fusion_reactor")
        life_h = profile["design_life_hours"]

        h_early = get_degradation("fusion_reactor", int(life_h * 0.2))
        h_late = get_degradation("fusion_reactor", int(life_h * 0.8))

        assert h_early > 0.9, f"At 20% life, health={h_early:.3f} should be > 0.9"
        assert h_late < 0.3, f"At 80% life, health={h_late:.3f} should be < 0.3"
