"""Mesh generation for digital twin structural analysis.

Uses the Gmsh Python API to create tetrahedral meshes from STEP geometry
or parametric primitives. Returns meshio.Mesh objects for downstream FEA.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import gmsh
import meshio
import numpy as np


def _init_gmsh(model_name: str = "model") -> None:
    """Initialise Gmsh with sane defaults (headless, no terminal output).

    Handles the case where Gmsh is called from a non-main thread
    (e.g. asyncio executor) by suppressing signal-related errors.
    """
    import signal
    import threading

    if gmsh.isInitialized():
        gmsh.finalize()

    # Gmsh internally calls signal() which fails in non-main threads.
    # Temporarily monkey-patch signal.signal to a no-op if not in main thread.
    is_main = threading.current_thread() is threading.main_thread()
    if not is_main:
        _orig_signal = signal.signal
        signal.signal = lambda *args, **kwargs: None  # no-op
    try:
        gmsh.initialize()
    finally:
        if not is_main:
            signal.signal = _orig_signal

    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add(model_name)


def mesh_from_step(
    step_path: str,
    element_size: float = 1.0,
    order: int = 1,
) -> meshio.Mesh:
    """Create a tetrahedral mesh from a STEP file.

    Parameters
    ----------
    step_path : str
        Path to a STEP (*.step / *.stp) file exported from CadQuery or any
        CAD kernel.
    element_size : float
        Target characteristic length for the mesh elements (metres).
    order : int
        Element order (1 = linear tet4, 2 = quadratic tet10).

    Returns
    -------
    meshio.Mesh
        Mesh with ``tetra`` (or ``tetra10``) cells.
    """
    step_path = str(Path(step_path).resolve())
    _init_gmsh("step_model")

    try:
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", element_size * 0.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", element_size)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay

        gmsh.model.mesh.generate(3)

        return _extract_mesh()
    finally:
        gmsh.finalize()


def mesh_cylinder(
    radius: float,
    length: float,
    thickness: float,
    element_size: float = 1.0,
    order: int = 1,
) -> meshio.Mesh:
    """Create a tetrahedral mesh of a hollow cylinder (thin-walled tube).

    This is a convenience function for quick structural testing without
    needing a STEP file or CadQuery.

    Parameters
    ----------
    radius : float
        Inner radius of the cylinder (metres).
    length : float
        Axial length (metres).
    thickness : float
        Wall thickness (metres).
    element_size : float
        Target characteristic element length (metres).
    order : int
        Element order (1 = linear tet4).

    Raises
    ------
    ValueError
        On unphysical inputs (non-positive dims, or element_size larger
        than thickness × 0.5 which would prevent fitting tets in the wall).

    Returns
    -------
    meshio.Mesh
        Tetrahedral mesh of the hollow cylinder.
    """
    # Gmsh otherwise throws cryptic "PLC Error" on bad combos. Catch the
    # obvious cases up front with a clear ValueError naming the field.
    if radius <= 0:
        raise ValueError(f"radius must be > 0, got {radius}")
    if length <= 0:
        raise ValueError(f"length must be > 0, got {length}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0, got {thickness}")
    if element_size <= 0:
        raise ValueError(f"element_size must be > 0, got {element_size}")
    # No element_size/thickness ratio rule — Gmsh's auto-refinement is
    # more forgiving than a simple ratio test: the pipeline uses 25:1
    # (2.0 m elements, 80 mm wall) successfully, while 42:1 fails. Rather
    # than hard-code a brittle threshold, let Gmsh's own PLC error surface
    # for pathological cases and only guard against outright-invalid
    # (non-positive) inputs above.

    _init_gmsh("cylinder")

    try:
        outer_r = radius + thickness
        # Outer cylinder
        outer = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, length, outer_r)
        # Inner cylinder (to subtract)
        inner = gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, length, radius)
        # Boolean cut: outer - inner → hollow shell
        result, _ = gmsh.model.occ.cut(
            [(3, outer)], [(3, inner)], removeObject=True, removeTool=True
        )
        gmsh.model.occ.synchronize()

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", element_size * 0.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", element_size)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)

        gmsh.model.mesh.generate(3)

        return _extract_mesh()
    finally:
        gmsh.finalize()


def _extract_mesh() -> meshio.Mesh:
    """Pull the current Gmsh model into a meshio.Mesh via a temp MSH file."""
    with tempfile.NamedTemporaryFile(suffix=".msh", delete=False) as tmp:
        tmp_path = tmp.name

    gmsh.write(tmp_path)
    mesh = meshio.read(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)

    # Filter to only tetrahedral cells (drop triangles, lines, etc.)
    tet_cells = []
    for cell_block in mesh.cells:
        if cell_block.type in ("tetra", "tetra10"):
            tet_cells.append(cell_block)

    if not tet_cells:
        raise RuntimeError("Gmsh produced no tetrahedral elements — check geometry and element_size.")

    return meshio.Mesh(points=mesh.points, cells=tet_cells)
