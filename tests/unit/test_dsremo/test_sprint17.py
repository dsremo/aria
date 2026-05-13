"""Sprint 17: Incident Grouper + Hierarchical Alert Routing Tests.

Target: 881 existing + 35 new = 916 passing tests.

Classes
-------
TestIncidentModel        ( 5 tests) — Incident frozen dataclass
TestIncidentGrouper      (15 tests) — IncidentGrouper core logic
TestIncidentAPI          ( 8 tests) — GET/PATCH /incidents endpoints
TestIncidentSummaryAPI   ( 4 tests) — /satellites/{sat}/incidents/summary
TestIncidentSchemas      ( 3 tests) — IncidentOut / IncidentStatusIn / IncidentSummary
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_anomaly(
    satellite_id: str = "SAT-1",
    parameter: str = "voltage",
    severity: str = "warning",
    confidence: float = 0.75,
    detectors: tuple[str, ...] = ("cusum", "ewma"),
    ts: datetime | None = None,
):
    from aria.dsremo.core.models import Anomaly, Severity
    sev_map = {
        "nominal": Severity.NOMINAL,
        "watch":   Severity.WATCH,
        "warning": Severity.WARNING,
        "critical": Severity.CRITICAL,
    }
    return Anomaly(
        satellite_id=satellite_id,
        timestamp=ts or datetime.now(timezone.utc),
        subsystem="eps",
        parameter=parameter,
        value=28.0,
        severity=sev_map[severity],
        confidence=confidence,
        detectors_triggered=detectors,
        explanation="test",
    )


# ── TestIncidentModel ─────────────────────────────────────────────────────────

class TestIncidentModel:
    """Incident frozen dataclass."""

    def test_incident_is_frozen(self):
        from aria.dsremo.core.models import Incident
        inc = Incident()
        with pytest.raises((AttributeError, TypeError)):
            inc.status = "resolved"  # type: ignore[misc]

    def test_incident_default_status_open(self):
        from aria.dsremo.core.models import Incident
        inc = Incident()
        assert inc.status == "open"

    def test_incident_default_severity_watch(self):
        from aria.dsremo.core.models import Incident, Severity
        inc = Incident()
        assert inc.severity == Severity.WATCH

    def test_incident_has_id(self):
        from aria.dsremo.core.models import Incident
        inc = Incident()
        assert len(inc.id) >= 8

    def test_incident_channels_is_tuple(self):
        from aria.dsremo.core.models import Incident
        inc = Incident(channels=("voltage", "current"))
        assert isinstance(inc.channels, tuple)
        assert "voltage" in inc.channels


# ── TestIncidentGrouper ───────────────────────────────────────────────────────

class TestIncidentGrouper:
    """IncidentGrouper core logic — NASA GSFC event correlation pattern."""

    def test_first_anomaly_creates_incident(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        a = _make_anomaly()
        inc = g.process(a)
        assert inc.status == "open"
        assert inc.satellite_id == "SAT-1"
        assert inc.anomaly_count == 1

    def test_second_anomaly_within_window_joins_incident(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper(window_s=300)
        t0 = datetime.now(timezone.utc)
        a1 = _make_anomaly(ts=t0)
        a2 = _make_anomaly(parameter="current", ts=t0 + timedelta(seconds=60))
        g.process(a1)
        inc = g.process(a2)
        assert inc.anomaly_count == 2
        assert "voltage" in inc.channels
        assert "current" in inc.channels

    def test_anomaly_outside_window_creates_new_incident(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper(window_s=300)
        t0 = datetime.now(timezone.utc)
        a1 = _make_anomaly(ts=t0)
        a2 = _make_anomaly(ts=t0 + timedelta(seconds=400))
        inc1 = g.process(a1)
        inc2 = g.process(a2)
        assert inc1.id != inc2.id

    def test_incident_id_stable_for_members(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper(window_s=300)
        t0 = datetime.now(timezone.utc)
        a1 = _make_anomaly(ts=t0)
        a2 = _make_anomaly(parameter="current", ts=t0 + timedelta(seconds=30))
        a3 = _make_anomaly(parameter="temp", ts=t0 + timedelta(seconds=60))
        inc1 = g.process(a1)
        inc2 = g.process(a2)
        inc3 = g.process(a3)
        assert inc1.id == inc2.id == inc3.id

    def test_severity_escalates_to_max(self):
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        t0 = datetime.now(timezone.utc)
        g.process(_make_anomaly(severity="watch", ts=t0))
        inc = g.process(_make_anomaly(severity="critical", ts=t0 + timedelta(seconds=10)))
        assert inc.severity == Severity.CRITICAL

    def test_severity_never_downgrade(self):
        from aria.dsremo.core.models import Severity
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        t0 = datetime.now(timezone.utc)
        g.process(_make_anomaly(severity="critical", ts=t0))
        inc = g.process(_make_anomaly(severity="watch", ts=t0 + timedelta(seconds=10)))
        assert inc.severity == Severity.CRITICAL

    def test_confidence_is_average(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        t0 = datetime.now(timezone.utc)
        g.process(_make_anomaly(confidence=0.6, ts=t0))
        inc = g.process(_make_anomaly(confidence=0.8, ts=t0 + timedelta(seconds=10)))
        assert abs(inc.confidence - 0.7) < 0.01

    def test_channels_deduplicated(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        t0 = datetime.now(timezone.utc)
        g.process(_make_anomaly(parameter="voltage", ts=t0))
        inc = g.process(_make_anomaly(parameter="voltage", ts=t0 + timedelta(seconds=10)))
        assert inc.channels.count("voltage") == 1

    def test_different_satellites_get_separate_incidents(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        t0 = datetime.now(timezone.utc)
        inc1 = g.process(_make_anomaly(satellite_id="SAT-1", ts=t0))
        inc2 = g.process(_make_anomaly(satellite_id="SAT-2", ts=t0))
        assert inc1.id != inc2.id

    def test_get_incident_id_returns_current(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        inc = g.process(_make_anomaly(satellite_id="SAT-X"))
        assert g.get_incident_id("SAT-X") == inc.id

    def test_get_incident_id_none_for_unknown_satellite(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        assert g.get_incident_id("NONEXISTENT") is None

    def test_close_stale_returns_closed_incidents(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper(close_after_s=0)   # instant close
        g.process(_make_anomaly(satellite_id="SAT-STALE"))
        closed = g.close_stale()
        assert len(closed) == 1
        assert closed[0].status == "resolved"
        assert closed[0].satellite_id == "SAT-STALE"

    def test_close_stale_removes_from_open(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper(close_after_s=0)
        g.process(_make_anomaly(satellite_id="SAT-OLD"))
        g.close_stale()
        assert g.get_incident_id("SAT-OLD") is None

    def test_reset_clears_all_open(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        g.process(_make_anomaly(satellite_id="SAT-A"))
        g.process(_make_anomaly(satellite_id="SAT-B"))
        g.reset()
        assert g.open_count() == 0

    def test_root_cause_derived_from_detectors(self):
        from aria.dsremo.detection.incident_grouper import IncidentGrouper
        g = IncidentGrouper()
        a = _make_anomaly(detectors=("cusum", "ewma", "changepoint"))
        inc = g.process(a)
        assert inc.root_cause_summary  # non-empty
        assert "drift" in inc.root_cause_summary.lower()


# ── Shared fixtures for API tests ─────────────────────────────────────────────

def _make_incidents_app():
    """Minimal FastAPI app with only the incidents router — no DB, no demo mode."""
    from fastapi import FastAPI
    from aria.dsremo.api.dependencies import get_current_user
    from aria.dsremo.api.routes_incidents import incidents_router

    app = FastAPI()
    app.include_router(incidents_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test-admin",
        "tenant_id": "default",
        "role": "admin",
        "scope": "tenant",
    }
    return app


def _mock_queries(*, incidents=None, update_ok=False):
    """Return a MagicMock that satisfies the incidents route's queries calls."""
    import aria.dsremo.api.routes_incidents as inc_mod
    m = MagicMock()
    m.get_incidents_v2 = AsyncMock(return_value=incidents or [])
    m.update_incident_status = AsyncMock(return_value=update_ok)
    return patch.object(inc_mod, "queries", m)


