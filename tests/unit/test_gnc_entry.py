"""Tests for gnc_entry.py — GNC entry corridor probability analysis.

Coverage:
  - Navigation error budget: RSS combination, Apollo/modern values
  - Corridor probability: analytical CDF, margins, edge cases
  - Monte Carlo: sampling, corridor classification, peak-g/heat statistics
  - Physical consistency: tighter nav → higher P(safe), wider corridor → safer

References:
  NASA SP-287 (1971) §6 — Apollo GNC
  NASA/TM-2011-217144 §4 — Orion GN&C
"""

import math
import numpy as np
import pytest

from aria.simulation.gnc_entry import (
    CORRIDOR_NOMINAL_DEG, CORRIDOR_SHALLOW_DEG, CORRIDOR_STEEP_DEG,
    APOLLO_NAV_SIGMA_DEG, MODERN_NAV_SIGMA_DEG,
    NavigationErrorBudget, CorridorAnalysis, MonteCarloResult,
    navigation_error_budget, corridor_probability,
    monte_carlo_entry, apollo_gnc_analysis, artemis_gnc_analysis,
)


# ═══════════════════════════════════════════════════════════════════
#  1. NAVIGATION ERROR BUDGET
# ═══════════════════════════════════════════════════════════════════

class TestNavigationErrorBudget:

    def test_rss_combination(self):
        """Total sigma should be RSS of components."""
        b = navigation_error_budget(0.10, 0.03, 0.07)
        expected = math.sqrt(0.10**2 + 0.03**2 + 0.07**2)
        assert b.total_sigma_deg == pytest.approx(expected, rel=1e-9)

    def test_three_sigma(self):
        b = navigation_error_budget(0.10, 0.03, 0.07)
        assert b.three_sigma_deg == pytest.approx(3.0 * b.total_sigma_deg)

    def test_apollo_sigma_range(self):
        """Apollo total σ should be ~0.12° (NASA SP-287)."""
        b = navigation_error_budget(APOLLO_NAV_SIGMA_DEG, 0.03, 0.07)
        assert 0.05 < b.total_sigma_deg < 0.20

    def test_modern_tighter_than_apollo(self):
        """Modern nav should have smaller σ than Apollo."""
        apollo = navigation_error_budget(0.10, 0.03, 0.07)
        modern = navigation_error_budget(0.05, 0.02, 0.06)
        assert modern.total_sigma_deg < apollo.total_sigma_deg

    def test_returns_budget(self):
        b = navigation_error_budget()
        assert isinstance(b, NavigationErrorBudget)


# ═══════════════════════════════════════════════════════════════════
#  2. CORRIDOR PROBABILITY (ANALYTICAL)
# ═══════════════════════════════════════════════════════════════════

class TestCorridorProbability:

    def test_nominal_in_corridor(self):
        """With any reasonable σ, the nominal angle should be in the corridor."""
        c = corridor_probability(-6.5, 0.1)
        assert c.probability_in_corridor > 0.99

    def test_very_tight_nav_nearly_certain(self):
        """Very small σ → P(safe) ≈ 1.0."""
        c = corridor_probability(-6.5, 0.01)
        assert c.probability_in_corridor > 0.9999999

    def test_very_large_nav_uncertain(self):
        """Very large σ → P(safe) drops significantly."""
        c = corridor_probability(-6.5, 1.0)
        assert c.probability_in_corridor < 0.95

    def test_probabilities_sum_to_one(self):
        """P(skip) + P(overheat) + P(in corridor) = 1.0."""
        c = corridor_probability(-6.5, 0.5)
        total = c.probability_in_corridor + c.probability_skip_out + c.probability_overheat
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_symmetric_margins_at_center(self):
        """At corridor center (−6.5°), margins should be equal on both sides."""
        c = corridor_probability(-6.5, 0.1)
        assert c.margin_shallow_sigma == pytest.approx(c.margin_steep_sigma, rel=0.01)

    def test_off_center_asymmetric(self):
        """Off-center nominal → one margin is tighter than the other."""
        c = corridor_probability(-6.0, 0.1)
        assert c.margin_shallow_sigma != pytest.approx(c.margin_steep_sigma, rel=0.1)

    def test_corridor_width(self):
        """Corridor width should be 2.0° for default bounds."""
        c = corridor_probability(-6.5, 0.1)
        assert c.corridor_width_deg == pytest.approx(2.0)

    def test_returns_corridor_analysis(self):
        c = corridor_probability(-6.5, 0.1)
        assert isinstance(c, CorridorAnalysis)


# ═══════════════════════════════════════════════════════════════════
#  3. MONTE CARLO
# ═══════════════════════════════════════════════════════════════════

class TestMonteCarloEntry:

    def test_returns_result(self):
        r = monte_carlo_entry(n_samples=100)
        assert isinstance(r, MonteCarloResult)

    def test_correct_sample_count(self):
        r = monte_carlo_entry(n_samples=500)
        assert r.n_samples == 500
        assert len(r.angles_deg) == 500
        assert len(r.peak_decel_g) == 500

    def test_all_in_corridor_for_tight_nav(self):
        """With σ=0.01° and 1000 samples, all should be in corridor."""
        r = monte_carlo_entry(sigma_deg=0.01, n_samples=1000)
        assert r.fraction_in_corridor == 1.0

    def test_fractions_sum_to_one(self):
        r = monte_carlo_entry(sigma_deg=0.5, n_samples=1000)
        total = r.fraction_in_corridor + r.fraction_skip_out + r.fraction_overheat
        assert total == pytest.approx(1.0, abs=0.01)

    def test_peak_g_all_positive(self):
        r = monte_carlo_entry(n_samples=100)
        assert np.all(r.peak_decel_g > 0)

    def test_peak_heat_all_positive(self):
        r = monte_carlo_entry(n_samples=100)
        assert np.all(r.peak_heat_w_cm2 > 0)

    def test_reproducible_with_seed(self):
        r1 = monte_carlo_entry(seed=42, n_samples=100)
        r2 = monte_carlo_entry(seed=42, n_samples=100)
        assert np.allclose(r1.angles_deg, r2.angles_deg)

    def test_mean_angle_near_nominal(self):
        """Mean of sampled angles should be near the nominal angle."""
        r = monte_carlo_entry(n_samples=5000)
        assert np.mean(r.angles_deg) == pytest.approx(CORRIDOR_NOMINAL_DEG, abs=0.05)

    def test_mean_peak_g_near_nominal_g(self):
        """Mean peak-g should be near the nominal Apollo 6.9 g."""
        r = monte_carlo_entry(sigma_deg=0.08, n_samples=1000)
        assert r.peak_decel_g.mean() == pytest.approx(6.9, abs=0.5)


# ═══════════════════════════════════════════════════════════════════
#  4. MISSION PROFILES
# ═══════════════════════════════════════════════════════════════════

class TestMissionProfiles:

    def test_apollo_very_safe(self):
        """Apollo corridor probability should be > 0.999999."""
        c = apollo_gnc_analysis()
        assert c.probability_in_corridor > 0.999999

    def test_apollo_margin_high(self):
        """Apollo margin should be > 5σ."""
        c = apollo_gnc_analysis()
        assert c.min_margin_sigma > 5.0

    def test_artemis_even_safer(self):
        """Artemis (modern nav) should have higher margin than Apollo."""
        apollo = apollo_gnc_analysis()
        artemis = artemis_gnc_analysis()
        assert artemis.min_margin_sigma > apollo.min_margin_sigma

    def test_artemis_returns_corridor(self):
        c = artemis_gnc_analysis()
        assert isinstance(c, CorridorAnalysis)
