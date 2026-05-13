"""R46 — conjunction-screener-as-a-service tests.

Three layers of test:

  * **Pure-functional core** — `ConjunctionScreenerService.screen_pair`
    against the Iridium-Cosmos pair as a known-good input.
  * **HTTP layer** — auth, rate limit, malformed-request handling.
  * **End-to-end** — POST a screen request, verify the response
    classifies the Iridium-Cosmos pair correctly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from aria.products.conjunction_screener.service import (
    ConjunctionScreenerService,
    ScreenRequest,
    TLEPayload,
    TenantConfig,
    VERSION,
    _classify,
    _request_to_obj,
    _response_to_dict,
    create_app,
)
from aria.validation import iridium_cosmos_replay as ic


# ── Helpers ────────────────────────────────────────────────────


def _iridium_payload() -> TLEPayload:
    inputs = ic.load_inputs()
    return TLEPayload(
        norad_id=inputs.primary_norad_id,
        name=inputs.primary_name,
        line1=inputs.primary_line1,
        line2=inputs.primary_line2,
        radius_m=inputs.primary_radius_m,
    )


def _cosmos_payload() -> TLEPayload:
    inputs = ic.load_inputs()
    return TLEPayload(
        norad_id=inputs.secondary_norad_id,
        name=inputs.secondary_name,
        line1=inputs.secondary_line1,
        line2=inputs.secondary_line2,
        radius_m=inputs.secondary_radius_m,
    )


# ── Classification ────────────────────────────────────────────


class TestClassification:
    def test_red_when_pc_above_threshold(self):
        assert _classify(1e-3, 5.0) == "RED"

    def test_red_when_miss_below_100m(self):
        assert _classify(0.0, 0.05) == "RED"

    def test_yellow_when_pc_above_micro_pc(self):
        assert _classify(1e-6, 5.0) == "YELLOW"

    def test_yellow_when_miss_below_1km(self):
        assert _classify(0.0, 0.5) == "YELLOW"

    def test_green_when_clearly_safe(self):
        assert _classify(1e-9, 50.0) == "GREEN"


# ── Pure-functional screening core ─────────────────────────────


class TestScreenPair:
    def test_iridium_cosmos_screens(self):
        svc = ConjunctionScreenerService()
        result = svc.screen_pair(
            _iridium_payload(),
            _cosmos_payload(),
            approx_tca_utc=datetime(2009, 2, 10, 16, 56, tzinfo=timezone.utc),
            sigma_km=0.250,
            search_window_minutes=60.0,
        )
        assert result.tca_utc.startswith("2009-02-10T16:55:")
        assert 100.0 < result.miss_distance_m < 1500.0
        assert 11.5 < result.relative_velocity_kmps < 11.8
        assert result.risk_level in ("YELLOW", "RED")

    def test_screen_request_response(self):
        svc = ConjunctionScreenerService()
        req = ScreenRequest(
            primary=_iridium_payload(),
            secondaries=[_cosmos_payload()],
            approx_tca_utc="2009-02-10T16:56:00Z",
            search_window_minutes=60.0,
            operator_grade_sigma_km=0.250,
        )
        resp = svc.screen(req)
        assert len(resp.results) == 1
        assert resp.elapsed_ms < 60_000.0       # < 1 minute
        assert resp.version == VERSION


class TestRequestSerialization:
    def test_request_to_obj_round_trip(self):
        # Round-2 audit NEW-HIGH-8 — TLE lines are validated at the
        # boundary; use a real-shape TLE here.
        l1_p = "1 24946U 97051C   09040.74440185  .00000114  00000-0  35055-4 0  4373"
        l2_p = "2 24946  86.3938 124.4685 0002131  79.4630 280.6878 14.34219697598149"
        l1_s = "1 22675U 93036A   09040.79438886  .00000051  00000-0  44004-4 0  9351"
        l2_s = "2 22675  74.0354 213.6068 0028477 105.6164 254.7835 14.32320790819349"
        body = {
            "primary": {
                "norad_id": "24946", "name": "IRIDIUM 33",
                "line1": l1_p, "line2": l2_p, "radius_m": 1.5,
            },
            "secondaries": [{
                "norad_id": "22675", "name": "COSMOS 2251",
                "line1": l1_s, "line2": l2_s, "radius_m": 2.5,
            }],
            "approx_tca_utc": "2009-02-10T16:56:00Z",
            "search_window_minutes": 30,
            "operator_grade_sigma_km": 0.300,
        }
        req = _request_to_obj(body)
        assert req.primary.norad_id == "24946"
        assert len(req.secondaries) == 1
        assert req.search_window_minutes == 30
        assert req.operator_grade_sigma_km == 0.300

    def test_validation_rejects_nan_radius(self):
        """Round-2 audit NEW-HIGH-8."""
        l1 = "1 24946U 97051C   09040.74440185  .00000114  00000-0  35055-4 0  4373"
        l2 = "2 24946  86.3938 124.4685 0002131  79.4630 280.6878 14.34219697598149"
        body = {
            "primary": {"norad_id": "X", "line1": l1, "line2": l2,
                        "radius_m": float("nan")},
            "secondaries": [],
        }
        with pytest.raises(ValueError):
            _request_to_obj(body)

    def test_validation_clamps_search_window(self):
        """Round-2 audit NEW-HIGH-12."""
        l1 = "1 24946U 97051C   09040.74440185  .00000114  00000-0  35055-4 0  4373"
        l2 = "2 24946  86.3938 124.4685 0002131  79.4630 280.6878 14.34219697598149"
        body = {
            "primary": {"norad_id": "X", "line1": l1, "line2": l2},
            "secondaries": [],
            "search_window_minutes": 1_000_000,
        }
        with pytest.raises(ValueError):
            _request_to_obj(body)


# ── HTTP layer ────────────────────────────────────────────────


@pytest.fixture
def demo_tenant():
    return TenantConfig(
        tenant_id="test", api_key_hex="t" * 64,
        rate_limit_per_min=100, rate_limit_per_day=1000,
    )


async def _http_client(app):
    """Build an aiohttp TestClient without pytest-aiohttp."""
    from aiohttp.test_utils import TestServer, TestClient
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client, server


class TestHTTPLayer:
    @pytest.mark.asyncio
    async def test_healthz_open(self, demo_tenant):
        app = create_app(tenants=[demo_tenant])
        client, _ = await _http_client(app)
        try:
            resp = await client.get("/v1/healthz")
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_version_requires_admin(self, demo_tenant):
        # Audit HIGH-8 — /v1/version is admin-only; the version string
        # used to be readable by any anonymous attacker for CVE
        # fingerprinting.
        import hashlib as _h, hmac as _hm
        admin_secret = "Z" * 64
        wire = _hm.new(admin_secret.encode("utf-8"),
                       b"aria-screener:v1", _h.sha256).hexdigest()
        app = create_app(tenants=[demo_tenant], admin_token_hex=admin_secret)
        client, _ = await _http_client(app)
        try:
            resp = await client.get("/v1/version")
            assert resp.status == 401
            resp = await client.get(
                "/v1/version", headers={"X-ARIA-Admin-Token": wire},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["version"] == VERSION
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_screen_requires_auth(self, demo_tenant):
        client, _ = await _http_client(create_app(tenants=[demo_tenant]))
        try:
            resp = await client.post("/v1/screen", json={})
            assert resp.status == 401
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_screen_rejects_bad_token(self, demo_tenant):
        client, _ = await _http_client(create_app(tenants=[demo_tenant]))
        try:
            resp = await client.post(
                "/v1/screen", json={},
                headers={"X-ARIA-Token": "wrong"},
            )
            assert resp.status == 401
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_screen_rejects_malformed_body(self, demo_tenant):
        client, _ = await _http_client(create_app(tenants=[demo_tenant]))
        try:
            resp = await client.post(
                "/v1/screen",
                data="not json",
                headers={"X-ARIA-Token": demo_tenant.api_key_hex},
            )
            assert resp.status == 400
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_screen_e2e_iridium_cosmos(self, demo_tenant):
        client, _ = await _http_client(create_app(tenants=[demo_tenant]))
        try:
            body = {
                "primary": {
                    "norad_id": _iridium_payload().norad_id,
                    "name": _iridium_payload().name,
                    "line1": _iridium_payload().line1,
                    "line2": _iridium_payload().line2,
                    "radius_m": _iridium_payload().radius_m,
                },
                "secondaries": [{
                    "norad_id": _cosmos_payload().norad_id,
                    "name": _cosmos_payload().name,
                    "line1": _cosmos_payload().line1,
                    "line2": _cosmos_payload().line2,
                    "radius_m": _cosmos_payload().radius_m,
                }],
                "approx_tca_utc": "2009-02-10T16:56:00Z",
                "search_window_minutes": 60.0,
            }
            resp = await client.post(
                "/v1/screen", json=body,
                headers={"X-ARIA-Token": demo_tenant.api_key_hex},
            )
            assert resp.status == 200
            out = await resp.json()
            assert out["version"] == VERSION
            assert len(out["results"]) == 1
            r = out["results"][0]
            assert r["risk_level"] in ("YELLOW", "RED")
            assert r["tca_utc"].startswith("2009-02-10T16:55:")
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_rate_limit_per_min_enforced(self):
        tight_tenant = TenantConfig(
            tenant_id="tight", api_key_hex="t" * 64,
            rate_limit_per_min=2, rate_limit_per_day=100,
        )
        client, _ = await _http_client(create_app(tenants=[tight_tenant]))
        try:
            body = {"primary": {
                "norad_id": "x", "line1": "...", "line2": "...",
            }, "secondaries": []}
            h = {"X-ARIA-Token": tight_tenant.api_key_hex}
            for _ in range(2):
                await client.post("/v1/screen", json=body, headers=h)
            resp = await client.post("/v1/screen", json=body, headers=h)
            assert resp.status == 429
            # Retry-After header MUST be present + parseable as seconds.
            ra = resp.headers.get("Retry-After")
            assert ra is not None and ra.isdigit() and int(ra) >= 1
            ra_body = await resp.json()
            assert ra_body.get("retry_after_seconds", 0) == int(ra)
        finally:
            await client.close()


class TestE2ESmoke:
    @pytest.mark.asyncio
    async def test_full_round_trip(self):
        tenant = TenantConfig(
            tenant_id="e2e", api_key_hex="e" * 64,
            rate_limit_per_min=100, rate_limit_per_day=1000,
        )
        client, _ = await _http_client(create_app(tenants=[tenant]))
        try:
            body = {
                "primary": {
                    "norad_id": "24946", "name": "IRIDIUM 33",
                    "line1": _iridium_payload().line1,
                    "line2": _iridium_payload().line2,
                    "radius_m": 1.5,
                },
                "secondaries": [{
                    "norad_id": "22675", "name": "COSMOS 2251",
                    "line1": _cosmos_payload().line1,
                    "line2": _cosmos_payload().line2,
                    "radius_m": 2.5,
                }],
                "approx_tca_utc": "2009-02-10T16:56:00Z",
            }
            resp = await client.post(
                "/v1/screen", json=body,
                headers={"X-ARIA-Token": tenant.api_key_hex},
            )
            assert resp.status == 200
            out = await resp.json()
            assert out["results"][0]["risk_level"] in ("YELLOW", "RED")
            assert "16:55:" in out["results"][0]["tca_utc"]
        finally:
            await client.close()
