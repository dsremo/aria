"""Sprint 12: ML Alert Visibility + Operator Feedback tests.

36 tests across 4 classes:
  TestAnomalyOutExtended   (8) — ml_only, reviewed, false_positive in AnomalyOut
  TestFeedbackEndpoint    (12) — PATCH /anomalies/{id}/feedback via demo_client
  TestMLOnlyFilter         (8) — GET /anomalies?ml_only= filter
  TestMemoryStoreFeedback  (8) — update_anomaly_review in memory_store

Expected total after Sprint 12: 719 + 36 = 755 passing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from aria.dsremo.api.schemas import AnomalyOut, FeedbackIn
from aria.dsremo.core.models import Anomaly, Severity


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_anomaly_row(
    anomaly_id: str = "test-001",
    detectors: list[str] | None = None,
    reviewed: bool = False,
    false_positive: bool = False,
) -> dict:
    """Minimal anomaly dict as returned by the DB / memory_store."""
    return {
        "id": anomaly_id,
        "satellite_id": "SAT-TEST",
        "timestamp": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "subsystem": "eps",
        "parameter": "battery_voltage",
        "value": 7.1,
        "severity": "watch",
        "confidence": 0.62,
        "detectors_triggered": detectors or [],
        "explanation": "test explanation",
        "root_cause_group": None,
        "contributing_params": {},
        "reviewed": reviewed,
        "false_positive": false_positive,
    }


@pytest.fixture(scope="module")
def demo_client():
    """Demo-mode TestClient — no DB, memory_store used for all queries."""
    from aria.dsremo.api.app import create_app
    app = create_app(demo=True)
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. TestAnomalyOutExtended — schema fields and ml_only logic
# ---------------------------------------------------------------------------

class TestAnomalyOutExtended:

    # 1 — ml_only=True when detectors_triggered=["lstm"]
    def test_ml_only_true_for_lstm_sole_detector(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=["lstm"])
        out = _row_to_anomaly(row)
        assert out.ml_only is True

    # 2 — ml_only=False when detectors_triggered=["cusum", "lstm"]
    def test_ml_only_false_when_stats_also_triggered(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=["cusum", "lstm"])
        out = _row_to_anomaly(row)
        assert out.ml_only is False

    # 3 — ml_only=False when only stats triggered (no lstm)
    def test_ml_only_false_for_stats_only(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=["cusum", "ewma", "variance"])
        out = _row_to_anomaly(row)
        assert out.ml_only is False

    # 4 — ml_only=False when detectors_triggered=[]
    def test_ml_only_false_for_empty_detectors(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=[])
        out = _row_to_anomaly(row)
        assert out.ml_only is False

    # 5 — reviewed field present with default False
    def test_reviewed_field_defaults_false(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row()
        out = _row_to_anomaly(row)
        assert out.reviewed is False

    # 6 — false_positive field present with default False
    def test_false_positive_field_defaults_false(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row()
        out = _row_to_anomaly(row)
        assert out.false_positive is False

    # 7 — _row_to_anomaly maps reviewed=True correctly
    def test_row_to_anomaly_maps_reviewed_true(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(reviewed=True, false_positive=False)
        out = _row_to_anomaly(row)
        assert out.reviewed is True
        assert out.false_positive is False

    # 8 — AnomalyOut schema has all Sprint 12 fields
    def test_anomaly_out_has_sprint12_fields(self):
        fields = AnomalyOut.model_fields
        assert "reviewed" in fields
        assert "false_positive" in fields
        assert "ml_only" in fields


# ---------------------------------------------------------------------------
# 2. TestFeedbackEndpoint — PATCH /anomalies/{id}/feedback
# ---------------------------------------------------------------------------

class TestFeedbackEndpoint:

    @pytest.fixture(autouse=True)
    def _seed_anomaly(self, demo_client):
        """Insert one anomaly via telemetry + run_detection, or directly via memory_store."""
        from aria.dsremo.db import memory_store
        import asyncio
        # Insert anomaly directly into memory_store
        anomaly = Anomaly(
            id="fb-test-001",
            satellite_id="FB-SAT",
            subsystem="eps",
            parameter="battery_voltage",
            value=6.5,
            severity=Severity.WATCH,
            confidence=0.62,
            detectors_triggered=("cusum", "lstm"),
            explanation="test anomaly for feedback",
        )
        asyncio.get_event_loop().run_until_complete(memory_store.insert_anomaly(anomaly))
        # Also insert an ml-only anomaly
        ml_anomaly = Anomaly(
            id="fb-test-ml-001",
            satellite_id="FB-SAT",
            subsystem="eps",
            parameter="solar_current",
            value=2.8,
            severity=Severity.WATCH,
            confidence=0.60,
            detectors_triggered=("lstm",),
            explanation="ml-only test anomaly",
        )
        asyncio.get_event_loop().run_until_complete(memory_store.insert_anomaly(ml_anomaly))

    # 1 — PATCH with false_positive verdict → 200
    def test_patch_feedback_false_positive_returns_200(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-001/feedback",
            json={"verdict": "false_positive"},
        )
        assert resp.status_code == 200

    # 2 — PATCH with true_positive verdict → 200
    def test_patch_feedback_true_positive_returns_200(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-ml-001/feedback",
            json={"verdict": "true_positive"},
        )
        assert resp.status_code == 200

    # 3 — PATCH with unknown id → 404
    def test_patch_feedback_unknown_id_returns_404(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/does-not-exist-xyz/feedback",
            json={"verdict": "false_positive"},
        )
        assert resp.status_code == 404

    # 4 — After FP feedback, reviewed=True and false_positive=True in response
    def test_fp_feedback_sets_reviewed_and_false_positive(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-001/feedback",
            json={"verdict": "false_positive"},
        )
        data = resp.json()
        assert data["reviewed"] is True
        assert data["false_positive"] is True

    # 5 — After TP feedback, reviewed=True and false_positive=False
    def test_tp_feedback_sets_reviewed_false_positive_false(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-ml-001/feedback",
            json={"verdict": "true_positive"},
        )
        data = resp.json()
        assert data["reviewed"] is True
        assert data["false_positive"] is False

    # 6 — FeedbackIn schema exists and validates
    def test_feedback_in_schema_exists(self):
        fb = FeedbackIn(verdict="false_positive")
        assert fb.verdict == "false_positive"
        assert fb.note is None

    # 7 — FeedbackIn rejects invalid verdict
    def test_feedback_in_rejects_invalid_verdict(self):
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            FeedbackIn(verdict="maybe")

    # 8 — FeedbackIn verdict must be tp or fp
    def test_feedback_in_true_positive_valid(self):
        fb = FeedbackIn(verdict="true_positive")
        assert fb.verdict == "true_positive"

    # 9 — Note field accepted
    def test_feedback_in_accepts_note(self):
        fb = FeedbackIn(verdict="false_positive", note="Sensor glitch during eclipse")
        assert fb.note == "Sensor glitch during eclipse"

    # 10 — PATCH response contains AnomalyOut fields including ml_only
    def test_patch_feedback_response_includes_ml_only(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-ml-001/feedback",
            json={"verdict": "true_positive"},
        )
        data = resp.json()
        assert "ml_only" in data
        assert data["ml_only"] is True  # detectors_triggered=["lstm"]

    # 11 — Feedback can be re-submitted (update overrides previous verdict)
    def test_feedback_can_be_updated(self, demo_client):
        # First: mark FP
        demo_client.patch(
            "/api/v1/anomalies/fb-test-001/feedback",
            json={"verdict": "false_positive"},
        )
        # Then: correct to TP
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-001/feedback",
            json={"verdict": "true_positive"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["false_positive"] is False
        assert data["reviewed"] is True

    # 12 — PATCH endpoint responds with AnomalyOut (has confidence, detectors, explanation)
    def test_patch_response_is_full_anomaly_out(self, demo_client):
        resp = demo_client.patch(
            "/api/v1/anomalies/fb-test-001/feedback",
            json={"verdict": "true_positive"},
        )
        data = resp.json()
        assert "confidence" in data
        assert "detectors_triggered" in data
        assert "explanation" in data
        assert "satellite_id" in data


# ---------------------------------------------------------------------------
# 3. TestMLOnlyFilter — GET /anomalies?ml_only=
# ---------------------------------------------------------------------------

class TestMLOnlyFilter:

    @pytest.fixture(autouse=True)
    def _seed_mixed_anomalies(self, demo_client):
        """Seed stats-only, ml-only, and mixed anomalies."""
        from aria.dsremo.db import memory_store
        import asyncio

        loop = asyncio.get_event_loop()

        stats_anomaly = Anomaly(
            id="ml-filter-stats-001",
            satellite_id="ML-FILTER-SAT",
            subsystem="thermal",
            parameter="panel_temp",
            value=95.0,
            severity=Severity.WARNING,
            confidence=0.75,
            detectors_triggered=("cusum", "ewma"),
            explanation="stats drift",
        )
        ml_anomaly = Anomaly(
            id="ml-filter-lstm-001",
            satellite_id="ML-FILTER-SAT",
            subsystem="thermal",
            parameter="battery_temp",
            value=40.0,
            severity=Severity.WATCH,
            confidence=0.60,
            detectors_triggered=("lstm",),
            explanation="ml temporal pattern",
        )
        mixed_anomaly = Anomaly(
            id="ml-filter-mixed-001",
            satellite_id="ML-FILTER-SAT",
            subsystem="eps",
            parameter="bus_voltage",
            value=4.8,
            severity=Severity.CRITICAL,
            confidence=0.85,
            detectors_triggered=("cusum", "lstm"),
            explanation="both detectors",
        )

        loop.run_until_complete(memory_store.insert_anomaly(stats_anomaly))
        loop.run_until_complete(memory_store.insert_anomaly(ml_anomaly))
        loop.run_until_complete(memory_store.insert_anomaly(mixed_anomaly))

    # 1 — ml_only=true returns only lstm-sole anomalies
    def test_ml_only_true_filter(self, demo_client):
        resp = demo_client.get("/api/v1/anomalies?ml_only=true&satellite_id=ML-FILTER-SAT")
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            assert item["ml_only"] is True
            assert item["detectors_triggered"] == ["lstm"]

    # 2 — ml_only=false excludes lstm-only anomalies
    def test_ml_only_false_filter_excludes_lstm_only(self, demo_client):
        resp = demo_client.get("/api/v1/anomalies?ml_only=false&satellite_id=ML-FILTER-SAT")
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            assert item["ml_only"] is False

    # 3 — no ml_only filter returns all
    def test_no_ml_only_filter_returns_all(self, demo_client):
        resp = demo_client.get("/api/v1/anomalies?satellite_id=ML-FILTER-SAT")
        assert resp.status_code == 200
        data = resp.json()
        # Should include all 3 seeded anomalies (assuming not false_positive filtered)
        assert len(data) >= 3

    # 4 — ml_only=true with no matching satellite → empty list
    def test_ml_only_true_no_match(self, demo_client):
        resp = demo_client.get("/api/v1/anomalies?ml_only=true&satellite_id=NONEXISTENT-SAT-XYZABC")
        assert resp.status_code == 200
        assert resp.json() == []

    # 5 — ml_only field computed correctly: ["lstm"] → True
    def test_ml_only_computed_for_lstm_list(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=["lstm"])
        assert _row_to_anomaly(row).ml_only is True

    # 6 — ml_only field computed correctly: ["cusum", "lstm"] → False
    def test_ml_only_computed_for_mixed_list(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=["cusum", "lstm"])
        assert _row_to_anomaly(row).ml_only is False

    # 7 — ml_only field computed correctly: [] → False
    def test_ml_only_computed_for_empty_list(self):
        from aria.dsremo.api.routes import _row_to_anomaly
        row = _make_anomaly_row(detectors=[])
        assert _row_to_anomaly(row).ml_only is False

    # 8 — ml_only=true + severity filter combined
    def test_ml_only_combined_with_severity_filter(self, demo_client):
        resp = demo_client.get(
            "/api/v1/anomalies?ml_only=true&severity=watch&satellite_id=ML-FILTER-SAT"
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            assert item["ml_only"] is True
            assert item["severity"] == "watch"


# ---------------------------------------------------------------------------
# 4. TestMemoryStoreFeedback — update_anomaly_review in memory_store
# ---------------------------------------------------------------------------

class TestMemoryStoreFeedback:

    @pytest.fixture(autouse=True)
    def _seed(self):
        """Insert a fresh anomaly into memory_store before each test."""
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        self._anomaly_id = "mem-fb-001"
        anomaly = Anomaly(
            id=self._anomaly_id,
            satellite_id="MEM-SAT",
            subsystem="comms",
            parameter="signal_strength",
            value=-95.0,
            severity=Severity.WATCH,
            confidence=0.55,
            detectors_triggered=("lstm",),
            explanation="memory store feedback test",
        )
        loop.run_until_complete(memory_store.insert_anomaly(anomaly))

    # 1 — update_anomaly_review(id, fp=True) sets reviewed=True, fp=True
    def test_update_review_marks_false_positive(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            memory_store.update_anomaly_review(self._anomaly_id, false_positive=True)
        )
        assert result is True
        row = loop.run_until_complete(memory_store.get_anomaly_by_id(self._anomaly_id))
        assert row["reviewed"] is True
        assert row["false_positive"] is True

    # 2 — update_anomaly_review(id, fp=False) sets reviewed=True, fp=False
    def test_update_review_marks_true_positive(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            memory_store.update_anomaly_review(self._anomaly_id, false_positive=False)
        )
        assert result is True
        row = loop.run_until_complete(memory_store.get_anomaly_by_id(self._anomaly_id))
        assert row["reviewed"] is True
        assert row["false_positive"] is False

    # 3 — update_anomaly_review non-existent id → returns False
    def test_update_review_nonexistent_returns_false(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            memory_store.update_anomaly_review("does-not-exist-abc", false_positive=True)
        )
        assert result is False

    # 4 — update_anomaly_review existing → returns True
    def test_update_review_existing_returns_true(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            memory_store.update_anomaly_review(self._anomaly_id, false_positive=False)
        )
        assert result is True

    # 5 — _anomaly_to_dict includes reviewed=False by default (fresh insert)
    def test_anomaly_to_dict_reviewed_default_false(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        # Insert a brand-new anomaly to avoid interference from prior test modifications
        fresh = Anomaly(
            id="mem-fb-fresh-reviewed",
            satellite_id="MEM-SAT",
            subsystem="eps",
            parameter="bus_voltage",
            value=5.1,
            severity=Severity.WATCH,
            confidence=0.55,
            detectors_triggered=("cusum",),
            explanation="fresh reviewed test",
        )
        loop.run_until_complete(memory_store.insert_anomaly(fresh))
        row = loop.run_until_complete(memory_store.get_anomaly_by_id("mem-fb-fresh-reviewed"))
        assert "reviewed" in row
        assert row["reviewed"] is False

    # 6 — _anomaly_to_dict includes false_positive=False by default (fresh insert)
    def test_anomaly_to_dict_false_positive_default_false(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        fresh = Anomaly(
            id="mem-fb-fresh-fp",
            satellite_id="MEM-SAT",
            subsystem="eps",
            parameter="solar_array",
            value=2.4,
            severity=Severity.WATCH,
            confidence=0.55,
            detectors_triggered=("ewma",),
            explanation="fresh fp test",
        )
        loop.run_until_complete(memory_store.insert_anomaly(fresh))
        row = loop.run_until_complete(memory_store.get_anomaly_by_id("mem-fb-fresh-fp"))
        assert "false_positive" in row
        assert row["false_positive"] is False

    # 7 — get_anomaly_by_id returns updated values after review
    def test_get_anomaly_by_id_reflects_update(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            memory_store.update_anomaly_review(self._anomaly_id, false_positive=True)
        )
        row = loop.run_until_complete(memory_store.get_anomaly_by_id(self._anomaly_id))
        assert row["reviewed"] is True
        assert row["false_positive"] is True

    # 8 — mark_false_positive shim still works (backward compat)
    def test_mark_false_positive_still_works(self):
        import asyncio
        from aria.dsremo.db import memory_store

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            memory_store.mark_false_positive(self._anomaly_id)
        )
        assert result is True
        row = loop.run_until_complete(memory_store.get_anomaly_by_id(self._anomaly_id))
        assert row["false_positive"] is True
        assert row["reviewed"] is True
