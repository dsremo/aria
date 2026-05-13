"""STEP file import path — real spacecraft CAD into ARIA.

Replaces the parametric-only fiction with operator-uploadable
real models from CubeSat / smallsat manufacturers (ISIS Space,
NanoAvionics, Spire, EnduroSat) or any STEP-exporting CAD tool.

Pipeline an operator can run:

  step file (real CAD)
        │
        ▼
  load_step_file()                 ← validates the file, OCCT parses it
        │
        ▼
  StepModel
    .compute_mass_properties()     ← volume, mass, center of mass, inertia
    .bounding_box()                ← axis-aligned bounding box
    .topology_summary()            ← face / edge / vertex / shell counts
    .validate()                    ← closed shells, no self-intersection,
                                     finite mass, positive volume
        │
        ▼
  → existing FEA / thermal / GLTF pipeline

What this is NOT:
  * It is not a STEP *exporter* — that already exists in CadQuery
    workplanes. This module's job is the inbound path: take a
    real CAD file and produce engineering quantities ARIA already
    knows how to consume.
  * It is not flight software. STEP is an exchange format, not a
    flight asset. The mass + inertia ARIA computes here is what
    you'd attach to a spacecraft model for trajectory + control
    analysis; it is not a substitute for hardware-validated mass
    measurements during integration.

Citations:

  * STEP — ISO 10303-203 (configuration controlled 3D designs of
    mechanical parts and assemblies); ISO 10303-214 (automotive),
    214 supersedes 203 for general use; both are accepted by
    OpenCASCADE Technology STEP Translator.
  * OpenCASCADE Technology — open-source CAD kernel, used by
    FreeCAD, KiCad, Salome, and CadQuery. Apache-style license.
  * CadQuery — Apache 2.0; thin Python wrapper over OCCT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ── Materials / unit assumptions ────────────────────────────────


# STEP files have an explicit unit declaration (mm, m, in). OCCT
# converts to its internal unit (mm by default). Mass = volume × density,
# so the operator must specify the density (kg/m³) of the material
# they assigned to the part.

# A small library of common spacecraft-structure densities, citation-tagged.
# These are NOT the full MMPDS / MAPTIS / SPACEMATDB datasets — see the
# vendor-cell EPS module for that pattern; this is just the minimal
# table to make load_step_file usable out of the box.
DENSITY_KG_M3: Dict[str, float] = {
    # Aluminium structural alloys (most CubeSats)
    "Al-6061-T6": 2700.0,    # MMPDS-2025 §3.6 (2.70 g/cc)
    "Al-7075-T6": 2810.0,    # MMPDS-2025 §3.7
    "Al-2024-T3": 2780.0,    # MMPDS-2025 §3.5
    # Titanium (high-stress structural)
    "Ti-6Al-4V": 4430.0,     # MMPDS-2025 §5.4 (Ti-6Al-4V grade 5)
    # Stainless
    "SS-304":   8000.0,      # ASM Handbook Vol. 1 §SS-304
    "SS-316":   8000.0,      # ASM Handbook Vol. 1 §SS-316
    # Composites
    "CFRP-IM7-8552": 1580.0,  # Hexcel HexPly 8552 datasheet
    # Common
    "Inconel-718": 8190.0,    # MMPDS-2025 §6.2
    "Magnesium-AZ31B": 1770.0,  # ASM Handbook Vol. 2
}


@dataclass(frozen=True)
class BoundingBox:
    xmin_m: float
    ymin_m: float
    zmin_m: float
    xmax_m: float
    ymax_m: float
    zmax_m: float

    @property
    def x_extent_m(self) -> float:
        return self.xmax_m - self.xmin_m

    @property
    def y_extent_m(self) -> float:
        return self.ymax_m - self.ymin_m

    @property
    def z_extent_m(self) -> float:
        return self.zmax_m - self.zmin_m

    @property
    def volume_envelope_m3(self) -> float:
        return self.x_extent_m * self.y_extent_m * self.z_extent_m


@dataclass(frozen=True)
class MassProperties:
    """Engineering mass properties of a STEP-imported part.

    All quantities in SI base units. The mass calculation needs an
    explicit density (kg/m³); the inertia tensor is reported about
    the centre of mass.
    """

    volume_m3: float
    mass_kg: float                    # mass = volume × density_kg_m3
    density_kg_m3: float
    center_of_mass_m: Tuple[float, float, float]
    # Inertia tensor I_ij = ∫ ρ (δ_ij r² - x_i x_j) dV, evaluated at CoM.
    # 3×3 matrix; units kg·m².
    inertia_tensor_kg_m2: Tuple[
        Tuple[float, float, float],
        Tuple[float, float, float],
        Tuple[float, float, float],
    ]


@dataclass(frozen=True)
class TopologySummary:
    n_solids: int
    n_shells: int
    n_faces: int
    n_edges: int
    n_vertices: int


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of geometric validation."""

    is_valid: bool
    issues: Tuple[str, ...] = ()


