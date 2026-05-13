"""Unit tests for the ARIA material properties database."""

from __future__ import annotations

import pytest

from aria.digital_twin.materials.material_db import (
    MATERIAL_DATABASE,
    MaterialProperty,
    get_material,
    get_property,
)


# ------------------------------------------------------------------
# 1. All nine materials are present
# ------------------------------------------------------------------

EXPECTED_MATERIALS = [
    "Ti-6Al-4V",
    "EUROFER97",
    "NaK-78",
    "B4C",
    "Kevlar-49",
    "UHMWPE",
    "Al-7075-T6",
    "CNT-Composite",
    "HfB2",
    "Inconel-718",
    "SS-316L",
    "Fused-Silica",
    "Aerogel",
    "MLI-Mylar",
    "Liquid-Hydrogen",
    "Water-Ice",
    "MgB2",
    "Tungsten",
    "Li2TiO3",
    "Borated-Concrete",
    "GaAs",
]


class TestDatabaseCompleteness:
    """Every expected material must be loadable."""

    @pytest.mark.parametrize("name", EXPECTED_MATERIALS)
    def test_material_exists(self, name: str) -> None:
        mat = get_material(name)
        assert isinstance(mat, MaterialProperty)
        assert mat.name == name

    def test_database_has_at_least_expected_entries(self) -> None:
        """Database has grown over time — assert we still cover the expected
        set plus some minimum floor. Exact count (67 as of Round-2 audit) not
        enforced so adding materials doesn't trip this test."""
        assert len(MATERIAL_DATABASE) >= len(EXPECTED_MATERIALS), (
            f"DB shrank: {len(MATERIAL_DATABASE)} entries, "
            f"expected ≥ {len(EXPECTED_MATERIALS)}"
        )
        # Post-audit floor: 60 materials covers ship-subsystem needs
        assert len(MATERIAL_DATABASE) >= 60, (
            f"DB has only {len(MATERIAL_DATABASE)} materials; "
            f"expected ≥60 post Round-2 audit (heat-pipe fluids, "
            f"superconductors, wick materials added)"
        )


# ------------------------------------------------------------------
# 2. Ti-6Al-4V density is 4430
# ------------------------------------------------------------------

class TestTi6Al4V:
    def test_density(self) -> None:
        assert get_property("Ti-6Al-4V", "density_kg_m3") == 4430.0

    def test_youngs_modulus(self) -> None:
        assert get_property("Ti-6Al-4V", "youngs_modulus_pa") == pytest.approx(
            113.8e9
        )

    def test_fatigue_limit(self) -> None:
        assert get_property("Ti-6Al-4V", "fatigue_limit_pa") == pytest.approx(
            510e6
        )


# ------------------------------------------------------------------
# 3. CNT Composite marked as futuristic / projected
# ------------------------------------------------------------------

class TestCNTComposite:
    def test_source_mentions_projected(self) -> None:
        mat = get_material("CNT-Composite")
        assert "PROJECTED" in mat.source.upper()

    def test_source_mentions_not_flight_qualified(self) -> None:
        mat = get_material("CNT-Composite")
        assert "NOT YET FLIGHT-QUALIFIED" in mat.source

    def test_bulk_composite_yield_strength(self) -> None:
        """~2 GPa yield — realistic for bulk CNT composite (not single tube).

        Sharma (Materials PDR): single-tube MWCNT values (~60 GPa) do not
        translate to bulk composite performance. Downgraded to 2 GPa to
        match Cheng 2009 / Wang 2014 / Bakshi 2010 bulk measurements.
        """
        assert get_property("CNT-Composite", "yield_strength_pa") == pytest.approx(
            2.0e9
        )


# ------------------------------------------------------------------
# 4. get_property returns correct values for various materials
# ------------------------------------------------------------------

class TestGetProperty:
    def test_eurofer97_thermal_conductivity(self) -> None:
        assert get_property("EUROFER97", "thermal_conductivity_w_mk") == pytest.approx(
            33.6
        )

    def test_nak78_specific_heat(self) -> None:
        assert get_property("NaK-78", "specific_heat_j_kgk") == pytest.approx(1042.0)

    def test_hfb2_melting_point(self) -> None:
        assert get_property("HfB2", "melting_point_k") == pytest.approx(3523.0)

    def test_kevlar49_low_thermal_conductivity(self) -> None:
        assert get_property("Kevlar-49", "thermal_conductivity_w_mk") == pytest.approx(
            0.04
        )

    def test_al7075_yield_strength(self) -> None:
        assert get_property("Al-7075-T6", "yield_strength_pa") == pytest.approx(
            503e6
        )

    def test_b4c_density(self) -> None:
        assert get_property("B4C", "density_kg_m3") == 2520.0

    def test_uhmwpe_modulus(self) -> None:
        assert get_property("UHMWPE", "youngs_modulus_pa") == pytest.approx(0.8e9)


# ------------------------------------------------------------------
# 5. Unknown material raises KeyError
# ------------------------------------------------------------------

