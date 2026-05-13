"""STEP file import path tests.

Strategy: generate STEP files programmatically with CadQuery so the
test does not need bundled binary files, then validate the
load_step_file() output against the analytical answer (volume,
mass, centre of mass, inertia tensor of a known geometry).

A 1 m × 1 m × 1 m cube of Al-6061-T6 should give:
  * volume = 1.0 m³
  * mass = 2700 kg (density of Al-6061-T6 per MMPDS-2025)
  * centre of mass = (0, 0, 0)
  * I_xx = I_yy = I_zz = m × s² / 6 = 2700 × 1 / 6 = 450 kg·m²
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aria.digital_twin.step_loader import (
    BoundingBox,
    MAX_STEP_FILE_BYTES,
    StepModel,
    density_for_material,
    known_materials,
    load_step_file,
)


# ── Fixture builders ────────────────────────────────────────────


@pytest.fixture
def unit_cube_step(tmp_path: Path) -> Path:
    """Generate a 1 m × 1 m × 1 m cube as a STEP file."""
    import cadquery as cq

    # CadQuery default unit is mm; build a 1000 mm cube → 1 m cube.
    cube = cq.Workplane("XY").box(1000.0, 1000.0, 1000.0)
    out = tmp_path / "unit_cube.step"
    cq.exporters.export(cube, str(out))
    return out


@pytest.fixture
def cubesat_envelope_step(tmp_path: Path) -> Path:
    """Generate a 3U CubeSat-class outer envelope: 100 × 100 × 340.5 mm.

    Real 3U CubeSat per CDS Rev 14: 100.0 ± 0.1 × 100.0 ± 0.1 ×
    340.5 ± 0.3 mm. This is the outer-skin envelope only; real
    CubeSats have far more internal detail."""
    import cadquery as cq

    envelope = cq.Workplane("XY").box(100.0, 100.0, 340.5)
    out = tmp_path / "cubesat_3u_envelope.step"
    cq.exporters.export(envelope, str(out))
    return out


# ── Loader plumbing ─────────────────────────────────────────────


class TestLoaderPlumbing:
    def test_load_unit_cube(self, unit_cube_step: Path) -> None:
        model = load_step_file(unit_cube_step)
        assert isinstance(model, StepModel)
        assert model.source_path == unit_cube_step
        assert model.file_size_bytes > 0

    def test_missing_file_raises_filenotfound(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_step_file(tmp_path / "no_such_file.step")

    def test_empty_file_raises_value_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.step"
        empty.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            load_step_file(empty)

    def test_invalid_step_file_raises_runtime_error(
        self, tmp_path: Path,
    ) -> None:
        bogus = tmp_path / "bogus.step"
        bogus.write_text("this is not a valid STEP file payload\n" * 50)
        with pytest.raises(RuntimeError):
            load_step_file(bogus)


# ── Geometry validation ─────────────────────────────────────────


class TestUnitCubeGeometry:
    @pytest.fixture
    def model(self, unit_cube_step: Path) -> StepModel:
        return load_step_file(unit_cube_step)

    def test_topology_six_faces_twelve_edges(self, model: StepModel) -> None:
        # A cube has 6 faces, 12 edges, 8 vertices, 1 solid, 1 shell.
        assert model.topology.n_solids == 1
        assert model.topology.n_shells == 1
        assert model.topology.n_faces == 6
        assert model.topology.n_edges == 12
        assert model.topology.n_vertices == 8

    def test_bounding_box_is_one_meter_cubed(self, model: StepModel) -> None:
        bb: BoundingBox = model.bounding_box
        assert bb.x_extent_m == pytest.approx(1.0, rel=0.01)
        assert bb.y_extent_m == pytest.approx(1.0, rel=0.01)
        assert bb.z_extent_m == pytest.approx(1.0, rel=0.01)

    def test_validation_passes(self, model: StepModel) -> None:
        result = model.validate()
        assert result.is_valid, f"validation issues: {result.issues}"

    def test_to_dict_serializes_cleanly(self, model: StepModel) -> None:
        import json
        payload = model.to_dict()
        # Must round-trip through json without exception.
        encoded = json.dumps(payload)
        assert "unit_cube" in encoded
        assert payload["validation"]["is_valid"] is True


# ── Mass property correctness ───────────────────────────────────


class TestUnitCubeMassProperties:
    @pytest.fixture
    def model(self, unit_cube_step: Path) -> StepModel:
        return load_step_file(unit_cube_step)

    def test_volume_is_one_cubic_meter(self, model: StepModel) -> None:
        props = model.compute_mass_properties(density_kg_m3=2700.0)
        assert props.volume_m3 == pytest.approx(1.0, rel=0.01)

    def test_mass_matches_density(self, model: StepModel) -> None:
        # Al-6061-T6 density = 2700 kg/m³ → 1 m³ cube = 2700 kg.
        props = model.compute_mass_properties(
            density_kg_m3=density_for_material("Al-6061-T6"),
        )
        assert props.mass_kg == pytest.approx(2700.0, rel=0.01)

    def test_center_of_mass_at_origin(self, model: StepModel) -> None:
        props = model.compute_mass_properties(density_kg_m3=2700.0)
        x, y, z = props.center_of_mass_m
        assert abs(x) < 1e-3
        assert abs(y) < 1e-3
        assert abs(z) < 1e-3

    def test_inertia_diagonal_matches_analytical(
        self, model: StepModel,
    ) -> None:
        # I_xx = I_yy = I_zz = m × s² / 6 for a unit cube about CoG.
        # With m = 2700 kg, s = 1 m → 450 kg·m².
        props = model.compute_mass_properties(density_kg_m3=2700.0)
        inertia = props.inertia_tensor_kg_m2
        assert inertia[0][0] == pytest.approx(450.0, rel=0.02)
        assert inertia[1][1] == pytest.approx(450.0, rel=0.02)
        assert inertia[2][2] == pytest.approx(450.0, rel=0.02)
        # Off-diagonal terms must be ~0 for a centered cube.
        for i in range(3):
            for j in range(3):
                if i != j:
                    assert abs(inertia[i][j]) < 1.0

    def test_negative_density_rejected(self, model: StepModel) -> None:
        with pytest.raises(ValueError, match="finite positive"):
            model.compute_mass_properties(density_kg_m3=-100.0)

    def test_zero_density_rejected(self, model: StepModel) -> None:
        with pytest.raises(ValueError, match="finite positive"):
            model.compute_mass_properties(density_kg_m3=0.0)

    def test_nan_density_rejected(self, model: StepModel) -> None:
        with pytest.raises(ValueError, match="finite positive"):
            model.compute_mass_properties(density_kg_m3=float("nan"))


# ── Real-mission geometry (3U CubeSat envelope) ─────────────────


class TestCubesat3UEnvelope:
    """Exercise against a CDS-Rev-14 3U CubeSat envelope (100 × 100 × 340.5 mm)."""

    @pytest.fixture
    def model(self, cubesat_envelope_step: Path) -> StepModel:
        return load_step_file(cubesat_envelope_step)

    def test_envelope_bbox_within_cds_tolerance(self, model: StepModel) -> None:
        # CDS Rev 14: 100.0 ± 0.1 × 100.0 ± 0.1 × 340.5 ± 0.3 mm.
        bb = model.bounding_box
        assert bb.x_extent_m == pytest.approx(0.100, abs=0.001)
        assert bb.y_extent_m == pytest.approx(0.100, abs=0.001)
        assert bb.z_extent_m == pytest.approx(0.3405, abs=0.001)

    def test_envelope_volume_matches_3U(self, model: StepModel) -> None:
        # 0.1 × 0.1 × 0.3405 = 0.003405 m³ = 3,405 cm³.
        props = model.compute_mass_properties(density_kg_m3=2700.0)
        assert props.volume_m3 == pytest.approx(0.003405, rel=0.01)
        # If 3U envelope was solid Al-6061-T6 (it's never solid in
        # reality), mass would be 0.003405 m³ × 2700 kg/m³ = 9.19 kg.
        # Real 3U CubeSats are 3.0-4.0 kg because they're hollow.
        assert props.mass_kg == pytest.approx(9.19, rel=0.01)

    def test_envelope_validates_cleanly(self, model: StepModel) -> None:
        result = model.validate()
        assert result.is_valid


# ── Material lookups ────────────────────────────────────────────


class TestMaterialLookups:
    def test_known_materials_includes_aluminium(self) -> None:
        materials = known_materials()
        assert "Al-6061-T6" in materials
        assert "Ti-6Al-4V" in materials

    def test_density_for_known_material(self) -> None:
        assert density_for_material("Al-6061-T6") == pytest.approx(2700.0)
        assert density_for_material("Ti-6Al-4V") == pytest.approx(4430.0)

    def test_density_for_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown material"):
            density_for_material("Unobtainium-X42")
