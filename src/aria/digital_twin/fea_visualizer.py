"""FEA result visualization for the ARIA digital twin.

Takes finite-element analysis results (von Mises stress per element)
and generates VTK exports, matplotlib cross-section plots, and
summary hotspot reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib
matplotlib.use("Agg")  # headless backend — no display required
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import meshio
import numpy as np


class FEAVisualizer:
    """Visualize FEA stress results on a mesh.

    Parameters
    ----------
    mesh : meshio.Mesh
        The finite-element mesh (must contain 3-D cells such as tetra,
        hexahedron, or triangle).
    stress : np.ndarray
        1-D array of von Mises stress values [MPa], one per cell.
        The length must match the total number of cells in the mesh.
    """

    def __init__(self, mesh: meshio.Mesh, stress: np.ndarray) -> None:
        self.mesh = mesh
        self.stress = np.asarray(stress, dtype=np.float64)

        total_cells = sum(len(block.data) for block in mesh.cells)
        if self.stress.shape[0] != total_cells:
            raise ValueError(
                f"Stress array length ({self.stress.shape[0]}) does not match "
                f"total cell count ({total_cells})."
            )

    # ── VTK export ───────────────────────────────────────────────────────

    def export_vtk(self, path: str) -> Path:
        """Write the mesh with stress as cell data to a VTK file.

        Parameters
        ----------
        path : str
            Output file path (typically ``*.vtk`` or ``*.vtu``).

        Returns
        -------
        Path
            The written file path.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Build per-block cell-data arrays
        offset = 0
        cell_data_blocks: list[np.ndarray] = []
        for block in self.mesh.cells:
            n = len(block.data)
            cell_data_blocks.append(self.stress[offset : offset + n])
            offset += n

        self.mesh.cell_data["von_mises_stress_MPa"] = cell_data_blocks
        meshio.write(str(out), self.mesh)
        return out

    # ── Cross-section plot ───────────────────────────────────────────────

    def plot_cross_section(
        self,
        z_position: float,
        output_path: str,
        *,
        tolerance: float | None = None,
    ) -> Path:
        """Generate a 2-D matplotlib plot of stress on a Z cross-section.

        Cells whose centroid Z-coordinate is within *tolerance* of
        *z_position* are projected onto the XY plane.

        Parameters
        ----------
        z_position : float
            Axial position of the cross-section [m].
        output_path : str
            Path for the saved figure (e.g. ``*.png``).
        tolerance : float | None
            Slab half-thickness for selecting cells.  Defaults to 1 %
            of the mesh Z-extent.

        Returns
        -------
        Path
            The saved figure path.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        points = self.mesh.points
        z_min, z_max = float(points[:, 2].min()), float(points[:, 2].max())

        if tolerance is None:
            tolerance = max((z_max - z_min) * 0.01, 1e-6)

        # Collect cell centroids, stress, and connectivity for plotting
        centroids_x: list[float] = []
        centroids_y: list[float] = []
        cell_stress: list[float] = []

        offset = 0
        for block in self.mesh.cells:
            for i, conn in enumerate(block.data):
                verts = points[conn]
                cz = float(verts[:, 2].mean())
                if abs(cz - z_position) <= tolerance:
                    centroids_x.append(float(verts[:, 0].mean()))
                    centroids_y.append(float(verts[:, 1].mean()))
                    cell_stress.append(float(self.stress[offset + i]))
            offset += len(block.data)

        if not centroids_x:
            # No cells in this slice — produce an empty placeholder
            fig, ax = plt.subplots()
            ax.set_title(f"Cross-section at z = {z_position:.1f} m (no data)")
            ax.set_xlabel("X [m]")
            ax.set_ylabel("Y [m]")
            fig.savefig(str(out), dpi=150)
            plt.close(fig)
            return out

        cx = np.array(centroids_x)
        cy = np.array(centroids_y)
        cs = np.array(cell_stress)

        fig, ax = plt.subplots(figsize=(8, 8))
        scatter = ax.scatter(
            cx, cy, c=cs, cmap="jet", s=4, edgecolors="none",
        )
        fig.colorbar(scatter, ax=ax, label="von Mises stress [MPa]")
        ax.set_aspect("equal")
        ax.set_title(f"Stress cross-section at z = {z_position:.1f} m")
        ax.set_xlabel("X [m]")
        ax.set_ylabel("Y [m]")

        fig.savefig(str(out), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return out

    # ── Hotspot detection ────────────────────────────────────────────────

    def get_hotspots(self, threshold_mpa: float) -> list[dict]:
        """Return cells where stress exceeds a threshold.

        Parameters
        ----------
        threshold_mpa : float
            Stress threshold [MPa].

        Returns
        -------
        list[dict]
            Each dict contains:
              - ``cell_index``: global cell index
              - ``stress_mpa``: von Mises stress value
              - ``centroid``: (x, y, z) tuple of the cell centroid
              - ``cell_type``: meshio cell type string
        """
        points = self.mesh.points
        hotspots: list[dict] = []

        offset = 0
        for block in self.mesh.cells:
            for i, conn in enumerate(block.data):
                global_idx = offset + i
                s = float(self.stress[global_idx])
                if s > threshold_mpa:
                    verts = points[conn]
                    centroid = tuple(float(c) for c in verts.mean(axis=0))
                    hotspots.append({
                        "cell_index": global_idx,
                        "stress_mpa": s,
                        "centroid": centroid,
                        "cell_type": block.type,
                    })
            offset += len(block.data)

        # Sort descending by stress
        hotspots.sort(key=lambda h: h["stress_mpa"], reverse=True)
        return hotspots
