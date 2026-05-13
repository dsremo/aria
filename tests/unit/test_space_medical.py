"""Tests for space_medical_rates module and its integration with medical_robotics.

Validates empirical incidence rates from Crucian et al. 2016 and
correct wiring into the MedicalEmergencySimulator.
"""

from __future__ import annotations

import math
import pytest

from aria.simulation.space_medical_rates import (
    ALL_CAUSE_RATE,
    ALLERGIC_HYPERSENSITIVITY_RATE,
    BURN_RATE,
    CARDIAC_EVENT_RATE,
    DENTAL_EVENT_RATE,
    HERPES_VIRUS_RATE,
    ISS_TOTAL_IMMUNE_EVENT_RATE,
    MSK_INJURY_RATE,
    OPHTHALMOLOGICAL_RATE,
    PSYCHIATRIC_RATE,
    SKIN_RASH_HYPERSENSITIVITY_RATE,
    TRAUMA_RATE,
    UPPER_RESPIRATORY_RATE,
    URINARY_TRACT_INFECTION_RATE,
    INCIDENCE_REGISTRY,
    MedicalCondition,
    get_all_rates,
    get_event_distribution_from_empirical,
    get_incidence_rate,
    get_record,
)
from aria.simulation.medical_robotics import (
    MedicalEmergencySimulator,
    MedicalEventType,
)


class TestCrucianRates:
    """Validate rates extracted from Crucian et al. 2016, Table 1."""

    def test_skin_rash_is_most_common(self):
        """Skin rash/hypersensitivity was the most reported event (23/70)."""
        assert SKIN_RASH_HYPERSENSITIVITY_RATE > UPPER_RESPIRATORY_RATE
        assert SKIN_RASH_HYPERSENSITIVITY_RATE == pytest.approx(1.12, abs=0.01)

    def test_upper_respiratory_second_most_common(self):
        """Prolonged congestion was second most common (20/70)."""
        assert UPPER_RESPIRATORY_RATE == pytest.approx(0.97, abs=0.01)

    def test_total_immune_rate(self):
        """Total immune-related incidence: 3.40 events/flight-year."""
        assert ISS_TOTAL_IMMUNE_EVENT_RATE == pytest.approx(3.40, abs=0.01)

    def test_crucian_rates_sum_to_total(self):
        """The nine Crucian Table 1 categories should sum to ~3.40."""
        crucian_sum = (
            ALLERGIC_HYPERSENSITIVITY_RATE
            + UPPER_RESPIRATORY_RATE
            + HERPES_VIRUS_RATE
            + 0.29  # EAR_RELATED_RATE
            + 0.05  # PHARYNGITIS_RATE
            + 0.29  # SKIN_INFECTION_RATE
            + SKIN_RASH_HYPERSENSITIVITY_RATE
            + URINARY_TRACT_INFECTION_RATE
            + 0.19  # OTHER_INFECTION_RATE
        )
        assert crucian_sum == pytest.approx(3.40, abs=0.15)

    def test_uti_rate_from_paper(self):
        """UTI rate: 2 events / 20.57 FY = ~0.10."""
        assert URINARY_TRACT_INFECTION_RATE == pytest.approx(0.10, abs=0.01)

    def test_herpes_rate_from_paper(self):
        """Herpes virus (cold sores): 6 events / 20.57 FY = ~0.29."""
        assert HERPES_VIRUS_RATE == pytest.approx(0.29, abs=0.01)


class TestBroaderRates:
    """Validate broader medical rates from NASA/analog literature."""

    def test_cardiac_rate_reasonable(self):
        """Cardiac events should be rare (~3 per 1000 person-years)."""
        assert 0.001 <= CARDIAC_EVENT_RATE <= 0.01

    def test_dental_rate(self):
        """Dental events ~0.2/person/year (Barratt & Pool 2008)."""
        assert DENTAL_EVENT_RATE == pytest.approx(0.20, abs=0.01)

    def test_psychiatric_rate(self):
        """Psychiatric: ~3 per 100 person-years (Kanas 2015)."""
        assert PSYCHIATRIC_RATE == pytest.approx(0.03, abs=0.005)

    def test_msk_most_common_broader(self):
        """MSK injuries should be the most common broader category."""
        assert MSK_INJURY_RATE > DENTAL_EVENT_RATE
        assert MSK_INJURY_RATE > TRAUMA_RATE

    def test_all_rates_positive(self):
        """Every registered rate must be > 0."""
        for mc, rec in INCIDENCE_REGISTRY.items():
            assert rec.rate_per_person_year > 0, f"{mc.name} has non-positive rate"


