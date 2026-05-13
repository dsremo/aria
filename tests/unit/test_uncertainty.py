"""R43 — uncertainty tier tagging tests."""

from __future__ import annotations

import pytest

from aria.physics.uncertainty import (
    ConfidenceTier, Prediction, TierDQuotedError,
    forbid_d_quote, tag_prediction,
)


class TestTier:
    def test_speculative_only_for_c_d(self):
        assert ConfidenceTier.TIER_A.is_speculative is False
        assert ConfidenceTier.TIER_B.is_speculative is False
        assert ConfidenceTier.TIER_C.is_speculative is True
        assert ConfidenceTier.TIER_D.is_speculative is True

    def test_labels_distinct(self):
        labels = {t.label for t in ConfidenceTier}
        assert len(labels) == 4


class TestTagPrediction:
    def test_tag_returns_frozen(self):
        p = tag_prediction(0.42, ConfidenceTier.TIER_C, units="Sv/yr")
        assert p.value == 0.42
        with pytest.raises(Exception):
            p.value = 0.5   # frozen dataclass — must reject

    def test_to_dict_includes_label(self):
        p = tag_prediction(
            value=0.42,
            tier=ConfidenceTier.TIER_C,
            units="Sv/yr",
            model="Cucinotta 2014",
            falsification_dataset="Mars-EVA TEPC",
            confidence_interval=(0.20, 0.65),
            notes="±50 %",
        )
        d = p.to_dict()
        assert d["tier"] == "C"
        assert d["tier_label"] == "speculative"
        assert d["confidence_interval"] == [0.20, 0.65]
        assert d["model"] == "Cucinotta 2014"
        assert d["falsification_dataset"] == "Mars-EVA TEPC"


class TestForbidDQuote:
    def test_d_raises(self):
        p = tag_prediction(
            value=0.0, tier=ConfidenceTier.TIER_D,
            model="no-model", falsification_dataset="N/A",
        )
        with pytest.raises(TierDQuotedError):
            forbid_d_quote(p)

    def test_a_b_c_pass_through(self):
        for tier in (ConfidenceTier.TIER_A, ConfidenceTier.TIER_B,
                     ConfidenceTier.TIER_C):
            p = tag_prediction(value=1.0, tier=tier)
            assert forbid_d_quote(p) == 1.0
