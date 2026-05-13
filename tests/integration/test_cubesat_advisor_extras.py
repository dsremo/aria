"""Tests for the new advisor layers — multi-impulse plan, PDF/HTML
report, FCC §25.114 waiver, HTTP service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aria.products.cubesat_deorbit.advisor import (
    SpacecraftState, MissionParams, Decision, advise_deorbit,
)
from aria.products.cubesat_deorbit.burn_planner import (
    plan_two_impulse_hohmann, plan_staged_drop,
)
from aria.products.cubesat_deorbit.report import render_html, render_report
from aria.products.cubesat_deorbit.fcc_waiver import build_waiver_application


# ── Multi-impulse burn planning ────────────────────────────────


class TestTwoImpulseHohmann:
    def test_lower_orbit_returns_plan(self):
        plan = plan_two_impulse_hohmann(
            start_alt_km=600.0, final_alt_km=300.0,
            epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            wet_mass_kg=12.0, propellant_kg=1.0, isp_s=220.0,
        )
        assert plan is not None
        assert plan.n_impulses == 2
        # Both burns retrograde and total Δv ≈ 170 m/s for 600→300 km LEO.
        for imp in plan.impulses:
            assert imp.direction == "retrograde"
            assert imp.delta_v_mps > 0.0
        assert 50.0 < plan.total_delta_v_mps < 300.0

    def test_lower_with_no_propellant_returns_none(self):
        plan = plan_two_impulse_hohmann(
            start_alt_km=600.0, final_alt_km=300.0,
            epoch_utc=datetime.now(timezone.utc),
            wet_mass_kg=12.0, propellant_kg=0.001, isp_s=220.0,
        )
        assert plan is None

    def test_invalid_altitude_pair(self):
        plan = plan_two_impulse_hohmann(
            start_alt_km=300.0, final_alt_km=600.0,    # raise — invalid
            epoch_utc=datetime.now(timezone.utc),
            wet_mass_kg=12.0, propellant_kg=1.0, isp_s=220.0,
        )
        assert plan is None


class TestStagedDrop:
    def test_staged_emits_multiple_burns(self):
        plan = plan_staged_drop(
            start_alt_km=800.0, final_alt_km=400.0,
            epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            wet_mass_kg=12.0, propellant_kg=2.0, isp_s=220.0,
            max_dv_per_burn_mps=30.0,
        )
        assert plan is not None
        # Total Δv 800→400 km ≈ 220 m/s ⇒ ≥4 stages × 2 impulses each.
        assert plan.n_impulses >= 4

    def test_staged_collapses_to_two_when_budget_loose(self):
        plan = plan_staged_drop(
            start_alt_km=600.0, final_alt_km=400.0,
            epoch_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            wet_mass_kg=12.0, propellant_kg=2.0, isp_s=220.0,
            max_dv_per_burn_mps=10_000.0,
        )
        assert plan is not None
        assert plan.n_impulses == 2


# ── Report rendering ───────────────────────────────────────────


class TestReportHTML:
    def test_html_contains_decision_and_compliance(self):
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6, mass_kg=12.0,
        )
        rec = advise_deorbit(state)
        html = render_html(rec, mission_name="Pratham-2")
        assert "Pratham-2" in html
        assert rec.decision.value.replace("_", " ").upper() in html
        assert "Natural-decay analysis" in html
        assert ("PASS" in html or "FAIL" in html)

    def test_render_report_writes_html_when_no_pdf(self, tmp_path: Path):
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6, mass_kg=12.0,
        )
        rec = advise_deorbit(state)
        out = tmp_path / "out.pdf"
        path, is_pdf = render_report(rec, out, mission_name="Demo")
        # weasyprint may or may not be installed.  Either way the
        # function returns a real file path.
        assert Path(path).is_file()
        if not is_pdf:
            assert path.suffix == ".html"
            assert "Demo" in Path(path).read_text()


# ── FCC waiver ─────────────────────────────────────────────────


class TestFCCWaiver:
    def test_waiver_for_infeasible(self):
        # Tight propellant — single-impulse burn infeasible.
        state = SpacecraftState(
            altitude_km=900.0, inclination_deg=98.0, mass_kg=15.0,
            propellant_kg=0.001, isp_s=220.0,
        )
        params = MissionParams(name="HighOrbitSat",
                               fcc_compliant_required=True)
        rec = advise_deorbit(state, params)
        assert rec.decision is Decision.INFEASIBLE
        waiver = build_waiver_application(rec, state, params,
                                          mission_name="HighOrbitSat")
        text = waiver.to_text()
        assert "47 CFR §25.114" in text or "25.114" in text
        assert "HighOrbitSat" in text
        assert any("propellant" in s.paragraph.lower()
                   or "Δv" in s.paragraph
                   or "delta-v" in s.paragraph.lower()
                   for s in waiver.sections)

    def test_waiver_for_compliant_emits_contingency(self):
        state = SpacecraftState(
            altitude_km=400.0, inclination_deg=51.6, mass_kg=12.0,
        )
        params = MissionParams(name="LEO-1")
        rec = advise_deorbit(state, params)
        # 400 km natural decays well within 5 yr → COMPLIANT.
        waiver = build_waiver_application(rec, state, params,
                                          mission_name="LEO-1")
        # Must still produce a usable document — operator can pre-stage.
        assert "LEO-1" in waiver.to_text()
        assert len(waiver.sections) >= 5


# ── HTTP service ───────────────────────────────────────────────


async def _client(app):
    from aiohttp.test_utils import TestServer, TestClient
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


class TestAdvisorHTTPService:
    @pytest.mark.asyncio
    async def test_healthz_open(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.get("/v1/healthz")
            assert r.status == 200
            body = await r.json()
            assert body["ok"] is True
            # Round-2 audit consistency — /v1/healthz is minimal,
            # /v1/version is admin-only.
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_requires_auth(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post("/v1/advise", json={})
            assert r.status == 401
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_natural_decay(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/advise",
                json={"state": {"altitude_km": 400.0, "mass_kg": 12.0}},
                headers={"X-ARIA-Token": "L" * 64},
            )
            assert r.status == 200
            body = await r.json()
            assert body["decision"] in (
                "natural_decay", "burn_required", "infeasible",
            )
            assert "natural_decay" in body
            assert "compliance" in body
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_report_returns_html(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/advise/report",
                json={"state": {"altitude_km": 400.0, "mass_kg": 12.0},
                      "mission": {"name": "Pratham-2"}},
                headers={"X-ARIA-Token": "L" * 64},
            )
            assert r.status == 200
            text = await r.text()
            assert "Pratham-2" in text
            assert "<html" in text.lower()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_waiver_returns_sections(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/advise/waiver",
                json={
                    "state": {"altitude_km": 900.0, "mass_kg": 15.0,
                              "propellant_kg": 0.001, "isp_s": 220.0,
                              "inclination_deg": 98.0},
                    "mission": {"name": "HighOrbitSat"},
                },
                headers={"X-ARIA-Token": "L" * 64},
            )
            assert r.status == 200
            body = await r.json()
            assert body["mission_name"] == "HighOrbitSat"
            assert len(body["sections"]) >= 5
            assert "rendered_text" in body
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_multi_two_impulse(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/advise/multi",
                json={"state": {"altitude_km": 600.0, "mass_kg": 12.0,
                                 "propellant_kg": 1.0, "isp_s": 220.0},
                      "final_alt_km": 300.0,
                      "mode": "two_impulse"},
                headers={"X-ARIA-Token": "L" * 64},
            )
            assert r.status == 200
            body = await r.json()
            assert body["n_impulses"] == 2
            assert body["total_delta_v_mps"] > 0.0
            assert len(body["impulses"]) == 2
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_advise_multi_staged(self):
        from aria.products.cubesat_deorbit.service import create_app
        app = create_app(legacy_token_hex="L" * 64)
        client = await _client(app)
        try:
            r = await client.post(
                "/v1/advise/multi",
                json={"state": {"altitude_km": 800.0, "mass_kg": 12.0,
                                 "propellant_kg": 2.0, "isp_s": 220.0},
                      "final_alt_km": 400.0,
                      "mode": "staged",
                      "max_dv_per_burn_mps": 30.0},
                headers={"X-ARIA-Token": "L" * 64},
            )
            assert r.status == 200
            body = await r.json()
            assert body["n_impulses"] >= 4
            assert body["total_delta_v_mps"] > 0.0
        finally:
            await client.close()
