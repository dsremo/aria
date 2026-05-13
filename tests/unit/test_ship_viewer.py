"""Tests for the 3D ship viewer feature.

Covers:
  - ship_viewer.html existence and Three.js script tags
  - web_dashboard.py route registration (/viewer, /api/ship.gltf, /api/ship/status)
  - export_gltf.py file generation
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── Paths ──
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "aria" / "simulator" / "web_assets"
DASHBOARD_PY = Path(__file__).resolve().parent.parent.parent / "src" / "aria" / "simulator" / "web_dashboard.py"
VIEWER_HTML = ASSETS_DIR / "ship_viewer.html"


class TestShipViewerHTML:
    """Tests for ship_viewer.html static file."""

    def test_ship_viewer_html_exists(self) -> None:
        """ship_viewer.html must exist in web_assets/."""
        assert VIEWER_HTML.exists(), f"Expected {VIEWER_HTML} to exist"

    def test_contains_threejs_import(self) -> None:
        """ship_viewer.html must load Three.js from CDN."""
        content = VIEWER_HTML.read_text()
        assert "three@0.160.0" in content, "Three.js CDN import not found"

    def test_contains_orbit_controls(self) -> None:
        """ship_viewer.html must load OrbitControls."""
        content = VIEWER_HTML.read_text()
        assert "OrbitControls" in content, "OrbitControls import not found"

    def test_contains_gltf_loader(self) -> None:
        """ship_viewer.html must load GLTFLoader."""
        content = VIEWER_HTML.read_text()
        assert "GLTFLoader" in content, "GLTFLoader import not found"

    def test_loads_ship_gltf_endpoint(self) -> None:
        """ship_viewer.html must reference /api/ship.gltf endpoint."""
        content = VIEWER_HTML.read_text()
        assert "/api/ship.gltf" in content, "ship.gltf API endpoint not referenced"

    def test_contains_subsystem_colors(self) -> None:
        """ship_viewer.html must define color coding for subsystems."""
        content = VIEWER_HTML.read_text()
        for subsystem in ["hull", "radiator", "reactor", "shield", "habitat"]:
            assert subsystem in content, f"Color coding for {subsystem} not found"


class TestDashboardRoutes:
    """Tests that web_dashboard.py registers the required routes."""

    def test_dashboard_has_viewer_route(self) -> None:
        """web_dashboard.py must register GET /viewer."""
        content = DASHBOARD_PY.read_text()
        assert '"/viewer"' in content, "/viewer route not registered"

    def test_dashboard_has_ship_gltf_route(self) -> None:
        """web_dashboard.py must register GET /api/ship.gltf."""
        content = DASHBOARD_PY.read_text()
        assert '"/api/ship.gltf"' in content, "/api/ship.gltf route not registered"

    def test_dashboard_has_ship_status_route(self) -> None:
        """web_dashboard.py must register GET /api/ship/status."""
        content = DASHBOARD_PY.read_text()
        assert '"/api/ship/status"' in content, "/api/ship/status route not registered"

    def test_dashboard_handles_missing_gltf(self) -> None:
        """web_dashboard.py must handle missing glTF file gracefully.

        Updated: behaviour changed from returning an error string to
        auto-generating the glTF on first access (P2-10 fix in
        _handle_ship_gltf). Assert the auto-generation path is present.
        """
        content = DASHBOARD_PY.read_text()
        # The handler must:
        #   (1) check gltf_path.exists()
        #   (2) call export_gltf() to auto-generate if missing
        #   (3) return a 500 with an error payload if generation itself fails
        assert "gltf_path.exists()" in content, "glTF path-existence check missing"
        assert "from aria.digital_twin.export_gltf import export_gltf" in content, (
            "auto-generation fallback missing — handler must regenerate ship.gltf"
        )
        assert "Failed to generate ship.gltf" in content, (
            "error-path missing — handler must return JSON error if regen fails"
        )


class TestExportGltf:
    """Tests for the glTF export script."""

    def test_export_creates_file(self) -> None:
        """export_gltf.py must create a .gltf file at the given path."""
        from aria.digital_twin.export_gltf import export_gltf

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test_ship.gltf"
            result = export_gltf(out)
            assert result.exists(), f"Expected {result} to be created"
            assert result.stat().st_size > 100, "glTF file is suspiciously small"

    def test_export_produces_valid_json(self) -> None:
        """The exported .gltf file must be valid JSON."""
        from aria.digital_twin.export_gltf import export_gltf

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test_ship.gltf"
            export_gltf(out)
            data = json.loads(out.read_text())
            assert data["asset"]["version"] == "2.0"

    def test_export_contains_ship_meshes(self) -> None:
        """The exported glTF must contain named ship meshes."""
        from aria.digital_twin.export_gltf import export_gltf

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "test_ship.gltf"
            export_gltf(out)
            data = json.loads(out.read_text())
            mesh_names = [m["name"] for m in data.get("meshes", [])]
            assert any("hull" in n for n in mesh_names), "No hull mesh found"
            assert any("reactor" in n for n in mesh_names), "No reactor mesh found"
            assert any("shield" in n for n in mesh_names), "No shield mesh found"
            assert any("radiator" in n for n in mesh_names), "No radiator mesh found"
            assert any("habitat" in n for n in mesh_names), "No habitat mesh found"

    def test_build_ship_gltf_structure(self) -> None:
        """build_ship_gltf must return a valid glTF 2.0 structure."""
        from aria.digital_twin.export_gltf import build_ship_gltf

        gltf = build_ship_gltf()
        assert "asset" in gltf
        assert "scenes" in gltf
        assert "nodes" in gltf
        assert "meshes" in gltf
        assert "buffers" in gltf
        assert len(gltf["meshes"]) >= 5, "Expected at least 5 mesh parts"
