"""Tests for aria.digital_twin.nasa42_models — OBJ model loader.

Covers:
  - Clean import and OBJModel construction
  - load_obj with valid and missing files
  - OBJModel.scale_to rescaling
  - list_available_models on missing directory
  - load_obj round-trip with a synthetic OBJ file
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aria.digital_twin.nasa42_models import (
    OBJModel,
    list_available_models,
    load_obj,
)


@pytest.fixture
def simple_obj_file(tmp_path: Path) -> Path:
    """Create a minimal OBJ file with a triangle and a quad."""
    obj_content = """\
# Simple test model
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
v 0.5 0.5 2.0
f 1 2 3
f 1 3 4
f 1 2 5
"""
    path = tmp_path / "test_model.obj"
    path.write_text(obj_content)
    return path


@pytest.fixture
def loaded_model(simple_obj_file: Path) -> OBJModel:
    return load_obj(simple_obj_file)


class TestOBJModelConstruction:

    def test_default_fields(self):
        model = OBJModel(
            name="empty",
            vertices=np.zeros((0, 3)),
            faces=[],
        )
        assert model.name == "empty"
        assert model.n_vertices == 0
        assert model.n_faces == 0

    def test_loaded_model_vertex_count(self, loaded_model: OBJModel):
        assert loaded_model.n_vertices == 5
        assert loaded_model.vertices.shape == (5, 3)

    def test_loaded_model_face_count(self, loaded_model: OBJModel):
        assert loaded_model.n_faces == 3
        assert len(loaded_model.faces) == 3

    def test_loaded_model_name_from_stem(self, loaded_model: OBJModel):
        assert loaded_model.name == "test_model"


class TestBoundingBox:

    def test_bbox_values(self, loaded_model: OBJModel):
        np.testing.assert_allclose(loaded_model.bbox_min, [0.0, 0.0, 0.0])
        np.testing.assert_allclose(loaded_model.bbox_max, [1.0, 1.0, 2.0])
        np.testing.assert_allclose(loaded_model.bbox_size, [1.0, 1.0, 2.0])


class TestScaleTo:

    def test_scale_to_target_length(self, loaded_model: OBJModel):
        # Longest axis is z = 2.0; scale to 10.0
        scaled = loaded_model.scale_to(10.0)
        assert abs(max(scaled.bbox_size) - 10.0) < 1e-6
        # The x and y axes should be 5.0 (half of z)
        assert abs(scaled.bbox_size[0] - 5.0) < 1e-6

    def test_scale_preserves_vertex_count(self, loaded_model: OBJModel):
        scaled = loaded_model.scale_to(100.0)
        assert scaled.n_vertices == loaded_model.n_vertices
        assert scaled.n_faces == loaded_model.n_faces

    def test_scale_zero_size_model(self):
        """A degenerate model with all vertices at origin should survive scale_to."""
        model = OBJModel(
            name="degenerate",
            vertices=np.zeros((3, 3)),
            faces=[[0, 1, 2]],
            n_vertices=3,
            n_faces=1,
            bbox_min=np.zeros(3),
            bbox_max=np.zeros(3),
            bbox_size=np.zeros(3),
        )
        scaled = model.scale_to(10.0)
        # Should return without error; no actual scaling since size is 0
        assert scaled.name == "degenerate"


class TestLoadObj:

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_obj(tmp_path / "nonexistent.obj")

    def test_load_empty_obj(self, tmp_path: Path):
        empty = tmp_path / "empty.obj"
        empty.write_text("# empty file\n")
        model = load_obj(empty)
        assert model.n_vertices == 0
        assert model.n_faces == 0

    def test_face_indices_are_zero_based(self, loaded_model: OBJModel):
        """OBJ files are 1-indexed; loaded faces should be 0-indexed."""
        for face in loaded_model.faces:
            for idx in face:
                assert 0 <= idx < loaded_model.n_vertices


class TestListAvailableModels:

    def test_missing_directory_returns_empty(self, tmp_path: Path):
        result = list_available_models(tmp_path / "nonexistent")
        assert result == []

    def test_finds_obj_files(self, tmp_path: Path):
        (tmp_path / "model_a.obj").write_text("v 0 0 0\n")
        (tmp_path / "model_b.obj").write_text("v 1 0 0\n")
        (tmp_path / "readme.txt").write_text("not a model\n")
        result = list_available_models(tmp_path)
        assert result == ["model_a", "model_b"]
