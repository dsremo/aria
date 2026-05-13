"""Live-server integration tests for the engineering-lab API.

Round-2 audit flagged that the 7 `/api/ship/*` + `/api/materials` endpoints
had ZERO coverage. This module hits them on a running instance
(``localhost:8765``) and asserts:

  * HTTP 200
  * Valid JSON / glTF body
  * Non-empty payload with expected structure
  * Consistency between endpoints (e.g. parts list / glTF mesh set)

Tests are marked ``live_server`` and skipped automatically if the dashboard
is not reachable — keeps CI green when nobody's running the service, and
provides a fast smoke-check when it is.
"""

from __future__ import annotations

import json
import socket

import pytest

try:
    import urllib.request
    import urllib.error
except Exception:   # pragma: no cover
    urllib = None

BASE = "http://localhost:8765"


def _server_alive() -> bool:
    """Non-blocking liveness probe. Returns False if nothing is listening."""
    try:
        with socket.create_connection(("localhost", 8765), timeout=0.25):
            return True
    except OSError:
        return False


live_server = pytest.mark.skipif(
    not _server_alive(),
    reason="web dashboard not running on localhost:8765",
)


@pytest.fixture(autouse=True)
def _reset_ship_class_to_cruiser():
    """Reset the on-disk /api/ship.gltf to the cruiser-class baseline
    before every test in this module. Without this, a prior run (or a
    separate shell invocation of /api/ship/apply_class with `stealth` /
    `cargo_interstellar`) leaves the glTF pruned — habitat ring + spokes
    + hab modules disappear — and `test_gltf_and_parts_list_consistent`
    flakes because mesh counts differ from the cruiser baseline. The
    reset is idempotent and cheap."""
    if not _server_alive():
        yield
        return
    try:
        req = urllib.request.Request(
            f"{BASE}/api/ship/apply_class",
            data=json.dumps({"class_id": "cruiser"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20):
            pass
    except Exception:
        pass
    yield


def _get(path: str, timeout: float = 5.0) -> tuple[int, bytes]:
    """Fetch a URL; return (status, body). Never raises on HTTP error."""
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


@live_server
class TestShipEndpoints:
    def test_ship_parts(self):
        code, body = _get("/api/ship/parts")
        assert code == 200, f"parts endpoint returned {code}"
        d = json.loads(body)
        assert "parts" in d
        assert len(d["parts"]) >= 5, f"expected ≥5 parts, got {len(d['parts'])}"
        # Each part has required keys
        for p in d["parts"]:
            for key in ("id", "name", "material", "description"):
                assert key in p, f"part missing '{key}': {p}"

    def test_ship_params(self):
        code, body = _get("/api/ship/params")
        assert code == 200
        d = json.loads(body)
        for key in (
            "hull_radius_m", "hull_length_m", "habitat_ring_radius_m",
            "habitat_spoke_count", "crew_size",
        ):
            assert key in d, f"params missing '{key}'"
        # Post-audit defaults we're locking in
        assert d["habitat_spoke_count"] == 6
        assert d["crew_size"] == 1000

    def test_ship_gltf_served(self):
        code, body = _get("/api/ship.gltf", timeout=10.0)
        assert code == 200
        # Should parse as JSON (glTF 2.0 is JSON)
        gltf = json.loads(body)
        assert gltf.get("asset", {}).get("version") == "2.0"
        assert "meshes" in gltf and len(gltf["meshes"]) > 20, (
            f"glTF has only {len(gltf.get('meshes', []))} meshes; expected >20"
        )

    def test_gltf_and_parts_list_consistent(self):
        """Every part id in /api/ship/parts should correspond to a mesh
        (or mesh group) in the glTF."""
        _, parts_body = _get("/api/ship/parts")
        _, gltf_body = _get("/api/ship.gltf", timeout=10.0)
        parts = json.loads(parts_body)["parts"]
        gltf = json.loads(gltf_body)
        mesh_names = {m["name"] for m in gltf["meshes"]}
        part_ids = [p["id"] for p in parts]
        for pid in part_ids:
            matched = any(n == pid or n.startswith(pid + "_") for n in mesh_names)
            # Virtual groups: the parts-list API uses aggregation ids that
            # don't map 1:1 to glTF mesh names. Each is a UI category the
            # Three.js click-handler translates:
            #   radiator_panel  → radiator_array_0..(N-1)
            #   shield_bow      → shield_layer_0..6 + bow_sensor_ring
            #   propulsion      → reactor_engine + magnetic_nozzle + engine_bell_*
            allowed_virtual = {"radiator_panel", "shield_bow", "propulsion"}
            assert matched or pid in allowed_virtual, (
                f"parts-list id '{pid}' has no matching mesh in glTF"
            )


@live_server
class TestMaterialsEndpoint:
    def test_materials(self):
        code, body = _get("/api/materials")
        assert code == 200
        d = json.loads(body)
        assert "materials" in d
        mats = d["materials"]
        assert len(mats) >= 40, f"expected ≥40 materials, got {len(mats)}"
        # Spot-check a few key materials
        for key in ("Ti-6Al-4V", "Water-Ice", "NaK-78"):
            assert key in mats, f"material '{key}' missing from API"
            for prop in ("density_kg_m3", "source"):
                assert prop in mats[key], f"{key} missing '{prop}'"

    def test_added_materials_present(self):
        """Round-2 audit added Potassium/YBCO/Nb3Sn/Sintered-Nickel."""
        code, body = _get("/api/materials")
        mats = json.loads(body)["materials"]
        for key in ("Potassium", "YBCO", "Nb3Sn", "Sintered-Nickel"):
            assert key in mats, f"audit-added material '{key}' missing from API response"


@live_server
class TestRebuildEndpoint:
    def test_rebuild_returns_ok(self):
        """POST /api/ship/rebuild with empty overrides — should succeed with
        the current ShipParameters defaults."""
        data = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}/api/ship/rebuild",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as r:
                assert r.status == 200
                body = json.loads(r.read())
                assert not body.get("error"), f"rebuild returned error: {body}"
        except urllib.error.HTTPError as e:
            pytest.fail(f"rebuild HTTP error {e.code}: {e.read()}")
