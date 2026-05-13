"""Tests for radiation damage models."""

from __future__ import annotations

from aria.genastra.core.models import ParticleType, RadiationEnvironment, RadiationType
from aria.genastra.radiation.damage_predictor import predict_heuristic
from aria.genastra.radiation.dose_response import (
    compute_dose_response_curve,
    compute_rbe,
    lnt_model,
    threshold_model,
)
from aria.genastra.radiation.environment import (
    iss_6_month,
    mars_transit,
    spe_event,
    validate_radiation_environment,
)
from aria.genastra.radiation.let_model import classify_damage_type, estimate_let


class TestDoseResponse:
    def test_lnt_zero_dose_zero_damage(self) -> None:
        assert lnt_model(0.0) == 0.0

    def test_lnt_monotonically_increasing(self) -> None:
        prev = 0.0
        for dose in [10, 50, 100, 500, 1000, 5000]:
            current = lnt_model(float(dose))
            assert current >= prev
            prev = current

    def test_lnt_asymptotic_to_one(self) -> None:
        # With protein-level α=5e-5, need very high dose to approach 1.0
        # At 1,000,000 mGy (1000 Gy) with RBE=1.5: P ≈ 1-exp(-5e-5 × 1e6 × 1.5) ≈ 1.0
        assert lnt_model(1_000_000.0) > 0.99

    def test_threshold_below_threshold_zero(self) -> None:
        assert threshold_model(30.0, threshold_mgy=50.0) == 0.0

    def test_threshold_above_threshold_nonzero(self) -> None:
        assert threshold_model(100.0, threshold_mgy=50.0) > 0.0

    def test_threshold_at_threshold_zero(self) -> None:
        # Exactly at threshold, effective dose = 0
        result = threshold_model(50.0, threshold_mgy=50.0)
        assert result == 0.0

    def test_rbe_proton_reasonable(self) -> None:
        rbe = compute_rbe(1.0, "proton")
        assert 1.0 <= rbe <= 5.0

    def test_rbe_hze_ion_high(self) -> None:
        rbe = compute_rbe(150.0, "hze_ion")
        assert rbe > 10.0

    def test_rbe_no_let_uses_default(self) -> None:
        rbe = compute_rbe(None, "proton")
        assert rbe == 1.5  # default for protons

    def test_dose_response_curve_length(self) -> None:
        curve = compute_dose_response_curve("lnt", n_points=100)
        assert len(curve.doses) == 100
        assert len(curve.probabilities) == 100


class TestRadiationEnvironments:
    def test_iss_6_month(self) -> None:
        env = iss_6_month()
        assert env.dose_mgy == 90.0
        assert env.duration_days == 180.0

    def test_mars_transit(self) -> None:
        env = mars_transit()
        assert env.radiation_type == RadiationType.GCR

    def test_spe_event(self) -> None:
        env = spe_event()
        assert env.radiation_type == RadiationType.SPE
        assert env.dose_mgy > 1000  # Very high dose

    def test_validate_normal_env(self) -> None:
        env = iss_6_month()
        warnings = validate_radiation_environment(env)
        assert isinstance(warnings, list)

    def test_validate_high_dose_rate_warning(self) -> None:
        env = RadiationEnvironment(
            radiation_type=RadiationType.GCR,
            dose_mgy=100.0,
            dose_rate_mgy_per_day=10.0,  # Too high for GCR
            particle_type=ParticleType.MIXED,
        )
        warnings = validate_radiation_environment(env)
        assert len(warnings) > 0


class TestLETModel:
    def test_classify_low_let(self) -> None:
        assert classify_damage_type(1.0) == "isolated"

    def test_classify_medium_let(self) -> None:
        assert classify_damage_type(50.0) == "mixed"

    def test_classify_high_let(self) -> None:
        assert classify_damage_type(150.0) == "clustered"

    def test_estimate_let_proton(self) -> None:
        let = estimate_let("proton")
        assert 0.5 < let < 10.0

    def test_estimate_let_iron(self) -> None:
        let = estimate_let("iron")
        assert let > 100.0


class TestHeuristicPredictor:
    def test_predict_returns_scores(self) -> None:
        env = iss_6_month()
        result = predict_heuristic("MKTLCCSHLVEALYLVCGERGFFYTPKT", env)
        assert len(result.vulnerability_scores) == 28
        assert 0.0 <= result.overall_damage_score <= 1.0

    def test_cysteine_more_vulnerable(self) -> None:
        env = iss_6_month()
        # Sequence with many cysteines should have higher damage
        cys_result = predict_heuristic("CCCCCCCCCC", env)
        ala_result = predict_heuristic("AAAAAAAAAA", env)
        assert cys_result.overall_damage_score > ala_result.overall_damage_score

    def test_higher_dose_higher_damage(self) -> None:
        low_dose = RadiationEnvironment(
            radiation_type=RadiationType.GCR,
            dose_mgy=10.0,
            dose_rate_mgy_per_day=0.5,
            particle_type=ParticleType.MIXED,
        )
        high_dose = RadiationEnvironment(
            radiation_type=RadiationType.GCR,
            dose_mgy=5000.0,
            dose_rate_mgy_per_day=0.5,
            particle_type=ParticleType.MIXED,
        )
        low_result = predict_heuristic("MKTLCCSHLVEAL", low_dose)
        high_result = predict_heuristic("MKTLCCSHLVEAL", high_dose)
        assert high_result.overall_damage_score >= low_result.overall_damage_score

    def test_disclaimer_present(self) -> None:
        env = iss_6_month()
        result = predict_heuristic("MKTL", env)
        assert "RESEARCH USE ONLY" in result.disclaimer

    def test_sasa_weighted_field_exists(self) -> None:
        env = iss_6_month()
        result = predict_heuristic("MKTL", env)
        assert hasattr(result, "sasa_weighted")