class TestGetIncidenceRate:
    """Test the get_incidence_rate lookup function."""

    def test_exact_match(self):
        """Exact enum name match should work."""
        rate = get_incidence_rate("CARDIAC", crew_size=1000)
        assert rate == pytest.approx(CARDIAC_EVENT_RATE * 1000)

    def test_case_insensitive(self):
        """Lookup should be case-insensitive."""
        rate = get_incidence_rate("cardiac", crew_size=1)
        assert rate == pytest.approx(CARDIAC_EVENT_RATE)

    def test_partial_match(self):
        """Partial name match should work."""
        rate = get_incidence_rate("dental", crew_size=100)
        assert rate == pytest.approx(DENTAL_EVENT_RATE * 100)

    def test_unknown_condition_raises(self):
        """Unknown condition should raise KeyError."""
        with pytest.raises(KeyError, match="Unknown condition"):
            get_incidence_rate("nonexistent_disease")

    def test_crew_scaling(self):
        """Rate should scale linearly with crew size."""
        rate_1 = get_incidence_rate("SKIN_RASH", crew_size=1)
        rate_100 = get_incidence_rate("SKIN_RASH", crew_size=100)
        assert rate_100 == pytest.approx(rate_1 * 100)

    def test_default_crew_size(self):
        """Default crew size is 1000."""
        rate = get_incidence_rate("TRAUMA")
        assert rate == pytest.approx(TRAUMA_RATE * 1000)


class TestGetAllRates:
    """Test the get_all_rates function."""

    def test_returns_all_conditions(self):
        """Should return a rate for every registered condition."""
        rates = get_all_rates(crew_size=1)
        assert len(rates) == len(MedicalCondition)

    def test_per_person_rates(self):
        """With crew_size=1, rates should match individual rates."""
        rates = get_all_rates(crew_size=1)
        assert rates["CARDIAC"] == pytest.approx(CARDIAC_EVENT_RATE)
        assert rates["DENTAL"] == pytest.approx(DENTAL_EVENT_RATE)


class TestGetRecord:
    """Test the get_record lookup function."""

    def test_record_has_source(self):
        """Every record should have a non-empty source."""
        rec = get_record("SKIN_RASH")
        assert "Crucian" in rec.source

    def test_crucian_records_have_event_counts(self):
        """Crucian Table 1 records should have total_events."""
        rec = get_record("HERPES_VIRUS")
        assert rec.total_events == 6
        assert rec.total_flight_years == pytest.approx(20.57)

    def test_unknown_raises(self):
        """Unknown condition should raise KeyError."""
        with pytest.raises(KeyError):
            get_record("fake_condition")


class TestEmpiricalDistribution:
    """Test the event distribution derived from empirical data."""

    def test_distribution_sums_to_one(self):
        """Normalized distribution must sum to 1.0."""
        dist = get_event_distribution_from_empirical()
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-6)

    def test_infection_dominates(self):
        """Infection should be the largest category (Crucian data)."""
        dist = get_event_distribution_from_empirical()
        assert dist["infection"] > dist["dental"]
        # Infection (intervention-requiring subset) should be substantial
        # but not overwhelming after filtering to notable events only.
        assert dist["infection"] > 0.3

    def test_all_event_types_present(self):
        """All 10 MedicalEventType values should have a weight."""
        dist = get_event_distribution_from_empirical()
        expected_keys = {
            "trauma", "dental", "infection", "psychological", "burn",
            "cardiac", "radiation_chronic", "radiation_acute",
            "childbirth", "surgical",
        }
        assert set(dist.keys()) == expected_keys

    def test_all_weights_positive(self):
        """Every weight must be > 0."""
        dist = get_event_distribution_from_empirical()
        for k, v in dist.items():
            assert v > 0, f"{k} has non-positive weight"


class TestMedicalRoboticsIntegration:
    """Test that medical_robotics.py correctly uses empirical rates."""

    def test_event_distribution_uses_empirical(self):
        """MedicalEmergencySimulator should use empirical distribution."""
        sim = MedicalEmergencySimulator(crew_size=100, seed=42)
        dist = sim.EVENT_DISTRIBUTION
        empirical = get_event_distribution_from_empirical()

        # Infection weight should match empirical
        infection_weight = dist[MedicalEventType.INFECTION]
        assert infection_weight == pytest.approx(
            empirical["infection"], abs=1e-6
        )

    def test_distribution_sums_to_one(self):
        """Simulator's distribution must sum to 1.0."""
        sim = MedicalEmergencySimulator(crew_size=100, seed=42)
        total = sum(sim.EVENT_DISTRIBUTION.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_simulator_runs_without_error(self):
        """Basic smoke test: simulate_year should not crash."""
        sim = MedicalEmergencySimulator(crew_size=100, seed=42)
        events = sim.simulate_year(mission_year=1.0)
        assert isinstance(events, list)

    def test_psych_rate_from_empirical(self):
        """PSYCH_EMERGENCY_RATE_PER_100_YR should be ~3.0."""
        from aria.simulation.medical_robotics import PSYCH_EMERGENCY_RATE_PER_100_YR
        assert PSYCH_EMERGENCY_RATE_PER_100_YR == pytest.approx(
            PSYCHIATRIC_RATE * 100, abs=0.1
        )
