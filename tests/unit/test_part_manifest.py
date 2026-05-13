"""Unit tests for the ARIA ship part manifest (Bill of Materials)."""

from __future__ import annotations

import pytest

from aria.digital_twin.part_manifest import (
    SHIP_MANIFEST,
    PartEntry,
    get_manifest,
    get_mass_by_material,
    validate_manifest,
)
from aria.digital_twin.materials.material_db import MATERIAL_DATABASE


# ------------------------------------------------------------------
# 1. Manifest has exactly 36 parts
# ------------------------------------------------------------------

class TestManifestCompleteness:
    def test_manifest_has_36_parts(self) -> None:
        assert len(SHIP_MANIFEST) == 36

    def test_get_manifest_returns_copy(self) -> None:
        """get_manifest() should return a copy, not the original list."""
        m = get_manifest()
        assert m == SHIP_MANIFEST
        assert m is not SHIP_MANIFEST

    def test_all_entries_are_part_entry(self) -> None:
        for part in SHIP_MANIFEST:
            assert isinstance(part, PartEntry), f"{part.name} is not a PartEntry"


# ------------------------------------------------------------------
# 2. Every part references a valid material
# ------------------------------------------------------------------

class TestMaterialTraceability:
    @pytest.mark.parametrize(
        "part", SHIP_MANIFEST, ids=lambda p: p.name,
    )
    def test_material_exists_in_db(self, part: PartEntry) -> None:
        assert part.material_name in MATERIAL_DATABASE, (
            f"Part '{part.name}' references unknown material "
            f"'{part.material_name}'"
        )

    @pytest.mark.parametrize(
        "part", SHIP_MANIFEST, ids=lambda p: p.name,
    )
    def test_material_has_density(self, part: PartEntry) -> None:
        """Every referenced material must have a non-zero density."""
        mat = MATERIAL_DATABASE[part.material_name]
        assert mat.density_kg_m3 > 0


# ------------------------------------------------------------------
# 3. All masses are positive
# ------------------------------------------------------------------

class TestMasses:
    @pytest.mark.parametrize(
        "part", SHIP_MANIFEST, ids=lambda p: p.name,
    )
    def test_mass_is_positive(self, part: PartEntry) -> None:
        assert part.mass_kg > 0, (
            f"Part '{part.name}' has non-positive mass: {part.mass_kg}"
        )

    def test_total_mass_is_reasonable(self) -> None:
        """Total manifest mass should be > 1000 tonnes (real ship)."""
        total = sum(p.mass_kg * p.quantity for p in SHIP_MANIFEST)
        assert total > 1e6, f"Total mass too low: {total:.0f} kg"


# ------------------------------------------------------------------
# 4. Dimensions are all positive and reasonable
# ------------------------------------------------------------------

class TestDimensions:
    @pytest.mark.parametrize(
        "part", SHIP_MANIFEST, ids=lambda p: p.name,
    )
    def test_dimensions_positive(self, part: PartEntry) -> None:
        for dim_name, dim_val in part.dimensions_m.items():
            assert dim_val > 0, (
                f"Part '{part.name}' dimension '{dim_name}' = {dim_val} <= 0"
            )

    @pytest.mark.parametrize(
        "part", SHIP_MANIFEST, ids=lambda p: p.name,
    )
    def test_dimensions_under_10km(self, part: PartEntry) -> None:
        for dim_name, dim_val in part.dimensions_m.items():
            assert dim_val < 10_000, (
                f"Part '{part.name}' dimension '{dim_name}' = {dim_val} >= 10 km"
            )


# ------------------------------------------------------------------
# 5. validate_manifest() reports no errors
# ------------------------------------------------------------------

class TestValidation:
    def test_validation_passes(self) -> None:
        errors = validate_manifest()
        assert errors == [], f"Validation errors:\n" + "\n".join(errors)


# ------------------------------------------------------------------
# 6. get_mass_by_material() is consistent
# ------------------------------------------------------------------

class TestMassByMaterial:
    def test_returns_dict(self) -> None:
        result = get_mass_by_material()
        assert isinstance(result, dict)

    def test_all_keys_are_valid_materials(self) -> None:
        for mat_name in get_mass_by_material():
            assert mat_name in MATERIAL_DATABASE

    def test_sum_matches_manifest_total(self) -> None:
        by_mat = get_mass_by_material()
        total_by_mat = sum(by_mat.values())
        total_direct = sum(p.mass_kg * p.quantity for p in SHIP_MANIFEST)
        assert total_by_mat == pytest.approx(total_direct, rel=1e-9)


# ------------------------------------------------------------------
# 7. Subsystem coverage — all expected subsystems present
# ------------------------------------------------------------------

class TestSubsystemCoverage:
    EXPECTED_SUBSYSTEMS = {
        "structure",
        "shield",
        "power",
        "propulsion",
        "eclss",
        "habitat_ring",
        "radiators",
        "thermal",
        "computing",
    }

    def test_all_subsystems_represented(self) -> None:
        actual = {p.subsystem for p in SHIP_MANIFEST}
        missing = self.EXPECTED_SUBSYSTEMS - actual
        assert not missing, f"Missing subsystems: {missing}"


# ------------------------------------------------------------------
# 8. Specific spot-check: pressure hull uses Ti-6Al-4V
# ------------------------------------------------------------------

class TestSpotChecks:
    def test_pressure_hull_material(self) -> None:
        hull = next(p for p in SHIP_MANIFEST if p.name == "Pressure Hull")
        assert hull.material_name == "Ti-6Al-4V"
        assert hull.has_3d_geometry is True

    def test_ablation_ice_uses_water_ice(self) -> None:
        ice = next(p for p in SHIP_MANIFEST if p.name == "Ablation Ice Shield")
        assert ice.material_name == "Water-Ice"

    def test_magnetic_deflector_uses_mgb2(self) -> None:
        coil = next(p for p in SHIP_MANIFEST if p.name == "Magnetic Deflector Coil")
        assert coil.material_name == "MgB2"

    def test_electrostatic_grid_uses_tungsten(self) -> None:
        grid = next(p for p in SHIP_MANIFEST if p.name == "Electrostatic Grid")
        assert grid.material_name == "Tungsten"

    def test_breeding_blanket_uses_li2tio3(self) -> None:
        blanket = next(p for p in SHIP_MANIFEST if p.name == "Tritium Breeding Blanket")
        assert blanket.material_name == "Li2TiO3"

    def test_bioshield_uses_borated_concrete(self) -> None:
        bio = next(p for p in SHIP_MANIFEST if p.name == "Biological Shield")
        assert bio.material_name == "Borated-Concrete"

    def test_solar_panels_use_gaas(self) -> None:
        solar = next(p for p in SHIP_MANIFEST if p.name == "Backup Solar Panels")
        assert solar.material_name == "GaAs"

    def test_unique_part_names(self) -> None:
        names = [p.name for p in SHIP_MANIFEST]
        assert len(names) == len(set(names)), "Duplicate part names found"