class TestErrorHandling:
    def test_unknown_material_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="Unknown material 'Unobtainium'"):
            get_material("Unobtainium")

    def test_get_property_unknown_material(self) -> None:
        with pytest.raises(KeyError):
            get_property("Vibranium", "density_kg_m3")

    def test_get_property_invalid_attribute(self) -> None:
        with pytest.raises(AttributeError, match="no attribute"):
            get_property("Ti-6Al-4V", "hardness_hrc")

    def test_get_property_none_value_raises(self) -> None:
        """NaK-78 has no Young's modulus (liquid)."""
        with pytest.raises(ValueError, match="not defined"):
            get_property("NaK-78", "youngs_modulus_pa")

    def test_liquid_hydrogen_no_youngs_modulus(self) -> None:
        """Liquid Hydrogen has no Young's modulus (liquid)."""
        with pytest.raises(ValueError, match="not defined"):
            get_property("Liquid-Hydrogen", "youngs_modulus_pa")

    def test_mli_mylar_no_youngs_modulus(self) -> None:
        """MLI-Mylar is a film — no Young's modulus."""
        with pytest.raises(ValueError, match="not defined"):
            get_property("MLI-Mylar", "youngs_modulus_pa")


# ------------------------------------------------------------------
# 6. New materials — spot-check key properties
# ------------------------------------------------------------------

class TestInconel718:
    def test_density(self) -> None:
        assert get_property("Inconel-718", "density_kg_m3") == 8190.0

    def test_yield_strength(self) -> None:
        assert get_property("Inconel-718", "yield_strength_pa") == pytest.approx(1035e6)

    def test_thermal_conductivity(self) -> None:
        assert get_property("Inconel-718", "thermal_conductivity_w_mk") == pytest.approx(11.2)

    def test_melting_point(self) -> None:
        assert get_property("Inconel-718", "melting_point_k") == pytest.approx(1609.0)


class TestSS316L:
    def test_density(self) -> None:
        assert get_property("SS-316L", "density_kg_m3") == 7990.0

    def test_youngs_modulus(self) -> None:
        assert get_property("SS-316L", "youngs_modulus_pa") == pytest.approx(193e9)

    def test_yield_strength(self) -> None:
        assert get_property("SS-316L", "yield_strength_pa") == pytest.approx(170e6)


class TestFusedSilica:
    def test_density(self) -> None:
        assert get_property("Fused-Silica", "density_kg_m3") == 2200.0

    def test_youngs_modulus(self) -> None:
        assert get_property("Fused-Silica", "youngs_modulus_pa") == pytest.approx(73e9)

    def test_melting_point(self) -> None:
        assert get_property("Fused-Silica", "melting_point_k") == pytest.approx(1986.0)

    def test_no_yield_strength(self) -> None:
        """Fused silica is a brittle glass — no yield strength."""
        with pytest.raises(ValueError, match="not defined"):
            get_property("Fused-Silica", "yield_strength_pa")


class TestAerogel:
    def test_density(self) -> None:
        assert get_property("Aerogel", "density_kg_m3") == 100.0

    def test_extremely_low_modulus(self) -> None:
        """Aerogel E ~ 1 MPa — orders of magnitude below metals."""
        assert get_property("Aerogel", "youngs_modulus_pa") == pytest.approx(0.001e9)

    def test_ultra_low_thermal_conductivity(self) -> None:
        assert get_property("Aerogel", "thermal_conductivity_w_mk") == pytest.approx(0.015)


class TestMLIMylar:
    def test_density(self) -> None:
        assert get_property("MLI-Mylar", "density_kg_m3") == 1390.0

    def test_low_emissivity(self) -> None:
        """Gold-coated MLI has extremely low emissivity."""
        assert get_property("MLI-Mylar", "emissivity") == pytest.approx(0.03)

    def test_thermal_conductivity(self) -> None:
        assert get_property("MLI-Mylar", "thermal_conductivity_w_mk") == pytest.approx(0.04)


class TestLiquidHydrogen:
    def test_density(self) -> None:
        assert get_property("Liquid-Hydrogen", "density_kg_m3") == 70.8

    def test_high_specific_heat(self) -> None:
        """LH2 has the highest specific heat of any substance."""
        assert get_property("Liquid-Hydrogen", "specific_heat_j_kgk") == pytest.approx(14300.0)

    def test_melting_point(self) -> None:
        assert get_property("Liquid-Hydrogen", "melting_point_k") == pytest.approx(14.0)


# ------------------------------------------------------------------
# 7. Every material has a non-empty source citation
# ------------------------------------------------------------------

class TestSourceCitations:
    @pytest.mark.parametrize("name", EXPECTED_MATERIALS)
    def test_source_is_nonempty(self, name: str) -> None:
        mat = get_material(name)
        assert mat.source, f"{name} is missing a source citation"
        assert len(mat.source) > 10, f"{name} source too short to be a real citation"
