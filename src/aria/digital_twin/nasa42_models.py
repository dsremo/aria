"""NASA 42 Reference Model Loader.

Loads OBJ spacecraft models from the NASA 42 simulator as reference
geometry for the ARIA digital twin. These provide real spacecraft
component proportions (ISS modules, radiators, solar panels).

Available models in tools/nasa-42/Model/:
  ISS_MainBody.obj      — ISS pressurized modules (29K vertices)
  ISS_Radiator.obj      — ISS thermal radiator panels
  ISS_SolarPanel.obj    — ISS solar array wings
  ISS_SolarTruss.obj    — ISS main truss structure
  ISS_HGA.obj           — ISS high-gain antenna
  SpaceShuttleOrbiter.obj — Space Shuttle reference
  Voyager.obj           — Voyager spacecraft
  CMG.obj               — Control moment gyroscope
  CubeSat*.obj          — CubeSat form factors
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

DEFAULT_MODEL_DIR = Path("tools/nasa-42/Model")


@dataclass
class OBJModel:
    """A loaded OBJ model with vertices, faces, and bounding box."""
    name: str
    vertices: np.ndarray  # (N, 3) float64
    faces: list[list[int]]  # List of face vertex index lists
    n_vertices: int = 0
    n_faces: int = 0
    bbox_min: np.ndarray = field(default_factory=lambda: np.zeros(3))
    bbox_max: np.ndarray = field(default_factory=lambda: np.zeros(3))
    bbox_size: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def scale_to(self, target_length_m: float) -> "OBJModel":
        """Scale model so longest axis = target_length_m."""
        current_max = max(self.bbox_size)
        if current_max < 1e-10:
            return self
        scale = target_length_m / current_max
        return OBJModel(
            name=self.name,
            vertices=self.vertices * scale,
            faces=self.faces,
            n_vertices=self.n_vertices,
            n_faces=self.n_faces,
            bbox_min=self.bbox_min * scale,
            bbox_max=self.bbox_max * scale,
            bbox_size=self.bbox_size * scale,
        )


def load_obj(filepath: Path | str) -> OBJModel:
    """Load an OBJ file into an OBJModel."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"OBJ file not found: {filepath}")

    vertices = []
    faces = []

    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()[1:]
                face = [int(p.split("/")[0]) - 1 for p in parts]  # OBJ is 1-indexed
                faces.append(face)

    verts = np.array(vertices, dtype=np.float64) if vertices else np.zeros((0, 3))
    bbox_min = verts.min(axis=0) if len(verts) > 0 else np.zeros(3)
    bbox_max = verts.max(axis=0) if len(verts) > 0 else np.zeros(3)

    return OBJModel(
        name=filepath.stem,
        vertices=verts,
        faces=faces,
        n_vertices=len(vertices),
        n_faces=len(faces),
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        bbox_size=bbox_max - bbox_min,
    )


def list_available_models(model_dir: Path | str | None = None) -> list[str]:
    """List all available OBJ models."""
    model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    if not model_dir.exists():
        return []
    return sorted(f.stem for f in model_dir.glob("*.obj"))


def load_iss_reference_models(model_dir: Path | str | None = None) -> dict[str, OBJModel]:
    """Load ISS models for reference proportions."""
    model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
    models = {}

    iss_files = {
        "main_body": "ISS_MainBody.obj",
        "radiator": "ISS_Radiator.obj",
        "solar_panel": "ISS_SolarPanel.obj",
        "truss": "ISS_SolarTruss.obj",
        "hga": "ISS_HGA.obj",
    }

    for key, filename in iss_files.items():
        path = model_dir / filename
        if path.exists():
            try:
                models[key] = load_obj(path)
                logger.info("nasa42.model_loaded", name=key,
                            vertices=models[key].n_vertices,
                            size=models[key].bbox_size.tolist())
            except Exception as e:
                logger.warning("nasa42.model_failed", name=key, error=str(e))

    return models


def get_iss_proportions(model_dir: Path | str | None = None) -> dict[str, Any]:
    """Extract dimensional proportions from ISS models.

    These proportions serve as reality-checks for the generation ship geometry.
    """
    models = load_iss_reference_models(model_dir)
    proportions = {}

    if "main_body" in models:
        m = models["main_body"]
        proportions["iss_module_length_ratio"] = m.bbox_size[2] / max(m.bbox_size[0], 1e-6)
        proportions["iss_module_aspect_ratio"] = max(m.bbox_size) / min(m.bbox_size[m.bbox_size > 0])

    if "radiator" in models:
        m = models["radiator"]
        proportions["iss_radiator_aspect_ratio"] = max(m.bbox_size) / min(m.bbox_size[m.bbox_size > 0])

    return proportions
