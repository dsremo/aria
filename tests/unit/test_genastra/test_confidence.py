"""Tests for pLDDT confidence interpretation."""

from __future__ import annotations

from aria.genastra.protein.confidence import (
    classify_residue_confidence,
    identify_low_confidence_regions,
    interpret_plddt,
)


class TestPLDDTInterpretation:
    def test_very_high_confidence(self) -> None:
        text = interpret_plddt(92.0, tuple([92.0] * 100))
        assert "Very high confidence" in text
        assert "pLDDT is a model confidence metric" in text

    def test_confident(self) -> None:
        text = interpret_plddt(75.0, tuple([75.0] * 100))
        assert "Confident prediction" in text

    def test_low_confidence(self) -> None:
        text = interpret_plddt(55.0, tuple([55.0] * 100))
        assert "Low confidence" in text

    def test_very_low_confidence(self) -> None:
        text = interpret_plddt(30.0, tuple([30.0] * 100))
        assert "Very low confidence" in text

    def test_always_includes_disclaimer(self) -> None:
        for plddt in [30.0, 55.0, 75.0, 92.0]:
            text = interpret_plddt(plddt, tuple([plddt] * 10))
            assert "not a probability" in text.lower()

    def test_empty_residues(self) -> None:
        text = interpret_plddt(0.0, ())
        assert "No residues" in text


class TestResidueClassification:
    def test_very_high(self) -> None:
        assert classify_residue_confidence(95.0) == "very_high"

    def test_confident(self) -> None:
        assert classify_residue_confidence(80.0) == "confident"

    def test_low(self) -> None:
        assert classify_residue_confidence(60.0) == "low"

    def test_disordered(self) -> None:
        assert classify_residue_confidence(30.0) == "disordered"


class TestLowConfidenceRegions:
    def test_finds_disordered_loop(self) -> None:
        plddt = tuple([90.0] * 10 + [30.0] * 8 + [90.0] * 10)
        regions = identify_low_confidence_regions(plddt, threshold=50.0, min_length=5)
        assert len(regions) == 1
        assert regions[0] == (10, 17)

    def test_no_regions_all_confident(self) -> None:
        plddt = tuple([90.0] * 50)
        regions = identify_low_confidence_regions(plddt)
        assert len(regions) == 0

    def test_short_regions_filtered(self) -> None:
        plddt = tuple([90.0] * 10 + [30.0] * 3 + [90.0] * 10)
        regions = identify_low_confidence_regions(plddt, min_length=5)
        assert len(regions) == 0