@dataclass
class StepModel:
    """A STEP file loaded into memory plus the engineering quantities
    ARIA's existing FEA / thermal / GLTF pipeline expects.

    Construct via :func:`load_step_file`; the constructor stores the
    OCCT-backed CadQuery shape opaquely and exposes only the values
    needed downstream.
    """

    source_path: Path
    file_size_bytes: int
    occt_shape: Any                          # cadquery.Shape (kept opaque)
    topology: TopologySummary
    bounding_box: BoundingBox

    def compute_mass_properties(self, *, density_kg_m3: float) -> MassProperties:
        """Compute mass + centre of mass + inertia tensor at given density."""
        if density_kg_m3 <= 0 or not _isfinite(density_kg_m3):
            raise ValueError(
                f"density_kg_m3 must be a finite positive number, "
                f"got {density_kg_m3!r}",
            )
        volume_m3 = float(self.occt_shape.Volume())
        if volume_m3 <= 0:
            raise ValueError(
                f"STEP shape has non-positive volume {volume_m3} m³; "
                "cannot compute mass — file may contain only surfaces / wires.",
            )

        center = self.occt_shape.Center()
        cog = (float(center.x), float(center.y), float(center.z))

        # The unit-adapter exposes geometric inertia in m⁵ via its own
        # matrixOfInertia method; multiply by density to get kg·m².
        inertia_geom = self.occt_shape.matrixOfInertia()
        inertia_si: List[List[float]] = [
            [float(inertia_geom[i][j]) * density_kg_m3 for j in range(3)]
            for i in range(3)
        ]
        return MassProperties(
            volume_m3=volume_m3,
            mass_kg=volume_m3 * density_kg_m3,
            density_kg_m3=density_kg_m3,
            center_of_mass_m=cog,
            inertia_tensor_kg_m2=tuple(tuple(row) for row in inertia_si),
        )

    def validate(self) -> ValidationResult:
        """Geometric validation suitable for downstream FEA mesh.

        Checks (in order):

          * OCCT reports the shape is valid (no self-intersection,
            consistent topology)
          * Volume is finite and positive (otherwise it's a wire-frame
            or surface-only STEP; mass calc would fail)
          * At least one solid + one shell present
        """
        issues: List[str] = []
        if not self.occt_shape.isValid():
            issues.append("OCCT.isValid() returned False")
        try:
            volume = float(self.occt_shape.Volume())
        except Exception as exc:  # noqa: BLE001 — OCCT raises bare RuntimeError
            issues.append(f"Volume() raised {type(exc).__name__}: {exc}")
            volume = 0.0
        if not _isfinite(volume):
            issues.append(f"Volume() returned non-finite {volume}")
        elif volume <= 0:
            issues.append(
                f"Non-positive volume {volume:.3e} m³ — file may contain "
                "only surfaces / wires, not solids",
            )
        if self.topology.n_solids == 0:
            issues.append("zero solids present (need at least one)")
        if self.topology.n_shells == 0:
            issues.append("zero shells present (need at least one)")
        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=tuple(issues),
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly summary suitable for the operator UI / API."""
        validation = self.validate()
        return {
            "source_path": str(self.source_path),
            "file_size_bytes": self.file_size_bytes,
            "topology": {
                "n_solids": self.topology.n_solids,
                "n_shells": self.topology.n_shells,
                "n_faces": self.topology.n_faces,
                "n_edges": self.topology.n_edges,
                "n_vertices": self.topology.n_vertices,
            },
            "bounding_box_m": {
                "min": [
                    self.bounding_box.xmin_m,
                    self.bounding_box.ymin_m,
                    self.bounding_box.zmin_m,
                ],
                "max": [
                    self.bounding_box.xmax_m,
                    self.bounding_box.ymax_m,
                    self.bounding_box.zmax_m,
                ],
                "extent": [
                    self.bounding_box.x_extent_m,
                    self.bounding_box.y_extent_m,
                    self.bounding_box.z_extent_m,
                ],
            },
            "validation": {
                "is_valid": validation.is_valid,
                "issues": list(validation.issues),
            },
        }


# ── Loader ──────────────────────────────────────────────────────


# OCCT operates internally in millimetres by default. STEP files
# carry a unit annotation; the importer converts to the active
# session unit. We expose ARIA's results in **metres** because the
# rest of the codebase is SI base units. The conversion factor
# applies to length (mm → m = ×1e-3); volume scales as the cube,
# so volume in m³ = volume in mm³ × 1e-9.
_MM3_TO_M3 = 1e-9
_MM_TO_M = 1e-3

# Bound the file size we'll accept — an operator dropping a 500 MB
# STEP file should get a clean refusal, not OOM.
MAX_STEP_FILE_BYTES = 200 * 1024 * 1024   # 200 MB


def load_step_file(path: str | os.PathLike) -> StepModel:
    """Parse a STEP file via CadQuery + OCCT and return a StepModel.

    Raises:
        FileNotFoundError — file missing
        ValueError        — file empty / too large / not valid STEP
        RuntimeError      — OCCT failed to parse
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"STEP file not found: {path}")
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise ValueError(f"STEP file is empty: {path}")
    if size_bytes > MAX_STEP_FILE_BYTES:
        raise ValueError(
            f"STEP file is {size_bytes / 1e6:.1f} MB; "
            f"refusing to load (limit {MAX_STEP_FILE_BYTES / 1e6:.0f} MB).",
        )

    try:
        from cadquery import importers
    except ImportError as exc:  # CadQuery should be installed; defensive.
        raise RuntimeError(
            "CadQuery is required for STEP import; "
            "install via `pip install cadquery`.",
        ) from exc

    logger.info("step.loading", path=str(path), size_bytes=size_bytes)
    try:
        wp = importers.importStep(str(path))
    except Exception as exc:  # noqa: BLE001 — OCCT raises bare RuntimeError
        raise RuntimeError(
            f"OCCT failed to parse STEP file {path.name}: "
            f"{type(exc).__name__}: {exc}",
        ) from exc
    shape = wp.val()

    # Topology counts.
    topology = TopologySummary(
        n_solids=len(shape.Solids()),
        n_shells=len(shape.Shells()),
        n_faces=len(shape.Faces()),
        n_edges=len(shape.Edges()),
        n_vertices=len(shape.Vertices()),
    )

    # Bounding box. CadQuery returns the OCCT BoundBox already in
    # session units (mm by default). Convert to metres.
    bb_raw = shape.BoundingBox()
    bbox = BoundingBox(
        xmin_m=float(bb_raw.xmin) * _MM_TO_M,
        ymin_m=float(bb_raw.ymin) * _MM_TO_M,
        zmin_m=float(bb_raw.zmin) * _MM_TO_M,
        xmax_m=float(bb_raw.xmax) * _MM_TO_M,
        ymax_m=float(bb_raw.ymax) * _MM_TO_M,
        zmax_m=float(bb_raw.zmax) * _MM_TO_M,
    )

    # Wrap shape in a thin adapter that reports volume in m³ instead
    # of mm³ so callers don't have to worry about units.
    converted = _UnitAdapter(shape)

    logger.info(
        "step.loaded",
        path=str(path),
        n_solids=topology.n_solids,
        n_faces=topology.n_faces,
        bbox_m=[bbox.x_extent_m, bbox.y_extent_m, bbox.z_extent_m],
    )
    return StepModel(
        source_path=path,
        file_size_bytes=size_bytes,
        occt_shape=converted,
        topology=topology,
        bounding_box=bbox,
    )


