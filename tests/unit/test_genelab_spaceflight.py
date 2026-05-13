"""Tests for GeneLab spaceflight gene expression module."""

from aria.simulation.genelab_spaceflight import (
    SPACEFLIGHT_DE_SUMMARY,
    SPACEFLIGHT_BIO_PARAMS,
    MISSION_RELEVANT_GENES,
    get_immune_shift_factor,
    get_muscle_atrophy_rate,
)


class TestDESummary:
    def test_dataset_is_glds254(self):
        assert "GLDS-254" in SPACEFLIGHT_DE_SUMMARY["dataset"]

    def test_total_genes(self):
        assert SPACEFLIGHT_DE_SUMMARY["total_genes_measured"] == 31760

    def test_more_upregulated_than_down(self):
        assert SPACEFLIGHT_DE_SUMMARY["sig_upregulated"] > SPACEFLIGHT_DE_SUMMARY["sig_downregulated"]

    def test_up_down_ratio(self):
        assert SPACEFLIGHT_DE_SUMMARY["up_down_ratio"] > 5.0  # ~6:1


class TestMissionRelevantGenes:
    def test_immune_shift_genes_present(self):
        assert len(MISSION_RELEVANT_GENES["immune_shift"]) > 0

    def test_muscle_atrophy_genes_present(self):
        genes = MISSION_RELEVANT_GENES["muscle_atrophy"]
        names = [g["gene"] for g in genes]
        assert "Ankrd1" in names
        assert "Ucp1" in names

    def test_all_genes_have_padj(self):
        for category in MISSION_RELEVANT_GENES.values():
            for gene in category:
                assert gene["padj"] < 0.05


class TestImmuneShiftFactor:
    def test_zero_g_maximum(self):
        f = get_immune_shift_factor(0.0)
        assert f == 1.4  # Full effect at 0g

    def test_one_g_no_effect(self):
        f = get_immune_shift_factor(1.0)
        assert f == 1.0  # No effect at 1g

    def test_partial_gravity(self):
        f = get_immune_shift_factor(0.56)
        assert 1.0 < f < 1.4  # Partial effect

    def test_monotonic(self):
        assert get_immune_shift_factor(0.0) > get_immune_shift_factor(0.5) > get_immune_shift_factor(1.0)


class TestMuscleAtrophyRate:
    def test_zero_g_maximum(self):
        rate = get_muscle_atrophy_rate(0.0)
        assert rate == SPACEFLIGHT_BIO_PARAMS["muscle_atrophy_monthly_0g"]

    def test_one_g_zero(self):
        assert get_muscle_atrophy_rate(1.0) == 0.0

    def test_partial_gravity(self):
        rate = get_muscle_atrophy_rate(0.56)
        assert 0 < rate < SPACEFLIGHT_BIO_PARAMS["muscle_atrophy_monthly_0g"]