# ── TestIncidentAPI ───────────────────────────────────────────────────────────

class TestIncidentAPI:
    """GET/PATCH /incidents endpoints — no DB, queries patched per test."""

    def test_list_incidents_returns_200(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_incidents_empty_initially(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents")
        assert resp.json() == []

    def test_list_incidents_filter_by_satellite(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents?satellite_id=NOSAT")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_incidents_filter_by_status(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents?status=open")
        assert resp.status_code == 200

    def test_list_incidents_invalid_status_422(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents?status=invalid")
        assert resp.status_code == 422

    def test_get_incident_404_for_unknown(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/incidents/nonexistent-id")
        assert resp.status_code == 404

    def test_patch_incident_status_404_for_unknown(self):
        from starlette.testclient import TestClient
        with _mock_queries(update_ok=False):
            with TestClient(_make_incidents_app()) as c:
                resp = c.patch(
                    "/api/v1/incidents/nonexistent-id/status",
                    json={"status": "resolved"},
                )
        assert resp.status_code == 404

    def test_patch_incident_status_invalid_422(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.patch(
                    "/api/v1/incidents/some-id/status",
                    json={"status": "open"},  # "open" not allowed in IncidentStatusIn
                )
        assert resp.status_code == 422


# ── TestIncidentSummaryAPI ────────────────────────────────────────────────────

class TestIncidentSummaryAPI:
    """GET /satellites/{sat}/incidents/summary endpoint."""

    def test_summary_returns_200(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/incidents/summary")
        assert resp.status_code == 200

    def test_summary_has_open_count(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/incidents/summary")
        body = resp.json()
        assert "open_count" in body
        assert body["open_count"] == 0

    def test_summary_has_severity_breakdown(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/satellites/SAT-1/incidents/summary")
        body = resp.json()
        assert "critical" in body
        assert "warning" in body
        assert "watch" in body

    def test_summary_satellite_id_in_response(self):
        from starlette.testclient import TestClient
        with _mock_queries():
            with TestClient(_make_incidents_app()) as c:
                resp = c.get("/api/v1/satellites/TEST-SAT/incidents/summary")
        assert resp.json()["satellite_id"] == "TEST-SAT"


# ── TestIncidentSchemas ───────────────────────────────────────────────────────

class TestIncidentSchemas:
    """Pydantic schema validation."""

    def test_incident_status_in_allows_resolved(self):
        from aria.dsremo.api.schemas import IncidentStatusIn
        s = IncidentStatusIn(status="resolved")
        assert s.status == "resolved"

    def test_incident_status_in_allows_false_positive(self):
        from aria.dsremo.api.schemas import IncidentStatusIn
        s = IncidentStatusIn(status="false_positive")
        assert s.status == "false_positive"

    def test_incident_status_in_rejects_open(self):
        from pydantic import ValidationError
        from aria.dsremo.api.schemas import IncidentStatusIn
        with pytest.raises(ValidationError):
            IncidentStatusIn(status="open")