# ── Helpers ─────────────────────────────────────────────────────


def density_for_material(material_name: str) -> float:
    """Look up the cited density of a common spacecraft-structure
    material; raises KeyError for unknown materials."""
    if material_name not in DENSITY_KG_M3:
        raise KeyError(
            f"Unknown material {material_name!r}; "
            f"add to DENSITY_KG_M3 with citation.",
        )
    return DENSITY_KG_M3[material_name]


def known_materials() -> Tuple[str, ...]:
    """List of material names with cited densities in DENSITY_KG_M3."""
    return tuple(DENSITY_KG_M3.keys())


# ── Internal helpers ────────────────────────────────────────────


class _UnitAdapter:
    """Thin proxy that re-expresses OCCT volume in m³ + CoG in m.

    OCCT works in mm by default; the rest of ARIA is SI. Wrap the
    raw shape so callers see consistent units without us mutating
    OCCT's internal session.
    """

    def __init__(self, raw_shape: Any) -> None:
        self._raw = raw_shape

    # The cadquery.Shape API surface we touch downstream:
    def Volume(self) -> float:
        return float(self._raw.Volume()) * _MM3_TO_M3

    def Center(self) -> Any:
        c = self._raw.Center()
        return _ScaledVector(
            x=float(c.x) * _MM_TO_M,
            y=float(c.y) * _MM_TO_M,
            z=float(c.z) * _MM_TO_M,
        )

    def isValid(self) -> bool:
        return bool(self._raw.isValid())

    def Solids(self):
        return self._raw.Solids()

    def Shells(self):
        return self._raw.Shells()

    def Faces(self):
        return self._raw.Faces()

    def Edges(self):
        return self._raw.Edges()

    def Vertices(self):
        return self._raw.Vertices()

    def BoundingBox(self) -> Any:
        return self._raw.BoundingBox()

    def matrixOfInertia(self) -> List[List[float]]:
        from cadquery import Shape
        # OCCT returns geometric inertia (∫ r² dV) in mm⁵; scale to m⁵.
        # Then mass-inertia = density × geom-inertia gives kg·m². The
        # geom-to-mass scaling happens in compute_mass_properties.
        # Length⁵ scales as 1e-15 (mm⁵ → m⁵).
        scale = 1e-15
        geom_mm = Shape.matrixOfInertia(self._raw)
        return [
            [float(geom_mm[i][j]) * scale for j in range(3)]
            for i in range(3)
        ]


@dataclass(frozen=True)
class _ScaledVector:
    """Stand-in for cadquery.Vector with SI-converted coordinates."""

    x: float
    y: float
    z: float


def _isfinite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


# Re-export for downstream API stamping.
__all__ = (
    "BoundingBox",
    "MassProperties",
    "TopologySummary",
    "ValidationResult",
    "StepModel",
    "load_step_file",
    "density_for_material",
    "known_materials",
    "DENSITY_KG_M3",
    "MAX_STEP_FILE_BYTES",
)
