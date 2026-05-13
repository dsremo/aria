"""CubeSat de-orbit advisor — HTTP service.

This wraps :mod:`aria.products.cubesat_deorbit.advisor` behind the
same authentication + rate-limit shell used by the conjunction
screener.  Operators with a tenant token already issued for the
screener can re-use it for the advisor; the two services share a
SQLite tenant store when both are deployed on the same host.

Endpoints:

  ``GET  /v1/healthz``        liveness probe.
  ``GET  /v1/version``        semver + service identity.
  ``POST /v1/advise``         single recommendation (JSON in / out).
  ``POST /v1/advise/report``  recommendation + 1-page HTML report.
  ``POST /v1/advise/waiver``  recommendation + FCC §25.114 skeleton.
  ``POST /v1/advise/multi``   multi-impulse burn plan.

The service is stateless beyond the tenant store; usage is metered
via the same :class:`TenantStore.record_usage` API as the screener.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger("aria.products.cubesat_deorbit")


VERSION = "1.0.0"


def _request_to_state_params(body: Dict[str, Any]):
    from aria.products.cubesat_deorbit.advisor import (
        SpacecraftState, MissionParams,
    )
    s = body.get("state", {})
    p = body.get("mission", {})
    state = SpacecraftState(
        altitude_km=float(s["altitude_km"]),
        inclination_deg=float(s.get("inclination_deg", 51.6)),
        mass_kg=float(s["mass_kg"]),
        drag_coefficient=float(s.get("drag_coefficient", 2.2)),
        cross_section_m2=float(s.get("cross_section_m2", 0.06)),
        propellant_kg=float(s.get("propellant_kg", 0.0)),
        isp_s=float(s.get("isp_s", 220.0)),
    )
    params = MissionParams(
        name=str(p.get("name", "CubeSat")),
        f107_solar_flux=float(p.get("f107_solar_flux", 150.0)),
        target_reentry_alt_km=float(p.get("target_reentry_alt_km", 120.0)),
        fcc_compliant_required=bool(p.get("fcc_compliant_required", True)),
        nasa_25yr_compliant_required=bool(p.get("nasa_25yr_compliant_required", True)),
    )
    return state, params


def _rec_to_dict(rec) -> Dict[str, Any]:
    """Convert a DeOrbitRecommendation into JSON-safe dict."""
    out: Dict[str, Any] = {
        "decision": rec.decision.value,
        "confidence_tier": rec.confidence_tier,
        "rationale": list(rec.rationale),
        "operator_actions": list(rec.operator_actions),
        "natural_decay": {
            "lifetime_years": rec.natural_decay.lifetime_years,
            "lifetime_days": rec.natural_decay.lifetime_days,
            "fcc_compliant": rec.natural_decay.fcc_compliant,
            "nasa_25yr_compliant": rec.natural_decay.nasa_25yr_compliant,
        },
        "compliance": {
            "fcc_5_year": rec.compliance.fcc_5_year,
            "nasa_25_year": rec.compliance.nasa_25_year,
            "fcc_5_year_margin_days": rec.compliance.fcc_5_year_margin_days,
            "nasa_25_year_margin_days": rec.compliance.nasa_25_year_margin_days,
        },
    }
    if rec.burn_plan is not None:
        b = rec.burn_plan
        out["burn_plan"] = {
            "burn_epoch_utc": b.burn_epoch_utc.isoformat(),
            "delta_v_mps": b.delta_v_mps,
            "direction": b.direction,
            "propellant_kg_burned": b.propellant_kg_burned,
            "propellant_margin_kg": b.propellant_margin_kg,
            "target_periapsis_km": b.target_periapsis_km,
            "expected_reentry_utc": b.expected_reentry_utc.isoformat(),
            "notes": b.notes,
        }
    if rec.footprint is not None:
        f = rec.footprint
        out["footprint"] = {
            "nominal_lat_deg": f.nominal_lat_deg,
            "nominal_lon_deg": f.nominal_lon_deg,
            "along_track_3sigma_km": f.along_track_3sigma_km,
            "cross_track_3sigma_km": f.cross_track_3sigma_km,
            "casualty_area_m2": f.casualty_area_m2,
            "occurs_over_water": f.occurs_over_water,
            "notes": f.notes,
        }
    return out


def create_app(
    tenant_store: Optional[Any] = None,
    legacy_token_hex: Optional[str] = None,
    admin_token_hex: Optional[str] = None,
):
    """Build an aiohttp Application instance for the advisor service.

    Auth modes (one of):

    * ``tenant_store`` — production SQLite-backed multi-tenant store
      (typically shared with the conjunction screener).
    * ``legacy_token_hex`` — single-token mode used by tests + demos.
    """
    try:
        from aiohttp import web
    except ImportError:                                   # pragma: no cover
        raise RuntimeError("aiohttp required: pip install aiohttp")

    using_store = tenant_store is not None

    # Audit CRIT-3 — service-bound admin token derivation; tokens minted
    # against the screener are not valid here (and vice-versa).
    SERVICE_ID = b"aria-cubesat-advisor:v1"
    if admin_token_hex:
        _expected_admin = hmac.new(
            admin_token_hex.encode("utf-8"), SERVICE_ID, hashlib.sha256,
        ).hexdigest()
    else:
        _expected_admin = ""

    def _auth(request) -> Optional[str]:
        token = request.headers.get("X-ARIA-Token", "")
        if not token:
            return None
        if using_store:
            t = tenant_store.find_by_key(token)
            if t is None or t.suspended:
                return None
            return t.tenant_id
        if legacy_token_hex and hmac.compare_digest(legacy_token_hex, token):
            return "legacy"
        return None

    def _admin_authed(request) -> bool:
        if not _expected_admin:
            return False
        token = request.headers.get("X-ARIA-Admin-Token", "")
        if not token:
            return False
        return hmac.compare_digest(_expected_admin, token)

    async def healthz(request):
        # Audit HIGH-8 — never include version in unauthenticated /v1/healthz.
        return web.json_response({"ok": True})

    async def version(request):
        # Round-2 audit consistency with screener HIGH-8 — version is
        # admin-only so it cannot be polled anonymously for service
        # fingerprinting.
        if not _admin_authed(request):
            return web.json_response({"error": "unauthorised"}, status=401)
        return web.json_response({"service": "aria-cubesat-advisor",
                                  "version": VERSION})

    async def _read_body(request):
        try:
            return await request.json()
        except Exception:
            return None

    async def advise(request):
        t0 = time.monotonic()
        tenant_id = _auth(request)
        if tenant_id is None:
            return web.json_response({"error": "unauthorised"}, status=401)
        body = await _read_body(request)
        if body is None:
            return web.json_response({"error": "bad_request"}, status=400)
        try:
            state, params = _request_to_state_params(body)
            from aria.products.cubesat_deorbit.advisor import advise_deorbit
            rec = advise_deorbit(state, params)
        except KeyError as exc:
            return web.json_response(
                {"error": "missing_field", "field": str(exc).strip("'\"")[:64]},
                status=400,
            )
        except Exception as exc:
            return web.json_response(
                {"error": "internal"}, status=500,
            )    # audit HIGH-4 — log full exception locally; never echo
        if using_store:
            tenant_store.record_usage(
                tenant_id, "advise", n_pairs=1,
                elapsed_ms=(time.monotonic() - t0) * 1000.0, status_code=200,
            )
        return web.json_response(_rec_to_dict(rec))

    async def advise_report(request):
        tenant_id = _auth(request)
        if tenant_id is None:
            return web.json_response({"error": "unauthorised"}, status=401)
        body = await _read_body(request)
        if body is None:
            return web.json_response({"error": "bad_request"}, status=400)
        try:
            state, params = _request_to_state_params(body)
            from aria.products.cubesat_deorbit.advisor import advise_deorbit
            from aria.products.cubesat_deorbit.report import render_html
            rec = advise_deorbit(state, params)
            html = render_html(rec, mission_name=params.name)
        except Exception as exc:
            return web.json_response(
                {"error": "internal"}, status=500,
            )    # audit HIGH-4 — log full exception locally; never echo
        return web.Response(body=html, content_type="text/html")

    async def advise_waiver(request):
        tenant_id = _auth(request)
        if tenant_id is None:
            return web.json_response({"error": "unauthorised"}, status=401)
        body = await _read_body(request)
        if body is None:
            return web.json_response({"error": "bad_request"}, status=400)
        try:
            state, params = _request_to_state_params(body)
            from aria.products.cubesat_deorbit.advisor import advise_deorbit
            from aria.products.cubesat_deorbit.fcc_waiver import (
                build_waiver_application,
            )
            rec = advise_deorbit(state, params)
            waiver = build_waiver_application(
                rec, state, params, mission_name=params.name,
            )
        except Exception as exc:
            return web.json_response(
                {"error": "internal"}, status=500,
            )    # audit HIGH-4 — log full exception locally; never echo
        return web.json_response({
            "mission_name": waiver.mission_name,
            "fcc_rule_cited": waiver.fcc_rule_cited,
            "waiver_authority": waiver.waiver_authority,
            "technical_summary": waiver.technical_summary,
            "sections": [
                {"heading": s.heading,
                 "paragraph": s.paragraph,
                 "operator_must_supply": list(s.operator_must_supply)}
                for s in waiver.sections
            ],
            "rendered_text": waiver.to_text(),
        })

    async def advise_multi(request):
        tenant_id = _auth(request)
        if tenant_id is None:
            return web.json_response({"error": "unauthorised"}, status=401)
        body = await _read_body(request)
        if body is None:
            return web.json_response({"error": "bad_request"}, status=400)
        try:
            state, params = _request_to_state_params(body)
            from aria.products.cubesat_deorbit.burn_planner import (
                plan_two_impulse_hohmann, plan_staged_drop,
            )
            mode = body.get("mode", "two_impulse")
            final_alt_km = float(body.get("final_alt_km", params.target_reentry_alt_km))
            epoch = state.epoch_utc
            if mode == "staged":
                plan = plan_staged_drop(
                    start_alt_km=state.altitude_km,
                    final_alt_km=final_alt_km,
                    epoch_utc=epoch,
                    wet_mass_kg=state.mass_kg,
                    propellant_kg=state.propellant_kg,
                    isp_s=state.isp_s,
                    max_dv_per_burn_mps=float(body.get("max_dv_per_burn_mps", 30.0)),
                    coast_orbits_between_burns=int(body.get("coast_orbits_between_burns", 1)),
                )
            else:
                plan = plan_two_impulse_hohmann(
                    start_alt_km=state.altitude_km,
                    final_alt_km=final_alt_km,
                    epoch_utc=epoch,
                    wet_mass_kg=state.mass_kg,
                    propellant_kg=state.propellant_kg,
                    isp_s=state.isp_s,
                    dwell_orbits_at_final=int(body.get("dwell_orbits_at_final", 0)),
                )
            if plan is None:
                return web.json_response({
                    "error": "infeasible",
                    "reason": "Insufficient propellant or invalid altitude pair.",
                }, status=422)
        except Exception as exc:
            return web.json_response(
                {"error": "internal"}, status=500,
            )    # audit HIGH-4 — log full exception locally; never echo
        return web.json_response({
            "mode": mode,
            "n_impulses": plan.n_impulses,
            "total_delta_v_mps": plan.total_delta_v_mps,
            "total_propellant_kg": plan.total_propellant_kg,
            "propellant_margin_kg": plan.propellant_margin_kg,
            "expected_reentry_utc": plan.expected_reentry_utc.isoformat(),
            "notes": plan.notes,
            "impulses": [
                {"sequence": i.sequence,
                 "epoch_utc": i.epoch_utc.isoformat(),
                 "delta_v_mps": i.delta_v_mps,
                 "direction": i.direction,
                 "propellant_kg": i.propellant_kg,
                 "perigee_after_km": i.perigee_after_km,
                 "apogee_after_km": i.apogee_after_km,
                 "notes": i.notes}
                for i in plan.impulses
            ],
        })

    app = web.Application(client_max_size=1 * 1024 * 1024)
    app.router.add_get("/v1/healthz", healthz)
    app.router.add_get("/v1/version", version)
    app.router.add_post("/v1/advise", advise)
    app.router.add_post("/v1/advise/report", advise_report)
    app.router.add_post("/v1/advise/waiver", advise_waiver)
    app.router.add_post("/v1/advise/multi", advise_multi)

    from aria.security.guard import HardenConfig, harden_aiohttp_app
    harden_aiohttp_app(
        app,
        config=HardenConfig(
            max_request_bytes=1 * 1024 * 1024,
            allowed_methods=("GET", "POST", "HEAD", "OPTIONS"),
        ),
    )
    return app
